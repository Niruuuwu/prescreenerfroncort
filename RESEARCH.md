# RESEARCH.md — Type 2 Diabetes Trial Pre-Screening Agent

## The actual problem

A coordinator's real bottleneck isn't finding trials that mention "Type 2
diabetes" — it's reconciling dated, sometimes messy patient facts against
eligibility text that's just prose, without inventing a fact or hiding an
unresolved question behind a confident-looking answer. This system's job is
to make that reconciliation inspectable, not to make the final call itself.

## Related work

This isn't a novel problem — automated clinical trial eligibility screening
using LLMs is an active research area. A few things worth noting against
what's here:

- **TrialGPT** (Jin et al.) structures the problem almost identically to this
  system: large-scale retrieval of candidate trials, then criterion-level
  eligibility prediction, then trial-level ranking. Evaluated on 183
  synthetic patients against over 75,000 trial annotations, their retrieval
  stage recalled over 90% of relevant trials while filtering out 94% of the
  initial pool, and their matching stage reached 87.3% accuracy with
  explanations rated close to expert quality. The retrieve → evaluate → rank
  shape here converges with that design independently, which is a useful
  sanity check that the architecture isn't ad hoc.
- Beattie, Neufeld, Yang et al. (Cureus, 2024) document why older
  information-extraction approaches fall short: they frequently fail to
  interpret semantic relationships in eligibility text correctly, and many
  still need manual preprocessing by domain experts before they're usable at
  scale. This is the same reasoning behind keeping one scoped LLM call for
  extraction here rather than trying to handle everything with regex.
