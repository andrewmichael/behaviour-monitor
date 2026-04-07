---
phase: 17-foundation-and-rehydration
plan: 01
subsystem: detection
tags: [tier-classification, rehydration, startup-fix]

# Dependency graph
requires: []
provides:
  - "Fixed classify_tier() that retries when confidence is low or data is missing on startup"
  - "Three rehydration retry tests verifying retry-until-success behavior"
affects: [coordinator, acute-detector]

# Tech tracking
tech-stack:
  added: []
  patterns: ["conditional date guard: only set _tier_classified_date when classification actually succeeds"]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/routine_model.py
    - tests/test_routine_model.py

key-decisions:
  - "Only set _tier_classified_date when _activity_tier is assigned a real tier (not None)"

patterns-established:
  - "Conditional guard pattern: once-per-day guard checks both date AND result before blocking"

requirements-completed: [RHY-01]

# Metrics
duration: 2min
completed: 2026-04-03
---

# Phase 17 Plan 01: Tier Rehydration Fix Summary

**Fixed classify_tier() to retry on subsequent update cycles when startup confidence is low or median data is unavailable, instead of blocking until midnight**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-03T20:54:52Z
- **Completed:** 2026-04-03T20:56:29Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Fixed the once-per-day guard to allow retries when _activity_tier is still None
- Removed premature _tier_classified_date assignment from the median_rate=None branch
- Added 3 new tests confirming retry-until-success behavior on same calendar day

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1 RED: Add failing rehydration tests** - `70ccfad` (test)
2. **Task 1 GREEN: Fix classify_tier() rehydration retry** - `109238e` (fix)

## Files Created/Modified
- `custom_components/behaviour_monitor/routine_model.py` - Fixed once-per-day guard and median_rate=None branch
- `tests/test_routine_model.py` - Added test_rehydration_retry_low_confidence, test_rehydration_retry_no_median_data, test_once_per_day_guard_allows_retry_when_tier_none

## Decisions Made
- Only set `_tier_classified_date` when a real tier (HIGH/MEDIUM/LOW) is assigned, not when classification fails due to insufficient data

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None.

## Next Phase Readiness
- classify_tier() rehydration fix is complete, ready for coordinator wiring in Plan 02
- All 451 existing tests pass (1 pre-existing failure in test_init.py::test_storage_version_is_8 is unrelated)

---
*Phase: 17-foundation-and-rehydration*
*Completed: 2026-04-03*

## Self-Check: PASSED
