"""
evals/test_generate_report.py

Assertions for Node 4.
All inputs are constructed in-memory — no LLM, no disk reads.
"""

from __future__ import annotations

import pytest

from prescreener.config import CRITERION_STATES
from prescreener.nodes.generate_report import generate_report
from evals.conftest import make_state


def _make_criterion_results(nct_id: str, overrides: dict | None = None) -> dict:
    """Return a full criterion_results dict for nct_id with all SUPPORTED defaults."""
    base = {
        "hba1c": {
            "state": "SUPPORTED",
            "evidence_ids": ["obs-001"],
            "explanation": "HbA1c within range.",
            "observation_date": "2026-04-15",
        },
        "egfr": {
            "state": "UNKNOWN",
            "evidence_ids": [],
            "explanation": "No eGFR reading (missing domain).",
            "observation_date": None,
        },
        "type2_diabetes_diagnosis": {
            "state": "SUPPORTED",
            "evidence_ids": ["cond-001"],
            "explanation": "T2D confirmed.",
            "observation_date": None,
        },
        "current_medications": {
            "state": "SUPPORTED",
            "evidence_ids": ["med-001"],
            "explanation": "No excluded medications.",
            "observation_date": None,
        },
        "bmi": {
            "state": "SUPPORTED",
            "evidence_ids": ["obs-003"],
            "explanation": "BMI within range.",
            "observation_date": "2026-03-12",
        },
    }
    if overrides:
        for criterion, values in overrides.items():
            base[criterion] = {**base[criterion], **values}
    return {nct_id: base}


def _make_trial(nct_id: str, status: str = "RECRUITING") -> dict:
    return {
        "nct_id": nct_id,
        "title": f"Trial {nct_id}",
        "overall_status": status,
        "minimum_age_years": 18,
        "maximum_age_years": None,
        "eligibility_text": "",
    }


def _run(
    trials: list[dict],
    criterion_results: dict,
    other_requirements: dict | None = None,
    open_questions: list[str] | None = None,
) -> list[dict]:
    patient = {
        "patient_id": "P001",
        "age_at_reference_date": 58,
        "as_of_date": "2026-07-01",
        "conditions": [],
        "observations": [],
        "medications": [],
        "record_quality": {"missing_expected_domains": []},
    }
    state = make_state(patient, candidate_trials=trials)
    state["criterion_results"]  = criterion_results
    state["other_requirements"] = other_requirements or {}
    state["open_questions"]     = open_questions or []
    patch = generate_report(state)
    return patch["final_report"]


# ── Report length ──────────────────────────────────────────────────────────────

def test_report_contains_at_most_three_entries():
    trials = [_make_trial(f"NCT_{i}") for i in range(5)]
    cr = {}
    for t in trials:
        cr.update(_make_criterion_results(t["nct_id"]))
    report = _run(trials, cr)
    assert len(report) <= 3, "final_report must contain ≤3 entries"


def test_single_trial_produces_one_entry():
    trial = _make_trial("NCT_SOLO")
    cr = _make_criterion_results("NCT_SOLO")
    report = _run([trial], cr)
    assert len(report) == 1


# ── clinical_fit and overall_status are separate keys ─────────────────────────

def test_clinical_fit_and_status_are_separate_keys():
    """A trial can be a strong fit but not recruiting — reviewer must see both."""
    trial = _make_trial("NCT_SEP", status="ENROLLING_BY_INVITATION")
    cr = _make_criterion_results("NCT_SEP")
    report = _run([trial], cr)
    entry = report[0]
    assert "clinical_fit"  in entry, "clinical_fit must be a top-level key"
    assert "overall_status" in entry, "overall_status must be a top-level key"
    assert entry["overall_status"] == "ENROLLING_BY_INVITATION"
    assert isinstance(entry["clinical_fit"], dict)


# ── evidence_ids cite real source_ids ─────────────────────────────────────────

def test_evidence_ids_reference_real_source_ids():
    """
    Every source_id in every evidence_ids list must match a known
    source_id in the patient record (simulated via a whitelist here).
    """
    known_ids = {"obs-001", "obs-003", "cond-001", "med-001"}
    trial = _make_trial("NCT_EV")
    cr = _make_criterion_results("NCT_EV")
    report = _run([trial], cr)
    for entry in report:
        for criterion, result in entry["clinical_fit"].items():
            for eid in result.get("evidence_ids", []):
                assert eid in known_ids or eid == "", (
                    f"evidence_id {eid!r} for {criterion} not in known patient source_ids"
                )


# ── Ranking: NOT_SUPPORTED ranked worse than UNKNOWN ──────────────────────────

