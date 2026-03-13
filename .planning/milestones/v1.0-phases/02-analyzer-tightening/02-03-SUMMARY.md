---
phase: 02-analyzer-tightening
plan: 03
subsystem: ml_analyzer
tags: [ml, ema, anomaly-detection, contamination, cross-sensor, river]

# Dependency graph
requires:
  - phase: 01-coordinator-suppression
    provides: coordinator suppression gates that consume ML anomaly results

provides:
  - EMA score smoothing in MLPatternAnalyzer.check_anomaly() (alpha=0.3)
  - MIN_CROSS_SENSOR_OCCURRENCES=30 constant replacing hardcoded 10
  - Updated ML_CONTAMINATION: LOW=0.005, MEDIUM=0.02, HIGH=0.05
  - EMA state (_score_ema) persists across to_dict()/from_dict() serialization
  - TestCrossSensorGuard, TestMLContaminationConstants, TestEMASmoothing test classes

affects:
  - coordinator.py (receives fewer marginal ML detections)
  - future tuning of contamination values (provisional — see STATE.md research flag)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - EMA smoothing pattern for score time-series: prev_ema stored per entity, alpha=0.3
    - Named constant pattern for guard thresholds (MIN_CROSS_SENSOR_OCCURRENCES)
    - ML_AVAILABLE patching pattern for unit testing ML logic without River installed

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/ml_analyzer.py
    - tests/test_ml_analyzer.py

key-decisions:
  - "EMA alpha=0.3 (not 0.5): lower alpha means more smoothing, weighted toward history — a spike from 0.5 baseline stays at 0.647 (below 0.98 threshold)"
  - "ML_CONTAMINATION LOW lowered to 0.005 (not kept at 0.01): directionally consistent with tightening; provisional, monitor in production"
  - "test_sustained_anomaly_detected patches ml_mod.ML_AVAILABLE=True temporarily: cleanest way to test EMA logic without River installed in test env"

patterns-established:
  - "EMA smoothing state per entity: self._score_ema dict, prev_ema = get(entity_id, score) default"
  - "ML guard constants: extracted to const.py, imported by name — no hardcoded thresholds in ml_analyzer.py"

requirements-completed: [ML-01, ML-02, ML-03]

# Metrics
duration: 5min
completed: 2026-03-13
---

# Phase 02 Plan 03: ML Analyzer Tightening Summary

**EMA score smoothing (alpha=0.3) added to suppress single-spike ML false positives, cross-sensor co-occurrence threshold raised from 10 to 30, and ML_CONTAMINATION tightened to LOW=0.005/MEDIUM=0.02/HIGH=0.05**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-13T12:15:39Z
- **Completed:** 2026-03-13T12:20:45Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments

- Added `_score_ema: dict[str, float]` per-entity EMA state with `ML_EMA_ALPHA=0.3` constant
- Applied EMA smoothing in `check_anomaly()` — single-spike score 0.99 with prior EMA 0.5 yields smoothed 0.647, below threshold 0.98
- Replaced hardcoded `co_occurrence_count >= 10` with `MIN_CROSS_SENSOR_OCCURRENCES=30` constant
- Updated ML_CONTAMINATION: LOW 0.01→0.005, MEDIUM 0.05→0.02, HIGH 0.10→0.05
- Persisted `_score_ema` in `to_dict()`/`from_dict()` for continuity across HA restarts
- 7 new tests (TestCrossSensorGuard×2, TestMLContaminationConstants×2, TestEMASmoothing×3) all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for ML changes** - `f7151fe` (test)
2. **Task 2: Implement ML changes to turn tests green** - `07ff8dd` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD tasks have separate test and feat commits (RED → GREEN)_

## Files Created/Modified

- `custom_components/behaviour_monitor/const.py` — Added MIN_CROSS_SENSOR_OCCURRENCES=30, ML_EMA_ALPHA=0.3; updated ML_CONTAMINATION values; added provisional note
- `custom_components/behaviour_monitor/ml_analyzer.py` — Added EMA state attrs in __init__; EMA smoothing in check_anomaly(); MIN_CROSS_SENSOR_OCCURRENCES in check_cross_sensor_anomalies(); score_ema in to_dict()/from_dict()
- `tests/test_ml_analyzer.py` — Added const imports (ML_CONTAMINATION, ML_EMA_ALPHA, MIN_CROSS_SENSOR_OCCURRENCES); TestCrossSensorGuard, TestMLContaminationConstants, TestEMASmoothing classes

## Decisions Made

- **EMA alpha=0.3:** Lower = more smoothing. A single 0.99 spike from a 0.5 baseline yields smoothed 0.647, well below 0.98 threshold. Sustained 10× repeats of 0.99 exceed threshold on the first call (EMA = 0.99 when no prior state).
- **ML_CONTAMINATION LOW = 0.005:** Directionally consistent with tightening all three levels. Provisional — marked in const.py comment.
- **Test strategy for ML_AVAILABLE=False:** `patch ml_mod.ML_AVAILABLE = True` temporarily. Cleaner than mocking `is_trained` property since it keeps the actual property logic intact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected test_low_count_excluded to use count=20 instead of count=15**
- **Found during:** Task 1 (Writing failing tests)
- **Issue:** count=15 with a_before=13, b_before=2 yields correlation_strength=0.481 < 0.5, so the pattern is excluded by the strength filter before reaching the count filter — the test passed for the wrong reason
- **Fix:** Changed to count=20, a_before=18, b_before=2 which yields strength≈0.548 > 0.5, so the old hardcoded 10 allows it through and produces an anomaly (making the test fail correctly)
- **Files modified:** tests/test_ml_analyzer.py
- **Verification:** Test properly fails with old code (count=20 >= 10), passes with new code (count=20 < 30)
- **Committed in:** f7151fe (Task 1 commit)

**2. [Rule 1 - Bug] Fixed test_spike_suppressed and test_sustained_anomaly_detected to patch ML_AVAILABLE**
- **Found during:** Task 2 (Implementing green phase)
- **Issue:** Tests passed/failed for wrong reasons because ML_AVAILABLE=False in test environment, causing is_trained=False and check_anomaly to return None before reaching EMA logic
- **Fix:** Added `ml_mod.ML_AVAILABLE = True` patching with restore in finally block so EMA code path is actually exercised
- **Files modified:** tests/test_ml_analyzer.py
- **Verification:** test_spike_suppressed confirms None returned at 0.647 (not None due to is_trained=False); test_sustained_anomaly_detected confirms anomaly fires on first call with score=0.99
- **Committed in:** 07ff8dd (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Both auto-fixes required for tests to correctly exercise the target behavior. No scope creep.

## Issues Encountered

None beyond the test design fixes documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ML tightening complete: EMA smoothing active, cross-sensor guard at 30, contamination at tighter values
- Coordinator suppression (Phase 1) + ML tightening (Phase 2 Plan 3) together reduce false-positive notification rate
- Monitor contamination values in production — MEDIUM=0.02 and LOW=0.005 are provisional
- Phase 2 complete: all three plans done (analyzer.py tightening plans 01-02 + ml_analyzer.py plan 03)

---
*Phase: 02-analyzer-tightening*
*Completed: 2026-03-13*
