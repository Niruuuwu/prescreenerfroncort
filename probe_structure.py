import json
with open("data/Type2-Diabetes-Trial-Agent-Dataset.json", encoding="utf-8") as f:
    data = json.load(f)

# Patient with medications
for p in data["patients"]:
    meds = p.get("medications", [])
    if meds:
        print("=== Patient", p["patient_id"], "medications ===")
        for m in meds:
            print(json.dumps(m, indent=2))
        print()
        break

# Sample eligibility text
t = next(t for t in data["trials"] if t["nct_id"] == "NCT07719894")
print("=== NCT07719894 eligibility_text (first 2000 chars) ===")
print(t["eligibility_text"][:2000])

# record_quality
p2 = data["patients"][2]
print()
print("=== record_quality sample ===")
print(json.dumps(p2.get("record_quality", {}), indent=2))

# How many patients have medications at all
with_meds = [p["patient_id"] for p in data["patients"] if p.get("medications")]
print()
print("Patients with medications:", with_meds)
