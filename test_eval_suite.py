"""
test_eval_suite.py — Comprehensive 10-Case Evaluation Suite

Category 1: Retrieval
  1. test_operator_preservation_and_escape_stripping
  2. test_outlier_eligibility_text_handling

Category 2: Criterion State
  3. test_explicit_missing_domain_priority_p3098
  4. test_most_recent_wins_observation_eval_p1842

Category 3: Agent Behaviour
  5. test_age_hard_exclusion_p1842_vs_nct07702097
  6. test_soft_recruiting_status_preservation_real_data

Category 4: Dataset Coverage
  7. test_active_vs_completed_medication_filtering_p2483
  8. test_missing_rule_absence_is_not_permission

Category 5: Output Quality
  9. test_no_padding_clean_pool_ranking
 10. test_fallback_flag_selection_tier_and_human_review_trigger
"""

import json
from filter_structured import filter_structured
from retrieve_evidence import build_patient_evidence, retrieve_evidence, split_eligibility_text, _clean_markdown_escapes
from evaluate_criteria import evaluate_criteria
from generate_report import generate_report

# Load global dataset once for testing
with open("data/Type2-Diabetes-Trial-Agent-Dataset.json", encoding="utf-8") as f:
    DATASET = json.load(f)

PATIENTS_BY_ID = {p["patient_id"]: p for p in DATASET["patients"]}
TRIALS_BY_ID   = {t["nct_id"]: t for t in DATASET["trials"]}


# ── Category 1: Retrieval ──────────────────────────────────────────────────────

def test_operator_preservation_and_escape_stripping():
    """
    Test 1: Given trial NCT07719894 (raw text contains '\\< 30' scraper artifacts),
    verify that split_eligibility_text strips the backslash escape ('\\<' -> '<')
    while preserving unicode operator characters '≤' and '<' intact.
    """
    raw_trial = TRIALS_BY_ID["NCT07719894"]
    split = split_eligibility_text(raw_trial["eligibility_text"])

    exclusion_text = split["exclusion"]
    assert r"\<" not in exclusion_text, "Stray backslash markdown escape '\\<' must be stripped"
    assert "< 30" in exclusion_text or "eGFR < 30" in exclusion_text, (
        "Cleaned text must contain '< 30'"
    )

    inclusion_text = split["inclusion"]
    assert "≤ 9.9%" in inclusion_text, "Unicode operator '≤' must be preserved verbatim"
    print("PASS 1: Operator preservation & escape stripping (NCT07719894)")


def test_outlier_eligibility_text_handling():
    """
    Test 2: Trial NCT06094491 has inclusion criteria but no explicit 'Exclusion Criteria' header.
    Verify split_eligibility_text parses inclusion without error and returns empty exclusion.
    """
    raw_trial = TRIALS_BY_ID["NCT06094491"]
    split = split_eligibility_text(raw_trial["eligibility_text"])

    assert len(split["inclusion"]) > 0, "Inclusion text must be captured"
    assert split["exclusion"] == "", "Exclusion text must be empty string"
    print("PASS 2: Outlier eligibility text handling (NCT06094491)")


# ── Category 2: Criterion State ────────────────────────────────────────────────

def test_explicit_missing_domain_priority_p3098():
    """
    Test 3: Patient P-3098 explicitly lists missing_expected_domains: ['egfr'].
    Verify eGFR evaluation against trial NCT07719894 outputs state UNKNOWN,
    cites missing_expected_domains in explanation, and has empty citations [].
    """
    patient = PATIENTS_BY_ID["P-3098"]
    trial = TRIALS_BY_ID["NCT07719894"]

    # Stage 1 & 2
    candidates = filter_structured(patient, DATASET["trials"])
    cand_dict = next(c for c in candidates if c["nct_id"] == "NCT07719894")
    pev = build_patient_evidence(patient)

    # Mock trial evidence for eGFR span
    mock_trial_ev = {
        "nct_id": "NCT07719894",
        "_prefilter_criteria": cand_dict["_prefilter_criteria"],
        "hba1c": [],
        "current_diabetes_medications": [],
        "egfr": [{"section": "exclusion", "text": "eGFR < 30 mL/min/1.73m²"}],
        "other_requirements": [],
    }

    eval_res = evaluate_criteria(pev, mock_trial_ev)
    egfr_res = eval_res["criterion_results"]["egfr"]

    assert egfr_res["state"] == "UNKNOWN", f"Expected UNKNOWN, got {egfr_res['state']}"
    assert "missing_expected_domains" in egfr_res["explanation"].lower(), (
        "Explanation must cite missing_expected_domains"
    )
    assert egfr_res["citations"] == [], "Citations must be empty []"
    print("PASS 3: Explicit missing domain priority check (P-3098)")


