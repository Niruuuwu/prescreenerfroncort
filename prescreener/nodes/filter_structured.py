"""
filter_structured.py — Node 1: Deterministic structured pre-filter.

Jobs:
1. AGE (Hard Filter): If patient's age is outside the trial's [minimum_age_years, maximum_age_years]
   window, the trial is dropped from candidate_trials. Null bounds are open.
2. RECRUITING STATUS (Soft Annotation): Computed here, attached to trial via _prefilter_criteria,
   does NOT drop trials.
"""

from __future__ import annotations


def filter_structured(patient_record: dict, trials: list[dict]) -> list[dict]:
    """
    Pre-filters trials based on demographics and annotates recruiting status.

    Args:
        patient_record: Dict containing patient details (must have 'demographics').
        trials: List of trial dicts.

    Returns:
        List of candidate trial dicts that passed age filtering, with _prefilter_criteria attached.
    """
    demographics = patient_record.get("demographics", {})
    patient_age = demographics.get("age_at_reference_date")

    if patient_age is None:
        raise ValueError("Patient record missing 'demographics.age_at_reference_date'")

    candidate_trials = []

    for trial in trials:
        min_age = trial.get("minimum_age_years")
        max_age = trial.get("maximum_age_years")

        # 1. Hard Age Filtering
        if min_age is not None and patient_age < min_age:
            continue
        if max_age is not None and patient_age > max_age:
            continue

        # Format age explanation
        if min_age is not None and max_age is not None:
            age_explanation = f"Patient age {patient_age} is within required window [{min_age}, {max_age}]."
        elif min_age is not None:
            age_explanation = f"Patient age {patient_age} satisfies minimum age requirement of {min_age} (no upper limit)."
        elif max_age is not None:
            age_explanation = f"Patient age {patient_age} satisfies maximum age requirement of {max_age} (no lower limit)."
        else:
            age_explanation = f"Trial has no age restrictions; patient age {patient_age} is eligible."

        # 2. Soft Recruiting Status Annotation
        overall_status = trial.get("overall_status")
        is_recruiting = (overall_status == "RECRUITING")

        if is_recruiting:
            status_state = "SUPPORTED"
            status_explanation = "Trial is currently RECRUITING."
        else:
            status_state = "NOT_SUPPORTED"
            status_explanation = f"Trial overall_status is '{overall_status}' (not RECRUITING)."

        # Attach _prefilter_criteria to trial copy
        trial_copy = dict(trial)
        trial_copy["_prefilter_criteria"] = {
            "age": {
                "state": "SUPPORTED",
                "explanation": age_explanation,
            },
            "trial_recruiting_status": {
                "state": status_state,
                "explanation": status_explanation,
            },
        }

        candidate_trials.append(trial_copy)

    return candidate_trials
