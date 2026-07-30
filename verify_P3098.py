"""
verify_P3098.py — Spot-check the output_P3098.json against the four
hand-verification points documented in the user's request.

Run:
    python verify_P3098.py
or:
    python verify_P3098.py output_P3098.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Ensure UTF-8 output encoding for Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "  ..."

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"{PASS}  {label}")
        if detail:
            print(f"{INFO}  {detail}")
    else:
        print(f"{FAIL}  {label}")
        if detail:
            print(f"{INFO}  {detail}")
        failures.append(label)


# ── Load output ────────────────────────────────────────────────────────────────

output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output_P3098.json")
if not output_path.exists():
    print(f"Output file not found: {output_path}")
    sys.exit(1)

with open(output_path, encoding="utf-8") as f:
    result = json.load(f)

print(f"\n{'='*60}")
print(f"  Verifying: {output_path}")
print(f"  Patient:   {result.get('patient_id', '?')}")
print(f"{'='*60}\n")

# ── CHECK 1: candidate_trials_count == 30 ──────────────────────────────────────

count = result.get("candidate_trials_count", -1)
check(
    "CHECK 1 — candidate_trials_count == 30",
    count == 30,
    f"Got: {count}",
)

# ── CHECK 2: eGFR criterion is UNKNOWN on all report entries ──────────────────

report = result.get("report", [])
egfr_states: list[tuple[str, str]] = []
egfr_not_unknown: list[str] = []
missing_domain_in_explanation: list[str] = []

for entry in report:
    nct = entry.get("nct_id", "?")
    cr = entry.get("criterion_results", {})
    egfr_cr = cr.get("egfr", {})
    state = egfr_cr.get("state", "MISSING")
    explanation = egfr_cr.get("explanation", "")
    egfr_states.append((nct, state))
    if state != "UNKNOWN":
        egfr_not_unknown.append(f"{nct}: {state}")
    else:
        # Also check the explanation mentions missing_expected_domains
        if "missing_expected_domains" in explanation or "not present" in explanation:
            missing_domain_in_explanation.append(nct)

check(
    "CHECK 2a — eGFR is UNKNOWN on all report entries",
    len(egfr_not_unknown) == 0,
    "eGFR states: " + str(egfr_states) if egfr_not_unknown else
    "All report entries have eGFR=UNKNOWN",
)
if egfr_not_unknown:
    print(f"  Non-UNKNOWN eGFR entries: {egfr_not_unknown}")

check(
    "CHECK 2b — UNKNOWN explanation cites missing_expected_domains",
    len(missing_domain_in_explanation) == len(report) and len(report) > 0,
    f"Explanations citing missing domain: {missing_domain_in_explanation}",
)

# ── CHECK 3: selection_tier == 'clean' on top entries ─────────────────────────

tiers: list[tuple[str, str, int]] = []
for entry in report:
    nct = entry.get("nct_id", "?")
    tier = entry.get("selection_tier", "?")
    ns_count = len(entry.get("not_supported_criteria", []))
    tiers.append((nct, tier, ns_count))

all_clean = all(t[2] == 0 for t in tiers)

if all_clean:
    check(
        "CHECK 3 — selection_tier == 'clean' (no NOT_SUPPORTED on any top entry)",
        all(t[1] == "clean" for t in tiers),
        str([(nct, tier) for nct, tier, _ in tiers]),
    )
else:
    # Fallback is acceptable (but note it)
    check(
        "CHECK 3 — selection_tier correct given NOT_SUPPORTED counts",
        all(
            (t[2] == 0 and t[1] == "clean") or (t[2] > 0 and t[1] == "fallback")
            for t in tiers
        ),
        "Some entries have NOT_SUPPORTED -> fallback tier: " + str(tiers),
    )

# ── CHECK 4: Every criterion result has citations with real source_id strings ──

print()
print("CHECK 4 — Citations include actual source_id strings")

SOURCE_ID_PATTERN_PREFIXES = ("OBS-", "MED-", "COND-", "LAB-", "ONC-")

citation_issues: list[str] = []
citation_samples: list[str] = []

def _is_patient_source_id(c: str) -> bool:
    if not isinstance(c, str):
        return False
    if any(c.startswith(p) for p in SOURCE_ID_PATTERN_PREFIXES):
        return True
    # Match UUID format (36 chars with hyphens)
    if re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", c):
        return True
    return False

for entry in report:
    nct = entry.get("nct_id", "?")
    cr = entry.get("criterion_results", {})
    for crit_name, crit in cr.items():
        citations = crit.get("citations", [])
        state = crit.get("state", "?")

        # States that SHOULD have patient source_id citations (clinical criteria only, not age/status pre-filters)
        if crit_name in ("hba1c", "egfr", "current_diabetes_medications") and state in ("SUPPORTED", "NOT_SUPPORTED", "CONFLICTING_EVIDENCE"):
            patient_src_ids = [c for c in citations if _is_patient_source_id(c)]
            if not patient_src_ids:
                citation_issues.append(f"{nct}.{crit_name} [{state}]: no patient source_id in {citations}")
            else:
                citation_samples.append(f"  {nct}.{crit_name}: {patient_src_ids}")

if citation_samples:
    print(f"{PASS}  Patient source_ids found in citations:")
    for s in citation_samples[:8]:  # cap display
        print(s)
else:
    print(f"{INFO}  No SUPPORTED/NOT_SUPPORTED criteria in report (all UNKNOWN/RCR) — citations not required")

if citation_issues:
    for issue in citation_issues:
        print(f"{FAIL}  {issue}")
        failures.append(issue)

# ── CHECK 5: human_review_required flag set to True ──────────────────────────

print()
root_hrr = result.get("human_review_required")
report_hrrs = [entry.get("human_review_required") for entry in report]
all_hrr_true = root_hrr is True and all(h is True for h in report_hrrs)

check(
    "CHECK 5 — human_review_required is True at root and on all report entries",
    all_hrr_true,
    f"Root human_review_required={root_hrr}, Report entries={report_hrrs}",
)

# ── Summary ────────────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
if not failures:
    print(f"  All checks passed ({len(report)} report entries).")
else:
    print(f"  {len(failures)} check(s) failed:")
    for f in failures:
        print(f"    * {f}")
print(f"{'='*60}\n")

# ── Quick summary of report entries ───────────────────────────────────────────

print("Report entries:")
for entry in report:
    nct   = entry.get("nct_id", "?")
    tier  = entry.get("selection_tier", "?")
    status = entry.get("overall_status", "?")
    ns    = entry.get("not_supported_criteria", [])
    cr    = entry.get("criterion_results", {})
    states_summary = {k: v.get("state", "?") for k, v in cr.items()}
    print(f"  {nct} [{tier}] status={status} NOT_SUPPORTED={ns}")
    print(f"    criteria: {states_summary}")

sys.exit(len(failures))
