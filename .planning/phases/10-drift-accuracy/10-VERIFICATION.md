---
phase: 10-drift-accuracy
verified: 2026-03-14T19:30:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 10: Drift Accuracy Verification Report

**Phase Goal:** CUSUM drift detection uses day-type-aware and recency-weighted baselines so weekend behavior is only compared to weekends and recent patterns outweigh stale history
**Verified:** 2026-03-14T19:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                          | Status     | Evidence                                                                                                    |
|----|------------------------------------------------------------------------------------------------|------------|-------------------------------------------------------------------------------------------------------------|
| 1  | Weekday drift baseline uses only weekday historical observations                               | VERIFIED   | `_compute_baseline_rates_for_day_type` filters on `event_date.weekday() >= 5`; TestDayTypeBaseline x3 pass |
| 2  | Weekend drift baseline uses only weekend historical observations                               | VERIFIED   | Same helper, `is_weekend` flag inverts the filter; test_weekend_filter_excludes_weekday_dates passes       |
| 3  | Recent days contribute more weight than days 60+ days ago via exponential decay                | VERIFIED   | `_compute_weighted_mean` applies `decay_factor=0.95 ** age_days`; TestDecayWeighting x3 pass              |
| 4  | When a day-type has fewer than MIN_EVIDENCE_DAYS observations, the combined pool is used       | VERIFIED   | `check()` branches on `len(day_type_counts) >= MIN_EVIDENCE_DAYS`; TestDayTypeSplitIntegration fallback passes |
| 5  | All existing DriftDetector tests continue to pass (no regression)                             | VERIFIED   | 362 total tests pass (`make test`); no failures                                                             |
| 6  | A weekend-only behavior change triggers a drift alert without being diluted by weekday data    | VERIFIED   | `TestWeekendIsolationScenario.test_weekend_shift_alerts_without_weekday_dilution` passes                   |
| 7  | Entities with insufficient day-type-split data still receive drift detection via fallback      | VERIFIED   | `TestWeekendIsolationScenario.test_fallback_still_detects_drift_with_few_weekend_days` passes              |
| 8  | Weekend-isolating CUSUM fires alert with direction == "increase" for a 4x rate shift          | VERIFIED   | Alert direction asserted in TestWeekendIsolationScenario; direction field present in AlertResult.details   |
| 9  | Recency-weighted baseline makes recent high-rate days dominate over older low-rate history    | VERIFIED   | `TestRecencyWeightingScenario.test_recency_weighted_baseline_reflects_recent_data` passes (decrease alert) |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact                                                         | Expected                                              | Status     | Details                                                                                     |
|------------------------------------------------------------------|-------------------------------------------------------|------------|---------------------------------------------------------------------------------------------|
| `custom_components/behaviour_monitor/drift_detector.py`          | Day-type-split and recency-weighted CUSUM computation | VERIFIED   | Contains `_compute_baseline_rates_for_day_type`, `_compute_weighted_mean`, updated `check()` |
| `tests/test_drift_detector.py`                                   | Unit tests for day-type split and decay weighting     | VERIFIED   | Contains `TestDayTypeBaseline`, `TestDecayWeighting`, `TestDayTypeSplitIntegration`         |
| `tests/test_drift_detector.py` (plan 02)                         | End-to-end scenario tests for DRFT-01 and DRFT-02     | VERIFIED   | Contains `TestWeekendIsolationScenario`, `TestRecencyWeightingScenario`                     |

### Key Link Verification

| From                                           | To                                    | Via                                                        | Status  | Details                                                                                                   |
|------------------------------------------------|---------------------------------------|------------------------------------------------------------|---------|-----------------------------------------------------------------------------------------------------------|
| `DriftDetector.check()`                        | `_compute_baseline_rates_for_day_type()` | `today.weekday() >= 5` determines `day_type`            | WIRED   | Lines 156-164 of drift_detector.py; day_type set, helper called, result used for `baseline_mean`        |
| `_compute_baseline_rates_for_day_type()`       | `_compute_weighted_mean()`            | `dict[date, int]` passed with `reference_date=today`       | WIRED   | Lines 164, 178 of drift_detector.py; both primary and fallback paths call `_compute_weighted_mean`       |
| `TestWeekendIsolationScenario`                 | `DriftDetector.check()`               | Saturday `check_date` ensures `day_type='weekend'` path   | WIRED   | Test uses `date(2024, 1, 27)` (Saturday, weekday=5); detector.check() invoked directly                  |

### Requirements Coverage

| Requirement | Source Plan | Description                                                                                     | Status    | Evidence                                                                                              |
|-------------|-------------|-------------------------------------------------------------------------------------------------|-----------|-------------------------------------------------------------------------------------------------------|
| DRFT-01     | 10-01, 10-02 | CUSUM drift baseline splits by day-type; weekend compared only to weekends                    | SATISFIED | `_compute_baseline_rates_for_day_type` filters by day_type; `check()` routes by `today.weekday()`; TestDayTypeBaseline, TestWeekendIsolationScenario all pass |
| DRFT-02     | 10-01, 10-02 | Drift baseline applies exponential decay weighting; recent days influence more than 60+ days ago | SATISFIED | `_compute_weighted_mean` with `decay_factor=0.95`; called for both primary and fallback paths in `check()`; TestDecayWeighting, TestRecencyWeightingScenario pass |

No orphaned requirements — REQUIREMENTS.md traceability table maps DRFT-01 and DRFT-02 exclusively to Phase 10, and both plans claim them.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | —    | —       | —        | No TODOs, stubs, or empty implementations found in phase-10 files |

Scan performed on `drift_detector.py` and `tests/test_drift_detector.py`. No `TODO`, `FIXME`, `placeholder`, `return null`, or console-log-only implementations detected.

### Human Verification Required

None. All success criteria are deterministic algorithmic behaviors verifiable via the test suite. The test suite passes (362/362).

### Gaps Summary

No gaps. All must-haves from both plan frontmatter blocks are satisfied:

- `_compute_baseline_rates_for_day_type` exists, is substantive (17 lines of filtering logic), and is called from `check()` on both the primary and fallback paths.
- `_compute_weighted_mean` exists, is substantive (exponential decay over `age_days`), and is called in both branches of `check()` to produce `baseline_mean`.
- `check()` determines `day_type` from `today.weekday()` and uses it to route baseline computation.
- Fallback to the combined pool triggers when same-day-type evidence is below `MIN_EVIDENCE_DAYS`.
- All 41 drift detector tests pass; 362 total tests pass; ruff clean on phase-10 files.
- Commits `55a144e`, `18fe2c9`, `8a579d0` all verified present in `git log`.

---

_Verified: 2026-03-14T19:30:00Z_
_Verifier: Claude (gsd-verifier)_
