"""
test_generate_report_harness.py

All tests are deterministic — no API calls.
Verifies: clean pool selection, no-padding rule, fallback path,
human_review_required three-trigger logic, and ranking order.
"""

from generate_report import generate_report


# ── Helpers ────────────────────────────────────────────────────────────────────

def _trial(nct_id, status="RECRUITING", title=None):
    return {
        "nct_id":         nct_id,
        "brief_title":    title or f"Trial {nct_id}",
        "overall_status": status,
    }


def _cr(hba1c="SUPPORTED", egfr="SUPPORTED", meds="SUPPORTED",
        age="SUPPORTED", status="SUPPORTED", other=None):
    results = {
        "age":                          {"state": age,    "explanation": "", "citations": []},
        "trial_recruiting_status":      {"state": status, "explanation": "", "citations": []},
        "hba1c":                        {"state": hba1c,  "explanation": "", "citations": []},
        "egfr":                         {"state": egfr,   "explanation": "", "citations": []},
        "current_diabetes_medications": {"state": meds,   "explanation": "", "citations": []},
    }
    if other:
        results["other_requirements"] = {"state": other, "explanation": "", "citations": []}
    return results


def _entry(nct_id, criterion_results, human_review=False, trial_status="RECRUITING"):
    return {
        "trial":               _trial(nct_id, status=trial_status),
        "criterion_results":   criterion_results,
        "human_review_required": human_review,
    }


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_not_supported_trial_never_in_clean_pool():
    """
    Design decision: NOT_SUPPORTED trials never qualify for primary top-3.
    A perfectly ranked NOT_SUPPORTED trial must not displace a clean one.
    """
    clean = _entry("NCT_CLEAN", _cr())                  # zero NOT_SUPPORTED
    dirty = _entry("NCT_DIRTY", _cr(hba1c="NOT_SUPPORTED"))  # one NOT_SUPPORTED

    report = generate_report([dirty, clean])
    ids = [e["nct_id"] for e in report]
    assert "NCT_CLEAN" in ids
    assert "NCT_DIRTY" not in ids, "NOT_SUPPORTED trial must not appear when clean pool is non-empty"
    assert report[0]["selection_tier"] == "clean"
    print("PASS: NOT_SUPPORTED trial excluded from report when clean pool is non-empty")


def test_no_padding_when_fewer_than_3_clean():
    """
    If only 2 clean trials exist, report must have 2 entries — not 3.
    Must not pad with a NOT_SUPPORTED trial.
    """
    clean1 = _entry("NCT_C1", _cr())
    clean2 = _entry("NCT_C2", _cr())
    dirty  = _entry("NCT_D1", _cr(egfr="NOT_SUPPORTED"))

    report = generate_report([clean1, clean2, dirty])
    assert len(report) == 2, f"Expected 2 entries, got {len(report)}"
    ids = [e["nct_id"] for e in report]
    assert "NCT_D1" not in ids
    assert all(e["selection_tier"] == "clean" for e in report)
    print("PASS: report has 2 entries when only 2 clean trials exist — no padding")


def test_empty_clean_pool_triggers_fallback():
    """
    When ALL trials have NOT_SUPPORTED, the fallback path must activate.
    All entries must have is_fallback=True and human_review_required=True.
    """
    e1 = _entry("NCT_F1", _cr(hba1c="NOT_SUPPORTED"))
    e2 = _entry("NCT_F2", _cr(egfr="NOT_SUPPORTED"))
    e3 = _entry("NCT_F3", _cr(meds="NOT_SUPPORTED"))
    e4 = _entry("NCT_F4", _cr(hba1c="NOT_SUPPORTED", egfr="NOT_SUPPORTED"))

    report = generate_report([e1, e2, e3, e4])
    assert len(report) == 3
    for entry in report:
        assert entry["selection_tier"] == "fallback"
        assert entry["is_fallback"] is True
        assert entry["human_review_required"] is True
    print("PASS: fallback path activated; all entries selection_tier='fallback' and human_review_required=True")


def test_fallback_ranking_fewest_not_supported_first():
    """In fallback, trial with 1 NOT_SUPPORTED must rank above trial with 2."""
    bad  = _entry("NCT_BAD",  _cr(hba1c="NOT_SUPPORTED", egfr="NOT_SUPPORTED"))
    less = _entry("NCT_LESS", _cr(hba1c="NOT_SUPPORTED"))

    report = generate_report([bad, less])
    assert report[0]["nct_id"] == "NCT_LESS", (
        "Trial with 1 NOT_SUPPORTED must rank above trial with 2"
    )
    print("PASS: fallback ranking — fewest NOT_SUPPORTED first")


