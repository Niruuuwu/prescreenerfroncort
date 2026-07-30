"""
evals/test_retrieve_evidence.py

Assertions for Node 2.
The LLM call is always mocked — no API key required.
"""

from __future__ import annotations

import json

import pytest

from prescreener.nodes.retrieve_evidence import retrieve_evidence
from evals.conftest import make_mock_llm_response, make_state


_PATIENT = {
    "patient_id": "P001",
    "age_at_reference_date": 58,
    "as_of_date": "2026-07-01",
    "conditions": [
        {
            "snomed_code": "44054006",
            "display": "Type 2 diabetes mellitus",
            "onset_date": "2019-03-15",
            "source_id": "cond-001",
        }
    ],
    "observations": [
        {"type": "hba1c", "value": 7.0, "unit": "%", "effective_date": "2026-04-15", "source_id": "obs-001"},
        {"type": "hba1c", "value": 8.0, "unit": "%", "effective_date": "2024-08-03", "source_id": "obs-002"},
        {"type": "bmi",   "value": 31.4,"unit": "kg/m²","effective_date": "2026-03-12","source_id": "obs-003"},
    ],
    "medications": [
        {"name": "metformin", "status": "active",    "start_date": "2019-04-01", "end_date": None, "source_id": "med-001"},
        {"name": "sitagliptin","status": "completed","start_date": "2021-06-01", "end_date": "2023-01-15", "source_id": "med-002"},
    ],
    "record_quality": {"missing_expected_domains": ["egfr"]},
}


_MOCK_SPANS = [
    {"side": "inclusion", "criterion": "hba1c",   "text": "HbA1c between 7.5% and 11.0%"},
    {"side": "exclusion", "criterion": "current_medications", "text": "Current use of GLP-1 receptor agonist"},
    {"side": "inclusion", "criterion": "other",   "text": "Willingness to attend monthly visits"},
]


def _run_with_mock(trials, spans=None):
    mock_llm = make_mock_llm_response(spans if spans is not None else _MOCK_SPANS)
    state = make_state(_PATIENT, candidate_trials=trials)
    patch = retrieve_evidence(state, llm_fn=mock_llm)
    return patch["retrieved_evidence"]


# ── Most-recent observation selected ──────────────────────────────────────────

def test_most_recent_hba1c_selected():
    """
    Patient has two HbA1c readings: 7.0% (Apr 2026) and 8.0% (Aug 2024).
    The most recent (obs-001) must be selected.
    """
    trial = {"nct_id": "NCT_A", "title": "A", "overall_status": "RECRUITING",
             "minimum_age_years": 18, "maximum_age_years": None, "eligibility_text": "Type 2 diabetes."}
    ev = _run_with_mock([trial])
    hba1c = ev["NCT_A"]["patient_evidence"]["hba1c"]
    assert hba1c["source_id"] == "obs-001", "Most recent HbA1c reading must be obs-001"
    assert hba1c["date"] == "2026-04-15"


def test_all_hba1c_readings_populated():
    """The full history must be stored for audit-trail use in evaluate_criteria."""
    trial = {"nct_id": "NCT_B", "title": "B", "overall_status": "RECRUITING",
             "minimum_age_years": 18, "maximum_age_years": None, "eligibility_text": "T2D."}
    ev = _run_with_mock([trial])
    all_readings = ev["NCT_B"]["patient_evidence"]["all_hba1c_readings"]
    assert len(all_readings) == 2, "Both HbA1c readings must be stored in all_hba1c_readings"
    dates = [r["date"] for r in all_readings]
    assert dates == sorted(dates, reverse=True), "Readings must be sorted most-recent first"


# ── Patient-side and trial-side are stored separately ─────────────────────────

def test_patient_and_trial_evidence_not_merged():
    """
    RESEARCH §6: patient_evidence and eligibility_spans must be stored as
    separate keys — never merged into a single blob.
    """
    trial = {"nct_id": "NCT_C", "title": "C", "overall_status": "RECRUITING",
             "minimum_age_years": 18, "maximum_age_years": None, "eligibility_text": "T2D."}
    ev = _run_with_mock([trial])
    assert "patient_evidence"  in ev["NCT_C"]
    assert "eligibility_spans" in ev["NCT_C"]
    assert "hba1c" not in ev["NCT_C"]["eligibility_spans"], (
        "Patient observations must not appear inside eligibility_spans"
    )


