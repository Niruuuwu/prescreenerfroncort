import json

with open("data/Type2-Diabetes-Trial-Agent-Dataset.json", encoding="utf-8") as f:
    data = json.load(f)

print("=== eGFR coverage per patient ===")
for p in data["patients"]:
    pid = p["patient_id"]
    obs_types = [o["type"] for o in p.get("observations", [])]
    missing = p.get("record_quality", {}).get("missing_expected_domains", [])
    has_egfr_obs = "egfr" in obs_types
    egfr_in_missing = "egfr" in missing
    egfr_obs = [o for o in p.get("observations", []) if o["type"] == "egfr"]
    print(f"  {pid}: has_egfr_obs={has_egfr_obs}, egfr_in_missing_domains={egfr_in_missing}, obs_count={len(egfr_obs)}")

print()
print("=== HbA1c coverage per patient ===")
for p in data["patients"]:
    pid = p["patient_id"]
    hba1c_obs = [o for o in p.get("observations", []) if o["type"] == "hba1c"]
    missing = p.get("record_quality", {}).get("missing_expected_domains", [])
    print(f"  {pid}: hba1c_count={len(hba1c_obs)}, hba1c_in_missing={'hba1c' in missing}")

print()
print("=== Medication coverage per patient ===")
for p in data["patients"]:
    pid = p["patient_id"]
    meds = p.get("medications", [])
    active = [m for m in meds if m.get("status") == "active"]
    missing = p.get("record_quality", {}).get("missing_expected_domains", [])
    print(f"  {pid}: total_meds={len(meds)}, active={len(active)}, medications_in_missing={'medications' in missing}")
