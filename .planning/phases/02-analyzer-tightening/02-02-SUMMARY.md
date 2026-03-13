---
phase: 02-analyzer-tightening
plan: 02
subsystem: analyzer
tags: [z-score, anomaly-detection, statistical-analysis, tdd, false-positive-reduction, adaptive-threshold]

# Dependency graph
requires:
  - phase: 02-analyzer-tightening
    plan: 01
    provides: MIN_BUCKET_OBSERVATIONS bucket guard and SENSITIVITY_MEDIUM=2.5 sigma from Plan 01 — _get_variance_multiplier() depends on bucket guard logic

provides:
  - MAX_VARIANCE_MULTIPLIER=2.0 constant in const.py
  - _get_variance_multiplier() method on PatternAnalyzer — computes CV-based multiplier in [1.0, 2.0]
  - Adaptive threshold in check_for_anomalies() — effective_threshold = sensitivity * variance_multiplier
  - TestAdaptiveThresholds test class with 5 tests in test_analyzer.py

affects: [02-03-ml-tightening, any future plans that call check_for_anomalies()]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD red-green: write failing tests first, then implement to pass"
    - "Adaptive threshold pattern: multiply base sensitivity by CV-derived multiplier per entity"
    - "Coefficient of Variation (CV) = avg_std / avg_mean across qualifying buckets"

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/analyzer.py
    - tests/test_analyzer.py

key-decisions:
  - "MAX_VARIANCE_MULTIPLIER=2.0 cap: prevents extreme outlier entities from widening threshold to infinity; ensures adaptive thresholds remain meaningful"
  - "Multiplier formula: 1.0 + CV (not 1.0 + 0.5*CV or similar scaling) — direct CV maps linearly to threshold expansion, intuitive and bounded by cap"
  - "Entities with no qualifying buckets (all count < MIN_BUCKET_OBSERVATIONS) default to multiplier 1.0 — graceful degradation preserves existing behavior for sparse entities"

patterns-established:
  - "Adaptive threshold in check_for_anomalies(): always compute variance_multiplier before z-score comparison, never inline the math"
  - "Qualifying bucket criterion: bucket.count >= MIN_BUCKET_OBSERVATIONS AND bucket.mean > 0 — reuses same guard as bucket guard from Plan 01"

requirements-completed: [STAT-04]

# Metrics
duration: 4min
completed: 2026-03-13
---

# Phase 02 Plan 02: Analyzer Tightening — Adaptive Thresholds Summary

**Per-entity adaptive thresholds using coefficient of variation widen effective z-score threshold for high-variance entities, reducing false positives without loosening detection for stable entities**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-13T12:23:46Z
- **Completed:** 2026-03-13T12:27:00Z
- **Tasks:** 1 (TDD: RED + GREEN commits)
- **Files modified:** 3

## Accomplishments

- Added `MAX_VARIANCE_MULTIPLIER=2.0` constant to const.py (STAT-04)
- Implemented `_get_variance_multiplier(pattern)` on PatternAnalyzer: computes CV (avg_std/avg_mean) across qualifying buckets, returns multiplier in [1.0, 2.0]
- Updated `check_for_anomalies()` to use `effective_threshold = sensitivity_threshold * variance_multiplier` instead of bare `sensitivity_threshold`
- 5 new tests (TestAdaptiveThresholds) all green; full suite 240 passed, 2 skipped

## Task Commits

Each task was committed atomically:

1. **RED: Write failing tests for adaptive thresholds** - `4396678` (test)
2. **GREEN: Implement _get_variance_multiplier and adaptive threshold** - `3f75a26` (feat)

_Note: TDD tasks have two commits (test RED, then feat GREEN)_

## Files Created/Modified

- `custom_components/behaviour_monitor/const.py` - Added `MAX_VARIANCE_MULTIPLIER: Final = 2.0`
- `custom_components/behaviour_monitor/analyzer.py` - Added `_get_variance_multiplier()` method; updated `check_for_anomalies()` to use adaptive threshold; imported `MAX_VARIANCE_MULTIPLIER`
- `tests/test_analyzer.py` - Added `TestAdaptiveThresholds` (5 tests)

## Decisions Made

- `MAX_VARIANCE_MULTIPLIER=2.0`: caps the adaptive expansion at 2x the base threshold — an entity with extreme variance (CV=20) still gets only 2x threshold, not 21x
- Multiplier formula `1.0 + CV` maps linearly to threshold expansion: CV=0.1 gives 1.1x, CV=0.8 gives 1.8x, CV>=1.0 gives 2.0x (capped)
- Entities with no qualifying buckets (count < MIN_BUCKET_OBSERVATIONS or mean=0) return multiplier 1.0 — existing behavior preserved

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- Adaptive thresholds are in place — high-variance entities (motion sensors, frequently-toggled lights) will generate fewer false positives without reducing detection sensitivity on stable entities
- Phase 02 Plan 03 (ML tightening) was already completed; it targeted ml_analyzer.py and is independent of these statistical analyzer changes
- Full suite remains green with 240 passed

---
*Phase: 02-analyzer-tightening*
*Completed: 2026-03-13*
