"""
evals/test_filter_structured.py

Deterministic assertions for Node 1.
No LLM calls. No disk reads (trials cache is patched per test).
"""

from __future__ import annotations

import pytest

from prescreener.nodes.filter_structured import _clear_trials_cache, filter_structured
from evals.conftest import make_state


def _run(patient_record: dict, trials: list[dict]) -> list[dict]:
    """Run filter_structured with an injected trials list."""
    _clear_trials_cache()

    # Patch the module-level cache directly
    import prescreener.nodes.filter_structured as fs_mod
    fs_mod._TRIALS_CACHE = trials

    state = make_state(patient_record)
    patch = filter_structured(state)
    return patch["candidate_trials"]


# ── as_of_date validation ──────────────────────────────────────────────────────

def test_missing_as_of_date_raises(patient_no_as_of_date, trial_hba1c_6_5_to_10):
    """Missing as_of_date must raise ValueError — no silent fallback (Q4)."""
    _clear_trials_cache()
    import prescreener.nodes.filter_structured as fs_mod
    fs_mod._TRIALS_CACHE = [trial_hba1c_6_5_to_10]

    state = make_state(patient_no_as_of_date)
    with pytest.raises(ValueError, match="as_of_date"):
        filter_structured(state)


# ── Status filter ──────────────────────────────────────────────────────────────

def test_completed_trial_excluded(patient_with_dual_hba1c, trial_completed):
    result = _run(patient_with_dual_hba1c, [trial_completed])
    assert result == [], "COMPLETED trial must be excluded"


def test_recruiting_trial_included(patient_with_dual_hba1c, trial_hba1c_6_5_to_10):
    result = _run(patient_with_dual_hba1c, [trial_hba1c_6_5_to_10])
    assert len(result) == 1
    assert result[0]["nct_id"] == "NCT04100001"


# ── Age filter — null boundary ─────────────────────────────────────────────────

def test_null_max_age_is_open_boundary(patient_with_dual_hba1c, trial_hba1c_7_5_to_11):
    """
    NCT04100002 has maximum_age_years=None.
    Patient is 58. A null max should never exclude the patient (RESEARCH §3.3).
    """
    result = _run(patient_with_dual_hba1c, [trial_hba1c_7_5_to_11])
    assert len(result) == 1, (
        "Null max_age must be treated as an open boundary, not a grounds for exclusion"
    )


def test_null_min_age_is_open_boundary(patient_with_dual_hba1c):
    trial = {
        "nct_id": "NCT_NULL_MIN",
        "title": "No min age",
        "overall_status": "RECRUITING",
        "minimum_age_years": None,
        "maximum_age_years": 80,
        "eligibility_text": "",
    }
    result = _run(patient_with_dual_hba1c, [trial])
    assert len(result) == 1, "Null min_age must be treated as open boundary"


def test_patient_too_old_for_paediatric_trial(
    patient_with_dual_hba1c, trial_age_too_young
):
    """Patient age 58 must be excluded from a trial with max_age=25."""
    result = _run(patient_with_dual_hba1c, [trial_age_too_young])
    assert result == []


def test_patient_exactly_at_min_age_boundary(patient_with_dual_hba1c):
    """Boundary: patient age equals minimum_age_years — must be included."""
    trial = {
        "nct_id": "NCT_BOUNDARY",
        "title": "Boundary trial",
        "overall_status": "RECRUITING",
        "minimum_age_years": 58,   # exactly patient's age
        "maximum_age_years": None,
        "eligibility_text": "",
    }
    result = _run(patient_with_dual_hba1c, [trial])
    assert len(result) == 1, "Patient at exactly min_age must be included (>=)"


def test_patient_exactly_at_max_age_boundary(patient_with_dual_hba1c):
    """Boundary: patient age equals maximum_age_years — must be included."""
    trial = {
        "nct_id": "NCT_MAX_BOUNDARY",
        "title": "Max boundary trial",
        "overall_status": "RECRUITING",
        "minimum_age_years": 18,
        "maximum_age_years": 58,   # exactly patient's age
        "eligibility_text": "",
    }
    result = _run(patient_with_dual_hba1c, [trial])
    assert len(result) == 1, "Patient at exactly max_age must be included (<=)"


# ── Mixed batch ────────────────────────────────────────────────────────────────

def test_mixed_batch_filters_correctly(
    patient_with_dual_hba1c,
    trial_hba1c_6_5_to_10,
    trial_hba1c_7_5_to_11,
    trial_completed,
    trial_age_too_young,
):
    """Two trials pass (RECRUITING + age ok), two fail."""
    all_trials = [
        trial_hba1c_6_5_to_10,    # RECRUITING, age 18-75 → patient 58 passes
        trial_hba1c_7_5_to_11,    # RECRUITING, null max  → patient 58 passes
        trial_completed,           # COMPLETED              → excluded
        trial_age_too_young,       # max_age 25             → excluded
    ]
    result = _run(patient_with_dual_hba1c, all_trials)
    passing_ids = {t["nct_id"] for t in result}
    assert passing_ids == {"NCT04100001", "NCT04100002"}
