"""
test_evaluate_criteria_harness.py

All tests are deterministic — no API calls, no disk reads beyond the dataset.
Mock LLM responses are injected directly as trial_evidence dicts.
"""

import json
from evaluate_criteria import evaluate_criteria

# ── Helpers ────────────────────────────────────────────────────────────────────

def _prefilter(age_state="SUPPORTED", status_state="SUPPORTED"):
    return {
        "age": {
            "state": age_state,
            "explanation": f"Age {age_state.lower()}.",
        },
        "trial_recruiting_status": {
            "state": status_state,
            "explanation": f"Status {status_state.lower()}.",
        },
    }


def _make_patient(hba1c_current=None, hba1c_historical=None,
                   egfr_current=None, active_meds=None, missing_domains=None):
    return {
        "hba1c": {
            "current": hba1c_current,
            "historical": hba1c_historical or [],
        },
        "egfr": {
            "current": egfr_current,
            "historical": [],
        },
        "active_medications": active_meds or [],
        "missing_domains": missing_domains or [],
    }


def _make_trial(hba1c=None, egfr=None, meds=None, other=None, prefilter=None):
    return {
        "nct_id": "NCT_TEST",
        "_prefilter_criteria": prefilter or _prefilter(),
        "hba1c": hba1c or [],
        "egfr": egfr or [],
        "current_diabetes_medications": meds or [],
        "other_requirements": other or [],
    }


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_p3098_egfr_missing_domain():
    """
    P-3098 hand-check: patient has egfr in missing_expected_domains, no eGFR obs.
    Trial has an eGFR threshold. Must output UNKNOWN with missing-domain reason.
    The missing-domain check must fire BEFORE the trial threshold check.
    """
    patient = _make_patient(
        hba1c_current={"value": 9.7, "unit": "%", "effective_date": "2026-05-31",
                       "source_id": "9ddf153d-54aa-5ce2-b5d5-ba1d880290c9"},
        missing_domains=["egfr"],
    )
    trial = _make_trial(
        egfr=[{"section": "exclusion",
               "text": "estimated glomerular filtration rate < 30 mL/min/1.73 m²"}],
    )
    result = evaluate_criteria(patient, trial)
    egfr_res = result["criterion_results"]["egfr"]
    assert egfr_res["state"] == "UNKNOWN", f"Expected UNKNOWN, got {egfr_res['state']}"
    assert "missing_expected_domains" in egfr_res["explanation"].lower(), (
        "Explanation must cite missing_expected_domains as the reason"
    )
    assert egfr_res["citations"] == [], "No citation possible for missing domain"
    print("PASS: P-3098 eGFR hand-check — UNKNOWN with missing-domain reason")


def test_egfr_no_trial_threshold():
    """Trial has no eGFR span → UNKNOWN (not SUPPORTED)."""
    patient = _make_patient(
        egfr_current={"value": 91, "unit": "mL/min/1.73m2",
                      "effective_date": "2026-04-25", "source_id": "egfr-src-1"},
    )
    trial = _make_trial(egfr=[])
    result = evaluate_criteria(patient, trial)
    assert result["criterion_results"]["egfr"]["state"] == "UNKNOWN"
    print("PASS: eGFR UNKNOWN when no trial threshold extracted")


def test_egfr_patient_passes_inclusion():
    """Patient eGFR 91 satisfies inclusion ≥ 30."""
    patient = _make_patient(
        egfr_current={"value": 91, "unit": "mL/min/1.73m2",
                      "effective_date": "2026-04-25", "source_id": "egfr-src-1"},
    )
    trial = _make_trial(
        egfr=[{"section": "inclusion",
               "text": "eGFR ≥ 30 mL/min/1.73m²"}],
    )
    result = evaluate_criteria(patient, trial)
    assert result["criterion_results"]["egfr"]["state"] == "SUPPORTED"
    assert "egfr-src-1" in result["criterion_results"]["egfr"]["citations"]
    print("PASS: eGFR SUPPORTED when patient value passes inclusion threshold")


def test_egfr_patient_triggers_exclusion():
    """Patient eGFR 20 triggers exclusion < 30 → NOT_SUPPORTED."""
    patient = _make_patient(
        egfr_current={"value": 20, "unit": "mL/min/1.73m2",
                      "effective_date": "2026-04-25", "source_id": "egfr-src-2"},
    )
    trial = _make_trial(
        egfr=[{"section": "exclusion",
               "text": "severe renal dysfunction defined as eGFR < 30 mL/min/1.73 m²"}],
    )
    result = evaluate_criteria(patient, trial)
    assert result["criterion_results"]["egfr"]["state"] == "NOT_SUPPORTED"
    print("PASS: eGFR NOT_SUPPORTED when patient value triggers exclusion threshold")


