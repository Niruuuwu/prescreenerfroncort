import json

with open("data/Type2-Diabetes-Trial-Agent-Dataset.json", encoding="utf-8") as f:
    data = json.load(f)

patients_by_id = {p["patient_id"]: p for p in data["patients"]}
trials_by_id = {t["nct_id"]: t for t in data["trials"]}

p = patients_by_id["P-3098"]
print("=== P-3098 record_quality ===")
print(json.dumps(p["record_quality"], indent=2))
print()
print("=== P-3098 observations ===")
print(json.dumps(p["observations"], indent=2))
print()
print("=== P-3098 medications ===")
print(json.dumps(p["medications"], indent=2))
print()
print("=== P-3098 demographics ===")
print("age:", p["demographics"]["age_at_reference_date"])
print("as_of_date:", p["as_of_date"])

# Show a trial that has an eGFR criterion in its text
# Find trials mentioning eGFR
for t in data["trials"][:5]:
    txt = t.get("eligibility_text", "")
    if "eGFR" in txt or "glomerular" in txt.lower():
        print()
        print(f"=== Trial {t['nct_id']} eGFR mention ===")
        for line in txt.split("\n"):
            if "egfr" in line.lower() or "glomerular" in line.lower() or "renal" in line.lower():
                print(" ", line.strip())
        break