def test_most_recent_wins_observation_eval_p1842():
    """
    Test 4: Patient P-1842 has HbA1c 7.0% (2026-04-30) and 8.0% (2024-08-19).
    Against a trial requiring HbA1c ≤ 7.5%, verify state is SUPPORTED based on 7.0%,
    and 8.0% is mentioned in explanation only, not cited in citations.
    """
    patient = PATIENTS_BY_ID["P-1842"]
    pev = build_patient_evidence(patient)

    mock_trial_ev = {
        "nct_id": "TEST_HBA1C",
        "_prefilter_criteria": {
            "age": {"state": "SUPPORTED", "explanation": ""},
            "trial_recruiting_status": {"state": "SUPPORTED", "explanation": ""},
        },
        "hba1c": [{"section": "inclusion", "text": "HbA1c ≤ 7.5%"}],
        "current_diabetes_medications": [],
        "egfr": [],
        "other_requirements": [],
    }

    eval_res = evaluate_criteria(pev, mock_trial_ev)
    hba1c_res = eval_res["criterion_results"]["hba1c"]

    assert hba1c_res["state"] == "SUPPORTED", f"Expected SUPPORTED, got {hba1c_res['state']}"
    assert "428a24e1-51f1-5c8a-b4a2-c4f182156f22" in hba1c_res["citations"], (
        "Must cite current HbA1c reading source_id"
    )
    assert "8.0%" in hba1c_res["explanation"], "Older reading must appear in explanation"
    print("PASS 4: Most-recent-wins observation evaluation (P-1842)")


# ── Category 3: Agent Behaviour ────────────────────────────────────────────────

def test_age_hard_exclusion_p1842_vs_nct07702097():
    """
    Test 5: Patient P-1842 (age 60). Trial NCT07702097 has age window [30, 50].
    Verify filter_structured completely excludes NCT07702097 from candidate trials.
    """
    patient = PATIENTS_BY_ID["P-1842"]
    candidates = filter_structured(patient, DATASET["trials"])
    cand_ids = {t["nct_id"] for t in candidates}

    assert "NCT07702097" not in cand_ids, (
        "Patient age 60 must be hard-excluded by trial age window [30, 50]"
    )
    print("PASS 5: Age hard exclusion (P-1842 vs NCT07702097)")


def test_soft_recruiting_status_preservation_real_data():
    """
    Test 6: Trial NCT07047248 has actual dataset overall_status == 'NOT_YET_RECRUITING'.
    Verify filter_structured does NOT drop it for patient P-1842, and attaches
    _prefilter_criteria with trial_recruiting_status state == 'NOT_SUPPORTED'.
    """
    patient = PATIENTS_BY_ID["P-1842"]
    candidates = filter_structured(patient, DATASET["trials"])
    cand_dict = next((c for c in candidates if c["nct_id"] == "NCT07047248"), None)

    assert cand_dict is not None, (
        "NOT_YET_RECRUITING trial NCT07047248 must NOT be dropped by filter_structured"
    )
    status_state = cand_dict["_prefilter_criteria"]["trial_recruiting_status"]["state"]
    assert status_state == "NOT_SUPPORTED", (
        f"Expected NOT_SUPPORTED for recruiting status, got {status_state}"
    )
    print("PASS 6: Soft recruiting status preservation on real dataset trial (NCT07047248)")


# ── Category 4: Dataset Coverage ───────────────────────────────────────────────

def test_active_vs_completed_medication_filtering_p2483():
    """
    Test 7: Patient P-2483 has active Metformin & Glipizide.
    Verify build_patient_evidence extracts active medications only (status == 'active').
    """
    patient = PATIENTS_BY_ID["P-2483"]
    pev = build_patient_evidence(patient)

    active_meds = pev["active_medications"]
    assert len(active_meds) == 2, f"Expected 2 active meds, got {len(active_meds)}"
    med_names = [m["name"] for m in active_meds]
    assert "Metformin 500 MG Oral Tablet" in med_names
    assert "Glipizide 5 MG Oral Tablet" in med_names
    for m in active_meds:
        assert m["status"] == "active"
    print("PASS 7: Active vs completed medication filtering (P-2483)")


def test_missing_rule_absence_is_not_permission():
    """
    Test 8: Patient P-3098 evaluated against a trial evidence dict with no medication rules.
    Verify current_diabetes_medications state is UNKNOWN (not SUPPORTED).
    """
    patient = PATIENTS_BY_ID["P-3098"]
    pev = build_patient_evidence(patient)

    mock_trial_ev = {
        "nct_id": "TEST_NO_MED_RULE",
        "_prefilter_criteria": {
            "age": {"state": "SUPPORTED", "explanation": ""},
            "trial_recruiting_status": {"state": "SUPPORTED", "explanation": ""},
        },
        "hba1c": [],
        "current_diabetes_medications": [],  # no rules extracted
        "egfr": [],
        "other_requirements": [],
    }

    eval_res = evaluate_criteria(pev, mock_trial_ev)
    med_res = eval_res["criterion_results"]["current_diabetes_medications"]

    assert med_res["state"] == "UNKNOWN", f"Expected UNKNOWN, got {med_res['state']}"
    print("PASS 8: Missing rule absence-is-not-permission")


