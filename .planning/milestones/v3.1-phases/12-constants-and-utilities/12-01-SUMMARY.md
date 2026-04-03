---
phase: 12-constants-and-utilities
plan: 01
subsystem: detection
tags: [enum, constants, formatting, utility]

# Dependency graph
requires: []
provides:
  - ActivityTier enum (HIGH/MEDIUM/LOW) for entity frequency classification
  - TIER_BOUNDARY_HIGH/LOW thresholds for tier classification
  - TIER_FLOOR_SECONDS and TIER_BOOST_FACTOR lookup dicts per tier
  - format_duration() utility for human-readable duration strings
affects: [13-tier-classification, 14-tier-aware-detection, 15-alert-formatting, 16-config-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Enum-keyed lookup dicts for tier-specific parameters"
    - "Module-level utility function in routine_model.py for shared formatting"

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/routine_model.py
    - tests/test_routine_model.py

key-decisions:
  - "TIER_BOUNDARY_HIGH=24 events/day (~1 event/hour) per research ARCHITECTURE.md"
  - "TIER_BOUNDARY_LOW=4 events/day per research ARCHITECTURE.md"
  - "TIER_FLOOR_SECONDS HIGH=3600s (1 hour conservative floor for chatty sensors)"
  - "TIER_BOOST_FACTOR HIGH=2.0 (doubles effective multiplier for high-frequency entities)"
  - "format_duration placed in routine_model.py (not const.py) since it contains logic"

patterns-established:
  - "ActivityTier enum values are lowercase strings matching existing sensitivity level convention"
  - "Tier lookup dicts use ActivityTier enum members as keys for type safety"

requirements-completed: [DET-03]

# Metrics
duration: 2min
completed: 2026-04-02
---

# Phase 12 Plan 01: Constants and Utilities Summary

**ActivityTier enum with HIGH/MEDIUM/LOW classification, tier boundary/floor/boost constants, and format_duration() utility for human-readable duration strings**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-02T17:42:29Z
- **Completed:** 2026-04-02T17:44:36Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- ActivityTier enum with HIGH/MEDIUM/LOW members added to const.py for entity frequency classification
- Tier boundary thresholds (24/4 events/day), floor seconds, and boost factor dicts added to const.py
- format_duration() utility added to routine_model.py -- formats sub-hour as minutes-only, 1h+ as hours+minutes
- 8 new tests for format_duration covering edge cases (zero, sub-minute, float input, large values)
- All 410 tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for format_duration** - `341aa9d` (test)
2. **Task 1 (GREEN): Add ActivityTier enum, tier constants, and format_duration** - `8c7d97d` (feat)
3. **Task 2: Verify imports and lint** - no code changes needed (verification only)

_Note: TDD task has separate RED and GREEN commits._

## Files Created/Modified
- `custom_components/behaviour_monitor/const.py` - Added ActivityTier enum, tier boundary/floor/boost constants
- `custom_components/behaviour_monitor/routine_model.py` - Added format_duration() utility function
- `tests/test_routine_model.py` - Added TestFormatDuration class with 8 test cases

## Decisions Made
- TIER_BOUNDARY_HIGH=24 events/day (~1 event/hour) based on research ARCHITECTURE.md recommendations
- TIER_BOUNDARY_LOW=4 events/day based on research ARCHITECTURE.md recommendations
- TIER_FLOOR_SECONDS[HIGH]=3600s (1 hour) as conservative floor for high-frequency entities
- TIER_BOOST_FACTOR[HIGH]=2.0 doubles the effective inactivity multiplier for chatty sensors
- format_duration() placed in routine_model.py (contains logic, not just constants) accessible to both acute_detector and coordinator

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- ActivityTier enum, tier constants, and format_duration() are ready for import by phases 13-16
- All downstream phases can use `from .const import ActivityTier, TIER_BOUNDARY_HIGH, TIER_BOUNDARY_LOW, TIER_FLOOR_SECONDS, TIER_BOOST_FACTOR`
- format_duration() importable via `from .routine_model import format_duration`

## Self-Check: PASSED

All files verified present. All commit hashes verified in git log.

---
*Phase: 12-constants-and-utilities*
*Completed: 2026-04-02*
