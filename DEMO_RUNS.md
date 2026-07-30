# DEMO_RUNS.md — Execution Log & Terminal Proof

This document provides a record of actual terminal executions, demonstrating how to run each command and the exact output produced by the Type 2 Diabetes Clinical Trial Pre-Screening Agent.

---

## 1. Listing All Patients in Dataset

**Command**:
```bash
python main.py --list-patients
```

**Output**:
```text
================================================================================
PATIENTS IN DATASET
================================================================================
Patient P-1842  | Age: 60 | Active Meds: 0 | Missing Domains: None
Patient P-2483  | Age: 57 | Active Meds: 2 | Missing Domains: None
Patient P-2715  | Age: 42 | Active Meds: 1 | Missing Domains: bmi
Patient P-3098  | Age: 59 | Active Meds: 1 | Missing Domains: egfr
Patient P-3916  | Age: 72 | Active Meds: 1 | Missing Domains: pregnancy_status
Patient P-4471  | Age: 67 | Active Meds: 1 | Missing Domains: bmi, pregnancy_status
Patient P-4752  | Age: 57 | Active Meds: 2 | Missing Domains: None
Patient P-5236  | Age: 45 | Active Meds: 2 | Missing Domains: None
Patient P-5691  | Age: 40 | Active Meds: 1 | Missing Domains: None
Patient P-6184  | Age: 61 | Active Meds: 2 | Missing Domains: None
Patient P-7029  | Age: 69 | Active Meds: 1 | Missing Domains: egfr, pregnancy_status
Patient P-7438  | Age: 38 | Active Meds: 2 | Missing Domains: pregnancy_status
Patient P-8361  | Age: 36 | Active Meds: 2 | Missing Domains: None
Patient P-8624  | Age: 53 | Active Meds: 1 | Missing Domains: None
Patient P-9157  | Age: 57 | Active Meds: 1 | Missing Domains: egfr
================================================================================
```

---

## 2. Pre-Screening Patient P-3098 (CLI Report Output)

**Command**:
```bash
python main.py --patient P-3098
```

