"""
config.py — Project-wide constants.

All constants in this module are derived from the assignment spec.
Do not add or remove criterion states without documenting the change in RESEARCH.md.
"""

# ── In-scope criteria ──────────────────────────────────────────────────────────
# These are the five criteria the system evaluates deterministically.
# Everything else found in eligibility_text goes to other_requirements.
IN_SCOPE_CRITERIA: list[str] = [
    "hba1c",
    "egfr",
    "type2_diabetes_diagnosis",
    "current_medications",
    "bmi",
]

# ── Trial statuses that pass the structured filter ─────────────────────────────
RECRUITING_STATUSES: frozenset[str] = frozenset({
    "RECRUITING",
    "ENROLLING_BY_INVITATION",
})

# ── Criterion states (spec-mandated five — do not alter without RESEARCH.md note)
# NOT_APPLICABLE was proposed and rejected; it appears nowhere in the assignment spec.
# CONFLICTING_EVIDENCE is reserved for structurally contradictory facts that the
# deterministic rules cannot resolve (e.g. same drug in both inclusion and exclusion).
# For lab values, "most recent wins" resolves contradictions deterministically —
# see RESEARCH.md §3.1 and evaluate_criteria.py for the explicit audit-trail pattern.
CRITERION_STATES: frozenset[str] = frozenset({
    "SUPPORTED",
    "NOT_SUPPORTED",
    "UNKNOWN",
    "CONFLICTING_EVIDENCE",
    "REQUIRES_CLINICAL_REVIEW",
})

# ── Type 2 Diabetes SNOMED codes ───────────────────────────────────────────────
T2D_SNOMED_CODES: frozenset[str] = frozenset({
    "44054006",   # Type 2 diabetes mellitus
    "237599002",  # Insulin-treated type 2 diabetes mellitus
    "359642000",  # Diabetes mellitus type 2 in nonobese
    "420270002",  # Diabetes mellitus type 2 without complication
})

# ── LLM models ─────────────────────────────────────────────────────────────────
# gemini-2.5-flash is phased out (June 2026). Use 3.6-flash (GA 2026-07-21).
# gemini-3.5-flash-lite is available for cost reduction on the narrow extraction task.
DEFAULT_MODEL: str = "gemini-3.6-flash"
LITE_MODEL: str = "gemini-3.5-flash-lite"

# ── Data paths (relative to project root) ──────────────────────────────────────
TRIALS_DATA_PATH: str = "data/trials.json"
PATIENTS_DATA_DIR: str = "data/patients"
