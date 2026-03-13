---
phase: 03-foundation-and-routine-model
plan: "04"
subsystem: coordinator
tags: [routine_model, config, testing, bootstrap]

# Dependency graph
requires:
  - phase: 03-foundation-and-routine-model plan 03
    provides: RoutineModel bootstrap from recorder, coordinator migration to v3 data model
provides:
  - Correct CONF_HISTORY_WINDOW_DAYS config key used for RoutineModel history window
  - Test coverage for partial history confidence (~0.5 for 14/28 days)
  - Test coverage confirming coordinator reads v3 config key not v1 key
affects:
  - all future coordinator tests relying on history_window_days config

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Config key correctness: read CONF_HISTORY_WINDOW_DAYS (v3) not CONF_LEARNING_PERIOD (v1) for RoutineModel window"

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_coordinator.py

key-decisions:
  - "CONF_HISTORY_WINDOW_DAYS is the correct config key for RoutineModel history window — CONF_LEARNING_PERIOD is retained only for PatternAnalyzer (statistical learning period, different purpose)"
  - "Partial history confidence test uses fixed reference_now datetime to make confidence calculation deterministic"

patterns-established:
  - "Test isolation: custom mock config entry per test avoids polluting shared fixture when testing config key behavior"

requirements-completed:
  - INFRA-01
  - INFRA-02
  - ROUTINE-01
  - ROUTINE-02
  - ROUTINE-03

# Metrics
duration: 5min
completed: 2026-03-13
---

# Phase 03 Plan 04: Config Key Fix and Partial History Test Summary

**Fixed coordinator reading wrong config key (CONF_LEARNING_PERIOD → CONF_HISTORY_WINDOW_DAYS) for RoutineModel, cutting detection window from 7 to 28 days, and added two regression tests**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-13T19:51:00Z
- **Completed:** 2026-03-13T19:56:28Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Fixed coordinator line 91: now reads CONF_HISTORY_WINDOW_DAYS (28-day default) instead of CONF_LEARNING_PERIOD (7-day default)
- Added CONF_HISTORY_WINDOW_DAYS to coordinator imports (alphabetically after CONF_ENABLE_NOTIFICATIONS)
- Added test_history_window_days_reads_correct_config_key: creates coordinator with history_window_days=14, asserts _history_window_days == 14 (not 7 from old key)
- Added test_bootstrap_partial_history: bootstraps 14 days of binary events against 28-day window, asserts overall_confidence is between 0.4 and 0.6
- All 225 tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix config key and add partial history confidence test** - `d73f99b` (fix)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `custom_components/behaviour_monitor/coordinator.py` - Import CONF_HISTORY_WINDOW_DAYS; use it at line 91 for RoutineModel window initialization
- `tests/test_coordinator.py` - Added test_history_window_days_reads_correct_config_key and test_bootstrap_partial_history to TestRecorderBootstrap

## Decisions Made
- CONF_LEARNING_PERIOD is NOT removed from imports or usage — it is still the correct key for PatternAnalyzer (statistical learning period) at lines 114, 329, and 380. Only the RoutineModel initialization line was wrong.
- Used a local `_MockEntry` class per test rather than modifying the shared `mock_config_entry` fixture, keeping test isolation clean.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 3 gap closure complete: coordinator correctly initializes RoutineModel with the full 28-day history window
- Test suite at 225 tests with full coverage of the config key regression
- Ready for Phase 4 (acute detector and drift detector implementation)

## Self-Check: PASSED

All files present. Commit d73f99b verified in git log.

---
*Phase: 03-foundation-and-routine-model*
*Completed: 2026-03-13*
