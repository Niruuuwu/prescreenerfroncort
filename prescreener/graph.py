"""
graph.py — Linear LangGraph runner for PreScreenState.

Wires the 4 stages into a linear LangGraph pipeline:
  filter_structured → retrieve_evidence → evaluate_criteria → generate_report

Includes dev-mode logging/printing of state after each node execution.
"""

from __future__ import annotations

import json
import logging
import warnings
from typing import Callable

# Suppress a noisy LangGraph deprecation warning about JsonPlusSerializer's
# `allowed_objects` default — non-breaking, just cosmetic noise on every run.
# LangChainPendingDeprecationWarning is a custom class (not plain DeprecationWarning)
# so we filter by message string with category=Warning to catch it regardless.
warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects`",
    category=Warning,
)

from langgraph.graph import StateGraph, START, END

from prescreener.state import PreScreenState
from prescreener.nodes.filter_structured import filter_structured
from prescreener.nodes.retrieve_evidence import build_patient_evidence, retrieve_evidence
from prescreener.nodes.evaluate_criteria import evaluate_criteria
from prescreener.nodes.generate_report import generate_report, compute_evidence_leverage_summary

logger = logging.getLogger("prescreener.graph")


def _log_node_state(node_name: str, state: dict, dev_log: bool = True):
    """Prints/logs the state object after a node runs for dev runs."""
    if dev_log:
        print(f"\n==================== [DEV LOG] Node Completed: {node_name} ====================")
        summary = {
            "patient_id": state.get("patient_id"),
            "candidate_trials_count": len(state.get("candidate_trials", [])),
            "retrieved_evidence_keys": list(state.get("retrieved_evidence", {}).keys()),
            "evaluated_count": len(state.get("evaluated_trials", [])),
            "final_report_count": len(state.get("final_report", [])),
            "human_review_required": state.get("human_review_required", False),
        }
        print(json.dumps(summary, indent=2))
        print("================================================================================\n")


def build_graph(
    all_trials: list[dict],
    llm_fn: Callable[[str], str] | None = None,
    dev_log: bool = False,
    use_cache: bool = True,
):
    """
    Constructs and compiles the linear LangGraph for trial pre-screening.

    Args:
        all_trials: Complete list of trials from dataset.
        llm_fn: Optional LLM callable override for testing/mocking.
        dev_log: If True, prints node state logs after each step.
        use_cache: If False, skips reading from disk cache.
    """

    def node_filter_structured(state: PreScreenState) -> dict:
        patient_record = state["patient_record"]
        candidates = filter_structured(patient_record, all_trials)
        patch = {"candidate_trials": candidates}
        new_state = {**state, **patch}
        _log_node_state("filter_structured", new_state, dev_log=dev_log)
        return patch

    def node_retrieve_evidence(state: PreScreenState) -> dict:
        patient_record = state["patient_record"]
        candidates = state["candidate_trials"]

        pev = build_patient_evidence(patient_record)
        retrieved_dict = {}
        retrieved_list = []

        for candidate in candidates:
            tev = retrieve_evidence(pev, candidate, llm_fn=llm_fn, use_cache=use_cache)
            retrieved_dict[candidate["nct_id"]] = tev
            retrieved_list.append(tev)

        patch = {
            "patient_evidence": pev,
            "retrieved_evidence": retrieved_dict,
            "retrieved_evidence_list": retrieved_list,
        }
        new_state = {**state, **patch}
        _log_node_state("retrieve_evidence", new_state, dev_log=dev_log)
        return patch

    def node_evaluate_criteria(state: PreScreenState) -> dict:
        pev = state.get("patient_evidence") or build_patient_evidence(state["patient_record"])
        candidates = state["candidate_trials"]
        retrieved_dict = state.get("retrieved_evidence", {})

        evaluated = []
        criterion_results_map = {}

        for candidate in candidates:
            nct_id = candidate["nct_id"]
            tev = retrieved_dict.get(nct_id)
            if tev is None:
                tev = retrieve_evidence(pev, candidate, llm_fn=llm_fn, use_cache=use_cache)

            eval_res = evaluate_criteria(pev, tev["trial_evidence"])
            criterion_results_map[nct_id] = eval_res["criterion_results"]

            evaluated.append({
                "trial": candidate,
                "criterion_results": eval_res["criterion_results"],
                "human_review_required": eval_res["human_review_required"],
            })

        any_human_review = any(e["human_review_required"] for e in evaluated)

        patch = {
            "evaluated_trials": evaluated,
            "criterion_results": criterion_results_map,
            "human_review_required": any_human_review,
        }
        new_state = {**state, **patch}
        _log_node_state("evaluate_criteria", new_state, dev_log=dev_log)
        return patch

    def node_generate_report(state: PreScreenState) -> dict:
        evaluated = state.get("evaluated_trials", [])
        report_entries = generate_report(evaluated)
        leverage_summary = compute_evidence_leverage_summary(evaluated)

        any_human_review = state.get("human_review_required", False) or any(
            r.get("human_review_required", False) for r in report_entries
        )

        patch = {
            "final_report": report_entries,
            "evidence_leverage_summary": leverage_summary,
            "human_review_required": any_human_review,
        }
        new_state = {**state, **patch}
        _log_node_state("generate_report", new_state, dev_log=dev_log)
        return patch

    builder = StateGraph(PreScreenState)

    builder.add_node("filter_structured", node_filter_structured)
    builder.add_node("retrieve_evidence", node_retrieve_evidence)
    builder.add_node("evaluate_criteria", node_evaluate_criteria)
    builder.add_node("generate_report", node_generate_report)

    builder.add_edge(START, "filter_structured")
    builder.add_edge("filter_structured", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "evaluate_criteria")
    builder.add_edge("evaluate_criteria", "generate_report")
    return builder.compile()


def make_initial_state(patient_id: str, patient_record: dict) -> PreScreenState:
    """Convenience constructor for a blank initial state."""
    return {
        "patient_id":            patient_id,
        "patient_record":        patient_record,
        "candidate_trials":      [],
        "retrieved_evidence":    {},
        "criterion_results":     {},
        "other_requirements":    {},
        "open_questions":        [],
        "final_report":          [],
        "human_review_required": False,
    }