# ── Category 5: Output Quality ─────────────────────────────────────────────────

def test_no_padding_clean_pool_ranking():
    """
    Test 9: Given 2 clean trials and 1 NOT_SUPPORTED trial, generate_report must return
    exactly 2 entries, selection_tier == 'clean', and NOT pad with the NOT_SUPPORTED trial.
    """
    clean1 = {
        "trial": {"nct_id": "NCT_C1", "overall_status": "RECRUITING"},
        "criterion_results": {
            "age": {"state": "SUPPORTED"}, "trial_recruiting_status": {"state": "SUPPORTED"},
            "hba1c": {"state": "SUPPORTED"}, "egfr": {"state": "SUPPORTED"},
            "current_diabetes_medications": {"state": "SUPPORTED"},
        },
        "human_review_required": False,
    }
    clean2 = {
        "trial": {"nct_id": "NCT_C2", "overall_status": "RECRUITING"},
        "criterion_results": {
            "age": {"state": "SUPPORTED"}, "trial_recruiting_status": {"state": "SUPPORTED"},
            "hba1c": {"state": "SUPPORTED"}, "egfr": {"state": "UNKNOWN"},
            "current_diabetes_medications": {"state": "SUPPORTED"},
        },
        "human_review_required": False,
    }
    dirty = {
        "trial": {"nct_id": "NCT_D1", "overall_status": "RECRUITING"},
        "criterion_results": {
            "age": {"state": "SUPPORTED"}, "trial_recruiting_status": {"state": "SUPPORTED"},
            "hba1c": {"state": "NOT_SUPPORTED"}, "egfr": {"state": "SUPPORTED"},
            "current_diabetes_medications": {"state": "SUPPORTED"},
        },
        "human_review_required": False,
    }

    report = generate_report([clean1, clean2, dirty])
    assert len(report) == 2, f"Expected 2 entries, got {len(report)}"
    assert all(e["selection_tier"] == "clean" for e in report)
    assert not any(e["nct_id"] == "NCT_D1" for e in report)
    print("PASS 9: No-padding clean pool ranking (returns 2 clean entries, 0 dirty)")


def test_fallback_flag_selection_tier_and_human_review_trigger():
    """
    Test 10: When all candidate trials have at least one NOT_SUPPORTED criterion,
    generate_report activates fallback path, returning up to 3 entries with
    selection_tier == 'fallback', is_fallback == True, and human_review_required == True.
    """
    dirty1 = {
        "trial": {"nct_id": "NCT_D1", "overall_status": "RECRUITING"},
        "criterion_results": {
            "age": {"state": "SUPPORTED"}, "trial_recruiting_status": {"state": "SUPPORTED"},
            "hba1c": {"state": "NOT_SUPPORTED"}, "egfr": {"state": "SUPPORTED"},
            "current_diabetes_medications": {"state": "SUPPORTED"},
        },
        "human_review_required": False,
    }
    dirty2 = {
        "trial": {"nct_id": "NCT_D2", "overall_status": "RECRUITING"},
        "criterion_results": {
            "age": {"state": "SUPPORTED"}, "trial_recruiting_status": {"state": "SUPPORTED"},
            "hba1c": {"state": "NOT_SUPPORTED"}, "egfr": {"state": "NOT_SUPPORTED"},
            "current_diabetes_medications": {"state": "SUPPORTED"},
        },
        "human_review_required": False,
    }

    report = generate_report([dirty1, dirty2])
    assert len(report) == 2
    for entry in report:
        assert entry["selection_tier"] == "fallback"
        assert entry["is_fallback"] is True
        assert entry["human_review_required"] is True

    # Check ranking: dirty1 (1 NOT_SUPPORTED) must rank above dirty2 (2 NOT_SUPPORTED)
    assert report[0]["nct_id"] == "NCT_D1"
    print("PASS 10: Fallback flag, selection_tier='fallback', human_review_required=True trigger")


# ── Test Runner ────────────────────────────────────────────────────────────────

def run_all_eval_suite_tests():
    print("=== Running 10-Case Evaluation Suite ===")
    test_operator_preservation_and_escape_stripping()
    test_outlier_eligibility_text_handling()
    test_explicit_missing_domain_priority_p3098()
    test_most_recent_wins_observation_eval_p1842()
    test_age_hard_exclusion_p1842_vs_nct07702097()
    test_soft_recruiting_status_preservation_real_data()
    test_active_vs_completed_medication_filtering_p2483()
    test_missing_rule_absence_is_not_permission()
    test_no_padding_clean_pool_ranking()
    test_fallback_flag_selection_tier_and_human_review_trigger()
    print("\nAll 10 Evaluation Suite tests passed cleanly!")

if __name__ == "__main__":
    run_all_eval_suite_tests()
