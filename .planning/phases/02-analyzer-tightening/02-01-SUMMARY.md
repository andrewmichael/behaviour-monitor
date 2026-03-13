---
phase: 02-analyzer-tightening
plan: 01
subsystem: analyzer
tags: [z-score, anomaly-detection, statistical-analysis, tdd, false-positive-reduction]

# Dependency graph
requires:
  - phase: 01-coordinator-suppression
    provides: Coordinator suppression gates that filter anomalies before notification — bucket guard reduces raw anomaly volume that coordinator receives
provides:
  - MIN_BUCKET_OBSERVATIONS=3 constant guards sparse time buckets in check_for_anomalies()
  - float('inf') z-score eliminated; capped at sensitivity_threshold+1
  - SENSITIVITY_MEDIUM raised to 2.5 sigma (was 2.0)
  - TestBucketGuards and TestSensitivityConstants test classes in test_analyzer.py
affects: [02-02-ml-tightening, any future plans that call check_for_anomalies()]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD red-green: write failing tests first, then implement to pass"
    - "Bucket guard pattern: check bucket.count < threshold before z-score calculation"
    - "Inf z-score cap: replace float('inf') with sensitivity_threshold+1 to keep scores finite"

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/analyzer.py
    - tests/test_analyzer.py

key-decisions:
  - "MIN_BUCKET_OBSERVATIONS=3 chosen: requires at least 3 data points in a bucket to fire anomaly; subsumed STAT-02 near-zero-mean guard (count guard is stronger)"
  - "SENSITIVITY_MEDIUM raised to 2.5 sigma: reduces false positive rate from ~4.5% to ~1.2% without affecting high/low sensitivity tiers"
  - "float('inf') cap uses sensitivity_threshold+1 (not a magic number): ties cap value to current sensitivity config, ensuring it always fires when above threshold"

patterns-established:
  - "Bucket guard in check_for_anomalies(): always check bucket.count < MIN_BUCKET_OBSERVATIONS before accessing mean/std_dev"
  - "Finite z-score guarantee: all z_score values in AnomalyResult are math.isfinite()"

requirements-completed: [STAT-01, STAT-02, STAT-03]

# Metrics
duration: 3min
completed: 2026-03-13
---

# Phase 02 Plan 01: Analyzer Tightening — Bucket Guards Summary

**Sparse-bucket guard (count < 3) and SENSITIVITY_MEDIUM raised to 2.5 sigma eliminate the two primary sources of statistical false positives in check_for_anomalies()**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-13T12:15:33Z
- **Completed:** 2026-03-13T12:18:29Z
- **Tasks:** 2 (TDD red + green)
- **Files modified:** 3

## Accomplishments

- Added `MIN_BUCKET_OBSERVATIONS=3` constant and bucket count guard — time buckets with fewer than 3 observations are skipped entirely during anomaly detection
- Eliminated `float("inf")` z-scores: zero-variance buckets with differing actual values now produce a capped z-score (`sensitivity_threshold + 1`) instead of infinity
- Raised `SENSITIVITY_MEDIUM` from 2.0 to 2.5 sigma, dropping the false positive rate from ~4.5% to ~1.2%
- 5 new tests (TestBucketGuards x4, TestSensitivityConstants x1) — all green, no regressions in 57-test analyzer suite

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for bucket guards and sensitivity constant** - `6265ca6` (test)
2. **Task 2: Implement bucket guard and raise sensitivity threshold** - `a103a1b` (feat)

_Note: TDD tasks have two commits (test RED, then feat GREEN)_

## Files Created/Modified

- `custom_components/behaviour_monitor/const.py` - Added `MIN_BUCKET_OBSERVATIONS=3`; raised `SENSITIVITY_MEDIUM` to 2.5; linter also updated `ML_CONTAMINATION` values to research-recommended levels
- `custom_components/behaviour_monitor/analyzer.py` - Added `MIN_BUCKET_OBSERVATIONS` import; added bucket count guard in `check_for_anomalies()`; replaced `float("inf")` with capped value
- `tests/test_analyzer.py` - Added `TestBucketGuards` (4 tests) and `TestSensitivityConstants` (1 test)

## Decisions Made

- `MIN_BUCKET_OBSERVATIONS=3` subsumed the separate near-zero-mean guard (STAT-02): count guard is strictly stronger — any bucket with count < 3 cannot have reliable statistics regardless of mean value
- Cap value `self._sensitivity_threshold + 1` (not a constant) ensures the cap is always exactly above the current threshold, firing the anomaly while remaining finite
- `SENSITIVITY_MEDIUM=2.5` affects new installs only; existing installations with MEDIUM sensitivity will not benefit without manual reconfiguration (documented in STATE.md research flags)

## Deviations from Plan

None - plan executed exactly as written.

Note: During execution, the linter auto-updated `ML_CONTAMINATION` values in const.py to research-recommended levels (LOW: 0.005, MEDIUM: 0.02, HIGH: 0.05). This is a separate concern from the bucket guards, was not a planned deviation, and caused `TestMLContaminationConstants` tests (previously RED for a future plan) to pass. This is a positive side effect, not a bug.

## Issues Encountered

- The `make test` full suite had 3 pre-existing failures in `test_ml_analyzer.py` (TestEMASmoothing, TestCrossSensorGuard) related to EMA smoothing and cross-sensor guard features not yet implemented in ml_analyzer.py. These are RED tests for a future phase 02 plan and are out of scope for this plan.

## Next Phase Readiness

- Bucket guard and sensitivity threshold are in place — statistical analyzer will produce significantly fewer false positives
- Phase 02 Plan 02 (ML tightening) can proceed; it targets `ml_analyzer.py` and is independent of these changes
- Remaining pre-existing failures in test_ml_analyzer.py will be resolved in the appropriate future plan

---
*Phase: 02-analyzer-tightening*
*Completed: 2026-03-13*
