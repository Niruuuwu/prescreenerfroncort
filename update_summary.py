import json

def update_summary():
    with open('output_all_patients.json', encoding='utf-8') as f:
        data = json.load(f)

    with open('data/Type2-Diabetes-Trial-Agent-Dataset.json', encoding='utf-8') as f:
        ds = json.load(f)

    patients = ds['patients']
    p_map = {p['patient_id']: p for p in patients}

    md = '# Batch Pre-Screening Summary Report (All 15 Synthetic Patients)\n\n'
    md += '- **Total Patients Processed**: 15\n'
    md += '- **Dataset**: `Type2-Diabetes-Trial-Agent-Dataset.json`\n'
    md += '- **LLM Engine**: Mistral AI (`mistral-small-latest`)\n\n'
    md += '## Patient Pre-Screening Summary Table\n\n'
    md += '| Patient ID | Age | Missing Domains | Candidates (Stage 1) | Top Recommended Trials (Stage 4) | Selection Tier | Human Review Required |\n'
    md += '|---|---|---|---|---|---|---|\n'

    for pid, res in data.items():
        p = p_map[pid]
        age = p.get("demographics", {}).get("age_at_reference_date", "N/A")
        missing_domains = p.get("record_quality", {}).get("missing_expected_domains", [])
        missing_str = ", ".join(missing_domains) if missing_domains else "None"
        cand_count = res.get("candidate_trials_count", 0)
        report = res.get("report", [])
        top_trials = ", ".join([r["nct_id"] for r in report])
        top_tiers = ", ".join(set([r.get("selection_tier", "clean") for r in report]))
        hrr = res.get("human_review_required", False)
        md += f"| `{pid}` | {age} | {missing_str} | {cand_count} | `{top_trials}` | `{top_tiers}` | `{hrr}` |\n"

    with open('summary_all_patients.md', 'w', encoding='utf-8') as f:
        f.write(md)

    print('Updated summary_all_patients.md successfully!')

if __name__ == "__main__":
    update_summary()