**Output**:
```text
  [CACHE HIT] NCT04892199
  [CACHE HIT] NCT05168605
  [CACHE HIT] NCT05181449
  [CACHE HIT] NCT05766488
  [CACHE HIT] NCT05844644
  [CACHE HIT] NCT06003153
  [CACHE HIT] NCT06094491
  [CACHE HIT] NCT06254274
  [CACHE HIT] NCT06331338
  [CACHE HIT] NCT06561126
  [CACHE HIT] NCT06578676
  [CACHE HIT] NCT06649344
  [CACHE HIT] NCT06682351
  [CACHE HIT] NCT06760715
  [CACHE HIT] NCT06770829
  [CACHE HIT] NCT06775600
  [CACHE HIT] NCT06973954
  [CACHE HIT] NCT07005986
  [CACHE HIT] NCT07011147
  [CACHE HIT] NCT07047248
  [CACHE HIT] NCT07057518
  [CACHE HIT] NCT07184775
  [CACHE HIT] NCT07220759
  [CACHE HIT] NCT07278531
  [CACHE HIT] NCT07398495
  [CACHE HIT] NCT07399678
  [CACHE HIT] NCT07509502
  [CACHE HIT] NCT07510386
  [CACHE HIT] NCT07628985
  [CACHE HIT] NCT07719894

================================================================================
PRE-SCREENING REPORT FOR PATIENT P-3098 (As of Date: 2026-07-01)
Candidate Trials (Stage 1 Hard Filter): 30
Human Review Required: True
================================================================================

--------------------------------------------------------------------------------
HIGHEST-LEVERAGE ACTION: Obtaining a current eGFR reading would resolve uncertainty on 30 of 30 candidate trials — more than any other single missing data point.
HIGHEST-LEVERAGE ACTION: Obtaining HbA1c reading would resolve uncertainty on 14 of 30 candidate trials.
--------------------------------------------------------------------------------

--- [Match #1] NCT05168605 ---
Title:                 Assessing the Efficacy of Targeted Home Visits in the Management of Chronic Conditions
Recruiting Status:     RECRUITING
Selection Tier:        clean (is_fallback=False)
Human Review Required: True
Reason Surfaced:       Candidate trial for coordinator review. Criteria met: age, trial_recruiting_status, hba1c. Cannot evaluate (data absent): egfr, current_diabetes_medications. Requires clinical review: other_requirements.

Criteria Evaluation:
  * age                         : SUPPORTED                - Patient age 59 is within required window [18.0, 60.0].
  * trial_recruiting_status     : SUPPORTED                - Trial is currently RECRUITING.
  * hba1c                       : SUPPORTED                - Patient HbA1c 9.7% (2026-05-31) satisfies inclusion criterion: '* Hemoglobin A1C>8 in last 6 months (based on medical record)'. Older readings not used (most-recent-wins rule): 8.8% (2024-07-07) [6ca6d77f-ee8c-5dfa-a555-dc599a99f8f7]. [Citations: 9ddf153d-54aa-5ce2-b5d5-ba1d880290c9, * Hemoglobin A1C>8 in last 6 months (based on medical record)]
  * egfr                        : UNKNOWN                  - eGFR not present in patient record (listed in record_quality.missing_expected_domains). Absence is not a pass or fail.
  * current_diabetes_medications: UNKNOWN                  - No diabetes medication rule found in trial eligibility text. Absence of a rule is not permission to proceed.
  * other_requirements          : REQUIRES_CLINICAL_REVIEW - 7 other requirement(s) present; preserved verbatim for human review. [Citations: * Adult patients ages 18-60, * Spanish or English speaking, * Diagnosis of HTN or BP >140/90 in last 3 months (based on medical record), * Not pregnant, * Current oral steroid use, * History of solid organ transplant, * Language other than English or Spanish]
--------------------------------------------------------------------------------

--- [Match #2] NCT06003153 ---
Title:                 GLUCOSE-MGH: Genetic Links Understood Through Challenge With Oral Semaglutide Exposure at MGH
Recruiting Status:     RECRUITING
Selection Tier:        clean (is_fallback=False)
Human Review Required: True
Reason Surfaced:       Candidate trial for coordinator review. Criteria met: age, trial_recruiting_status, current_diabetes_medications. Cannot evaluate (data absent): hba1c, egfr. Requires clinical review: other_requirements.

Criteria Evaluation:
  * age                         : SUPPORTED                - Patient age 59 is within required window [18.0, 65.0].
  * trial_recruiting_status     : SUPPORTED                - Trial is currently RECRUITING.
  * hba1c                       : UNKNOWN                  - No HbA1c threshold found in trial eligibility text.
  * egfr                        : UNKNOWN                  - eGFR not present in patient record (listed in record_quality.missing_expected_domains). Absence is not a pass or fail.
  * current_diabetes_medications: SUPPORTED                - Patient's active medications satisfy all trial medication criteria. [Citations: f6b0d5c3-7fa0-5806-85ea-75c4a8992763, Currently taking medications or intending to take medications for diabetes, Currently taking medications or intending to take medications that affect glycemic parameters, such as glucocorticoids, growth hormone, or fluoroquinolones]
  * other_requirements          : REQUIRES_CLINICAL_REVIEW - 10 other requirement(s) present; preserved verbatim for human review. [Citations: Males or non-pregnant females, Ages 18-65 (inclusive), Able/willing to give consent, Span the metabolic range between normal glycemia and pre-diabetes (fasting glucose of 100-125 mg/dL based on chart review of existing laboratory data), Personal history of intestinal malabsorption, bariatric surgery, celiac disease, gallbladder disease, or pancreatitis, Personal or family history of medullary thyroid cancer or multiple endocrine neoplasia type 2, History of cirrhosis and/or aspartate aminotransferase or alanine aminotransferase more than 3x upper limit of normal, Dietary restrictions preventing consumption of a MMTT, Women who are pregnant, nursing, or at risk of becoming pregnant, Participation in other interventional studies during the current study]
--------------------------------------------------------------------------------

--- [Match #3] NCT07398495 ---
Title:                 Multimodal Training Effects in Middle-Aged and Older Adults With Diabetic Sarcopenia
Recruiting Status:     RECRUITING
Selection Tier:        clean (is_fallback=False)
Human Review Required: True
Reason Surfaced:       Candidate trial for coordinator review. Criteria met: age, trial_recruiting_status, current_diabetes_medications. Cannot evaluate (data absent): hba1c, egfr. Requires clinical review: other_requirements.

Criteria Evaluation:
  * age                         : SUPPORTED                - Patient age 59 is within required window [45.0, 85.0].
  * trial_recruiting_status     : SUPPORTED                - Trial is currently RECRUITING.
  * hba1c                       : UNKNOWN                  - No HbA1c threshold found in trial eligibility text.
  * egfr                        : UNKNOWN                  - eGFR not present in patient record (listed in record_quality.missing_expected_domains). Absence is not a pass or fail.
  * current_diabetes_medications: SUPPORTED                - Patient's active medications satisfy all trial medication criteria. [Citations: f6b0d5c3-7fa0-5806-85ea-75c4a8992763, * Maintained on a stable regimen of oral hypoglycemic agents.]
  * other_requirements          : REQUIRES_CLINICAL_REVIEW - 8 other requirement(s) present; preserved verbatim for human review. [Citations: * Diagnosed with both Type 2 Diabetes Mellitus (T2DM) and sarcopenia., * Aged 45 years or older., * Capable of communicating effectively in Mandarin or Taiwanese., * Willing to provide informed consent or have it obtained from a legally authorized representative., *  Limited limb or joint function that prevents exercise (e.g., recent fractures or dislocations)., * Communication barriers or severe emotional/psychological issues (e.g., uncontrolled depression or severe mental illness)., * Severe cognitive impairment (e.g., dementia)., * Major comorbidities or complications, including active diabetic foot ulcers, amputation, recent myocardial infarction, severe autonomic neuropathy, or a history of stroke within the last 3 years.]
--------------------------------------------------------------------------------
```

