"""
llm.py — Thin adapter for the hosted generative model.

Only retrieve_evidence calls this module. No patient data is ever passed here —
see README.md §"Hosted Model — Data & Privacy" for the full data-sent inventory.

To swap providers, replace call_llm's implementation only. The prompt contract
(system/user split, JSON output schema) lives in retrieve_evidence.py.
"""

from __future__ import annotations

import json
import os

from prescreener.config import DEFAULT_MODEL


def call_llm(prompt: str, *, model: str = DEFAULT_MODEL) -> str:
    """
    Send prompt to the hosted model and return the raw text response.

    Args:
        prompt: The complete prompt string (system + user content combined,
                or user-only if the caller builds a multi-turn structure).
        model:  Model ID. Defaults to DEFAULT_MODEL (gemini-3.6-flash).
                Pass LITE_MODEL for lower-cost runs, or a mock string in tests.

    Returns:
        Raw text from the model. The caller is responsible for parsing JSON.

    Raises:
        RuntimeError: If the GEMINI_API_KEY env var is missing.
        google.genai.errors.APIError: On upstream API failures.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "The LLM call inside retrieve_evidence requires this key."
        )

    # Lazy import so tests that mock call_llm don't need google-genai installed.
    try:
        from google import genai  # type: ignore[import-untyped]
        from google.genai import types  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "google-genai is required for LLM calls. "
            "Install with: pip install google-genai"
        ) from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return response.text


def parse_spans(raw: str) -> list[dict]:
    """
    Parse the LLM's JSON response into a list of span dicts.

    Each span should have keys: side, criterion, text.
    Malformed or missing keys are skipped with a warning rather than crashing —
    the evaluation node will emit REQUIRES_CLINICAL_REVIEW for any criterion
    whose spans could not be extracted.

    Returns:
        List of dicts, each guaranteed to have side, criterion, and text keys.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract a JSON array if the model wrapped it in markdown
        import re
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                return []
        else:
            return []

    if not isinstance(data, list):
        return []

    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not all(k in item for k in ("side", "criterion", "text")):
            continue
        if item["side"] not in ("inclusion", "exclusion"):
            continue
        result.append({
            "side": item["side"],
            "criterion": str(item["criterion"]),
            "text": str(item["text"]),
        })
    return result
