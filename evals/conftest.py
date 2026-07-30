"""
evals/conftest.py — Shared fixtures for the eval suite.

All fixtures are pure Python — no API keys, no disk reads, no LLM calls.
"""

from __future__ import annotations

import pytest

from prescreener.state import PreScreenState


# ── Patient fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def patient_with_dual_hba1c() -> dict:
    """
    Patient P001: age 58, T2D confirmed, two HbA1c readings, no eGFR (missing),
    active metformin, completed sitagliptin.
    Exercises: most-recent-wins, missing domain, completed-med exclusion.
    """
    return {
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
            {
                "type": "hba1c",
                "value": 7.0,
                "unit": "%",
                "effective_date": "2026-04-15",
                "source_id": "obs-001",
            },
            {
                "type": "hba1c",
                "value": 8.0,
                "unit": "%",
                "effective_date": "2024-08-03",
                "source_id": "obs-002",
            },
            {
                "type": "bmi",
                "value": 31.4,
                "unit": "kg/m²",
                "effective_date": "2026-03-12",
                "source_id": "obs-003",
            },
        ],
        "medications": [
            {
                "name": "metformin",
                "status": "active",
                "start_date": "2019-04-01",
                "end_date": None,
                "source_id": "med-001",
            },
            {
                "name": "sitagliptin",
                "status": "completed",
                "start_date": "2021-06-01",
                "end_date": "2023-01-15",
                "source_id": "med-002",
            },
        ],
        "record_quality": {
            "missing_expected_domains": ["egfr"]
        },
    }


@pytest.fixture
def patient_no_as_of_date() -> dict:
    """Patient record with as_of_date intentionally absent."""
    return {
        "patient_id": "P_BAD",
        "age_at_reference_date": 50,
        # as_of_date deliberately omitted
        "conditions": [],
        "observations": [],
        "medications": [],
        "record_quality": {"missing_expected_domains": []},
    }


@pytest.fixture
def patient_on_glp1() -> dict:
    """Patient with an active GLP-1 agonist — triggers medication NOT_SUPPORTED."""
    return {
        "patient_id": "P002",
        "age_at_reference_date": 62,
        "as_of_date": "2026-07-01",
        "conditions": [
            {
                "snomed_code": "44054006",
                "display": "Type 2 diabetes mellitus",
                "onset_date": "2020-01-10",
                "source_id": "cond-002",
            }
        ],
        "observations": [
            {
                "type": "hba1c",
                "value": 8.5,
                "unit": "%",
                "effective_date": "2026-05-01",
                "source_id": "obs-010",
            },
            {
                "type": "egfr",
                "value": 65,
                "unit": "mL/min/1.73m²",
                "effective_date": "2026-05-01",
                "source_id": "obs-011",
            },
            {
                "type": "bmi",
                "value": 33.0,
                "unit": "kg/m²",
                "effective_date": "2026-05-01",
                "source_id": "obs-012",
            },
        ],
        "medications": [
            {
                "name": "semaglutide",   # GLP-1 agonist — should trigger exclusion
                "status": "active",
                "start_date": "2025-01-15",
                "end_date": None,
                "source_id": "med-010",
            },
        ],
        "record_quality": {"missing_expected_domains": []},
    }


# ── Trial fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def trial_hba1c_6_5_to_10() -> dict:
    return {
        "nct_id": "NCT04100001",
        "title": "Test Trial A",
        "overall_status": "RECRUITING",
        "minimum_age_years": 18,
        "maximum_age_years": 75,
        "eligibility_text": (
            "INCLUSION CRITERIA:\n"
            "Type 2 diabetes mellitus.\n"
            "HbA1c between 6.5% and 10.0%.\n"
            "eGFR >= 45 mL/min/1.73m².\n"
            "EXCLUSION CRITERIA:\n"
            "Current use of GLP-1 receptor agonist."
        ),
    }


@pytest.fixture
def trial_hba1c_7_5_to_11() -> dict:
    """HbA1c 7.5–11.0%; patient's most-recent 7.0% is OUTSIDE this range."""
    return {
        "nct_id": "NCT04100002",
        "title": "Test Trial B",
        "overall_status": "RECRUITING",
        "minimum_age_years": 30,
        "maximum_age_years": None,    # open upper boundary
        "eligibility_text": (
            "INCLUSION CRITERIA:\n"
            "Type 2 diabetes mellitus.\n"
            "HbA1c between 7.5% and 11.0%.\n"
            "EXCLUSION CRITERIA:\n"
            "Severe renal impairment (eGFR < 30)."
        ),
    }


@pytest.fixture
def trial_completed() -> dict:
    return {
        "nct_id": "NCT04100004",
        "title": "Completed Trial",
        "overall_status": "COMPLETED",
        "minimum_age_years": 18,
        "maximum_age_years": 70,
        "eligibility_text": "INCLUSION CRITERIA:\nType 2 diabetes.",
    }


@pytest.fixture
def trial_age_too_young() -> dict:
    """Max age 25 — patient age 58 should be excluded."""
    return {
        "nct_id": "NCT04100005",
        "title": "Paediatric Trial",
        "overall_status": "RECRUITING",
        "minimum_age_years": 10,
        "maximum_age_years": 25,
        "eligibility_text": "INCLUSION CRITERIA:\nType 2 diabetes.",
    }


# ── LLM span mock ──────────────────────────────────────────────────────────────

def make_mock_llm_response(spans: list[dict]):
    """
    Returns a mock LLM callable that always returns the given spans as JSON.
    Spans must match the {side, criterion, text} schema.
    """
    import json

    def _mock(_prompt: str) -> str:
        return json.dumps(spans)

    return _mock


# ── State builder ──────────────────────────────────────────────────────────────

def make_state(patient_record: dict, candidate_trials: list[dict] | None = None) -> PreScreenState:
    """Build a minimal PreScreenState for use in unit tests."""
    return {
        "patient_id":            patient_record.get("patient_id", "TEST"),
        "patient_record":        patient_record,
        "candidate_trials":      candidate_trials or [],
        "retrieved_evidence":    {},
        "criterion_results":     {},
        "other_requirements":    {},
        "open_questions":        [],
        "final_report":          [],
        "human_review_required": False,
    }