---

## 3. Running All Patients Batch Summary (`main.py --all`)

**Command**:
```bash
python main.py --all
```

**Output**:
```text
================================================================================
RUNNING ALL 15 PATIENTS THROUGH PRE-SCREENING PIPELINE
================================================================================

Patient ID   | Candidates | Report Count | Has Fallback | Human Review Req
---------------------------------------------------------------------------
P-1842       | 30         | 3            | False        | True
P-2483       | 30         | 3            | False        | True
P-2715       | 32         | 3            | False        | True
P-3098       | 30         | 3            | False        | True
P-3916       | 21         | 3            | False        | True
P-4471       | 24         | 3            | False        | True
P-4752       | 30         | 3            | False        | True
P-5236       | 32         | 3            | False        | True
P-5691       | 33         | 3            | False        | True
P-6184       | 29         | 3            | False        | True
P-7029       | 24         | 3            | False        | True
P-7438       | 32         | 3            | False        | True
P-8361       | 32         | 3            | False        | True
P-8624       | 30         | 3            | False        | True
P-9157       | 30         | 3            | False        | True

================================================================================
ALL PATIENT RUNS COMPLETE
================================================================================
```

---

## 4. Hand-Verification Runner (`verify_P3098.py`)

**Command**:
```bash
python verify_P3098.py output_cache_test2.json
```

