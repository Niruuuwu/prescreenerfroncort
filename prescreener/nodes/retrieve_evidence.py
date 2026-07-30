"""
retrieve_evidence.py — Node 2: Evidence retrieval.

Job:
1. build_patient_evidence(patient_record): Deterministic, runs once per patient.
   - Extracts HbA1c & eGFR observations: tags latest effective_date <= as_of_date as "current",
     keeps remaining as "historical".
   - Filters medications to status == "active" only.
   - Copies missing_expected_domains from record_quality.
   - BMI is completely excluded (not in scope).

2. split_eligibility_text(text): Deterministic helper to split eligibility_text
   into inclusion and exclusion criteria sections.

3. retrieve_evidence(patient_evidence, candidate_trial, llm_fn=None):
   - Given pre-built patient_evidence and a single trial, makes a Gemini 3.6 Flash
     call (or uses supplied llm_fn for testing) with the approved extraction prompt.
   - Extracts sentences verbatim for HbA1c, current_diabetes_medications, eGFR,
     and buckets everything else to other_requirements.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from typing import Any, Callable

# Prompt version identifier used for cache invalidation
PROMPT_TEMPLATE_VERSION = "v1.0"
CACHE_DIR = "cache"
CACHE_FILE = os.path.join(CACHE_DIR, "extraction_cache.json")


def _get_cache_key(nct_id: str, eligibility_text: str) -> str:
    """Computes a SHA256 cache key from (nct_id, eligibility_text, PROMPT_TEMPLATE_VERSION)."""
    raw_key = f"{nct_id}:{eligibility_text}:{PROMPT_TEMPLATE_VERSION}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


# Global in-memory cache store to eliminate redundant disk reads/writes
_CACHE_STORE: dict[str, str] | None = None


def _load_cache_store() -> dict[str, str]:
    """Loads the disk cache store into memory once."""
    global _CACHE_STORE
    if _CACHE_STORE is not None:
        return _CACHE_STORE

    if not os.path.exists(CACHE_FILE):
        _CACHE_STORE = {}
        return _CACHE_STORE

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            _CACHE_STORE = json.load(f)
    except Exception:
        _CACHE_STORE = {}
    return _CACHE_STORE


def _save_cache_store() -> None:
    """Persists the in-memory cache store to cache/extraction_cache.json."""
    global _CACHE_STORE
    if _CACHE_STORE is None:
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(_CACHE_STORE, f, indent=2)


def _get_cached_response(nct_id: str, cache_key: str) -> str | None:
    """Returns cached LLM response string on hit, or None on miss."""
    store = _load_cache_store()
    if cache_key in store:
        print(f"  [CACHE HIT] {nct_id}", flush=True)
        return store[cache_key]
    print(f"  [CACHE MISS] {nct_id}", flush=True)
    return None


def _set_cached_response(cache_key: str, response: str) -> None:
    """Saves LLM response string to in-memory cache and flushes to disk."""
    store = _load_cache_store()
    store[cache_key] = response
    _save_cache_store()


# ── Extraction Prompt Template ──────────────────────────────────────────────────

EXTRACTION_PROMPT_TEMPLATE = """\
You are extracting specific sentences from a clinical trial eligibility document.

Extract ONLY sentences or bullet points that mention any of these three topics:
  1. HbA1c / glycated haemoglobin / A1c — thresholds, ranges, or limits
  2. Diabetes medications — any named drug or drug class used to treat diabetes
     (e.g. metformin, insulin, GLP-1 agonists, SGLT2 inhibitors, DPP-4 inhibitors,
     sulfonylureas, thiazolidinediones, or any combination thereof)
  3. eGFR / renal function / kidney function / glomerular filtration rate /
     creatinine clearance — thresholds or limits

RULES — you must follow these exactly:
- Copy each sentence VERBATIM from the source text. Do not rephrase or summarise.
- Preserve every comparison operator character-for-character:
    ≤ must stay ≤  (not <=, not <, not "less than or equal to")
    ≥ must stay ≥  (not >=, not >, not "greater than or equal to")
    < must stay <  (not ≤)
    > must stay >  (not ≥)
- If a sentence is relevant to more than one topic, include it under each topic
  it belongs to.
- Every sentence NOT relevant to the three topics goes into "other_requirements"
  verbatim — do not drop anything.
- You must output valid JSON and nothing else (no markdown fences, no explanation).

Output schema:
{{
  "hba1c": [
    {{"section": "inclusion" | "exclusion", "text": "<verbatim sentence>"}}
  ],
  "current_diabetes_medications": [
    {{"section": "inclusion" | "exclusion", "text": "<verbatim sentence>"}}
  ],
  "egfr": [
    {{"section": "inclusion" | "exclusion", "text": "<verbatim sentence>"}}
  ],
  "other_requirements": [
    {{"section": "inclusion" | "exclusion", "text": "<verbatim sentence>"}}
  ]
}}

=== INCLUSION CRITERIA ===
{inclusion_text}

