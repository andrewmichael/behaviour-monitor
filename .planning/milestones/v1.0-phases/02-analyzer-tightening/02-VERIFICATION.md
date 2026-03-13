---
phase: 02-analyzer-tightening
verified: 2026-03-13T13:00:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
gaps: []
human_verification: []
---

# Phase 02: Analyzer Tightening — Verification Report

**Phase Goal:** Analyzers produce fewer false anomalies so the coordinator has less noise to suppress
**Verified:** 2026-03-13T13:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

All twelve must-have truths derived from three plan frontmatter blocks were verified against the live codebase.

| #  | Truth                                                                                               | Status     | Evidence                                                                                    |
|----|-----------------------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------------------------|
| 1  | Zero-variance buckets with sparse data do not produce anomaly results                               | VERIFIED   | `analyzer.py` line 467: `if bucket.count < MIN_BUCKET_OBSERVATIONS: continue`              |
| 2  | `float('inf')` z-scores are eliminated from the detection path                                      | VERIFIED   | `grep float.*inf analyzer.py` returns no matches; capped path at lines 481-483             |
| 3  | Time buckets with fewer than MIN_BUCKET_OBSERVATIONS are skipped entirely                           | VERIFIED   | `MIN_BUCKET_OBSERVATIONS = 3` in `const.py` line 47; guard in `check_for_anomalies()`      |
| 4  | SENSITIVITY_MEDIUM threshold is 2.5 (not 2.0)                                                      | VERIFIED   | `const.py` line 28: `SENSITIVITY_MEDIUM: 2.5`; `TestSensitivityConstants` passes           |
| 5  | High-variance entities get a wider effective threshold than low-variance entities                   | VERIFIED   | `_get_variance_multiplier()` in `analyzer.py` lines 423-443; `test_high_variance_wider_threshold` passes |
| 6  | The variance multiplier is capped at MAX_VARIANCE_MULTIPLIER (2.0)                                 | VERIFIED   | `const.py` line 50: `MAX_VARIANCE_MULTIPLIER = 2.0`; `test_multiplier_capped` passes       |
| 7  | Entities with no qualifying buckets get a multiplier of 1.0 (no change)                            | VERIFIED   | `_get_variance_multiplier()` returns `1.0` when `not means`; `test_no_qualifying_buckets` passes |
| 8  | Cross-sensor patterns with fewer than MIN_CROSS_SENSOR_OCCURRENCES co-occurrences are excluded      | VERIFIED   | `ml_analyzer.py` line 513: `p.co_occurrence_count >= MIN_CROSS_SENSOR_OCCURRENCES`; `test_low_count_excluded` passes |
| 9  | ML contamination for MEDIUM sensitivity is 0.02 (not 0.05)                                         | VERIFIED   | `const.py` line 36: `SENSITIVITY_MEDIUM: 0.02`; `test_medium_contamination_raised` passes  |
| 10 | A single-spike ML score below the smoothed threshold does not produce an anomaly result             | VERIFIED   | EMA smoothing in `ml_analyzer.py` lines 473-477; `test_spike_suppressed` passes: smoothed=0.647 < 0.98 |
| 11 | Sustained high ML scores (multiple consecutive intervals) do produce anomaly results                | VERIFIED   | First call with score=0.99, prev_ema=0.99 → smoothed=0.99 > 0.98; `test_sustained_anomaly_detected` passes |
| 12 | EMA state survives to_dict/from_dict serialization round-trip                                      | VERIFIED   | `to_dict()` line 631: `"score_ema": dict(self._score_ema)`; `from_dict()` line 696: restores; `test_ema_serialization` passes |

**Score:** 12/12 truths verified

---

## Required Artifacts