**Output**:
```text
============================================================
  Verifying: output_cache_test2.json
  Patient:   P-3098
============================================================

[PASS]  CHECK 1 — candidate_trials_count == 30
  ...  Got: 30
[PASS]  CHECK 2a — eGFR is UNKNOWN on all report entries
  ...  All report entries have eGFR=UNKNOWN
[PASS]  CHECK 2b — UNKNOWN explanation cites missing_expected_domains
  ...  Explanations citing missing domain: ['NCT05168605', 'NCT06003153', 'NCT07398495']
[PASS]  CHECK 3 — selection_tier == 'clean' (no NOT_SUPPORTED on any top entry)
  ...  [('NCT05168605', 'clean'), ('NCT06003153', 'clean'), ('NCT07398495', 'clean')]

CHECK 4 — Citations include actual source_id strings
[PASS]  Patient source_ids found in citations:
  NCT05168605.hba1c: ['9ddf153d-54aa-5ce2-b5d5-ba1d880290c9']
  NCT06003153.current_diabetes_medications: ['f6b0d5c3-7fa0-5806-85ea-75c4a8992763']
  NCT07398495.current_diabetes_medications: ['f6b0d5c3-7fa0-5806-85ea-75c4a8992763']

[PASS]  CHECK 5 — human_review_required is True at root and on all report entries
  ...  Root human_review_required=True, Report entries=[True, True, True]

============================================================
  All checks passed (3 report entries).
============================================================
```

---

## 5. 10-Case Evaluation Suite (`test_eval_suite.py`)

**Command**:
```bash
python test_eval_suite.py
```

**Output**:
```text
=== Running 10-Case Evaluation Suite ===
PASS 1: Operator preservation & escape stripping (NCT07719894)
PASS 2: Outlier eligibility text handling (NCT06094491)
PASS 3: Explicit missing domain priority check (P-3098)
PASS 4: Most-recent-wins observation evaluation (P-1842)
PASS 5: Age hard exclusion (P-1842 vs NCT07702097)
PASS 6: Soft recruiting status preservation on real dataset trial (NCT07047248)
PASS 7: Active vs completed medication filtering (P-2483)
PASS 8: Missing rule absence-is-not-permission
PASS 9: No-padding clean pool ranking (returns 2 clean entries, 0 dirty)
PASS 10: Fallback flag, selection_tier='fallback', human_review_required=True trigger

All 10 Evaluation Suite tests passed cleanly!
```

---

## 6. Original Evaluation Metric Suite (`test_original_metric.py`)

**Command**:
```bash
python test_original_metric.py
```

**Output**:
```text
================================================================================
ORIGINAL EVALUATION METRIC: Citation Traceability & Hallucination Gap Index
================================================================================

Hypothesis: Accuracy tests miss evidence hallucinations where state is correct
            but patient source_id links are missing or invented.
Target: 100% strict patient source_id verification.

Results across 15 patients:
  Patient P-1842: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-2483: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-2715: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-3098: CTHGI = 100.0% (5/5 criteria with verified raw source_ids)
  Patient P-3916: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-4471: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-4752: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-5236: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-5691: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-6184: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-7029: CTHGI = 100.0% (5/5 criteria with verified raw source_ids)
  Patient P-7438: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-8361: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-8624: CTHGI = 100.0% (10/10 criteria with verified raw source_ids)
  Patient P-9157: CTHGI = 100.0% (5/5 criteria with verified raw source_ids)

--------------------------------------------------------------------------------
OVERALL CTHGI SCORE: 100.00%
BASELINE COMPARISON: Naive baseline without structured state mapping = 25.0%
OUR SYSTEM PERFORMANCE: 100.00% (100% patient evidence traceability)
--------------------------------------------------------------------------------

Original Metric Test Passed Successfully!
```

---

## 5. Native Pytest Suite Execution

**Command**:
```bash
pytest
```

**Output**:
```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\coding\prescreener
configfile: pyproject.toml
testpaths: .
plugins: anyio-4.10.0, Faker-40.28.1, hypothesis-6.151.9, langsmith-0.7.17, asyncio-1.3.0, cov-7.1.0, mock-3.15.1
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 10 items

test_eval_suite.py ..........                                            [100%]

======================== 10 passed, 1 warning in 1.92s ========================
```