# ── LLM call receives only one trial's eligibility_text ──────────────────────

def test_llm_called_once_per_trial():
    """Each trial must trigger exactly one LLM call (not a batch)."""
    call_log: list[str] = []

    def recording_llm(prompt: str) -> str:
        call_log.append(prompt)
        return json.dumps(_MOCK_SPANS)

    trials = [
        {"nct_id": "NCT_D", "title": "D", "overall_status": "RECRUITING",
         "minimum_age_years": 18, "maximum_age_years": None, "eligibility_text": "Trial D text."},
        {"nct_id": "NCT_E", "title": "E", "overall_status": "RECRUITING",
         "minimum_age_years": 18, "maximum_age_years": None, "eligibility_text": "Trial E text."},
    ]
    state = make_state(_PATIENT, candidate_trials=trials)
    retrieve_evidence(state, llm_fn=recording_llm)

    assert len(call_log) == 2, "Must make exactly one LLM call per trial"
    assert "Trial D text." in call_log[0]
    assert "Trial E text." in call_log[1]


def test_no_patient_data_in_llm_prompt():
    """
    Patient identifiers, observations, and medications must never appear
    in the LLM prompt (only eligibility_text is sent).
    """
    captured_prompts: list[str] = []

    def capturing_llm(prompt: str) -> str:
        captured_prompts.append(prompt)
        return "[]"

    trial = {"nct_id": "NCT_F", "title": "F", "overall_status": "RECRUITING",
             "minimum_age_years": 18, "maximum_age_years": None,
             "eligibility_text": "HbA1c between 7.0% and 10.0%."}
    state = make_state(_PATIENT, candidate_trials=[trial])
    retrieve_evidence(state, llm_fn=capturing_llm)

    prompt = captured_prompts[0]
    assert "P001" not in prompt,       "Patient ID must not appear in LLM prompt"
    assert "obs-001" not in prompt,    "Observation source_ids must not appear in LLM prompt"
    assert "med-001" not in prompt,    "Medication source_ids must not appear in LLM prompt"
    assert "cond-001" not in prompt,   "Condition source_ids must not appear in LLM prompt"
    assert "metformin" not in prompt,  "Patient medication names must not appear in LLM prompt"


# ── Active vs completed medications ───────────────────────────────────────────

def test_only_active_medications_in_patient_evidence():
    """
    sitagliptin is completed — must NOT appear in active_medications.
    """
    trial = {"nct_id": "NCT_G", "title": "G", "overall_status": "RECRUITING",
             "minimum_age_years": 18, "maximum_age_years": None, "eligibility_text": "T2D."}
    ev = _run_with_mock([trial])
    active_names = [m["name"] for m in ev["NCT_G"]["patient_evidence"]["active_medications"]]
    assert "sitagliptin" not in active_names, (
        "Completed sitagliptin must not appear in active_medications"
    )
    assert "metformin" in active_names


# ── Unclassified spans routed correctly ───────────────────────────────────────

def test_unclassified_spans_in_eligibility_spans():
    """Spans with criterion='other' must appear in the unclassified list."""
    trial = {"nct_id": "NCT_H", "title": "H", "overall_status": "RECRUITING",
             "minimum_age_years": 18, "maximum_age_years": None, "eligibility_text": "T2D."}
    ev = _run_with_mock([trial], spans=_MOCK_SPANS)
    unclassified = ev["NCT_H"]["eligibility_spans"]["unclassified"]
    assert "Willingness to attend monthly visits" in unclassified


# ── missing_domains copied verbatim ───────────────────────────────────────────

def test_missing_domains_copied_verbatim():
    """
    record_quality.missing_expected_domains must be copied into patient_evidence
    unchanged — not inferred from the absence of observations.
    """
    trial = {"nct_id": "NCT_I", "title": "I", "overall_status": "RECRUITING",
             "minimum_age_years": 18, "maximum_age_years": None, "eligibility_text": "T2D."}
    ev = _run_with_mock([trial])
    assert ev["NCT_I"]["patient_evidence"]["missing_domains"] == ["egfr"]
