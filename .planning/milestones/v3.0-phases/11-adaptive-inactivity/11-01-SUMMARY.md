---
phase: 11-adaptive-inactivity
plan: 01
subsystem: detection
tags: [coefficient-of-variation, adaptive-threshold, inactivity-detection, routine-model, tdd]

# Dependency graph
requires: []
provides:
  - ActivitySlot.interval_cv() — CV of inter-event intervals, None for sparse/insufficient data
  - EntityRoutine.interval_cv(hour, dow) — per-slot CV proxy
  - AcuteDetector adaptive threshold using clamp(1+cv, min, max) scalar
  - CONF_MIN/MAX_INACTIVITY_MULTIPLIER constants and defaults (1.5 / 10.0)
  - Coordinator passes min/max bounds from config to AcuteDetector
affects: [12-config-flow-adaptive, any phase using AcuteDetector or EntityRoutine]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - CV computed at query time (not persisted) — pure derived metric from event_times deque
    - Adaptive threshold = global_multiplier x clamp(1+cv, min_multiplier, max_multiplier) x expected_gap
    - details dict carries adaptive_scalar for diagnostic transparency (None when CV unavailable)
    - TDD: RED tests added to existing test files; GREEN implemented; no REFACTOR needed

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/routine_model.py
    - custom_components/behaviour_monitor/acute_detector.py
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_routine_model.py
    - tests/test_acute_detector.py

key-decisions:
  - "CV computed at query time, not persisted — always derived from existing event_times deque, zero storage overhead"
  - "Clamp formula: max(min_multiplier, min(max_multiplier, 1+cv)) ensures regular entities get tighter thresholds without going below min=1.5"
  - "adaptive_scalar added to AlertResult.details for operator diagnostics without changing alert API"
  - "Fallback to global_multiplier x expected_gap when CV is None (sparse slot) preserves existing behavior"

patterns-established:
  - "Per-slot CV: interval_cv() follows same sparse guard pattern as expected_gap_seconds() — None below MIN_SLOT_OBSERVATIONS"
  - "Adaptive scalar clamped between DEFAULT_MIN_INACTIVITY_MULTIPLIER=1.5 and DEFAULT_MAX_INACTIVITY_MULTIPLIER=10.0"

requirements-completed: [INAC-01]

# Metrics
duration: 4min
completed: 2026-03-14
---

# Phase 11 Plan 01: Adaptive Inactivity Threshold Summary

**Per-slot coefficient-of-variation (CV) added to ActivitySlot/EntityRoutine; AcuteDetector now uses adaptive threshold = global_multiplier x clamp(1+cv, 1.5, 10.0) x expected_gap so regular entities get tighter thresholds than erratic ones**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T19:43:12Z
- **Completed:** 2026-03-14T19:47:55Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- ActivitySlot.interval_cv() computes stdev/mean of inter-event intervals; returns None when sparse, 0.0 when mean=0
- AcuteDetector.check_inactivity() applies adaptive clamped scalar when CV is available, falls back gracefully to plain multiplier x gap
- Coordinator updated to read CONF_MIN/MAX_INACTIVITY_MULTIPLIER from config entry and pass to AcuteDetector constructor
- 27 new TDD tests added (12 cv-tagged for routine_model, 15 adaptive/fallback/clamp/compare for acute_detector)
- 389 total tests pass, no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: interval_cv() on ActivitySlot and EntityRoutine (TDD)** - `32913eb` (feat)
2. **Task 2: adaptive threshold in AcuteDetector + new constants (TDD)** - `da19078` (feat)
3. **Task 3: wire min/max multipliers into coordinator** - `48bf41f` (feat)

_Note: TDD RED and GREEN combined per task commit (no REFACTOR pass needed)._

## Files Created/Modified

- `custom_components/behaviour_monitor/routine_model.py` - Added ActivitySlot.interval_cv() and EntityRoutine.interval_cv() proxy
- `custom_components/behaviour_monitor/acute_detector.py` - Updated __init__ with min/max params; adaptive threshold in check_inactivity(); adaptive_scalar in details
- `custom_components/behaviour_monitor/const.py` - Added CONF_MIN/MAX_INACTIVITY_MULTIPLIER and DEFAULT_MIN/MAX_INACTIVITY_MULTIPLIER
- `custom_components/behaviour_monitor/coordinator.py` - Import new constants; pass min/max to AcuteDetector constructor
- `tests/test_routine_model.py` - 12 new cv-tagged tests for ActivitySlot.interval_cv() and EntityRoutine.interval_cv()
- `tests/test_acute_detector.py` - 15 new adaptive/fallback/clamp/compare tests; added pytest import; updated make_routine() with interval_cv kwarg

## Decisions Made

- CV computed at query time from the existing event_times deque — no serialization overhead, always fresh
- Clamp formula preserves a minimum scalar of 1.5 (even for perfectly regular entities) so thresholds never collapse to just the global multiplier alone
- adaptive_scalar stored in AlertResult.details for diagnostic transparency without altering the alert API surface
- Fallback path (CV=None) preserves identical behavior to pre-phase baseline — sparse slots unaffected

## Deviations from Plan

None — plan executed exactly as written. The only minor issue was a missing `import pytest` in the test file, caught immediately during the first GREEN run and fixed inline (Rule 3 - blocking import).

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added missing `import pytest` to test_acute_detector.py**
- **Found during:** Task 2 (first GREEN run)
- **Issue:** New tests used `pytest.approx` but pytest was not imported at the top of the test file
- **Fix:** Added `import pytest` to the import block
- **Files modified:** tests/test_acute_detector.py
- **Verification:** All 15 adaptive/fallback/clamp/compare tests passed
- **Committed in:** da19078 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking import)
**Impact on plan:** Trivial fix, no scope creep.

## Issues Encountered

None beyond the import noted above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- interval_cv() and adaptive threshold fully tested and integrated
- min/max multiplier constants ready for ConfigFlow UI exposure in a future plan
- INAC-01 requirement fulfilled; coordinator wired end-to-end

---
*Phase: 11-adaptive-inactivity*
*Completed: 2026-03-14*
