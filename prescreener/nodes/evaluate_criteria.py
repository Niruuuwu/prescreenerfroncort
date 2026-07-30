"""
evaluate_criteria.py — Node 3: Criterion evaluation.

Assigns one of exactly five spec-mandated states per criterion:
    SUPPORTED, NOT_SUPPORTED, UNKNOWN, CONFLICTING_EVIDENCE, REQUIRES_CLINICAL_REVIEW

Rules (all verified against the real dataset):
- No trial threshold extracted from text → UNKNOWN  (not SUPPORTED)
- No patient reading → UNKNOWN, checking missing_expected_domains first
- No medication mention in trial text → UNKNOWN  (absence is not permission)
- age and trial_recruiting_status come pre-computed from _prefilter_criteria → carry forward unchanged
- other_requirements → REQUIRES_CLINICAL_REVIEW, verbatim citations preserved
- Every state cites the source_id(s) and/or verbatim text span it used

human_review_required is set True by this node for:
  - any REQUIRES_CLINICAL_REVIEW state
  - any CONFLICTING_EVIDENCE state
(generate_report additionally sets it True for fallback-tier entries)
"""

from __future__ import annotations

import re

# ── Five spec-mandated states ──────────────────────────────────────────────────

_VALID_STATES = frozenset({
    "SUPPORTED",
    "NOT_SUPPORTED",
    "UNKNOWN",
    "CONFLICTING_EVIDENCE",
    "REQUIRES_CLINICAL_REVIEW",
})

# ── Medication alias groups ────────────────────────────────────────────────────
# Each key is a drug class. Each value is a list of substrings that identify
# that class in either a patient medication name or a trial eligibility snippet.

_MED_ALIASES: dict[str, list[str]] = {
    "glp1": [
        "glp-1", "glp1", "glucagon-like peptide", "glucagon like peptide",
        "semaglutide", "liraglutide", "dulaglutide", "exenatide",
        "tirzepatide", "albiglutide",
        "ozempic", "wegovy", "victoza", "trulicity", "byetta", "mounjaro",
    ],
    "sglt2": [
        "sglt2", "sglt-2", "sodium-glucose cotransporter",
        "empagliflozin", "dapagliflozin", "canagliflozin", "ertugliflozin",
        "jardiance", "farxiga", "invokana", "steglatro",
    ],
    "dpp4": [
        "dpp-4", "dpp4", "dipeptidyl peptidase",
        "sitagliptin", "saxagliptin", "linagliptin", "alogliptin", "vildagliptin",
        "januvia", "onglyza", "tradjenta", "nesina",
    ],
    "insulin": [
        "insulin", "basal insulin", "bolus insulin",
        "glargine", "detemir", "degludec", "lispro", "aspart", "glulisine",
        "lantus", "toujeo", "levemir", "tresiba", "novolog", "humalog",
    ],
    "metformin": [
        "metformin", "glucophage", "glumetza", "fortamet",
    ],
    "sulfonylurea": [
        "sulfonylurea", "sulphonylurea",
        "glipizide", "glyburide", "glibenclamide", "glimepiride",
        "gliclazide", "tolbutamide",
        "glucotrol", "diabeta", "micronase", "amaryl",
    ],
    "thiazolidinedione": [
        "thiazolidinedione", "tzd", "glitazone",
        "pioglitazone", "rosiglitazone",
        "actos", "avandia",
    ],
    "meglitinide": [
        "meglitinide", "repaglinide", "nateglinide",
        "prandin", "starlix",
    ],
}


# ── Result builder ─────────────────────────────────────────────────────────────

def _result(state: str, explanation: str, citations: list) -> dict:
    assert state in _VALID_STATES, f"Invalid state emitted: {state!r}"
    return {"state": state, "explanation": explanation, "citations": citations}


def _unknown(reason: str) -> dict:
    return _result("UNKNOWN", reason, [])


def _rcr(reason: str, citations: list) -> dict:
    return _result("REQUIRES_CLINICAL_REVIEW", reason, citations)


def _supported(explanation: str, citations: list) -> dict:
    return _result("SUPPORTED", explanation, citations)


def _not_supported(explanation: str, citations: list) -> dict:
    return _result("NOT_SUPPORTED", explanation, citations)


def _conflicting(explanation: str, citations: list) -> dict:
    return _result("CONFLICTING_EVIDENCE", explanation, citations)


# ── Threshold parsing ──────────────────────────────────────────────────────────

