---
phase: 19-break-detection-and-alerting
plan: 01
subsystem: detection
tags: [correlation, break-detection, pmi, sustained-evidence, alertresult]

# Dependency graph
requires:
  - phase: 18-correlation-sensor-attributes
    provides: CorrelationDetector with record_event, recompute, get_correlated_entities, persistence
provides:
  - check_breaks method on CorrelationDetector with sustained evidence gating
  - _break_cycles persistence in to_dict/from_dict
  - Group-level dedup (one alert per triggering entity)
affects: [19-02-coordinator-wiring, coordinator]

# Tech tracking
tech-stack:
  added: []
  patterns: [sustained-evidence-gating-for-correlation-breaks, group-dedup-per-entity]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/correlation_detector.py
    - tests/test_correlation_detector.py

key-decisions:
  - "Confidence uses co_occurrence_rate of highest-rate missing partner (matches PMI-based scoring pattern)"
  - "Partner absent from last_seen_map counts as a miss (conservative — unknown state treated as missing)"

patterns-established:
  - "Break detection follows same sustained-evidence pattern as AcuteDetector (counter increment/reset, SUSTAINED_EVIDENCE_CYCLES threshold)"
  - "Group dedup: one AlertResult per triggering entity regardless of number of missing partners"

requirements-completed: [COR-05, COR-06, COR-07]

# Metrics
duration: 2min
completed: 2026-04-05
---

# Phase 19 Plan 01: Break Detection Summary

**check_breaks method on CorrelationDetector with 3-cycle sustained evidence gating and group-level dedup for CORRELATION_BREAK alerts**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-05T10:17:58Z
- **Completed:** 2026-04-05T10:19:56Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- check_breaks() method detects missing correlation partners beyond time window
- Sustained evidence gating requires 3 consecutive misses before alert fires (matches AcuteDetector pattern)
- Group dedup produces one AlertResult per triggering entity regardless of missing partner count
- _break_cycles dict persists through to_dict/from_dict round trip
- 33 total tests passing (14 new: 9 break detection + 1 persistence + 4 existing passing)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add check_breaks method to CorrelationDetector with tests**
   - `463c8ee` (test) - TDD RED: failing tests for check_breaks
   - `94aac4e` (feat) - TDD GREEN: implementation passing all 33 tests

## Files Created/Modified
- `custom_components/behaviour_monitor/correlation_detector.py` - Added check_breaks method, _break_cycles state, updated to_dict/from_dict
- `tests/test_correlation_detector.py` - Added TestCheckBreaks class (9 tests) and break_cycles persistence test

## Decisions Made
- Confidence uses co_occurrence_rate of highest-rate missing partner (matches PMI scoring pattern)
- Partner absent from last_seen_map counts as a miss (conservative approach)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- check_breaks method ready for coordinator wiring in plan 02
- AlertResult with AlertType.CORRELATION_BREAK ready for alert suppression pipeline
- _break_cycles persisted so break detection state survives restarts

---
*Phase: 19-break-detection-and-alerting*
*Completed: 2026-04-05*
