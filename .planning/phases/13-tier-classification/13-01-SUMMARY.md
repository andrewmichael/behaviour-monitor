---
phase: 13-tier-classification
plan: 01
subsystem: detection
tags: [tier-classification, activity-rate, median, routine-model]

# Dependency graph
requires:
  - phase: 12-constants-and-utilities
    provides: ActivityTier enum, TIER_BOUNDARY_HIGH, TIER_BOUNDARY_LOW constants
provides:
  - EntityRoutine.classify_tier() method for activity tier classification
  - EntityRoutine.activity_tier property exposing current tier
  - EntityRoutine._compute_median_daily_rate() helper for median daily event rate
affects: [14-acute-tier-awareness, 15-config-ui-tier-override, 16-display-formatting]

# Tech tracking
tech-stack:
  added: []
  patterns: [once-per-day classification guard, confidence-gated computation, median-based rate bucketing]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/routine_model.py
    - tests/test_routine_model.py

key-decisions:
  - "Tier classification state (_activity_tier, _tier_classified_date) not serialized -- recomputed on startup via classify_tier() call"
  - "Median daily rate computed from all slots' event_times deques grouped by calendar date"

patterns-established:
  - "Confidence gate pattern: gate computation on confidence >= 0.8 before tier-dependent logic"
  - "Once-per-day guard pattern: store classified date and skip recomputation on same calendar day"

requirements-completed: [CLASS-01, CLASS-02, CLASS-03, CLASS-05]

# Metrics
duration: 13min
completed: 2026-04-02
---

# Phase 13 Plan 01: Tier Classification Summary

**EntityRoutine.classify_tier() with median daily rate mapping to HIGH/MEDIUM/LOW tiers, confidence gating, once-per-day guard, and DEBUG-level tier change logging**

## Performance

- **Duration:** 13 min
- **Started:** 2026-04-02T18:22:00Z
- **Completed:** 2026-04-02T18:35:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- classify_tier() method computes median daily event rate from slot event_times and maps to ActivityTier enum
- Confidence gating (>= 0.8) prevents premature classification of entities still in learning phase
- Once-per-day guard prevents redundant recomputation within the same calendar date
- Tier change logging at DEBUG level with entity_id, old tier, new tier, and median rate
- 12 new tests in TestTierClassification covering all tiers, boundaries, gating, guard, logging, and numeric entity edge case
- Full suite: 422 tests passing, 0 regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tier classification tests** - `011b36d` (test)
2. **Task 1 (GREEN): Implement classify_tier, activity_tier, _compute_median_daily_rate** - `262912e` (feat)
3. **Task 2: Verify lint and full test suite** - verification only, no code changes

_Note: TDD task had RED and GREEN commits. No REFACTOR needed._

## Files Created/Modified
- `custom_components/behaviour_monitor/routine_model.py` - Added classify_tier(), activity_tier property, _compute_median_daily_rate(), tier state fields, logging import, const imports
- `tests/test_routine_model.py` - Added TestTierClassification class with 12 tests, _build_routine_with_rate helper, ActivityTier/boundary imports

## Decisions Made
- Tier classification state (_activity_tier, _tier_classified_date) is not serialized to storage -- it is recomputed on startup. This avoids storage schema changes and keeps tier always fresh.
- Median daily rate is computed from ALL slots' event_times deques grouped by calendar date, not from a single day's daily_activity_rate(). This provides a robust aggregate view.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed tier change logging test data setup**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Original test added 30 events to a single day on top of 7 days of 10 events/day, but the median of 8 values (seven 10s and one 30) remained 10, not exceeding TIER_BOUNDARY_HIGH
- **Fix:** Clear all event_times and repopulate with 5 days of 30 events/day to ensure median shifts above 24
- **Files modified:** tests/test_routine_model.py
- **Verification:** test_tier_change_logging passes with correct tier transition from MEDIUM to HIGH
- **Committed in:** 262912e (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test data)
**Impact on plan:** Test fix was necessary for correctness. No scope creep.

## Issues Encountered
None

## Known Stubs
None -- all classification logic is fully wired to real data from event_times deques.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- EntityRoutine.classify_tier() and activity_tier property ready for Phase 14 (acute tier awareness)
- Phase 14 can call classify_tier(now) in coordinator update cycle, then branch acute detection on activity_tier
- No blockers

---
*Phase: 13-tier-classification*
*Completed: 2026-04-02*