def test_hba1c_most_recent_wins_in_range():
    """Most-recent HbA1c 9.7% is within ≤ 9.9%. Older 8.8% is historical context only."""
    patient = _make_patient(
        hba1c_current={"value": 9.7, "unit": "%", "effective_date": "2026-05-31",
                       "source_id": "obs-current"},
        hba1c_historical=[{"value": 8.8, "unit": "%", "effective_date": "2024-07-07",
                            "source_id": "obs-old"}],
    )
    trial = _make_trial(
        hba1c=[{"section": "inclusion", "text": "Individuals with HbA1c ≤ 9.9%"}],
    )
    result = evaluate_criteria(patient, trial)
    hba1c_res = result["criterion_results"]["hba1c"]
    assert hba1c_res["state"] == "SUPPORTED"
    assert "obs-current" in hba1c_res["citations"]
    assert "obs-old" not in hba1c_res["citations"], "Historical reading must not be cited as evidence"
    assert "obs-old" in hba1c_res["explanation"], "Historical reading must be named in explanation"
    print("PASS: HbA1c most-recent-wins — current 9.7% SUPPORTED, historical 8.8% in explanation only")


def test_hba1c_most_recent_fails_range():
    """Most-recent HbA1c 9.7% is outside 7.5%–9.5% → NOT_SUPPORTED."""
    patient = _make_patient(
        hba1c_current={"value": 9.7, "unit": "%", "effective_date": "2026-05-31",
                       "source_id": "obs-current"},
    )
    trial = _make_trial(
        hba1c=[{"section": "inclusion", "text": "HbA1c ≥ 7.5% and ≤ 9.5%"}],
    )
    result = evaluate_criteria(patient, trial)
    assert result["criterion_results"]["hba1c"]["state"] == "NOT_SUPPORTED"
    print("PASS: HbA1c NOT_SUPPORTED when current value outside inclusion range")


def test_hba1c_no_trial_threshold():
    """No HbA1c spans in trial text → UNKNOWN (not SUPPORTED)."""
    patient = _make_patient(
        hba1c_current={"value": 7.5, "unit": "%", "effective_date": "2026-03-01",
                       "source_id": "obs-1"},
    )
    trial = _make_trial(hba1c=[])
    result = evaluate_criteria(patient, trial)
    assert result["criterion_results"]["hba1c"]["state"] == "UNKNOWN"
    print("PASS: HbA1c UNKNOWN when no threshold in trial text")


def test_medications_no_trial_rule():
    """No medication span in trial text → UNKNOWN (absence is not permission)."""
    patient = _make_patient(
        active_meds=[{"source_id": "med-1", "name": "Metformin 500 MG Oral Tablet",
                      "status": "active", "start_date": "2026-01-01", "end_date": None}],
    )
    trial = _make_trial(meds=[])
    result = evaluate_criteria(patient, trial)
    assert result["criterion_results"]["current_diabetes_medications"]["state"] == "UNKNOWN"
    print("PASS: medications UNKNOWN when no medication rule in trial text")


def test_medications_exclusion_triggered():
    """Active metformin matches exclusion span → NOT_SUPPORTED."""
    patient = _make_patient(
        active_meds=[{"source_id": "med-1", "name": "Metformin 500 MG Oral Tablet",
                      "status": "active", "start_date": "2026-01-01", "end_date": None}],
    )
    trial = _make_trial(
        meds=[{"section": "exclusion", "text": "Current use of metformin is prohibited"}],
    )
    result = evaluate_criteria(patient, trial)
    res = result["criterion_results"]["current_diabetes_medications"]
    assert res["state"] == "NOT_SUPPORTED"
    assert "med-1" in res["citations"]
    print("PASS: medications NOT_SUPPORTED when active med matches exclusion span")


def test_medications_no_active_meds_no_exclusion():
    """Patient has no active meds; trial has only an exclusion (e.g. no insulin).
    Patient can't trigger the exclusion → SUPPORTED."""
    patient = _make_patient(active_meds=[])
    trial = _make_trial(
        meds=[{"section": "exclusion", "text": "Current insulin therapy is excluded"}],
    )
    result = evaluate_criteria(patient, trial)
    assert result["criterion_results"]["current_diabetes_medications"]["state"] == "SUPPORTED"
    print("PASS: medications SUPPORTED when patient has no active meds and no exclusion triggered")