def _normalize_operators(text: str) -> str:
    """Normalize ASCII comparison operators to Unicode equivalents."""
    return text.replace(">=", "≥").replace("<=", "≤")


def _extract_percent_thresholds(text: str) -> list[tuple[str, float]] | None:
    """
    Parse operator+value pairs from a percentage-based threshold string.

    Returns:
        [(op, value), ...]  — list of (operator, float) pairs if % threshold found
        None  — pure mmol/mol units detected without % threshold; caller emits REQUIRES_CLINICAL_REVIEW
        []    — no numeric thresholds found
    """
    normalized = _normalize_operators(text)

    # 1. Try explicit comparison operator matches (e.g. ≤ 9.9%, > 8.0)
    matches = re.findall(r"([≤≥<>])\s*(\d+\.?\d*)\s*%?", normalized)
    if matches:
        return [(op, float(val)) for op, val in matches]

    # 2. Try "between X and Y" range pattern (e.g. between 6.5 % and 9.0%)
    m_between = re.search(
        r"between\s+(\d+\.?\d*)\s*%?\s*(?:and|to)\s*(\d+\.?\d*)\s*%",
        text, re.IGNORECASE,
    )
    if m_between:
        return [("≥", float(m_between.group(1))), ("≤", float(m_between.group(2)))]

    # 3. Try "X% to Y%" or "X to Y%" range pattern (e.g. 6.5% to 9.0%)
    m_range = re.search(
        r"(\d+\.?\d*)\s*%?\s*(?:to|-|–)\s*(\d+\.?\d*)\s*%",
        text, re.IGNORECASE,
    )
    if m_range:
        return [("≥", float(m_range.group(1))), ("≤", float(m_range.group(2)))]

    # 4. If no % threshold could be extracted AND mmol/mol is present without %, emit RCR
    if "mmol/mol" in text.lower():
        return None

    return []


def _extract_numeric_thresholds(text: str) -> list[tuple[str, float]]:
    """Parse operator+value pairs for plain-numeric thresholds (e.g. eGFR)."""
    text = _normalize_operators(text)
    matches = re.findall(r"([≤≥<>])\s*(\d+\.?\d*)", text)
    return [(op, float(val)) for op, val in matches]


def _passes_inclusion(value: float, thresholds: list[tuple[str, float]]) -> bool:
    """True if patient value satisfies ALL inclusion threshold conditions."""
    for op, threshold in thresholds:
        if op == "≥" and value < threshold:
            return False
        if op == ">" and value <= threshold:
            return False
        if op == "≤" and value > threshold:
            return False
        if op == "<" and value >= threshold:
            return False
    return True


def _triggers_exclusion(value: float, thresholds: list[tuple[str, float]]) -> bool:
    """True if patient value satisfies the exclusion condition (i.e. patient IS excluded)."""
    for op, threshold in thresholds:
        if op == "<" and value < threshold:
            return True
        if op == "≤" and value <= threshold:
            return True
        if op == ">" and value > threshold:
            return True
        if op == "≥" and value >= threshold:
            return True
    return False


# ── Medication helpers ─────────────────────────────────────────────────────────

def _drug_groups(text: str) -> set[str]:
    """Return set of drug class keys whose aliases appear in text (case-insensitive)."""
    t = text.lower()
    return {
        group for group, aliases in _MED_ALIASES.items()
        if any(alias in t for alias in aliases)
    }


# ── Individual criterion evaluators ───────────────────────────────────────────

def _carry_forward(prefilter_entry: dict) -> dict:
    """Carry age / trial_recruiting_status forward from _prefilter_criteria unchanged."""
    return {
        "state":       prefilter_entry.get("state", "UNKNOWN"),
        "explanation": prefilter_entry.get("explanation", ""),
        "citations":   [],   # pre-filter criteria reference the trial record, not a patient source_id
    }


