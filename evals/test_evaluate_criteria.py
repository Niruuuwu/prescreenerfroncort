"""
evals/test_evaluate_criteria.py

Deterministic assertions for Node 3.
All tests construct retrieved_evidence directly — no LLM, no disk reads.
"""

from __future__ import annotations

import pytest

from prescreener.config import CRITERION_STATES
from prescreener.nodes.evaluate_criteria import evaluate_criteria
from evals.conftest import make_state


def _make_retrieved_evidence(
    nct_id: str,
    patient_evidence: dict,
    inclusion: list[dict] | None = None,
    exclusion: list[dict] | None = None,
    unclassified: list[str] | None = None,
) -> dict:
    return {
        nct_id: {
            "patient_evidence": patient_evidence,
            "eligibility_spans": {
                "inclusion":    inclusion    or [],
                "exclusion":    exclusion    or [],
                "unclassified": unclassified or [],
            },
        }
    }


def _run(patient_record: dict, retrieved_evidence: dict) -> dict:
    state = make_state(patient_record)
    state["retrieved_evidence"] = retrieved_evidence
    return evaluate_criteria(state)


# ── All emitted states must be in CRITERION_STATES ────────────────────────────

def test_all_states_in_spec_enum(patient_with_dual_hba1c):
    """HARD ASSERTION: every state value must be one of the five spec states."""
    ev = _make_retrieved_evidence(
        "NCT_ANY",
        {
            **_base_patient_ev(patient_with_dual_hba1c),
            "missing_domains": ["egfr"],
        },
        inclusion=[{"criterion": "hba1c", "text": "HbA1c between 6.5% and 10.0%"}],
    )
    patch = _run(patient_with_dual_hba1c, ev)
    for nct_id, results in patch["criterion_results"].items():
        for criterion, result in results.items():
            assert result["state"] in CRITERION_STATES, (
                f"{nct_id}/{criterion} emitted invalid state {result['state']!r}"
            )


# ── Missing domain → UNKNOWN (never NOT_SUPPORTED) ───────────────────────────

def test_missing_egfr_domain_yields_unknown(patient_with_dual_hba1c):
    """
    RESEARCH §3.5: absence is not evidence. A missing egfr domain must yield
    UNKNOWN, never NOT_SUPPORTED.
    """
    ev = _make_retrieved_evidence(
        "NCT_EGFR",
        {
            **_base_patient_ev(patient_with_dual_hba1c),
            "egfr": None,
            "missing_domains": ["egfr"],
        },
        inclusion=[{"criterion": "egfr", "text": "eGFR >= 45 mL/min/1.73m²"}],
    )
    patch = _run(patient_with_dual_hba1c, ev)
    egfr_result = patch["criterion_results"]["NCT_EGFR"]["egfr"]
    assert egfr_result["state"] == "UNKNOWN", (
        "Missing domain must yield UNKNOWN, not NOT_SUPPORTED"
    )
    assert egfr_result["evidence_ids"] == [], "No evidence can be cited for a missing domain"


def test_missing_conditions_domain_yields_unknown(patient_with_dual_hba1c):
    ev = _make_retrieved_evidence(
        "NCT_COND",
        {
            **_base_patient_ev(patient_with_dual_hba1c),
            "t2d_diagnosis": None,
            "missing_domains": ["conditions"],
        },
    )
    patch = _run(patient_with_dual_hba1c, ev)
    result = patch["criterion_results"]["NCT_COND"]["type2_diabetes_diagnosis"]
    assert result["state"] == "UNKNOWN"


def test_missing_medications_domain_yields_unknown(patient_with_dual_hba1c):
    ev = _make_retrieved_evidence(
        "NCT_MEDS",
        {
            **_base_patient_ev(patient_with_dual_hba1c),
            "missing_domains": ["medications"],
        },
        exclusion=[{"criterion": "current_medications", "text": "Current use of GLP-1 agonist"}],
    )
    patch = _run(patient_with_dual_hba1c, ev)
    result = patch["criterion_results"]["NCT_MEDS"]["current_medications"]
    assert result["state"] == "UNKNOWN"


# ── No span extracted → REQUIRES_CLINICAL_REVIEW ──────────────────────────────

