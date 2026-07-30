"""
helpers.py — Pure, deterministic helper functions shared across nodes.

None of these functions make LLM calls or network requests.
All date comparisons use ISO strings (YYYY-MM-DD) converted to datetime.date.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from prescreener.config import T2D_SNOMED_CODES


# ── Date handling ──────────────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    """Parse an ISO date string to a datetime.date."""
    return date.fromisoformat(s)


def get_as_of_date(patient_record: dict) -> str:
    """
    Return the as_of_date from the patient record.

    Raises ValueError if the field is missing.

    No silent fallback to wall-clock time is permitted — this is a frozen
    synthetic dataset (reference date 2026-07-01). Falling back to today would
    silently corrupt every age and observation comparison against the wrong
    reference point.
    """
    aod = patient_record.get("as_of_date")
    if aod is None:
        pid = patient_record.get("patient_id", "<unknown>")
        raise ValueError(
            f"Patient {pid!r} is missing 'as_of_date'. "
            "This field is required for all date comparisons. "
            "Falling back to wall-clock time would silently corrupt "
            "every age and observation comparison — aborting."
        )
    return aod


# ── Observation helpers ────────────────────────────────────────────────────────

def _obs_before_or_on(obs: dict, as_of_date: str) -> bool:
    """True if the observation's effective_date is ≤ as_of_date."""
    return _parse_date(obs["effective_date"]) <= _parse_date(as_of_date)


def get_latest_observation(
    observations: list[dict],
    obs_type: str,
    as_of_date: str,
) -> dict | None:
    """
    Return the single most-recent observation of obs_type with
    effective_date ≤ as_of_date, or None if no such observation exists.

    This implements the "most recent wins" rule (RESEARCH.md §3.1).
    The caller is responsible for citing the returned source_id and noting
    any earlier readings that were not used.
    """
    matching = [
        o for o in observations
        if o.get("type") == obs_type and _obs_before_or_on(o, as_of_date)
    ]
    if not matching:
        return None
    return max(matching, key=lambda o: _parse_date(o["effective_date"]))


def get_all_observations(
    observations: list[dict],
    obs_type: str,
    as_of_date: str,
) -> list[dict]:
    """
    Return all observations of obs_type with effective_date ≤ as_of_date,
    sorted by effective_date descending (most recent first).

    Used to populate the audit trail alongside the selected observation so that
    the explanation can name readings that were not used — keeping the
    most-recent-wins decision inspectable without triggering CONFLICTING_EVIDENCE.
    """
    matching = [
        o for o in observations
        if o.get("type") == obs_type and _obs_before_or_on(o, as_of_date)
    ]
    return sorted(matching, key=lambda o: _parse_date(o["effective_date"]), reverse=True)


# ── Medication helpers ─────────────────────────────────────────────────────────

def get_active_medications(
    medications: list[dict],
    as_of_date: str,
) -> list[dict]:
    """
    Return medications where status == 'active' as of as_of_date.

    A completed course (status != 'active') does not count as current, even if
    the drug name matches an eligibility criterion (RESEARCH.md §3.2).
    An entry with end_date < as_of_date is also treated as no longer active,
    regardless of the status field.
    """
    result = []
    aod = _parse_date(as_of_date)
    for med in medications:
        if med.get("status") != "active":
            continue
        end = med.get("end_date")
        if end is not None and _parse_date(end) < aod:
            continue
        result.append(med)
    return result


# ── Record quality helpers ─────────────────────────────────────────────────────

def check_missing_domains(patient_record: dict) -> list[str]:
    """
    Return the list of domains explicitly absent from the patient record.

    Values are copied verbatim from record_quality.missing_expected_domains —
    never inferred from the absence of observation entries. An empty
    observations list is NOT the same as a domain being declared missing.
    """
    return (
        patient_record
        .get("record_quality", {})
        .get("missing_expected_domains", [])
    )


def has_t2d_diagnosis(conditions: list[dict], as_of_date: str) -> dict | None:
    """
    Return the first condition record whose SNOMED code is a known T2D code
    and whose onset_date ≤ as_of_date, or None if none found.
    """
    for cond in conditions:
        code = str(cond.get("snomed_code", ""))
        onset = cond.get("onset_date")
        if code in T2D_SNOMED_CODES:
            if onset is None or _parse_date(onset) <= _parse_date(as_of_date):
                return cond
    return None


# ── Medication matching ────────────────────────────────────────────────────────

_STOPWORDS: frozenset[str] = frozenset({
    "use", "of", "current", "treatment", "with", "or", "and",
    "any", "the", "a", "an", "by", "for", "in", "on", "at",
    "receptor", "agonist",  # too generic on their own
})


def fuzzy_medication_match(med_name: str, span_text: str) -> bool:
    """
    Return True if med_name has meaningful token overlap with span_text.

    Uses token-set intersection after lowercasing and removing punctuation.
    Common stopwords are stripped so that generic words don't trigger a match.
    Handles common drug class synonyms:
        glp-1 / glp1 / glucagon-like peptide
        sglt2 / sglt-2 / sodium-glucose cotransporter
    """
    def normalise(s: str) -> set[str]:
        s = s.lower()
        # Normalise drug class abbreviations
        s = re.sub(r"glp[-\s]?1", "glp1", s)
        s = re.sub(r"sglt[-\s]?2", "sglt2", s)
        s = re.sub(r"dpp[-\s]?4", "dpp4", s)
        tokens = set(re.sub(r"[^\w\s]", " ", s).split())
        return tokens - _STOPWORDS

    med_tokens = normalise(med_name)
    span_tokens = normalise(span_text)

    if not med_tokens:
        return False
    return bool(med_tokens & span_tokens)


# ── Eligibility range parsing ──────────────────────────────────────────────────

def parse_range_from_span(span_text: str) -> tuple[float | None, float | None]:
    """
    Extract a numeric range (lo, hi) from an eligibility text span.

    Returns (None, None) if no numeric constraint can be extracted.
    Either end can be None (open boundary).

    Handles patterns:
        between X and Y     → (X, Y)
        from X to Y         → (X, Y)
        X to Y              → (X, Y)
        X–Y / X - Y         → (X, Y)
        ≥ X / >= X / > X    → (X, None)   [> treated as ≥ for pre-screening]
        ≤ Y / <= Y / < Y    → (None, Y)   [< treated as ≤ for pre-screening]
        of X%               → (X, None) if preceded by ≥
    """
    text = span_text.lower()

    # between X and Y / from X to Y
    m = re.search(
        r"(?:between|from)\s+([\d.]+)\s*%?\s*(?:and|to)\s+([\d.]+)", text
    )
    if m:
        return float(m.group(1)), float(m.group(2))

    # X to Y / X – Y
    m = re.search(r"([\d.]+)\s*%?\s*(?:to|–|-)\s*([\d.]+)\s*%?", text)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo < hi:  # sanity check — avoid matching e.g. "30 mL/min/1.73m²"
            return lo, hi

    # ≥ X or >= X or > X
    m = re.search(r"(?:≥|>=|>)\s*([\d.]+)", text)
    if m:
        return float(m.group(1)), None

    # ≤ Y or <= Y or < Y
    m = re.search(r"(?:≤|<=|<)\s*([\d.]+)", text)
    if m:
        return None, float(m.group(1))

    return None, None
