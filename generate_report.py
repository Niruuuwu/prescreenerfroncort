"""
generate_report.py — Node 4: Ranking and report generation.

Explicit design decision:
    A trial with ANY NOT_SUPPORTED criterion never appears in the primary top-3.
    The clean pool is: trials where NOT_SUPPORTED count == 0.
    If the clean pool has 1 or 2 trials → return 1 or 2 (no padding).
    If the clean pool is empty → fall back to full list ranked by
    (fewest NOT_SUPPORTED, fewest UNKNOWN, fewest RCR, RECRUITING first),
    return top 3, every entry flagged is_fallback=True and human_review_required=True.

human_review_required is True for three independent reasons:
    1. Any criterion state is REQUIRES_CLINICAL_REVIEW
    2. Any criterion state is CONFLICTING_EVIDENCE
    3. Trial is in the fallback pool (NOT_SUPPORTED count >= 1)
    evaluate_criteria already sets it for reasons 1 and 2.
    This node additionally sets it for reason 3.
"""

from __future__ import annotations


# ── State counting helpers ─────────────────────────────────────────────────────

def _count(criterion_results: dict, state: str) -> int:
    return sum(1 for v in criterion_results.values() if v.get("state") == state)


def _is_recruiting(trial: dict) -> bool:
    return trial.get("overall_status") == "RECRUITING"


def _rank_key_clean(entry: dict) -> tuple:
    """Rank key for the clean pool (zero NOT_SUPPORTED trials)."""
    cr = entry["criterion_results"]
    return (
        _count(cr, "UNKNOWN"),
        _count(cr, "REQUIRES_CLINICAL_REVIEW"),
        0 if _is_recruiting(entry["trial"]) else 1,
    )


def _rank_key_fallback(entry: dict) -> tuple:
    """Rank key for the fallback pool (all trials have ≥1 NOT_SUPPORTED)."""
    cr = entry["criterion_results"]
    return (
        _count(cr, "NOT_SUPPORTED"),
        _count(cr, "UNKNOWN"),
        _count(cr, "REQUIRES_CLINICAL_REVIEW"),
        0 if _is_recruiting(entry["trial"]) else 1,
    )


# ── Summary builder ────────────────────────────────────────────────────────────

def _plain_language_summary(
    trial: dict,
    criterion_results: dict,
    is_fallback: bool,
) -> str:
    """
    Generate a brief coordinator-facing summary of this trial's fit.
    No LLM — deterministic template from criterion states.
    """
    nct_id = trial.get("nct_id", "")
    status = trial.get("overall_status", "")

    supported    = [k for k, v in criterion_results.items() if v["state"] == "SUPPORTED"]
    not_supp     = [k for k, v in criterion_results.items() if v["state"] == "NOT_SUPPORTED"]
    unknown      = [k for k, v in criterion_results.items() if v["state"] == "UNKNOWN"]
    conflicting  = [k for k, v in criterion_results.items() if v["state"] == "CONFLICTING_EVIDENCE"]
    rcr          = [k for k, v in criterion_results.items() if v["state"] == "REQUIRES_CLINICAL_REVIEW"]

    parts = []

    if is_fallback:
        parts.append(
            f"FALLBACK CANDIDATE — shown because no trials are fully clear of "
            f"NOT_SUPPORTED criteria. Human review required before any referral."
        )
    else:
        parts.append("Candidate trial for coordinator review.")

    if supported:
        parts.append(f"Criteria met: {', '.join(supported)}.")
    if not_supp:
        parts.append(f"Criteria NOT met: {', '.join(not_supp)}.")
    if conflicting:
        parts.append(f"Conflicting evidence on: {', '.join(conflicting)} — coordinator must resolve.")
    if unknown:
        parts.append(f"Cannot evaluate (data absent): {', '.join(unknown)}.")
    if rcr:
        parts.append(f"Requires clinical review: {', '.join(rcr)}.")

    if status != "RECRUITING":
        parts.append(
            f"Note: trial is {status}, not currently RECRUITING. "
            "Check with the study team before referring."
        )

    return " ".join(parts)


# ── Report entry builder ───────────────────────────────────────────────────────

