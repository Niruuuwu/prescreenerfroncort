import json
from filter_structured import filter_structured
from retrieve_evidence import build_patient_evidence, retrieve_evidence, split_eligibility_text

def test_harness():
    with open("data/Type2-Diabetes-Trial-Agent-Dataset.json", encoding="utf-8") as f:
        data = json.load(f)

    patients_by_id = {p["patient_id"]: p for p in data["patients"]}
    trials_by_id = {t["nct_id"]: t for t in data["trials"]}

    # 1. Test build_patient_evidence for P-1842
    p1842 = patients_by_id["P-1842"]
    pev = build_patient_evidence(p1842)

    assert pev["hba1c"]["current"]["value"] == 7.0
    assert pev["hba1c"]["current"]["source_id"] == "428a24e1-51f1-5c8a-b4a2-c4f182156f22"
    assert len(pev["hba1c"]["historical"]) == 1
    assert pev["hba1c"]["historical"][0]["value"] == 8.0
    assert "bmi" not in pev, "BMI must be completely dropped"
    print("PASS: build_patient_evidence correct for P-1842 (HbA1c current 7.0, historical 8.0, no BMI)")

    # 2. Test build_patient_evidence for P-2483 (active medications check)
    p2483 = patients_by_id["P-2483"]
    pev2483 = build_patient_evidence(p2483)
    med_names = [m["name"] for m in pev2483["active_medications"]]
    assert len(med_names) == 2
    assert "Metformin 500 MG Oral Tablet" in med_names
    assert "Glipizide 5 MG Oral Tablet" in med_names
    print("PASS: active medications correctly extracted for P-2483")

    # 3. Test split_eligibility_text for regular and outlier trial
    t_normal = trials_by_id["NCT07719894"]
    sec_normal = split_eligibility_text(t_normal["eligibility_text"])
    assert "Inclusion Criteria:" not in sec_normal["inclusion"]
    assert "Exclusion Criteria:" not in sec_normal["exclusion"]
    assert len(sec_normal["inclusion"]) > 0
    assert len(sec_normal["exclusion"]) > 0
    print("PASS: split_eligibility_text correctly handles standard inclusion/exclusion trial")

    t_no_exc = trials_by_id["NCT06094491"]
    sec_no_exc = split_eligibility_text(t_no_exc["eligibility_text"])
    assert len(sec_no_exc["inclusion"]) > 0
    assert sec_no_exc["exclusion"] == ""
    print("PASS: split_eligibility_text gracefully handles trial without exclusion criteria")

    # 4. Test retrieve_evidence with mock LLM function
    mock_llm_response = json.dumps({
        "hba1c": [{"section": "inclusion", "text": "Individuals with HbA1c ≤ 9.9%"}],
        "current_diabetes_medications": [],
        "egfr": [{"section": "exclusion", "text": "estimated glomerular filtration rate < 30 mL/min/1.73 m²"}],
        "other_requirements": [{"section": "inclusion", "text": "Informed consent required"}]
    })

    result = retrieve_evidence(pev, t_normal, llm_fn=lambda prompt: mock_llm_response)
    assert result["patient_evidence"]["hba1c"]["current"]["value"] == 7.0
    assert result["trial_evidence"]["nct_id"] == "NCT07719894"
    assert result["trial_evidence"]["hba1c"][0]["text"] == "Individuals with HbA1c ≤ 9.9%"
    assert result["trial_evidence"]["egfr"][0]["text"] == "estimated glomerular filtration rate < 30 mL/min/1.73 m²"
    print("PASS: retrieve_evidence correctly formats patient and trial evidence structure")

    print("\nAll retrieve_evidence unit tests passed.")

if __name__ == "__main__":
    test_harness()