def _eval_hba1c(patient_evidence: dict, trial_evidence: dict) -> dict:
    spans = trial_evidence.get("hba1c", [])

    if not spans:
        return _unknown("No HbA1c threshold found in trial eligibility text.")

    current = patient_evidence.get("hba1c", {}).get("current")
    if current is None:
        return _unknown("No HbA1c reading available in patient record.")

    value      = current["value"]
    source_id  = current["source_id"]
    date_str   = current["effective_date"]
    historical = patient_evidence.get("hba1c", {}).get("historical", [])

    hist_note = ""
    if historical:
        older = ", ".join(
            f"{h['value']}% ({h['effective_date']}) [{h['source_id']}]"
            for h in historical
        )
        hist_note = f" Older readings not used (most-recent-wins rule): {older}."

    inclusion_spans = [s for s in spans if s.get("section") == "inclusion"]
    exclusion_spans = [s for s in spans if s.get("section") == "exclusion"]

    # Evaluate against inclusion spans first
    for span in inclusion_spans:
        text = span["text"]
        thresholds = _extract_percent_thresholds(text)

        if thresholds is None:
            return _rcr(
                "HbA1c threshold uses mmol/mol units; unit conversion required before evaluation.",
                [text],
            )
        if not thresholds:
            return _rcr(
                f"Could not parse numeric HbA1c threshold from: '{text}'",
                [text],
            )

        if _passes_inclusion(value, thresholds):
            return _supported(
                f"Patient HbA1c {value}% ({date_str}) satisfies inclusion criterion: '{text}'.{hist_note}",
                [source_id, text],
            )
        else:
            return _not_supported(
                f"Patient HbA1c {value}% ({date_str}) does not satisfy inclusion criterion: '{text}'.{hist_note}",
                [source_id, text],
            )

    # Only exclusion spans
    for span in exclusion_spans:
        text = span["text"]
        thresholds = _extract_percent_thresholds(text)

        if thresholds is None:
            return _rcr("HbA1c threshold uses mmol/mol units.", [text])
        if not thresholds:
            return _rcr(f"Could not parse HbA1c threshold from: '{text}'", [text])

        if _triggers_exclusion(value, thresholds):
            return _not_supported(
                f"Patient HbA1c {value}% ({date_str}) triggers exclusion: '{text}'.",
                [source_id, text],
            )

    return _supported(
        f"Patient HbA1c {value}% ({date_str}) does not trigger any HbA1c exclusion criterion.",
        [source_id] + [s["text"] for s in exclusion_spans],
    )


def _eval_egfr(patient_evidence: dict, trial_evidence: dict) -> dict:
    # Step 1: missing domain takes absolute priority — stop here
    if "egfr" in patient_evidence.get("missing_domains", []):
        return _unknown(
            "eGFR not present in patient record "
            "(listed in record_quality.missing_expected_domains). "
            "Absence is not a pass or fail."
        )

    spans = trial_evidence.get("egfr", [])
    if not spans:
        return _unknown("No eGFR threshold found in trial eligibility text.")

    current = patient_evidence.get("egfr", {}).get("current")
    if current is None:
        return _unknown("No eGFR reading available in patient record.")

    value     = current["value"]
    source_id = current["source_id"]
    unit      = current.get("unit", "mL/min/1.73m²")
    date_str  = current["effective_date"]

    inclusion_spans = [s for s in spans if s.get("section") == "inclusion"]
    exclusion_spans = [s for s in spans if s.get("section") == "exclusion"]

    for span in inclusion_spans:
        text = span["text"]
        thresholds = _extract_numeric_thresholds(text)
        if not thresholds:
            return _rcr(f"Could not parse eGFR threshold from: '{text}'", [text])

        if not _passes_inclusion(value, thresholds):
            return _not_supported(
                f"Patient eGFR {value} {unit} ({date_str}) does not satisfy inclusion: '{text}'.",
                [source_id, text],
            )

    for span in exclusion_spans:
        text = span["text"]
        thresholds = _extract_numeric_thresholds(text)
        if not thresholds:
            return _rcr(f"Could not parse eGFR threshold from: '{text}'", [text])

        if _triggers_exclusion(value, thresholds):
            return _not_supported(
                f"Patient eGFR {value} {unit} ({date_str}) triggers exclusion: '{text}'.",
                [source_id, text],
            )

    all_texts = [s["text"] for s in inclusion_spans + exclusion_spans]
    return _supported(
        f"Patient eGFR {value} {unit} ({date_str}) satisfies all eGFR criteria.",
        [source_id] + all_texts,
    )