def test_other_requirements_rcr():
    """other_requirements present → REQUIRES_CLINICAL_REVIEW with verbatim citations."""
    patient = _make_patient()
    trial = _make_trial(
        other=[
            {"section": "inclusion", "text": "Must provide written informed consent"},
            {"section": "inclusion", "text": "Willing to attend monthly clinic visits"},
        ],
    )
    result = evaluate_criteria(patient, trial)
    rcr = result["criterion_results"]["other_requirements"]
    assert rcr["state"] == "REQUIRES_CLINICAL_REVIEW"
    assert len(rcr["citations"]) == 2
    assert result["human_review_required"] is True
    print("PASS: other_requirements -> REQUIRES_CLINICAL_REVIEW, human_review_required=True")


def test_human_review_false_when_all_clean():
    """Clean result (SUPPORTED/UNKNOWN only, no RCR/CONFLICTING) → human_review_required=False."""
    patient = _make_patient(
        hba1c_current={"value": 8.0, "unit": "%", "effective_date": "2026-03-01",
                       "source_id": "obs-1"},
        egfr_current={"value": 75, "unit": "mL/min/1.73m2",
                      "effective_date": "2026-03-01", "source_id": "obs-2"},
        active_meds=[],
    )
    trial = _make_trial(
        hba1c=[{"section": "inclusion", "text": "HbA1c ≤ 10%"}],
        # no egfr, no meds, no other
    )
    result = evaluate_criteria(patient, trial)
    assert result["human_review_required"] is False
    print("PASS: human_review_required=False when no RCR or CONFLICTING_EVIDENCE states")


def test_age_and_status_carried_forward():
    """age and trial_recruiting_status must be carried forward unchanged."""
    patient = _make_patient()
    trial = _make_trial(
        prefilter={
            "age": {"state": "SUPPORTED", "explanation": "Age 59 within [19, open]."},
            "trial_recruiting_status": {"state": "NOT_SUPPORTED",
                                        "explanation": "Trial is NOT_YET_RECRUITING."},
        }
    )
    result = evaluate_criteria(patient, trial)
    cr = result["criterion_results"]
    assert cr["age"]["state"] == "SUPPORTED"
    assert cr["age"]["explanation"] == "Age 59 within [19, open]."
    assert cr["trial_recruiting_status"]["state"] == "NOT_SUPPORTED"
    assert cr["trial_recruiting_status"]["citations"] == []
    print("PASS: age and trial_recruiting_status carried forward unchanged with empty citations")


def test_all_emitted_states_are_valid():
    """Smoke test: every state emitted must be one of the five spec-mandated states."""
    from evaluate_criteria import _VALID_STATES

    patient = _make_patient(
        hba1c_current={"value": 9.7, "unit": "%", "effective_date": "2026-05-31",
                       "source_id": "obs-hba1c"},
        egfr_current={"value": 91, "unit": "mL/min/1.73m2",
                      "effective_date": "2026-04-25", "source_id": "obs-egfr"},
        active_meds=[{"source_id": "med-1", "name": "Metformin 500 MG Oral Tablet",
                      "status": "active", "start_date": "2026-01-01", "end_date": None}],
        missing_domains=[],
    )
    trial = _make_trial(
        hba1c=[{"section": "inclusion", "text": "HbA1c ≤ 9.9%"}],
        egfr=[{"section": "exclusion", "text": "eGFR < 30 mL/min/1.73m²"}],
        meds=[{"section": "exclusion", "text": "Current use of GLP-1 receptor agonist"}],
        other=[{"section": "inclusion", "text": "Written consent required"}],
    )
    result = evaluate_criteria(patient, trial)
    for criterion, res in result["criterion_results"].items():
        assert res["state"] in _VALID_STATES, (
            f"Criterion '{criterion}' emitted invalid state: {res['state']!r}"
        )
    print("PASS: all emitted states are valid spec states")


if __name__ == "__main__":
    test_p3098_egfr_missing_domain()
    test_egfr_no_trial_threshold()
    test_egfr_patient_passes_inclusion()
    test_egfr_patient_triggers_exclusion()
    test_hba1c_most_recent_wins_in_range()
    test_hba1c_most_recent_fails_range()
    test_hba1c_no_trial_threshold()
    test_medications_no_trial_rule()
    test_medications_exclusion_triggered()
    test_medications_no_active_meds_no_exclusion()
    test_other_requirements_rcr()
    test_human_review_false_when_all_clean()
    test_age_and_status_carried_forward()
    test_all_emitted_states_are_valid()
    print()
    print("All evaluate_criteria tests passed.")
