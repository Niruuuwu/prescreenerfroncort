"""
runner.py — End-to-end runner function for prescreener pipeline using LangGraph.
"""

from __future__ import annotations

import json
from typing import Callable

from prescreener.graph import build_graph
from prescreener.state import PreScreenState


# Compiled graph cache to avoid recompiling graph on every call
_COMPILED_GRAPHS: dict[tuple, Any] = {}


def prescreen_patient(
    patient_id: str,
    dataset_path: str = "data/Type2-Diabetes-Trial-Agent-Dataset.json",
    llm_fn: Callable[[str], str] | None = None,
    dev_log: bool = False,
    use_cache: bool = True,
) -> dict:
    """
    Runs the complete 4-stage pre-screening agent for a given patient_id via LangGraph.

    Returns:
        Dict with keys:
          - "patient_id": str
          - "as_of_date": str
          - "candidate_trials_count": int (after Stage 1 hard filter)
          - "human_review_required": bool
          - "evidence_leverage_summary": list[dict]
          - "report": list[dict] (top 0-3 ranked trials)
    """
    with open(dataset_path, encoding="utf-8") as f:
        dataset = json.load(f)

    patients_by_id = {p["patient_id"]: p for p in dataset["patients"]}
    if patient_id not in patients_by_id:
        raise ValueError(f"Patient ID '{patient_id}' not found in dataset.")

    patient = patients_by_id[patient_id]
    trials  = dataset["trials"]

    initial_state: PreScreenState = {
        "patient_id": patient_id,
        "patient_record": patient,
        "candidate_trials": [],
        "retrieved_evidence": {},
        "criterion_results": {},
        "other_requirements": {},
        "open_questions": [],
        "final_report": [],
        "human_review_required": False,
    }

    graph_key = (id(llm_fn), dev_log, use_cache)
    if graph_key not in _COMPILED_GRAPHS:
        _COMPILED_GRAPHS[graph_key] = build_graph(trials, llm_fn=llm_fn, dev_log=dev_log, use_cache=use_cache)
    graph = _COMPILED_GRAPHS[graph_key]

    final_state = graph.invoke(initial_state)

    return {
        "patient_id": patient_id,
        "as_of_date": patient.get("as_of_date", ""),
        "candidate_trials_count": len(final_state.get("candidate_trials", [])),
        "human_review_required": final_state.get("human_review_required", False),
        "evidence_leverage_summary": final_state.get("evidence_leverage_summary", []),
        "report": final_state.get("final_report", []),
    }