| Artifact                                                          | Provides                                              | Status     | Details                                                                   |
|-------------------------------------------------------------------|-------------------------------------------------------|------------|---------------------------------------------------------------------------|
| `custom_components/behaviour_monitor/const.py`                   | All new constants (Plan 01, 02, 03)                   | VERIFIED   | `MIN_BUCKET_OBSERVATIONS=3`, `MAX_VARIANCE_MULTIPLIER=2.0`, `SENSITIVITY_MEDIUM=2.5`, `MIN_CROSS_SENSOR_OCCURRENCES=30`, `ML_EMA_ALPHA=0.3`, updated `ML_CONTAMINATION` |
| `custom_components/behaviour_monitor/analyzer.py`                | Bucket guard, inf-cap, adaptive threshold, multiplier | VERIFIED   | Bucket guard lines 463-468; inf-cap lines 479-483; adaptive threshold lines 474-476; `_get_variance_multiplier()` lines 423-443 |
| `tests/test_analyzer.py`                                         | TestBucketGuards, TestSensitivityConstants, TestAdaptiveThresholds | VERIFIED | All 3 classes present; 10 tests; all passing |
| `custom_components/behaviour_monitor/ml_analyzer.py`             | EMA smoothing, MIN_CROSS_SENSOR_OCCURRENCES guard     | VERIFIED   | `_score_ema` dict line 156; EMA logic lines 473-477; guard line 513; serialization lines 631/696 |
| `tests/test_ml_analyzer.py`                                      | TestCrossSensorGuard, TestMLContaminationConstants, TestEMASmoothing | VERIFIED | All 3 classes present; 7 tests; all passing |

---

## Key Link Verification

| From                    | To                           | Via                                   | Status   | Details                                                                               |
|-------------------------|------------------------------|---------------------------------------|----------|---------------------------------------------------------------------------------------|
| `analyzer.py`           | `const.py`                   | `import MIN_BUCKET_OBSERVATIONS`      | WIRED    | Line 10: `from .const import MAX_VARIANCE_MULTIPLIER, MIN_BUCKET_OBSERVATIONS`        |
| `analyzer.py`           | `const.py`                   | `import MAX_VARIANCE_MULTIPLIER`      | WIRED    | Line 10: same import statement                                                        |
| `ml_analyzer.py`        | `const.py`                   | `import MIN_CROSS_SENSOR_OCCURRENCES` | WIRED    | Line 10: `from .const import ML_EMA_ALPHA, MIN_CROSS_SENSOR_OCCURRENCES, MIN_SAMPLES_FOR_ML` |
| `ml_analyzer.py`        | `const.py`                   | `import ML_EMA_ALPHA`                 | WIRED    | Line 10: same import statement; used at line 157: `self._ema_alpha: float = ML_EMA_ALPHA` |
| `ml_analyzer.py`        | `ml_analyzer.py to_dict/from_dict` | EMA state persistence           | WIRED    | `to_dict()` line 631 serializes `_score_ema`; `from_dict()` line 696 restores it     |

---

## Requirements Coverage

| Requirement | Source Plan | Description                                                                                  | Status    | Evidence                                                                        |
|-------------|-------------|----------------------------------------------------------------------------------------------|-----------|---------------------------------------------------------------------------------|
| STAT-01     | 02-01       | Minimum observation count per time bucket prevents flagging when insufficient data exists    | SATISFIED | `bucket.count < MIN_BUCKET_OBSERVATIONS` guard eliminates sparse-bucket z-scores |
| STAT-02     | 02-01       | Minimum mean activity guard skips anomaly detection for near-zero historical activity        | SATISFIED | Subsumed by STAT-01 count guard (count < 3 cannot have reliable statistics); documented in decisions |
| STAT-03     | 02-01       | Default sensitivity thresholds raised so Medium sensitivity no longer flags ~4.5% of normal events | SATISFIED | `SENSITIVITY_MEDIUM = 2.5` in const.py; reduces false positive rate from ~4.5% to ~1.2% |
| STAT-04     | 02-02       | Adaptive thresholds adjust per-entity based on historical variance profile                  | SATISFIED | `_get_variance_multiplier()` + `effective_threshold = sensitivity * multiplier` in `check_for_anomalies()` |
| ML-01       | 02-03       | Cross-sensor correlation thresholds raised — minimum co-occurrence count increased from 10   | SATISFIED | `co_occurrence_count >= MIN_CROSS_SENSOR_OCCURRENCES` (30) replaces hardcoded 10 |
| ML-02       | 02-03       | ML anomaly score threshold raised to reduce marginal detections                             | SATISFIED | `ML_CONTAMINATION` updated: MEDIUM 0.05→0.02, HIGH 0.10→0.05, LOW 0.01→0.005  |
| ML-03       | 02-03       | ML score smoothing via exponential moving average reduces noise from single-point spikes    | SATISFIED | EMA smoothing with alpha=0.3; single-spike 0.99 from 0.5 baseline yields 0.647 < 0.98 threshold |