def test_not_supported_trial_ranked_below_unknown_trial():
    """
    Trial A has one NOT_SUPPORTED; Trial B has one UNKNOWN.
    Trial B must rank higher (appear first in report).
    """
    trial_a = _make_trial("NCT_A")
    trial_b = _make_trial("NCT_B")

    cr_a = _make_criterion_results("NCT_A", {"hba1c": {"state": "NOT_SUPPORTED"}})
    cr_b = _make_criterion_results("NCT_B", {"hba1c": {"state": "UNKNOWN", "evidence_ids": []}})
    cr = {**cr_a, **cr_b}

    report = _run([trial_a, trial_b], cr)
    ids = [e["nct_id"] for e in report]
    assert ids.index("NCT_B") < ids.index("NCT_A"), (
        "UNKNOWN trial (NCT_B) must rank above NOT_SUPPORTED trial (NCT_A)"
    )


# ── Soft exclusion: clean trials preferred ────────────────────────────────────

def test_clean_trial_preferred_over_not_supported_trial():
    """
    NCT_CLEAN has zero NOT_SUPPORTED; NCT_DIRTY has one.
    NCT_CLEAN must be in the top-3 even if NCT_DIRTY would otherwise score well.
    """
    clean = _make_trial("NCT_CLEAN")
    dirty = _make_trial("NCT_DIRTY")

    cr_clean = _make_criterion_results("NCT_CLEAN")   # all SUPPORTED/UNKNOWN
    cr_dirty = _make_criterion_results("NCT_DIRTY", {
        "hba1c": {"state": "NOT_SUPPORTED"},
        "egfr":  {"state": "SUPPORTED", "evidence_ids": ["obs-011"]},
    })
    cr = {**cr_clean, **cr_dirty}

    report = _run([clean, dirty], cr)
    ids = [e["nct_id"] for e in report]
    assert "NCT_CLEAN" in ids, "Clean trial must be in report"


def test_fallback_when_all_trials_have_not_supported():
    """
    If ALL candidates have ≥1 NOT_SUPPORTED, fall back to the full sorted list.
    Report must be non-empty and human_review_required must be True.
    """
    trial_a = _make_trial("NCT_FA")
    trial_b = _make_trial("NCT_FB")

    cr_a = _make_criterion_results("NCT_FA", {"hba1c": {"state": "NOT_SUPPORTED"}})
    cr_b = _make_criterion_results("NCT_FB", {"egfr":  {"state": "NOT_SUPPORTED", "evidence_ids": []}})
    cr = {**cr_a, **cr_b}

    report = _run([trial_a, trial_b], cr)
    assert len(report) > 0, "Fallback must still return results when all have NOT_SUPPORTED"
    assert all(e["human_review_required"] for e in report), (
        "human_review_required must be True for all entries in the NOT_SUPPORTED fallback"
    )


# ── RECRUITING ranked before non-recruiting ───────────────────────────────────

def test_recruiting_trial_ranked_above_enrolling_by_invitation():
    """
    Both trials are otherwise equal; RECRUITING must rank above ENROLLING_BY_INVITATION
    as the fourth tiebreak.
    """
    recruiting  = _make_trial("NCT_REC",  status="RECRUITING")
    enrolling   = _make_trial("NCT_ENR",  status="ENROLLING_BY_INVITATION")

    # Both trials: same criterion states (all SUPPORTED)
    cr_rec = _make_criterion_results("NCT_REC",  {"egfr": {"state": "SUPPORTED", "evidence_ids": ["obs-011"]}})
    cr_enr = _make_criterion_results("NCT_ENR",  {"egfr": {"state": "SUPPORTED", "evidence_ids": ["obs-011"]}})
    cr = {**cr_rec, **cr_enr}

    report = _run([enrolling, recruiting], cr)  # pass in reverse order to test sorting
    ids = [e["nct_id"] for e in report]
    assert ids.index("NCT_REC") <= ids.index("NCT_ENR"), (
        "RECRUITING must rank at least as high as ENROLLING_BY_INVITATION"
    )


# ── other_requirements not silently dropped ───────────────────────────────────

def test_other_requirements_appear_in_report():
    trial = _make_trial("NCT_OTH")
    cr = _make_criterion_results("NCT_OTH")
    other = {"NCT_OTH": ["Willingness to attend monthly visits", "Written consent required"]}
    report = _run([trial], cr, other_requirements=other)
    assert len(report[0]["other_requirements"]) == 2


# ── plain_language_summary is present ─────────────────────────────────────────

def test_plain_language_summary_present_and_non_empty():
    trial = _make_trial("NCT_PLS")
    cr = _make_criterion_results("NCT_PLS")
    report = _run([trial], cr)
    summary = report[0].get("plain_language_summary", "")
    assert isinstance(summary, str) and len(summary) > 0