def _build_entry(entry: dict, is_fallback: bool) -> dict:
    trial            = entry["trial"]
    criterion_results = entry["criterion_results"]

    # human_review_required: OR of evaluate_criteria flag + fallback override
    human_review = entry.get("human_review_required", False) or is_fallback
    selection_tier = "fallback" if is_fallback else "clean"

    return {
        "nct_id":         trial.get("nct_id", ""),
        "brief_title":    trial.get("brief_title", trial.get("title", "")),
        "overall_status": trial.get("overall_status", ""),
        "criterion_results": criterion_results,
        "human_review_required": human_review,
        "selection_tier": selection_tier,
        "is_fallback":    is_fallback,
        "not_supported_criteria": [
            k for k, v in criterion_results.items()
            if v.get("state") == "NOT_SUPPORTED"
        ],
        "summary": _plain_language_summary(trial, criterion_results, is_fallback),
    }


def compute_evidence_leverage_summary(evaluated_trials: list[dict]) -> list[dict]:
    """
    Scans ALL candidate trials (the full set that passed filter_structured) for
    criterion_results with state == "UNKNOWN".

    Identifies the underlying missing fact for each UNKNOWN, groups by missing fact,
    and returns top 1-2 missing facts where affected_trial_count >= 2.
    """
    if not evaluated_trials:
        return []

    missing_fact_trials: dict[str, set[str]] = {}

    for entry in evaluated_trials:
        trial = entry["trial"]
        nct_id = trial.get("nct_id", "")
        criterion_results = entry.get("criterion_results", {})

        for crit_name, crit_data in criterion_results.items():
            if crit_data.get("state") == "UNKNOWN":
                explanation = crit_data.get("explanation", "").lower()

                if "egfr" in crit_name or "egfr" in explanation:
                    fact_label = "eGFR reading"
                elif "hba1c" in crit_name or "hba1c" in explanation:
                    fact_label = "HbA1c reading"
                elif "medication" in crit_name or "medication" in explanation:
                    fact_label = "medication data"
                else:
                    fact_label = f"{crit_name} data"

                if fact_label not in missing_fact_trials:
                    missing_fact_trials[fact_label] = set()
                missing_fact_trials[fact_label].add(nct_id)

    # Sort descending by count
    sorted_facts = sorted(
        missing_fact_trials.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )

    total_candidates = len(evaluated_trials)
    summary_items = []

    for fact_label, affected_ids in sorted_facts:
        count = len(affected_ids)
        if count < 2:
            continue

        id_list = sorted(list(affected_ids))
        if len(summary_items) == 0:
            message = (
                f"Obtaining a current {fact_label} would resolve uncertainty on {count} of "
                f"{total_candidates} candidate trials — more than any other single missing data point."
            )
        else:
            message = (
                f"Obtaining {fact_label} would resolve uncertainty on {count} of "
                f"{total_candidates} candidate trials."
            )

        summary_items.append({
            "missing_fact": fact_label,
            "affected_trial_count": count,
            "affected_trial_ids": id_list,
            "message": message,
        })

        if len(summary_items) >= 2:
            break

    return summary_items


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_report(evaluated_trials: list[dict]) -> list[dict]:
    """
    Ranks evaluated trials and returns the top-3 report entries.

    Args:
        evaluated_trials: list of dicts, each containing:
            - "trial":              candidate trial dict (nct_id, brief_title, overall_status, ...)
            - "criterion_results":  output from evaluate_criteria()["criterion_results"]
            - "human_review_required": bool from evaluate_criteria() (reasons 1 & 2)

    Returns:
        List of 0–3 report entry dicts. Never pads with NOT_SUPPORTED trials
        if fewer than 3 clean-pool trials exist — returns fewer than 3 in that case.
        Falls back to top 3 from full list (all flagged) only when clean pool is empty.
    """
    if not evaluated_trials:
        return []

    # Partition into clean pool (zero NOT_SUPPORTED) and the rest
    clean    = [e for e in evaluated_trials if _count(e["criterion_results"], "NOT_SUPPORTED") == 0]
    is_fallback = len(clean) == 0

    if not is_fallback:
        ranked   = sorted(clean, key=_rank_key_clean)
        selected = ranked[:3]
    else:
        ranked   = sorted(evaluated_trials, key=_rank_key_fallback)
        selected = ranked[:3]

    return [_build_entry(e, is_fallback) for e in selected]