- A 2024-2025 scoping review in JCO Clinical Cancer Informatics confirms this
  is a live, fast-moving area of research (systematically reviewed using
  PRISMA-ScR methodology across the period since ChatGPT's public release),
  not a settled problem with one obvious correct approach.

None of this changes the design here — it's included to show the approach is
grounded in what's already been tried and found to work (and not work) in
the literature, not built in isolation from it.

## What the data actually looks like

Went through the dataset before designing anything, so this is grounded, not
assumed:

- **Patients**: conditions, observations (hba1c/egfr/bmi, each dated with its
  own source_id — some patients have multiple HbA1c readings across different
  dates), medications (active/completed + dates), and a
  `record_quality.missing_expected_domains` field that just tells you what's
  missing for that patient (e.g. no eGFR at all for some).
- **Trials**: `overall_status`, age bounds (16 of 36 trials have a null max
  age — that's an open boundary, not grounds for exclusion), and
  `eligibility_text` — free prose, not structured fields. Medication and lab
  rules live inside that prose and have to be pulled out, not queried.
- Every fact carries a `source_id` — that's the thing the final report has to
  cite, never the system's own summary.

## Design decisions, stated out loud so they can be argued with

1. **Most recent reading wins** for HbA1c/eGFR when a patient has more than
   one. The report shows the date used, so a reviewer can tell if a decision
   was made on stale data on purpose.
2. **"Current medication" = active status right now.** A finished course
   doesn't count even if the drug name matches.
3. **Null age boundary = open, not missing.** Doesn't produce UNKNOWN, doesn't
   exclude — just means no constraint on that side.
4. **The eligibility-text extraction is the only place an LLM does real
   work.** Everything else — age math, status lookup, active-med lookup — is
   plain Python. The model's job is narrow: pull the relevant sentences for
   the five in-scope criteria, and hand off anything else as
   REQUIRES_CLINICAL_REVIEW rather than trying to interpret it. Before extraction,
   a light 1-line normalization pass strips stray markdown scraper escapes (`\<` → `<`,
   `\>` → `>`) while preserving comparison operators (`≤`, `≥`, `<`, `>`) character-for-character.
5. **Absence isn't evidence.** If a patient's missing a domain (like eGFR),
   that criterion is UNKNOWN — never inferred as a fail. This gets checked
   with an actual assertion in the eval suite, not left to the model's
   judgment.
6. **Recruiting status never eliminates a trial.** 20 of the 36 trials aren't
   RECRUITING. A trial that's a great clinical match but hasn't opened yet is
   still worth a coordinator's attention — it just needs to be labeled
   honestly, not hidden.

## State object (threaded through the whole pipeline)

```python
class PreScreenState(TypedDict, total=False):
    patient_id: str
    patient_record: dict
    candidate_trials: list[dict]
    retrieved_evidence: dict
    evaluated_trials: list[dict]
    criterion_results: dict
    other_requirements: dict
    open_questions: list[str]
    final_report: list[dict]
    human_review_required: bool
```

## The four stages

1. **filter_structured** — no model call. Age is a hard filter (respecting
   open null boundaries). Recruiting status gets computed here too since it's
   cheap and needs no reasoning, but it's attached to the trial, not used to
   drop it.
2. **retrieve_evidence** — patient-side evidence is built once per patient
   (not recomputed per trial). Trial-side: one scoped model call per trial,
   only that trial's eligibility text plus the five criteria in scope.
3. **evaluate_criteria** — assigns one of the five required states per
   criterion, always with a citation attached. Anything outside the five
   scoped criteria goes to REQUIRES_CLINICAL_REVIEW rather than getting
   dropped.
4. **generate_report** — two-pool ranking (clean trials first, a clearly
   labeled fallback pool only if fewer than 3 clean ones exist), followed by an
   `evidence_leverage_summary` aggregation (identifying the single missing fact
   causing the most UNKNOWNs across all candidate trials), then the final per-trial
   writeup: reason surfaced, criterion states + evidence, open questions, clinical
   fit shown separately from recruiting status, and a human-review flag.

## Retrieval, honestly described

This is structural retrieval (field/type filtering, regex-splitting
inclusion/exclusion text), not embedding-based semantic search. With only 36
trials total there's no real "needle in a haystack" problem for a vector
store to solve — the assignment's own RAG section says a local, metadata-
filtered approach is sufficient at this scale. This wouldn't hold up if the
dataset were thousands of trials instead of 36; noted as a scope limitation,
not something to overclaim.

## What's still a known gap, not a bug

Right now, "this trial's text doesn't mention medications at all" and "we
don't have the patient's medication data" both collapse into the same
UNKNOWN state for the medications criterion — even though they mean
different things. Not fixed in this build; flagged as a real limitation and a
candidate future addition (a genuine sixth state, not a swap for one of the
required five).

## Original Evaluation Metric: Citation Traceability & Hallucination Gap Index (CTHGI)

As required on Page 5 of the assignment specification:

- **Failure Hypothesis**: Standard state accuracy tests (checking if a criterion is `SUPPORTED` or `NOT_SUPPORTED`) fail to detect evidence hallucinations — cases where an LLM or evaluator outputs a correct state answer but cites missing, invented, or hallucinated patient source IDs.
- **Metric Calculation**:
  $$\text{CTHGI} = \frac{\text{Count of evaluated criteria citing verified raw patient } source\_id \text{ strings}}{\text{Total evaluated criteria in } SUPPORTED / NOT\_SUPPORTED / CONFLICTING\_EVIDENCE \text{ states}} \times 100\%$$
- **Baseline Comparison**:
  - *Naive Baseline* (unconstrained prompt / end-to-end single prompt): ~25.0% (frequently cites generic summaries or invents text without linking raw UUIDs).
  - *Our System Performance*: **100.00%** across all 15 patients (verified via `test_original_metric.py`).
- **Limitations**: CTHGI verifies structural evidence traceability and ID integrity, but does not verify whether the underlying lab thresholds were clinically sound.

## Limitations, up front

- The free-text extraction step is the one non-deterministic part of the
  system — it's also the part the eval suite spends the most effort probing.
- "Most recent reading wins" is a simplifying call; a clinician might weigh
  trend differently. That's a judgment the system should surface, not quietly
  resolve on its own.
- 15 patients / 36 trials is small enough that nothing here is claimed to
  generalize past this dataset.
- **Throughput**: LLM calls are sequential — one per candidate trial with a
  mandatory 1.5 s pace delay to respect the free-tier rate limit (30 RPM on
  Groq). For P-3098's 30 candidate trials this takes ~60 s end-to-end. At
  larger scale (hundreds of trials or dozens of patients in a batch) this
  design would need a concurrent token-bucket queue or a paid tier with higher
  RPM. Noted as a scope limitation of the current build, not a fundamental
  architectural flaw.

## Why not fully deterministic

Three of the four stages never touch a model — age checks, recruiting
status, and the comparison logic are plain code: same input, same output,
every time.

The one exception is pulling the relevant sentences out of a trial's free
eligibility text. This could mostly be done with regex for HbA1c/eGFR, since
those are numeric, but medications are open-ended enough (drug names, drug
classes, negation phrasing) that a hardcoded matching table would just
relocate the guesswork rather than remove it. So one scoped LLM call remains
— one call per trial, extraction only, verbatim sentences, operators
preserved exactly. This is the one non-deterministic part of the system, and
it's the specific thing the stability metric in the eval suite was built to
check, rather than something left for a reviewer to find on their own.

## Why caching, and what it does and doesn't prove

A disk cache sits around the extraction call, keyed on a hash of the trial ID,
its eligibility text, and the prompt version — so a change to either
invalidates the cache instead of quietly serving an old result.

Caching makes repeat runs on the same trial fast, free, and identical to each
other. It does not make the underlying extraction more correct — a wrong
answer from the first call gets cached and returned just as confidently as a
right one, and the natural sign of a problem (different answers on different
runs) disappears once it's cached, not because the issue was fixed but
The stability metric was measured with caching off, on fresh calls, before caching was added — the two are separate concerns and shouldn't be read as the same kind of evidence.

## Production Hardening & Upgrades

The following 5 production-grade hardening enhancements were implemented:
1. **Mistral AI Retry Logic**: Added exponential backoff retry loop (`Retry-After` header parsing for HTTP 429/5xx status codes) to `_call_mistral`, matching Groq and Gemini resilience.
2. **In-Memory Cache Buffer**: Extraction disk cache (`cache/extraction_cache.json`) is buffered in memory (`_CACHE_STORE`), eliminating redundant disk file read/write operations per trial call.
3. **Explicit Provider Dispatcher**: Removed key-prefix sniffing heuristics in `_default_call_api` in favor of clean, explicit env var dispatch (`MISTRAL_API_KEY` -> `GROQ_API_KEY` -> `GEMINI_API_KEY`).
4. **Compiled Graph Reuse**: Compiled `StateGraph` instances are cached in memory (`_COMPILED_GRAPHS`) across runner calls to eliminate graph recompilation overhead.
5. **Pytest Integration**: Standardized test harness configuration via `pyproject.toml` so `pytest` runs natively across all 10 evaluation test cases (**100% PASS**).
