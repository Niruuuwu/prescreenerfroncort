"""
Node 1: filter_structured

Deterministic pre-filter. No LLM calls. Two jobs, and they are NOT symmetric:

1. AGE — a genuine hard filter. If the patient's age falls outside a trial's
   [minimum_age_years, maximum_age_years] window, the trial is dropped from
   candidate_trials entirely. A null bound is an OPEN boundary (per
   assignment_scope.age_filter_rule), not an automatic exclusion.

2. RECRUITING STATUS — computed here because it needs no semantic reasoning,
   but it does NOT exclude a trial. Design rationale (verified against this
   dataset): only 16 of 36 trials are RECRUITING; 10 are NOT_YET_RECRUITING
   and 9 are ACTIVE_NOT_RECRUITING. Hard-filtering on status would silently
   discard clinically excellent matches that are simply not open yet —
   exactly the "worth watching" case a coordinator needs. The assignment
   requires recruiting status to be shown SEPARATE from clinical fit in the
   final report, which only makes sense if the trial survives to be reported
   on at all. So status is evaluated as a criterion (state + explanation),
   attached to the trial, and passed forward.

Output: for each surviving trial, a partial criterion_results entry for
"age" and "trial_recruiting_status" is pre-populated, so later nodes don't
redo this work and the report can show the reasoning trail from node 1.
"""

from typing import Optional


def _age_state(patient_age: int, min_age_years: Optional[float], max_age_years: Optional[float]):
    """Returns (state, explanation). min/max None = open boundary on that side."""
    below_min = min_age_years is not None and patient_age < min_age_years
    above_max = max_age_years is not None and patient_age > max_age_years

    if below_min or above_max:
        return "NOT_SUPPORTED", (
            f"Patient age {patient_age} falls outside trial window "
            f"[{min_age_years if min_age_years is not None else 'open'}, "
            f"{max_age_years if max_age_years is not None else 'open'}]."
        )
    return "SUPPORTED", (
        f"Patient age {patient_age} falls within trial window "
        f"[{min_age_years if min_age_years is not None else 'open'}, "
        f"{max_age_years if max_age_years is not None else 'open'}]."
    )


def _recruiting_state(overall_status: str):
    """Returns (state, explanation). Does not gate candidacy — see module docstring."""
    if overall_status == "RECRUITING":
        return "SUPPORTED", "Trial is actively RECRUITING."
    if overall_status in ("NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"):
        return "NOT_SUPPORTED", f"Trial overall_status is {overall_status}, not RECRUITING."
    return "UNKNOWN", f"Unrecognized overall_status value: {overall_status!r}."


def filter_structured(patient_record: dict, trials: list[dict]) -> list[dict]:
    """
    Args:
        patient_record: one patient dict from the dataset (must contain
            demographics.age_at_reference_date).
        trials: full list of trial dicts from the dataset.

    Returns:
        List of trial dicts that pass the age hard-filter. Each returned
        trial dict is annotated with a "_prefilter_criteria" key containing
        the age and recruiting_status criterion results, e.g.:

        {
            ...original trial fields...,
            "_prefilter_criteria": {
                "age": {"state": "SUPPORTED", "explanation": "..."},
                "trial_recruiting_status": {"state": "NOT_SUPPORTED", "explanation": "..."}
            }
        }
    """
    patient_age = patient_record["demographics"]["age_at_reference_date"]
    candidates = []

    for trial in trials:
        age_state, age_explanation = _age_state(
            patient_age,
            trial.get("minimum_age_years"),
            trial.get("maximum_age_years"),
        )

        if age_state == "NOT_SUPPORTED":
            continue  # hard exclusion — not a candidate at all

        status_state, status_explanation = _recruiting_state(trial.get("overall_status"))

        annotated = dict(trial)
        annotated["_prefilter_criteria"] = {
            "age": {"state": age_state, "explanation": age_explanation},
            "trial_recruiting_status": {"state": status_state, "explanation": status_explanation},
        }
        candidates.append(annotated)

    return candidates
