import json
from filter_structured import filter_structured

with open("data/Type2-Diabetes-Trial-Agent-Dataset.json", encoding="utf-8") as f:
    data = json.load(f)

patients_by_id = {p["patient_id"]: p for p in data["patients"]}

# --- Hand-checkable case 1 ---
patient = patients_by_id["P-1842"]
candidates = filter_structured(patient, data["trials"])
candidate_ids = {t["nct_id"] for t in candidates}
assert "NCT07702097" not in candidate_ids, "Age 60 should be hard-excluded by [30,50] window"
print("PASS: age 60 patient correctly excluded from NCT07702097 (window 30-50)")

# --- Hand-checkable case 2 ---
assert "NCT07719894" in candidate_ids, "Null max age should be an open boundary, not exclusion"
nct_trial = next(t for t in candidates if t["nct_id"] == "NCT07719894")
assert nct_trial["_prefilter_criteria"]["age"]["state"] == "SUPPORTED"
print("PASS: age 60 patient correctly included for NCT07719894 (min 19, max open)")

# --- Hand-checkable case 3 ---
assert nct_trial["_prefilter_criteria"]["trial_recruiting_status"]["state"] == "SUPPORTED"
print("PASS: RECRUITING status correctly mapped to SUPPORTED")

# --- Hand-checkable case 4 ---
patient_2715 = patients_by_id["P-2715"]
assert patient_2715["demographics"]["age_at_reference_date"] == 42
candidates_2715 = filter_structured(patient_2715, data["trials"])
candidate_ids_2715 = {t["nct_id"] for t in candidates_2715}
assert "NCT07702097" in candidate_ids_2715, "NOT_YET_RECRUITING trial must still surface, not be excluded"
trial_2715 = next(t for t in candidates_2715 if t["nct_id"] == "NCT07702097")
assert trial_2715["_prefilter_criteria"]["trial_recruiting_status"]["state"] == "NOT_SUPPORTED"
print("PASS: NOT_YET_RECRUITING trial survives filtering (age-eligible patient) with status=NOT_SUPPORTED, not dropped")

# --- Sanity: overall shrinkage ---
print()
print("Candidate count per patient (of 36 total trials):")
for pid, p in patients_by_id.items():
    age = p["demographics"]["age_at_reference_date"]
    n = len(filter_structured(p, data["trials"]))
    print(f"  {pid} (age {age}): {n} candidates")

print()
print("All hand-checkable assertions passed.")