def test_clean_ranking_fewest_unknown_first():
    """Within clean pool: trial with fewer UNKNOWN ranks higher."""
    more_unk = _entry("NCT_MU", _cr(egfr="UNKNOWN", meds="UNKNOWN"))
    less_unk = _entry("NCT_LU", _cr(egfr="UNKNOWN"))

    report = generate_report([more_unk, less_unk])
    assert report[0]["nct_id"] == "NCT_LU", "Fewer UNKNOWN must rank higher"
    print("PASS: clean ranking — fewest UNKNOWN first")


def test_clean_ranking_fewest_rcr_as_tiebreak():
    """Within clean pool, same UNKNOWN count: fewer RCR ranks higher."""
    with_rcr    = _entry("NCT_RCR",  _cr(other="REQUIRES_CLINICAL_REVIEW"))
    without_rcr = _entry("NCT_NRCR", _cr())

    report = generate_report([with_rcr, without_rcr])
    assert report[0]["nct_id"] == "NCT_NRCR", "Fewer RCR must rank higher"
    print("PASS: clean ranking — fewest RCR as second tiebreak")


def test_recruiting_tiebreak():
    """
    RECRUITING must rank ahead of NOT_YET_RECRUITING when all other counts are equal.
    """
    not_yet  = _entry("NCT_NYR", _cr(), trial_status="NOT_YET_RECRUITING")
    recruit  = _entry("NCT_REC", _cr(), trial_status="RECRUITING")

    report = generate_report([not_yet, recruit])
    assert report[0]["nct_id"] == "NCT_REC", "RECRUITING must be final tiebreak winner"
    print("PASS: RECRUITING ranked above NOT_YET_RECRUITING as final tiebreak")


def test_human_review_required_rcr_trigger():
    """
    human_review_required must be True when REQUIRES_CLINICAL_REVIEW is present,
    even when the trial is in the clean pool (not a fallback).
    """
    e = _entry("NCT_RCR", _cr(other="REQUIRES_CLINICAL_REVIEW"), human_review=True)
    report = generate_report([e])
    assert report[0]["human_review_required"] is True
    assert report[0]["is_fallback"] is False
    print("PASS: human_review_required=True for RCR, is_fallback=False (clean pool)")


def test_human_review_false_when_fully_clean():
    """
    All SUPPORTED/UNKNOWN, clean pool, no fallback → human_review_required=False.
    """
    e = _entry("NCT_PURE", _cr(egfr="UNKNOWN"), human_review=False)
    report = generate_report([e])
    assert report[0]["human_review_required"] is False
    assert report[0]["is_fallback"] is False
    print("PASS: human_review_required=False for fully clean entry with no RCR")


def test_max_three_entries_returned():
    """Report must return at most 3 entries."""
    entries = [_entry(f"NCT_{i}", _cr()) for i in range(10)]
    report = generate_report(entries)
    assert len(report) <= 3
    print("PASS: report capped at 3 entries")


def test_empty_input_returns_empty():
    assert generate_report([]) == []
    print("PASS: empty input returns empty list")


def test_not_supported_criteria_field_populated():
    """is_fallback entry must list the NOT_SUPPORTED criterion names."""
    e = _entry("NCT_F", _cr(hba1c="NOT_SUPPORTED"))
    report = generate_report([e])   # fallback since only trial has NOT_SUPPORTED
    assert "hba1c" in report[0]["not_supported_criteria"]
    print("PASS: not_supported_criteria field correctly lists failing criteria")


def test_summary_present_and_non_empty():
    e = _entry("NCT_S", _cr())
    report = generate_report([e])
    assert isinstance(report[0]["summary"], str) and len(report[0]["summary"]) > 0
    print("PASS: summary field present and non-empty")


if __name__ == "__main__":
    test_not_supported_trial_never_in_clean_pool()
    test_no_padding_when_fewer_than_3_clean()
    test_empty_clean_pool_triggers_fallback()
    test_fallback_ranking_fewest_not_supported_first()
    test_clean_ranking_fewest_unknown_first()
    test_clean_ranking_fewest_rcr_as_tiebreak()
    test_recruiting_tiebreak()
    test_human_review_required_rcr_trigger()
    test_human_review_false_when_fully_clean()
    test_max_three_entries_returned()
    test_empty_input_returns_empty()
    test_not_supported_criteria_field_populated()
    test_summary_present_and_non_empty()
    print()
    print("All generate_report tests passed.")
