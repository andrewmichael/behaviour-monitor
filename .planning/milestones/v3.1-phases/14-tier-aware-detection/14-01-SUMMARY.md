---
phase: 14-tier-aware-detection
plan: 01
subsystem: detection
tags: [inactivity, tier-aware, format-duration, acute-detector]

# Dependency graph
requires:
  - phase: 12-constants-utilities
    provides: ActivityTier enum, TIER_FLOOR_SECONDS, TIER_BOOST_FACTOR, format_duration
  - phase: 13-tier-classification
    provides: EntityRoutine.activity_tier property and classify_tier()
provides:
  - Tier-aware inactivity threshold with boost factor and absolute floor
  - Human-readable duration formatting in alert explanations and details
affects: [coordinator, notifications]

# Tech tracking
tech-stack:
  added: []
  patterns: [tier-boost-then-floor threshold pattern]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/acute_detector.py
    - tests/test_acute_detector.py

key-decisions:
  - "Tier variable set unconditionally before conditional block so it is always available for AlertResult details dict"
  - "Pre-existing mypy error on scalar type annotation left untouched (out of scope)"

patterns-established:
  - "Tier-boost-then-floor: multiply threshold by boost factor first, then take max with floor"

requirements-completed: [DET-01, DET-02]

# Metrics
duration: 15min
completed: 2026-04-03
---

# Phase 14 Plan 01: Tier-Aware Detection Summary

**Tier-aware inactivity thresholds with HIGH/MEDIUM/LOW boost factors, absolute floors, and format_duration in alert explanations**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-03T08:23:12Z
- **Completed:** 2026-04-03T08:38:31Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- HIGH-tier entities protected by 2x boost factor AND 1-hour absolute floor before inactivity alerts fire
- MEDIUM-tier entities get 30-minute floor with no boost; LOW-tier and unclassified entities unchanged
- Alert explanations now show "45m" or "2h 15m" instead of "0.0h" or "2.0h"
- AlertResult.details includes activity_tier, elapsed_formatted, typical_formatted for downstream consumers
- All 55 tests pass (44 existing + 11 new tier-aware tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add tier-aware detection tests (TDD RED)** - `b031f36` (test)
2. **Task 2: Implement tier-aware detection in check_inactivity (TDD GREEN)** - `4f4b483` (feat)

## Files Created/Modified

- `custom_components/behaviour_monitor/acute_detector.py` - Added TIER_BOOST_FACTOR/TIER_FLOOR_SECONDS imports, tier-aware threshold logic, format_duration in explanations and details
- `tests/test_acute_detector.py` - Added TestTierAwareThreshold (5 tests), TestTierAwareDetails (4 tests), TestFormattedExplanation (2 tests); updated make_routine helper

## Decisions Made

- Tier variable (`tier = routine.activity_tier`) set unconditionally before the `if tier is not None` block so it is always available for the AlertResult details dict in both tiered and untiered paths
- Pre-existing mypy error on `scalar: float | None` type annotation left untouched as it is out-of-scope for this plan

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all data paths are wired and functional.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Tier-aware detection complete; coordinator can now pass tier-classified routines to AcuteDetector
- Ready for integration wiring in coordinator if a subsequent phase addresses that

## Self-Check: PASSED

All files exist. All commit hashes verified.

---
*Phase: 14-tier-aware-detection*
*Completed: 2026-04-03*