def _eval_medications(patient_evidence: dict, trial_evidence: dict) -> dict:
    spans = trial_evidence.get("current_diabetes_medications", [])

    if not spans:
        return _unknown(
            "No diabetes medication rule found in trial eligibility text. "
            "Absence of a rule is not permission to proceed."
        )

    active_meds = patient_evidence.get("active_medications", [])
    inclusion_spans = [s for s in spans if s.get("section") == "inclusion"]
    exclusion_spans = [s for s in spans if s.get("section") == "exclusion"]

    triggered_exclusions: list[tuple[str, str, str]] = []  # (source_id, span_text, med_name)
    unmet_inclusions:     list[str] = []                    # span_text

    for span in exclusion_spans:
        text        = span["text"]
        span_groups = _drug_groups(text)
        if not span_groups:
            continue   # unresolvable drug class — will surface in other_requirements

        for med in active_meds:
            if _drug_groups(med["name"]) & span_groups:
                triggered_exclusions.append((med["source_id"], text, med["name"]))

    for span in inclusion_spans:
        text        = span["text"]
        span_groups = _drug_groups(text)
        if not span_groups:
            continue

        patient_satisfies = any(
            bool(_drug_groups(m["name"]) & span_groups) for m in active_meds
        )
        if not patient_satisfies:
            unmet_inclusions.append(text)

    # CONFLICTING_EVIDENCE: a drug group is simultaneously required and excluded
    if triggered_exclusions and unmet_inclusions:
        excl_groups = set().union(*[_drug_groups(e[1]) for e in triggered_exclusions])
        req_groups  = set().union(*[_drug_groups(r) for r in unmet_inclusions])
        if excl_groups & req_groups:
            citations = (
                [e[0] for e in triggered_exclusions] +
                [e[1] for e in triggered_exclusions] +
                unmet_inclusions
            )
            return _conflicting(
                "A medication class is both required by an inclusion criterion and prohibited by an exclusion criterion.",
                citations,
            )

    if triggered_exclusions:
        citations = []
        details   = []
        for src, text, name in triggered_exclusions:
            citations.extend([src, text])
            details.append(f"'{name}' matches exclusion: '{text}'")
        return _not_supported(
            "Active medication(s) trigger a trial exclusion criterion. " + "; ".join(details) + ".",
            citations,
        )

    if unmet_inclusions:
        return _not_supported(
            f"Patient does not have an active medication required by an inclusion criterion: {unmet_inclusions}.",
            unmet_inclusions,
        )

    all_texts   = [s["text"] for s in spans]
    med_src_ids = [m["source_id"] for m in active_meds]
    return _supported(
        "Patient's active medications satisfy all trial medication criteria.",
        med_src_ids + all_texts,
    )


def _eval_other_requirements(other_reqs: list[dict]) -> dict:
    verbatim = [item["text"] for item in other_reqs if "text" in item]
    return _rcr(
        f"{len(verbatim)} other requirement(s) present; preserved verbatim for human review.",
        verbatim,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def evaluate_criteria(patient_evidence: dict, trial_evidence: dict) -> dict:
    """
    Assigns one of five spec-mandated states per criterion.

    Args:
        patient_evidence: output of build_patient_evidence()
        trial_evidence:   output of retrieve_evidence()["trial_evidence"],
                          must include _prefilter_criteria (copied by retrieve_evidence)

    Returns:
        {
            "criterion_results":     {<criterion>: {"state", "explanation", "citations"}},
            "human_review_required": bool   (True if RCR or CONFLICTING_EVIDENCE present)
        }
    """
    prefilter = trial_evidence.get("_prefilter_criteria", {})

    results: dict[str, dict] = {}

    # 1 & 2: Pre-computed by filter_structured — carry forward unchanged
    results["age"]                     = _carry_forward(prefilter.get("age", {}))
    results["trial_recruiting_status"] = _carry_forward(prefilter.get("trial_recruiting_status", {}))

    # 3: HbA1c
    results["hba1c"] = _eval_hba1c(patient_evidence, trial_evidence)

    # 4: eGFR
    results["egfr"] = _eval_egfr(patient_evidence, trial_evidence)

    # 5: Current diabetes medications
    results["current_diabetes_medications"] = _eval_medications(patient_evidence, trial_evidence)

    # 6: Other requirements
    other_reqs = trial_evidence.get("other_requirements", [])
    if other_reqs:
        results["other_requirements"] = _eval_other_requirements(other_reqs)

    # human_review_required: triggered by RCR or CONFLICTING_EVIDENCE
    # (generate_report additionally sets True for fallback-tier entries)
    states = {v["state"] for v in results.values()}
    human_review_required = bool(states & {"REQUIRES_CLINICAL_REVIEW", "CONFLICTING_EVIDENCE"})

    return {
        "criterion_results":     results,
        "human_review_required": human_review_required,
    }
