---
phase: 07-config-flow-additions
plan: 02
subsystem: coordinator, testing
tags: [coordinator, config-flow, learning-period, track-attributes, migration, tests]

# Dependency graph
requires:
  - phase: 07-config-flow-additions plan 01
    provides: CONF_LEARNING_PERIOD, CONF_TRACK_ATTRIBUTES constants, schema fields, v4->v5 migration in __init__.py
provides:
  - Coordinator reads CONF_LEARNING_PERIOD and passes it to RoutineModel as history_window_days
  - Coordinator reads CONF_TRACK_ATTRIBUTES and gates attribute-only state change events
  - Test coverage for new config fields in config_flow schema (setup + options)
  - Test coverage for v4->v5 migration: defaults, version bump, preserves existing values
  - Test coverage for coordinator reading both new config values with correct defaults
affects: [coordinator, testing, phase-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Coordinator reads new config values in __init__ after existing config reads"
    - "Attribute-only event guard: early return when _track_attributes=False and old_state.state == ns.state"
    - "RoutineModel receives learning_period_days (not history_window_days) — separate concerns"

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_config_flow.py
    - tests/test_init.py
    - tests/test_coordinator.py

key-decisions:
  - "CONF_LEARNING_PERIOD passed to RoutineModel as history_window_days — controls confidence ramp-up window, distinct from recorder bootstrap fetch window (_history_window_days)"
  - "Attribute-only guard placed immediately after ns-is-None guard in _handle_state_changed — minimal diff, correct early-exit ordering"
  - "Pre-existing test failures caused by plan 07-01 (STORAGE_VERSION 4->5, VERSION 4->5, v4->v5 migration calls) fixed as Rule 1 auto-fixes"

patterns-established:
  - "Migration call_args indexing: v2 entries produce 3 calls (v3, v4, v5) — tests must use call_args_list[N] not call_args"

requirements-completed: [CONF-01, CONF-02, CONF-03]

# Metrics
duration: 4min
completed: 2026-03-14
---

# Phase 7 Plan 02: Config Flow Wiring Summary

**Coordinator uses learning_period_days from config to seed RoutineModel, skips attribute-only events when track_attributes=False, backed by 14 new tests across 3 test files**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T11:41:33Z
- **Completed:** 2026-03-14T11:45:19Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Coordinator wired to read CONF_LEARNING_PERIOD (default 7) and pass it to RoutineModel constructor
- Coordinator wired to read CONF_TRACK_ATTRIBUTES (default True) and skip attribute-only state change events when False
- Full test coverage added: config_flow schema tests, migration tests (v4->v5 defaults/version/preserve), coordinator constructor tests
- Fixed 10 pre-existing test failures introduced by plan 07-01 (version number assertions, migration call indexing)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire coordinator.py to read and apply the two new config values** - `e860bb6` (feat)
2. **Task 2: Add test coverage for new config fields and migration** - `b194a1a` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `custom_components/behaviour_monitor/coordinator.py` - Added CONF_LEARNING_PERIOD/CONF_TRACK_ATTRIBUTES imports and instance vars; RoutineModel now uses _learning_period_days; attribute-only event guard in _handle_state_changed
- `tests/test_config_flow.py` - Added schema inclusion tests for both new fields; fixed VERSION assertion from 4 to 5
- `tests/test_init.py` - Added 4 v4->v5 migration tests; fixed 8 pre-existing failures (call indexing, STORAGE_VERSION, migration call counts)
- `tests/test_coordinator.py` - Added 4 tests for coordinator reading new config values with defaults

## Decisions Made
- CONF_LEARNING_PERIOD is passed as `history_window_days` to RoutineModel (controls confidence ramp-up window). CONF_HISTORY_WINDOW_DAYS remains the recorder bootstrap fetch window. These are distinct concerns sharing the same parameter name on RoutineModel.
- Attribute-only guard uses early return after existing `ns is None` guard, accessing `event.data.get("old_state")` to compare state values.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pre-existing test failures caused by plan 07-01 changes**
- **Found during:** Task 2 (Add test coverage)
- **Issue:** Plan 07-01 added v4->v5 migration, bumped STORAGE_VERSION to 5 and config flow VERSION to 5, but did not update existing tests that asserted version=4, STORAGE_VERSION==4, or assumed v4 was the terminal migration version. 10 tests failed before any new code was written.
- **Fix:** Updated test assertions to reflect v5: `STORAGE_VERSION == 5`, `config_flow.VERSION == 5`, v2 migration call count 3 (not 2), v3 migration produces 2 calls (v4+v5), ML key removal tests now check `call_args_list[1]` (v3->v4 call, not last call)
- **Files modified:** tests/test_init.py, tests/test_config_flow.py
- **Verification:** 331 tests pass after fix
- **Committed in:** b194a1a (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix was essential for a green test suite. No scope creep — all changes directly correct test assertions that became stale when plan 07-01 added the v4->v5 migration path.

## Issues Encountered
None beyond the pre-existing test failures documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 07-config-flow-additions is now complete (both plans done)
- Config values are wired end-to-end: schema -> migration -> coordinator -> RoutineModel
- Phase 08 can proceed with any remaining housekeeping work