No orphaned requirements: all 7 requirement IDs (STAT-01 through STAT-04, ML-01 through ML-03) were claimed by plans and are satisfied.

---

## Anti-Patterns Found

No blockers or stubs detected in modified files.

| File                                              | Pattern                   | Severity | Notes                                                                               |
|---------------------------------------------------|---------------------------|----------|-------------------------------------------------------------------------------------|
| `custom_components/behaviour_monitor/analyzer.py` | None found                | —        | Bucket guard, inf-cap, and adaptive threshold are substantive implementations      |
| `custom_components/behaviour_monitor/ml_analyzer.py` | None found             | —        | EMA state, cross-sensor guard, contamination values are substantive implementations |
| `tests/test_analyzer.py`                          | None found                | —        | 10 targeted tests with real assertions                                              |
| `tests/test_ml_analyzer.py`                       | None found                | —        | 7 targeted tests including ML_AVAILABLE patching to exercise EMA code path         |

---

## Human Verification Required

None. All goal-relevant behaviors are fully programmable and verified:
- Constant values verified by direct inspection
- Guard logic verified by unit tests with boundary conditions
- Wiring verified by import analysis and test execution
- Full suite (240 passed, 2 skipped) confirms no regressions

---

## Test Execution Results

```
tests/test_analyzer.py::TestBucketGuards (4 tests)          PASSED
tests/test_analyzer.py::TestSensitivityConstants (1 test)   PASSED
tests/test_analyzer.py::TestAdaptiveThresholds (5 tests)    PASSED
tests/test_ml_analyzer.py::TestCrossSensorGuard (2 tests)   PASSED
tests/test_ml_analyzer.py::TestMLContaminationConstants (2 tests) PASSED
tests/test_ml_analyzer.py::TestEMASmoothing (3 tests)       PASSED

Full suite: 240 passed, 2 skipped, 0 failures
```

---

## Summary

Phase 02 goal achieved. All three plans delivered substantive, wired, tested implementations:

- **Plan 01 (STAT-01, STAT-02, STAT-03):** Statistical analyzer now skips buckets with fewer than 3 observations, caps `float('inf')` z-scores at `sensitivity_threshold + 1`, and uses SENSITIVITY_MEDIUM = 2.5 sigma (was 2.0, false positive rate dropped from ~4.5% to ~1.2%).

- **Plan 02 (STAT-04):** Adaptive per-entity thresholds using coefficient of variation widen the effective threshold for high-variance entities (e.g., motion sensors) by up to 2x, without loosening detection for stable entities.

- **Plan 03 (ML-01, ML-02, ML-03):** ML analyzer raises cross-sensor co-occurrence requirement from 10 to 30, tightens contamination values (MEDIUM 0.05→0.02, HIGH 0.10→0.05), and applies EMA smoothing (alpha=0.3) to suppress single-spike false positives while allowing sustained anomalies through.

The coordinator will receive significantly less noise from both analyzers.

---

_Verified: 2026-03-13T13:00:00Z_
_Verifier: Claude (gsd-verifier)_
