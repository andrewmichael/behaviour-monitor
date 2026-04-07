---
phase: 18-correlation-discovery
plan: 02
subsystem: correlation
tags: [correlation-detector, coordinator, pmi, persistence, sensor-attributes]

requires:
  - phase: 18-correlation-discovery
    provides: CorrelationDetector class with record_event, recompute, to_dict/from_dict
provides:
  - CorrelationDetector wired into coordinator lifecycle (init, events, daily recompute, persistence, sensor data)
  - cross_sensor_patterns sensor attribute populated from learned correlation groups
  - correlated_with field in entity_status entries
affects: []

tech-stack:
  added: []
  patterns: [detector-to-coordinator wiring pattern, mock-based integration tests for coordinator internals]

key-files:
  created:
    - tests/test_coordinator_correlation.py
  modified:
    - custom_components/behaviour_monitor/coordinator.py

key-decisions:
  - "record_event called after last_seen update so all_last_seen includes current entity"
  - "recompute() placed after tier classification in date-change block following existing daily-batch pattern"
  - "Missing correlation_state in stored data gracefully keeps fresh detector (upgrade-safe)"

patterns-established:
  - "Coordinator wiring: import detector, instantiate in __init__, restore in async_setup, save in _save_data, call in lifecycle methods"

requirements-completed: [COR-03, COR-04]

duration: 8min
completed: 2026-04-04
---

# Phase 18 Plan 02: Coordinator Correlation Wiring Summary

**CorrelationDetector wired into coordinator for event recording, daily PMI recomputation, persistence, and sensor attribute exposure**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-04T14:20:27Z
- **Completed:** 2026-04-04T14:28:00Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- CorrelationDetector instantiated in coordinator __init__ with configurable window from user settings
- record_event called on every monitored entity state change, feeding co-occurrence data
- recompute() runs daily in date-change block alongside tier classification
- correlation_state persisted to storage and restored on startup (upgrade-safe graceful handling)
- cross_sensor_patterns populated from get_correlation_groups() instead of hardcoded empty list
- correlated_with field added to each entity_status entry
- 12 integration tests verifying all wiring points

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests for coordinator wiring** - `b6d5f06` (test)
2. **TDD GREEN: Wire CorrelationDetector + fix tests** - `58facc6` (feat)

_Note: TDD tasks have RED/GREEN commits._

## Files Created/Modified
- `tests/test_coordinator_correlation.py` - 12 integration tests for correlation wiring in coordinator
- `custom_components/behaviour_monitor/coordinator.py` - CorrelationDetector import, instantiation, event recording, daily recompute, persistence, sensor data exposure

## Decisions Made
- record_event placed after `self._last_seen[eid] = now` so the all_last_seen dict includes the current entity's timestamp
- recompute() placed after tier override block in date-change, following existing daily-batch scheduling pattern
- Missing correlation_state in stored data keeps the fresh detector created in __init__ (upgrade-safe)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Correlation discovery is fully wired end-to-end
- Ready for correlation break alerting (Phase 19 or next milestone feature)
- All 494 tests pass with zero regressions

## Self-Check: PASSED

---
*Phase: 18-correlation-discovery*
*Completed: 2026-04-04*
