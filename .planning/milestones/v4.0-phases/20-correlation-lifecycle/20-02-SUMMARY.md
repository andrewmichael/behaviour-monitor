---
phase: 20-correlation-lifecycle
plan: 02
subsystem: detection
tags: [correlation, lifecycle, entity-removal, coordinator]

# Dependency graph
requires:
  - phase: 20-correlation-lifecycle plan 01
    provides: "CorrelationDetector.remove_entity() method"
provides:
  - "Entity removal cleanup wired in coordinator async_setup"
  - "COR-09 end-to-end: config removes entity -> restart -> stale correlation data purged"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: ["stale entity detection via set difference on _entity_event_counts vs _monitored_entities"]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_coordinator_correlation.py

key-decisions:
  - "Cleanup runs inside the existing 'if correlation_state in stored' block, only after from_dict restore"

patterns-established:
  - "Stale entity detection: set(_monitored_entities) diff against restored detector state keys"

requirements-completed: [COR-09]

# Metrics
duration: 3min
completed: 2026-04-07
---

# Phase 20 Plan 02: Entity Removal Cleanup Summary

**Coordinator async_setup wires remove_entity() to purge stale correlation data when entities leave monitored list**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-07T09:35:01Z
- **Completed:** 2026-04-07T09:38:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Wired entity removal cleanup into coordinator async_setup after correlation state restore
- Added 4 tests in TestCorrelationEntityRemoval covering all scenarios (stale removal, monitored retention, no state, empty counts)
- COR-09 fully end-to-end: config removes entity -> HA restart -> async_setup restores detector -> detects stale -> calls remove_entity -> all pairs/counts/break_cycles purged
- 522 tests passing (full suite)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire entity removal cleanup** - `bad8c74` (test: RED) + `3a89116` (feat: GREEN)

_Note: TDD task with RED/GREEN commits._

## Files Created/Modified
- `custom_components/behaviour_monitor/coordinator.py` - Added stale entity cleanup logic in async_setup after correlation state restore
- `tests/test_coordinator_correlation.py` - Added TestCorrelationEntityRemoval class with 4 test methods

## Decisions Made
- Cleanup runs only inside the existing `if "correlation_state" in stored:` block, after `from_dict()` call -- no cleanup needed when there is no stored correlation state

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 20 (Correlation Lifecycle) is now complete -- both plans (01: detector methods, 02: coordinator wiring) delivered
- COR-08 (decay) and COR-09 (entity removal) are fully implemented and tested
- v4.0 milestone correlation features are complete

## Self-Check: PASSED

---
*Phase: 20-correlation-lifecycle*
*Completed: 2026-04-07*
