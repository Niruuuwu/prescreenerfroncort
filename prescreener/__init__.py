"""
prescreener — Type 2 Diabetes Trial Pre-Screening Agent.

Public API:
    prescreen_patient() - Run full 4-stage pipeline for a patient
    build_graph()       - Construct the 4-node sequential graph
    make_initial_state()- Convenience constructor for blank state
    PreScreenState      - TypedDict for the single state object
"""

from prescreener.graph import build_graph, make_initial_state
from prescreener.state import PreScreenState
from prescreener.runner import prescreen_patient

__all__ = ["prescreen_patient", "build_graph", "make_initial_state", "PreScreenState"]
