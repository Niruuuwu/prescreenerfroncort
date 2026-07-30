"""
state.py — Single state object threaded through the graph.

Schema is taken verbatim from RESEARCH.md §4 with evaluated_trials added for graph passing.

Criterion result sub-schema (stored inside criterion_results, not a separate TypedDict
so the whole state remains JSON-serialisable):

    {
        "state": one of CRITERION_STATES,
        "evidence_ids": [str, ...],       # source_ids from patient_record only
        "explanation":  str,              # one reviewer-facing sentence
        "observation_date": str | None    # ISO date; present for hba1c/egfr/bmi
    }
"""

from __future__ import annotations
from typing import TypedDict


class PreScreenState(TypedDict, total=False):
    patient_id: str
    patient_record: dict                # raw patient JSON for this run
    candidate_trials: list[dict]        # after structured filtering
    retrieved_evidence: dict            # {nct_id: {criterion: [source_ids/snippets]}}
    evaluated_trials: list[dict]        # evaluated candidate trials list
    criterion_results: dict             # {nct_id: {criterion: {state, evidence_ids, explanation}}}
    other_requirements: dict            # {nct_id: [free-text requirements -> REQUIRES_CLINICAL_REVIEW]}
    open_questions: list[str]
    final_report: list[dict]            # ≤3 trials, fully assembled
    evidence_leverage_summary: list[dict]  # top-level highest leverage summary
    human_review_required: bool
