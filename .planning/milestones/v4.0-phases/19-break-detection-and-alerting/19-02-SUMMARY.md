---
phase: 19-break-detection-and-alerting
plan: 02
subsystem: detection
tags: [correlation, welfare, coordinator, alert-pipeline]

# Dependency graph
requires:
  - phase: 19-01
    provides: CorrelationDetector.check_breaks() method and AlertType.CORRELATION_BREAK
provides:
  - check_breaks wired into coordinator _run_detection loop
  - CORRELATION_BREAK excluded from welfare status escalation
  - Correlation break alerts flow through existing suppression pipeline
affects: [coordinator, welfare, alerting]

# Tech tracking
tech-stack:
  added: []
  patterns: [welfare-exclusion-filter, post-detector-append]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_coordinator_correlation.py

key-decisions:
  - "Correlation breaks excluded entirely from welfare derivation (not just status but also reasons/counts) per D-03"
  - "check_breaks called for ALL monitored entities, not just those with routines (detector internally knows which have partners)"

patterns-established:
  - "welfare-exclusion-filter: Filter alert types from _derive_welfare using welfare_alerts list comprehension"
  - "post-detector-append: Append correlation alerts after acute/drift detector loop"

requirements-completed: [COR-05, COR-06, COR-07]

# Metrics
duration: 2min
completed: 2026-04-06
---

# Phase 19 Plan 02: Break Detection Wiring Summary

**check_breaks wired into coordinator _run_detection with welfare exclusion filter for CORRELATION_BREAK alerts**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-06T12:34:53Z
- **Completed:** 2026-04-06T12:37:00Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Wired CorrelationDetector.check_breaks() into _run_detection for all monitored entities
- Added welfare_alerts filter in _derive_welfare to exclude CORRELATION_BREAK from status escalation
- Verified correlation breaks use existing suppression pipeline via AlertType key format
- 5 new integration tests, 509 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for break detection wiring** - `d5bc4e5` (test)
2. **Task 1 GREEN: Wire check_breaks and welfare exclusion** - `896b419` (feat)

## Files Created/Modified
- `custom_components/behaviour_monitor/coordinator.py` - Added check_breaks loop in _run_detection, welfare_alerts filter in _derive_welfare
- `tests/test_coordinator_correlation.py` - Added TestCorrelationBreakDetection class with 5 tests

## Decisions Made
- Correlation breaks excluded entirely from welfare derivation (reasons, counts, status) per D-03 -- cleaner semantics than partial inclusion
- check_breaks called for ALL monitored entities (not just those with routine entries) since the detector internally tracks which entities have learned partners

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 19 (Break Detection and Alerting) complete
- Correlation breaks produce real alerts in the coordinator pipeline
- Welfare status never escalates from correlation breaks alone
- Ready for next phase of v4.0 milestone

## Self-Check: PASSED

- All created/modified files exist on disk
- All commit hashes (d5bc4e5, 896b419) verified in git log
- No stubs or placeholders found
- 509 tests passing, 0 failures

---
*Phase: 19-break-detection-and-alerting*
*Completed: 2026-04-06*