def test_no_hba1c_span_yields_rcr(patient_with_dual_hba1c):
    ev = _make_retrieved_evidence(
        "NCT_NO_SPAN",
        _base_patient_ev(patient_with_dual_hba1c),
        # No inclusion span for hba1c
    )
    patch = _run(patient_with_dual_hba1c, ev)
    result = patch["criterion_results"]["NCT_NO_SPAN"]["hba1c"]
    assert result["state"] == "REQUIRES_CLINICAL_REVIEW"


def test_no_medication_span_yields_rcr(patient_with_dual_hba1c):
    ev = _make_retrieved_evidence(
        "NCT_NO_MED_SPAN",
        _base_patient_ev(patient_with_dual_hba1c),
        # No medication spans at all
    )
    patch = _run(patient_with_dual_hba1c, ev)
    result = patch["criterion_results"]["NCT_NO_MED_SPAN"]["current_medications"]
    assert result["state"] == "REQUIRES_CLINICAL_REVIEW"


# ── HbA1c most-recent-wins: NOT CONFLICTING_EVIDENCE ──────────────────────────

def test_dual_hba1c_uses_most_recent_not_conflicting(patient_with_dual_hba1c):
    """
    Patient has HbA1c 7.0% (Apr 2026) and 8.0% (Aug 2024).
    Trial requires 7.5–11.0%.
    Most-recent (7.0%) is OUTSIDE range → NOT_SUPPORTED.
    State must be NOT_SUPPORTED, NOT CONFLICTING_EVIDENCE.
    Explanation must mention the unused 8.0% reading.
    """
    ev = _make_retrieved_evidence(
        "NCT_DUAL",
        _base_patient_ev(patient_with_dual_hba1c),
        inclusion=[{"criterion": "hba1c", "text": "HbA1c between 7.5% and 11.0%"}],
    )
    patch = _run(patient_with_dual_hba1c, ev)
    result = patch["criterion_results"]["NCT_DUAL"]["hba1c"]

    assert result["state"] == "NOT_SUPPORTED", (
        "Most-recent 7.0% is outside 7.5-11.0%; must be NOT_SUPPORTED"
    )
    assert "obs-002" in result["explanation"], (
        "Explanation must cite the unused older reading (obs-002)"
    )
    assert "most-recent-wins" in result["explanation"].lower() or \
           "most recent" in result["explanation"].lower(), (
        "Explanation must name the selection rule"
    )
    assert result["observation_date"] == "2026-04-15"


def test_dual_hba1c_most_recent_in_range_is_supported(patient_with_dual_hba1c):
    """
    Most-recent HbA1c 7.0% is IN range 6.5–10.0% → SUPPORTED.
    """
    ev = _make_retrieved_evidence(
        "NCT_DUAL_SUPP",
        _base_patient_ev(patient_with_dual_hba1c),
        inclusion=[{"criterion": "hba1c", "text": "HbA1c between 6.5% and 10.0%"}],
    )
    patch = _run(patient_with_dual_hba1c, ev)
    result = patch["criterion_results"]["NCT_DUAL_SUPP"]["hba1c"]
    assert result["state"] == "SUPPORTED"
    assert result["evidence_ids"] == ["obs-001"]


# ── Medication evaluation ──────────────────────────────────────────────────────

def test_active_glp1_triggers_not_supported(patient_on_glp1):
    """Active semaglutide (GLP-1) matches exclusion span → NOT_SUPPORTED."""
    ev = _make_retrieved_evidence(
        "NCT_GLP1",
        _base_patient_ev_from(patient_on_glp1),
        exclusion=[
            {"criterion": "current_medications", "text": "Current use of GLP-1 receptor agonist"}
        ],
    )
    patch = _run(patient_on_glp1, ev)
    result = patch["criterion_results"]["NCT_GLP1"]["current_medications"]
    assert result["state"] == "NOT_SUPPORTED"
    assert "med-010" in result["evidence_ids"]


def test_completed_medication_does_not_trigger_not_supported(patient_with_dual_hba1c):
    """
    sitagliptin is COMPLETED — must not count as current.
    Even if the exclusion span mentions it, the state must be SUPPORTED.
    """
    ev = _make_retrieved_evidence(
        "NCT_SITA",
        _base_patient_ev(patient_with_dual_hba1c),
        exclusion=[
            {"criterion": "current_medications", "text": "Current use of sitagliptin or DPP-4 inhibitor"}
        ],
    )
    patch = _run(patient_with_dual_hba1c, ev)
    result = patch["criterion_results"]["NCT_SITA"]["current_medications"]
    assert result["state"] == "SUPPORTED", (
        "Completed sitagliptin must not count as active — state must be SUPPORTED"
    )


