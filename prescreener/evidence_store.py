"""
evidence_store.py — In-memory evidence store for a single graph run.

Patient-side evidence and trial-side eligibility spans are stored under
separate keys so they cannot be accidentally merged before evaluate_criteria
explicitly requests both (RESEARCH.md §6).

Store lifetime equals one graph run. There is no persistence layer and no
thread-safety requirement — each run creates its own EvidenceStore instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvidenceStore:
    """
    Keyed by (nct_id, side) where side is "patient" or "trial".

    Populated by retrieve_evidence; consumed by evaluate_criteria.
    The store acts as a typed accessor layer on top of the retrieved_evidence
    dict that lives in PreScreenState — it does not duplicate data, it wraps it.
    """

    _store: dict[tuple[str, str], dict] = field(default_factory=dict)

    # ── Patient-side ───────────────────────────────────────────────────────────

    def put_patient_evidence(self, nct_id: str, evidence: dict) -> None:
        """Store the extracted patient-side evidence for one trial."""
        self._store[(nct_id, "patient")] = evidence

    def get_patient_evidence(self, nct_id: str) -> dict | None:
        """Return the patient-side evidence for nct_id, or None."""
        return self._store.get((nct_id, "patient"))

    # ── Trial-side ─────────────────────────────────────────────────────────────

    def put_eligibility_spans(self, nct_id: str, spans: dict) -> None:
        """
        Store the parsed eligibility spans for one trial.

        spans must have keys: inclusion, exclusion, unclassified.
        """
        self._store[(nct_id, "trial")] = spans

    def get_eligibility_spans(self, nct_id: str) -> dict | None:
        """Return the eligibility spans for nct_id, or None."""
        return self._store.get((nct_id, "trial"))

    # ── Helpers ────────────────────────────────────────────────────────────────

    def trial_ids(self) -> list[str]:
        """Return all nct_ids that have at least one evidence entry."""
        return list({nct_id for nct_id, _ in self._store})

    def to_retrieved_evidence_dict(self) -> dict:
        """
        Flatten the store into the retrieved_evidence dict shape expected
        by PreScreenState:

            {nct_id: {"patient_evidence": {...}, "eligibility_spans": {...}}}
        """
        result: dict[str, dict] = {}
        for (nct_id, side), data in self._store.items():
            if nct_id not in result:
                result[nct_id] = {}
            key = "patient_evidence" if side == "patient" else "eligibility_spans"
            result[nct_id][key] = data
        return result
