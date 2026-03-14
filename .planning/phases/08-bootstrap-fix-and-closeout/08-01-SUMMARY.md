---
phase: 08-bootstrap-fix-and-closeout
plan: "01"
subsystem: persistence
tags: [coordinator, storage, bootstrap, recorder]

# Dependency graph
requires:
  - phase: 07-config-flow-additions
    provides: coordinator wiring with CONF_LEARNING_PERIOD and CONF_TRACK_ATTRIBUTES
provides:
  - coordinator.async_setup() persists bootstrapped data to storage before returning
  - regression test asserting _save_data() is called once on bootstrap path
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [TDD red-green for single-line production fixes]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_coordinator.py

key-decisions:
  - "DEBT-04 resolved: await self._save_data() added immediately after _bootstrap_from_recorder() in the elif branch — no other code paths changed"
  - "Two tests added: one asserting save IS called on bootstrap path, one asserting save is NOT called when loading existing storage"

patterns-established:
  - "Bootstrap path: _bootstrap_from_recorder() then _save_data() — ensures data is durable after first HA start"

requirements-completed: [DEBT-04]

# Metrics
duration: 5min
completed: 2026-03-14
---

# Phase 8 Plan 01: Bootstrap Fix and Closeout Summary

**Fixed missing `_save_data()` call after recorder bootstrap so first-start model data survives an immediate HA restart**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-14T12:00:00Z
- **Completed:** 2026-03-14T12:05:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Added `await self._save_data()` to the `elif not self._routine_model._entities:` bootstrap branch in `coordinator.async_setup()`
- Added `test_async_setup_saves_after_bootstrap` confirming `async_save` is called once on fresh-start path
- Added `test_async_setup_no_save_when_storage_exists` confirming `async_save` is NOT called on storage-load path
- All 333 tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add post-bootstrap save to async_setup and test it** - `6e06731` (fix)

**Plan metadata:** (docs commit follows)

_Note: TDD — wrote failing test first, then applied fix, then confirmed GREEN_

## Files Created/Modified
- `custom_components/behaviour_monitor/coordinator.py` - Added `await self._save_data()` after `_bootstrap_from_recorder()` in async_setup
- `tests/test_coordinator.py` - Added `test_async_setup_saves_after_bootstrap` and `test_async_setup_no_save_when_storage_exists`

## Decisions Made
- DEBT-04 resolved with minimal targeted change: one line inserted in the bootstrap branch only. No other setup paths affected.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 8 plan 01 complete; ready for phase closeout (no further plans defined)
- All tracked tech debt (DEBT-01, DEBT-02, DEBT-04) resolved across phases 6-8

---
*Phase: 08-bootstrap-fix-and-closeout*
*Completed: 2026-03-14*