def test_conflicting_evidence_when_med_required_and_excluded(patient_with_dual_hba1c):
    """
    metformin appears in both an inclusion requirement and an exclusion criterion
    → CONFLICTING_EVIDENCE (cannot resolve deterministically).
    """
    ev = _make_retrieved_evidence(
        "NCT_CONFLICT",
        _base_patient_ev(patient_with_dual_hba1c),
        inclusion=[
            {"criterion": "current_medications", "text": "Must be on current metformin therapy"}
        ],
        exclusion=[
            {"criterion": "current_medications", "text": "Current use of metformin is prohibited"}
        ],
    )
    patch = _run(patient_with_dual_hba1c, ev)
    result = patch["criterion_results"]["NCT_CONFLICT"]["current_medications"]
    assert result["state"] == "CONFLICTING_EVIDENCE"


# ── other_requirements — unclassified spans must not be dropped ───────────────

def test_unclassified_spans_appear_in_other_requirements(patient_with_dual_hba1c):
    ev = _make_retrieved_evidence(
        "NCT_OTHER",
        _base_patient_ev(patient_with_dual_hba1c),
        unclassified=[
            "Willingness to perform self-monitoring of blood glucose",
            "Patient must provide written informed consent",
        ],
    )
    patch = _run(patient_with_dual_hba1c, ev)
    assert "NCT_OTHER" in patch["other_requirements"]
    assert len(patch["other_requirements"]["NCT_OTHER"]) == 2
    assert patch["human_review_required"] is True


# ── open_questions populated correctly ────────────────────────────────────────

def test_unknown_criterion_added_to_open_questions(patient_with_dual_hba1c):
    ev = _make_retrieved_evidence(
        "NCT_OQ",
        {
            **_base_patient_ev(patient_with_dual_hba1c),
            "egfr": None,
            "missing_domains": ["egfr"],
        },
    )
    patch = _run(patient_with_dual_hba1c, ev)
    assert any("NCT_OQ" in q and "egfr" in q for q in patch["open_questions"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _base_patient_ev(patient_record: dict) -> dict:
    """Extract the patient evidence dict shape from a patient fixture."""
    return {
        "hba1c": {
            "value":     7.0,
            "unit":      "%",
            "date":      "2026-04-15",
            "source_id": "obs-001",
        },
        "egfr": None,
        "bmi": {
            "value":     31.4,
            "unit":      "kg/m²",
            "date":      "2026-03-12",
            "source_id": "obs-003",
        },
        "all_hba1c_readings": [
            {"value": 7.0, "unit": "%", "date": "2026-04-15", "source_id": "obs-001"},
            {"value": 8.0, "unit": "%", "date": "2024-08-03", "source_id": "obs-002"},
        ],
        "all_egfr_readings": [],
        "all_bmi_readings": [
            {"value": 31.4, "unit": "kg/m²", "date": "2026-03-12", "source_id": "obs-003"},
        ],
        "active_medications": [
            {"name": "metformin", "source_id": "med-001"},
        ],
        "t2d_diagnosis": {
            "snomed_code": "44054006",
            "date":        "2019-03-15",
            "source_id":   "cond-001",
        },
        "missing_domains": ["egfr"],
    }


def _base_patient_ev_from(patient_record: dict) -> dict:
    """Build a patient evidence dict from the patient_on_glp1 fixture."""
    return {
        "hba1c": {"value": 8.5, "unit": "%", "date": "2026-05-01", "source_id": "obs-010"},
        "egfr":  {"value": 65,  "unit": "mL/min/1.73m²", "date": "2026-05-01", "source_id": "obs-011"},
        "bmi":   {"value": 33.0,"unit": "kg/m²", "date": "2026-05-01", "source_id": "obs-012"},
        "all_hba1c_readings": [{"value": 8.5, "unit": "%", "date": "2026-05-01", "source_id": "obs-010"}],
        "all_egfr_readings":  [{"value": 65,  "unit": "mL/min/1.73m²", "date": "2026-05-01", "source_id": "obs-011"}],
        "all_bmi_readings":   [{"value": 33.0,"unit": "kg/m²", "date": "2026-05-01", "source_id": "obs-012"}],
        "active_medications":  [{"name": "semaglutide", "source_id": "med-010"}],
        "t2d_diagnosis": {"snomed_code": "44054006", "date": "2020-01-10", "source_id": "cond-002"},
        "missing_domains": [],
    }
