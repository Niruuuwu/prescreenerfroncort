"""
main.py — Beautiful CLI Entry Point for Type 2 Diabetes Trial Pre-Screening Agent.

Provides a clean, inspectable CLI for reviewers with the following flags:
  --patient <id>     Run full pipeline for one patient and print readable report.
  --list-patients    Print dataset patient IDs, age, active med count, & missing domains.
  --all              Run all 15 patients in sequence and print a 1-line summary per patient.
  --out <path>.json  Save full JSON report to specified file (used with --patient).
  --verbose          Enable per-stage LangGraph state logging.
  --no-cache         Bypass extraction cache to force fresh LLM calls without overwriting cache.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from prescreener.runner import prescreen_patient

# Enable ANSI escape sequences on Windows terminals
if sys.platform == "win32":
    os.system("")

# Ensure UTF-8 output formatting for terminal rendering (handles unicode symbols safely)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Check if stdout supports color
COLOR_ENABLED = sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"

if COLOR_ENABLED:
    CLR_RESET = "\033[0m"
    CLR_BOLD = "\033[1m"
    CLR_DIM = "\033[2m"
    CLR_CYAN = "\033[1;36m"
    CLR_GREEN = "\033[1;32m"
    CLR_RED = "\033[1;31m"
    CLR_YELLOW = "\033[1;33m"
    CLR_MAGENTA = "\033[1;35m"
    CLR_BLUE = "\033[1;34m"
    CLR_WHITE = "\033[1;37m"
else:
    CLR_RESET = ""
    CLR_BOLD = ""
    CLR_DIM = ""
    CLR_CYAN = ""
    CLR_GREEN = ""
    CLR_RED = ""
    CLR_YELLOW = ""
    CLR_MAGENTA = ""
    CLR_BLUE = ""
    CLR_WHITE = ""


DATASET_PATH = "data/Type2-Diabetes-Trial-Agent-Dataset.json"


def load_dataset(dataset_path: str = DATASET_PATH) -> dict[str, Any]:
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset file not found at '{dataset_path}'", file=sys.stderr)
        sys.exit(1)
    with open(dataset_path, encoding="utf-8") as f:
        return json.load(f)


def get_patient_summary_info(patient: dict) -> tuple[str, Any, int, list[str]]:
    pid = patient["patient_id"]
    demographics = patient.get("demographics", {})
    age = demographics.get("age_at_reference_date", "N/A")
    
    medications = patient.get("medications", [])
    active_meds_count = sum(1 for m in medications if m.get("status") == "active")
    
    missing_domains = patient.get("record_quality", {}).get("missing_expected_domains", [])
    return pid, age, active_meds_count, missing_domains


def list_patients(dataset: dict[str, Any]) -> None:
    patients = dataset.get("patients", [])
    header_str = f" PATIENTS IN DATASET ({len(patients)} Records Total) "
    print(f"\n{CLR_CYAN}╔{'═' * 78}╗{CLR_RESET}")
    print(f"{CLR_CYAN}║{CLR_WHITE}{CLR_BOLD}{header_str:^78s}{CLR_CYAN}║{CLR_RESET}")
    print(f"{CLR_CYAN}╠{'═' * 78}╣{CLR_RESET}")
    print(f"{CLR_CYAN}║{CLR_BOLD} {'Patient ID':<12s} │ {'Age':<6s} │ {'Active Meds':<13s} │ {'Missing EHR Domains':<38s}{CLR_RESET} {CLR_CYAN}║{CLR_RESET}")
    print(f"{CLR_CYAN}╠{'─' * 78}╣{CLR_RESET}")

    for p in patients:
        pid, age, active_meds_count, missing_domains = get_patient_summary_info(p)
        if missing_domains:
            missing_str = f"{CLR_YELLOW}{', '.join(missing_domains)}{CLR_RESET}"
            missing_raw = ", ".join(missing_domains)
        else:
            missing_str = f"{CLR_DIM}None (Complete Record){CLR_RESET}"
            missing_raw = "None (Complete Record)"
        
        pad_len = 38 - len(missing_raw)
        missing_display = missing_str + (" " * max(0, pad_len))

        print(f"{CLR_CYAN}║{CLR_RESET} {CLR_WHITE}{CLR_BOLD}{pid:<12s}{CLR_RESET} │ {str(age):>4s}   │ {active_meds_count:^13d} │ {missing_display} {CLR_CYAN}║{CLR_RESET}")

    print(f"{CLR_CYAN}╚{'═' * 78}╝{CLR_RESET}\n")


def format_state_badge(state: str) -> str:
    if state == "SUPPORTED":
        return f"{CLR_GREEN}✔ SUPPORTED              {CLR_RESET}"
    elif state == "NOT_SUPPORTED":
        return f"{CLR_RED}✘ NOT_SUPPORTED          {CLR_RESET}"
    elif state == "UNKNOWN":
        return f"{CLR_YELLOW}? UNKNOWN                {CLR_RESET}"
    elif state == "CONFLICTING_EVIDENCE":
        return f"{CLR_MAGENTA}⚡ CONFLICTING           {CLR_RESET}"
    elif state == "REQUIRES_CLINICAL_REVIEW":
        return f"{CLR_CYAN}📋 CLINICAL_REVIEW       {CLR_RESET}"
    return f"{CLR_DIM}{state:<25s}{CLR_RESET}"


def print_patient_report(res: dict[str, Any]) -> None:
    pid = res.get("patient_id", "")
    as_of = res.get("as_of_date", "")
    candidates_count = res.get("candidate_trials_count", 0)
    root_hrr = res.get("human_review_required", False)
    report = res.get("report", [])

    hrr_badge = f"{CLR_RED}{CLR_BOLD}YES (Clinical Review Mandatory){CLR_RESET}" if root_hrr else f"{CLR_GREEN}NO{CLR_RESET}"

    print(f"\n{CLR_CYAN}╔{'═' * 78}╗{CLR_RESET}")
    print(f"{CLR_CYAN}║{CLR_WHITE}{CLR_BOLD} PRE-SCREENING REPORT: PATIENT {pid:<10s} (As of Date: {as_of}) {CLR_CYAN}║{CLR_RESET}")
    print(f"{CLR_CYAN}╠{'═' * 78}╣{CLR_RESET}")
    print(f"{CLR_CYAN}║{CLR_RESET}  • Candidate Trials Evaluated (Stage 1 Filter) : {CLR_WHITE}{CLR_BOLD}{candidates_count}{CLR_RESET}")
    print(f"{CLR_CYAN}║{CLR_RESET}  • Human Clinical Review Required             : {hrr_badge}")
    print(f"{CLR_CYAN}╚{'═' * 78}╝{CLR_RESET}\n")

    leverage_summary = res.get("evidence_leverage_summary", [])
    if leverage_summary:
        print(f"{CLR_YELLOW}┌{'─' * 78}┐{CLR_RESET}")
        print(f"{CLR_YELLOW}│ 💡 {CLR_BOLD}HIGHEST-LEVERAGE CLINICAL ACTIONS (Data Gap Optimization){CLR_RESET}{CLR_YELLOW}{' ' * 20}│{CLR_RESET}")
        print(f"{CLR_YELLOW}├{'─' * 78}┤{CLR_RESET}")
        for item in leverage_summary:
            msg = item.get("message", "")
            print(f"{CLR_YELLOW}│{CLR_RESET}  {CLR_BOLD}•{CLR_RESET} {msg:<74s} {CLR_YELLOW}│{CLR_RESET}")
        print(f"{CLR_YELLOW}└{'─' * 78}┘{CLR_RESET}\n")

    if not report:
        print(f"{CLR_RED}No matching candidate trials found for this patient.{CLR_RESET}\n")
        return

    print(f"{CLR_WHITE}{CLR_BOLD}=== TOP RECOMMENDED CLINICAL TRIALS ({len(report)} SURFACED) ==={CLR_RESET}\n")

    for idx, entry in enumerate(report, 1):
        nct_id = entry.get("nct_id", "")
        title = entry.get("brief_title", "")
        status = entry.get("overall_status", "")
        tier = entry.get("selection_tier", "clean")
        is_fallback = entry.get("is_fallback", False)
        hrr = entry.get("human_review_required", False)
        summary = entry.get("summary", "")
        criterion_results = entry.get("criterion_results", {})

        if tier == "clean":
            tier_display = f"{CLR_GREEN}{CLR_BOLD}Tier 1 (Clean Match - Zero Disqualifiers){CLR_RESET}"
            border_color = CLR_GREEN
        else:
            tier_display = f"{CLR_YELLOW}{CLR_BOLD}Tier 2 (Fallback Match - Human Review Advised){CLR_RESET}"
            border_color = CLR_YELLOW

        rec_status_display = f"{CLR_GREEN}RECRUITING{CLR_RESET}" if status == "RECRUITING" else f"{CLR_YELLOW}{status}{CLR_RESET}"
        hrr_item_display = f"{CLR_RED}{CLR_BOLD}YES{CLR_RESET}" if hrr else f"{CLR_GREEN}NO{CLR_RESET}"

        print(f"{border_color}╭{'─' * 78}╮{CLR_RESET}")
        print(f"{border_color}│{CLR_RESET} {CLR_WHITE}{CLR_BOLD}MATCH #{idx}: {nct_id}{CLR_RESET}  [{tier_display}]")
        print(f"{border_color}├{'─' * 78}┤{CLR_RESET}")
        print(f"{border_color}│{CLR_RESET}  {CLR_BOLD}Title{CLR_RESET}             : {title}")
        print(f"{border_color}│{CLR_RESET}  {CLR_BOLD}Recruiting Status{CLR_RESET} : {rec_status_display}")
        print(f"{border_color}│{CLR_RESET}  {CLR_BOLD}Human Review Req{CLR_RESET}  : {hrr_item_display}")
        print(f"{border_color}│{CLR_RESET}  {CLR_BOLD}Surfaced Reason{CLR_RESET}   : {CLR_DIM}{summary}{CLR_RESET}")
        print(f"{border_color}├{'─' * 78}┤{CLR_RESET}")
        print(f"{border_color}│{CLR_RESET}  {CLR_BOLD}CRITERIA EVALUATION DETAILS:{CLR_RESET}")

        for crit_name, crit_data in criterion_results.items():
            state = crit_data.get("state", "UNKNOWN")
            explanation = crit_data.get("explanation", "")
            citations = crit_data.get("citations", [])
            badge = format_state_badge(state)

            cit_str = ""
            if citations:
                cit_str = f" {CLR_CYAN}[Citations: {', '.join(citations)}]{CLR_RESET}"

            print(f"{border_color}│{CLR_RESET}    • {CLR_BOLD}{crit_name:<28s}{CLR_RESET} : {badge} {explanation}{cit_str}")

        print(f"{border_color}╰{'─' * 78}╯{CLR_RESET}\n")


def run_single_patient(patient_id: str, dataset: dict[str, Any], args: argparse.Namespace) -> None:
    patients_map = {p["patient_id"]: p for p in dataset.get("patients", [])}
    if patient_id not in patients_map:
        print(f"\n{CLR_RED}Error: Patient ID '{patient_id}' not found in dataset.{CLR_RESET}\n", file=sys.stderr)
        print("Available patient IDs in dataset:", file=sys.stderr)
        list_patients(dataset)
        sys.exit(1)

    use_cache = not args.no_cache
    if args.no_cache:
        os.environ["PRESCREENER_NO_CACHE"] = "1"

    if not args.verbose:
        os.environ["PRESCREENER_QUIET_CACHE"] = "1"

    res = prescreen_patient(
        patient_id=patient_id,
        dataset_path=DATASET_PATH,
        dev_log=args.verbose,
        use_cache=use_cache,
    )

    print_patient_report(res)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
        print(f"{CLR_GREEN}✔ Full report JSON written to: {args.out}{CLR_RESET}\n")


def run_all_patients(dataset: dict[str, Any], args: argparse.Namespace) -> None:
    patients = dataset.get("patients", [])
    use_cache = not args.no_cache
    if args.no_cache:
        os.environ["PRESCREENER_NO_CACHE"] = "1"

    if not args.verbose:
        os.environ["PRESCREENER_QUIET_CACHE"] = "1"

    header_str = f" BATCH PRE-SCREENING: ALL {len(patients)} PATIENTS "
    print(f"\n{CLR_CYAN}╔{'═' * 78}╗{CLR_RESET}")
    print(f"{CLR_CYAN}║{CLR_WHITE}{CLR_BOLD}{header_str:^78s}{CLR_CYAN}║{CLR_RESET}")
    print(f"{CLR_CYAN}╠{'═' * 78}╣{CLR_RESET}")
    print(f"{CLR_CYAN}║{CLR_BOLD} {'Patient ID':<12s} │ {'Candidates':<10s} │ {'Top Matches':<12s} │ {'Has Fallback':<13s} │ {'Review Req'}{CLR_RESET} {CLR_CYAN}║{CLR_RESET}")
    print(f"{CLR_CYAN}╠{'─' * 78}╣{CLR_RESET}")

    for patient in patients:
        pid = patient["patient_id"]
        res = prescreen_patient(
            patient_id=pid,
            dataset_path=DATASET_PATH,
            dev_log=args.verbose,
            use_cache=use_cache,
        )
        cand_count = res.get("candidate_trials_count", 0)
        report = res.get("report", [])
        has_fallback = any(r.get("selection_tier") == "fallback" for r in report)
        root_hrr = res.get("human_review_required", False) or any(r.get("human_review_required", False) for r in report)

        fb_str = f"{CLR_YELLOW}Yes{CLR_RESET}" if has_fallback else f"{CLR_GREEN}No{CLR_RESET}"
        hrr_str = f"{CLR_RED}YES{CLR_RESET}" if root_hrr else f"{CLR_GREEN}NO{CLR_RESET}"

        fb_raw = "Yes" if has_fallback else "No"
        hrr_raw = "YES" if root_hrr else "NO"

        fb_pad = 13 - len(fb_raw)
        hrr_pad = 10 - len(hrr_raw)

        fb_disp = fb_str + (" " * max(0, fb_pad))
        hrr_disp = hrr_str + (" " * max(0, hrr_pad))

        print(f"{CLR_CYAN}║{CLR_RESET} {CLR_WHITE}{CLR_BOLD}{pid:<12s}{CLR_RESET} │ {cand_count:^10d} │ {len(report):^12d} │ {fb_disp} │ {hrr_disp} {CLR_CYAN}║{CLR_RESET}")

    print(f"{CLR_CYAN}╚{'═' * 78}╝{CLR_RESET}")
    print(f"\n{CLR_GREEN}✔ ALL {len(patients)} PATIENT PRE-SCREENING RUNS COMPLETE.{CLR_RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Type 2 Diabetes Clinical Trial Pre-Screening Agent CLI"
    )
    parser.add_argument(
        "--patient",
        type=str,
        help="Run full pipeline for one patient ID (e.g. P-3098).",
    )
    parser.add_argument(
        "--list-patients",
        action="store_true",
        help="List all patient IDs from the dataset with age, active med count, and missing domains.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all 15 patients through pipeline in sequence and print 1-line summary per patient.",
    )
    parser.add_argument(
        "--out",
        type=str,
        help="Path to write full report as JSON (used with --patient).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable per-stage LangGraph state logging.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass extraction cache to force fresh LLM calls without overwriting existing cache.",
    )

    args = parser.parse_args()

    if not (args.patient or args.list_patients or args.all):
        parser.print_help()
        sys.exit(0)

    dataset = load_dataset()

    if args.list_patients:
        list_patients(dataset)
        return

    if args.patient:
        run_single_patient(args.patient, dataset, args)
        return

    if args.all:
        run_all_patients(dataset, args)
        return


if __name__ == "__main__":
    main()