=== EXCLUSION CRITERIA ===
{exclusion_text}
"""


# ── Helper: Date Parsing ──────────────────────────────────────────────────────

def _parse_date(d_str: str) -> date:
    return date.fromisoformat(d_str.split("T")[0])


# ── 1. Patient Evidence Builder ────────────────────────────────────────────────

def build_patient_evidence(patient_record: dict) -> dict:
    """
    Builds patient-side evidence object ONCE per patient.

    Extracts:
    - hba1c: current (latest <= as_of_date) & historical
    - egfr: current (latest <= as_of_date) & historical
    - active_medications: status == 'active' only
    - missing_domains: copied verbatim from record_quality
    (BMI is dropped entirely)
    """
    as_of_date_str = patient_record.get("as_of_date", "2026-07-01")
    as_of = _parse_date(as_of_date_str)

    observations = patient_record.get("observations", [])

    def process_obs(obs_type: str) -> dict:
        matched = [
            o for o in observations
            if o.get("type") == obs_type and _parse_date(o["effective_date"]) <= as_of
        ]
        if not matched:
            return {"current": None, "historical": []}

        # Sort descending by effective_date
        matched.sort(key=lambda o: _parse_date(o["effective_date"]), reverse=True)

        current_raw = matched[0]
        historical_raw = matched[1:]

        def format_item(o: dict) -> dict:
            return {
                "source_id": o["source_id"],
                "value": o["value"],
                "unit": o.get("unit", ""),
                "effective_date": o["effective_date"],
            }

        return {
            "current": format_item(current_raw),
            "historical": [format_item(h) for h in historical_raw],
        }

    hba1c_data = process_obs("hba1c")
    egfr_data = process_obs("egfr")

    # Active medications only
    raw_meds = patient_record.get("medications", [])
    active_meds = [
        {
            "source_id": m["source_id"],
            "name": m["name"],
            "status": m["status"],
            "start_date": m.get("start_date"),
            "end_date": m.get("end_date"),
        }
        for m in raw_meds
        if m.get("status") == "active"
    ]

    # Missing expected domains
    record_quality = patient_record.get("record_quality", {})
    missing_domains = list(record_quality.get("missing_expected_domains", []))

    return {
        "hba1c": hba1c_data,
        "egfr": egfr_data,
        "active_medications": active_meds,
        "missing_domains": missing_domains,
    }


# ── Helper: Split Eligibility Text ─────────────────────────────────────────────

def _clean_markdown_escapes(text: str) -> str:
    """Strip stray markdown scraper escapes (\\< -> <, \\> -> >) while preserving operators."""
    if not text:
        return ""
    return text.replace(r"\<", "<").replace(r"\>", ">")


def split_eligibility_text(text: str) -> dict[str, str]:
    """
    Splits eligibility_text into inclusion and exclusion criteria sections.
    Strips stray markdown backslash escapes (\\< -> <, \\> -> >) first.
    Handles text without explicit exclusion section (e.g. NCT06094491).
    """
    text = _clean_markdown_escapes(text)
    if not text:
        return {"inclusion": "", "exclusion": ""}

    inc_match = re.search(r"inclusion criteria[:\s]*", text, re.IGNORECASE)
    exc_match = re.search(r"exclusion criteria[:\s]*", text, re.IGNORECASE)

    if inc_match and exc_match:
        if inc_match.start() < exc_match.start():
            inclusion = text[inc_match.end():exc_match.start()].strip()
            exclusion = text[exc_match.end():].strip()
        else:
            exclusion = text[exc_match.end():inc_match.start()].strip()
            inclusion = text[inc_match.end():].strip()
    elif inc_match:
        inclusion = text[inc_match.end():].strip()
        exclusion = ""
    elif exc_match:
        inclusion = ""
        exclusion = text[exc_match.end():].strip()
    else:
        # No explicit headers found
        inclusion = text.strip()
        exclusion = ""

    return {"inclusion": inclusion, "exclusion": exclusion}


# ── LLM provider dispatch ──────────────────────────────────────────────────────

def _call_groq(prompt: str, api_key: str) -> str:
    """Call Groq API (llama-3.3-70b-versatile) with rate-limit pacing and smart 429 retries."""
    import urllib.request
    import urllib.error
    import json
    import time

    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }).encode("utf-8")

    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                time.sleep(2.0)  # pace requests to respect 30 RPM rate limit
                return res["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_attempts:
                # Read Retry-After header if provided by Groq API
                retry_after_hdr = e.headers.get("retry-after") or e.headers.get("Retry-After")
                if retry_after_hdr and retry_after_hdr.isdigit():
                    wait_time = int(retry_after_hdr) + 2
                else:
                    wait_time = 10 * attempt  # 10s, 20s, 30s, 40s, 50s exponential backoff
                print(f"  [groq rate-limit 429] Quota exceeded. Waiting {wait_time}s before retry ({attempt}/{max_attempts})...", flush=True)
                time.sleep(wait_time)
            else:
                raise
        except Exception as e:
            if "429" in str(e) and attempt < max_attempts:
                wait_time = 10 * attempt
                print(f"  [groq rate-limit 429] Waiting {wait_time}s before retry ({attempt}/{max_attempts})...", flush=True)
                time.sleep(wait_time)
            else:
                raise


def _call_gemini(prompt: str) -> str:
    """Call Gemini 3.6 Flash with retry on 429 quota errors."""
    import os
    import re
    import time

    from google import genai
    from google.genai import types
    from google.genai import errors as genai_errors

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            return response.text
        except genai_errors.ClientError as exc:
            if exc.status_code != 429 or attempt == max_attempts:
                raise
            wait = 30
            m = re.search(r"retryDelay.*?(\d+(?:\.\d+)?)\s*s", str(exc))
            if m:
                wait = int(float(m.group(1))) + 2
            print(
                f"  [rate-limit] 429 quota exceeded — waiting {wait}s before retry "
                f"(attempt {attempt}/{max_attempts})...",
                flush=True,
            )
            time.sleep(wait)
    raise RuntimeError("Max retry attempts exceeded for Gemini API call.")


def _call_mistral(prompt: str, api_key: str, max_attempts: int = 4) -> str:
    """Call Mistral AI (mistral-small-latest) with exponential backoff retry on HTTP 429/5xx."""
    import urllib.request
    import urllib.error
    import json
    import time

    url = "https://api.mistral.ai/v1/chat/completions"
    payload = json.dumps({
        "model": "mistral-small-latest",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }).encode("utf-8")

    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                retry_after = exc.headers.get("Retry-After")
                wait_sec = int(retry_after) if retry_after and retry_after.isdigit() else 2 * attempt
                print(
                    f"  [Mistral HTTP {exc.code}] Rate limit/server busy. Waiting {wait_sec}s "
                    f"(attempt {attempt}/{max_attempts})...",
                    flush=True,
                )
                time.sleep(wait_sec)
            else:
                raise

    raise RuntimeError("Max retry attempts exceeded for Mistral API call.")


def _default_call_api(prompt: str) -> str:
    """
    Provider-aware dispatcher.
    Supports Mistral AI (MISTRAL_API_KEY), Groq (GROQ_API_KEY), and Gemini (GEMINI_API_KEY).
    """
    import os
    mistral_key = os.environ.get("MISTRAL_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if mistral_key:
        return _call_mistral(prompt, mistral_key)
    if groq_key:
        return _call_groq(prompt, groq_key)
    if gemini_key:
        return _call_gemini(prompt)

    raise RuntimeError(
        "No LLM API key found. Set MISTRAL_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY."
    )




def retrieve_evidence(
    patient_evidence: dict,
    candidate_trial: dict,
    llm_fn: Callable[[str], str] | None = None,
    use_cache: bool = True,
) -> dict:
    """
    Retrieves evidence for one candidate trial given pre-built patient_evidence.

    Args:
        patient_evidence: Pre-built patient evidence from build_patient_evidence().
        candidate_trial: Single trial dict.
        llm_fn: Optional custom LLM runner function (for testing/mocking).
        use_cache: Whether to use caching.

    Returns:
        Dict with keys:
          - patient_evidence
          - trial_evidence
    """
    import os
    elig_text = candidate_trial.get("eligibility_text", "")
    sections = split_eligibility_text(elig_text)

    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        inclusion_text=sections["inclusion"] or "None provided.",
        exclusion_text=sections["exclusion"] or "None provided.",
    )

    nct_id = candidate_trial.get("nct_id", "UNKNOWN")
    cache_key = _get_cache_key(nct_id, elig_text)

    bypass_cache = (not use_cache) or (os.environ.get("PRESCREENER_NO_CACHE") == "1")

    raw_response = None
    if llm_fn is None and not bypass_cache:
        raw_response = _get_cached_response(nct_id, cache_key)

    if raw_response is None:
        call_model = llm_fn if llm_fn is not None else _default_call_api
        raw_response = call_model(prompt)
        if llm_fn is None and not bypass_cache:
            _set_cached_response(cache_key, raw_response)

    # Clean markdown fences if present
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    try:
        extracted = json.loads(cleaned)
    except json.JSONDecodeError:
        extracted = {
            "hba1c": [],
            "current_diabetes_medications": [],
            "egfr": [],
            "other_requirements": [
                {"section": "unclassified", "text": elig_text}
            ],
        }

    trial_evidence = {
        "nct_id": candidate_trial["nct_id"],
        # Carry _prefilter_criteria forward so evaluate_criteria can read
        # age and trial_recruiting_status without touching the raw trial dict.
        "_prefilter_criteria": candidate_trial.get("_prefilter_criteria", {}),
        "hba1c": extracted.get("hba1c", []),
        "current_diabetes_medications": extracted.get("current_diabetes_medications", []),
        "egfr": extracted.get("egfr", []),
        "other_requirements": extracted.get("other_requirements", []),
    }

    return {
        "patient_evidence": patient_evidence,
        "trial_evidence": trial_evidence,
    }
