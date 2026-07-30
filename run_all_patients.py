"""
run_all_patients.py — Batch Runner for All 15 Synthetic Patients.

Runs the complete 4-stage LangGraph pre-screening pipeline for all 15 patients
in the dataset, generates an all-patient summary report, and saves:
  1. output_all_patients.json (Detailed JSON results for all 15 patients)
  2. summary_all_patients.md  (Clean markdown summary table for review/interviews)
"""

from __future__ import annotations

import json
import os
import time
from prescreener import prescreen_patient


def run_batch_prescreening(
    dataset_path: str = "data/Type2-Diabetes-Trial-Agent-Dataset.json",
    output_json_path: str = "output_all_patients.json",
    output_summary_path: str = "summary_all_patients.md",
):
    with open(dataset_path, encoding="utf-8") as f:
        dataset = json.load(f)

    patients = dataset["patients"]
    print(f"================================================================================")
    print(f"BATCH PRE-SCREENING RUNNER — Processing {len(patients)} Patients")
    print(f"================================================================================\n")

    all_results = {}
    summary_rows = []

    start_time = time.time()

    for idx, patient in enumerate(patients, 1):
        pid = patient["patient_id"]
        demographics = patient.get("demographics", {})
        age = demographics.get("age_at_reference_date", "N/A")
        missing_domains = patient.get("record_quality", {}).get("missing_expected_domains", [])
        missing_str = ", ".join(missing_domains) if missing_domains else "None"

        print(f"[{idx}/{len(patients)}] Processing Patient {pid} (Age: {age}, Missing Domains: {missing_str})...", flush=True)

        res = prescreen_patient(pid, dataset_path=dataset_path, dev_log=False)
        all_results[pid] = res

        cand_count = res.get("candidate_trials_count", 0)
        report = res.get("report", [])
        top_trials = [r["nct_id"] for r in report]
        top_tiers = [r.get("selection_tier", "clean") for r in report]
        hrr = res.get("human_review_required", False)

        top_trials_str = ", ".join(top_trials) if top_trials else "None"
        tier_str = ", ".join(set(top_tiers)) if top_tiers else "N/A"

        summary_rows.append({
            "patient_id": pid,
            "age": age,
            "missing_domains": missing_str,
            "candidate_trials": cand_count,
            "recommended_trials_count": len(report),
            "top_trials": top_trials_str,
            "selection_tier": tier_str,
            "human_review_required": hrr,
        })

    elapsed = time.time() - start_time

    # Save full JSON output
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # Build markdown summary report
    md_content = f"""# Batch Pre-Screening Summary Report

- **Total Patients Processed**: {len(patients)}
- **Total Execution Time**: {elapsed:.1f} seconds
- **Dataset**: `Type2-Diabetes-Trial-Agent-Dataset.json`

## Patient Pre-Screening Summary Table

| Patient ID | Age | Missing Domains | Candidates (Stage 1) | Recommended Trials (Stage 4) | Selection Tier | Human Review Required |
|---|---|---|---|---|---|---|
"""
    for r in summary_rows:
        md_content += f"| `{r['patient_id']}` | {r['age']} | {r['missing_domains']} | {r['candidate_trials']} | `{r['top_trials']}` | `{r['selection_tier']}` | `{r['human_review_required']}` |\n"

    with open(output_summary_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n================================================================================")
    print(f"BATCH PROCESSING COMPLETE in {elapsed:.1f}s")
    print(f"Full JSON results saved to:    {output_json_path}")
    print(f"Markdown summary saved to:    {output_summary_path}")
    print("================================================================================\n")

    # Print summary table to console
    print(md_content)


if __name__ == "__main__":
    run_batch_prescreening()
