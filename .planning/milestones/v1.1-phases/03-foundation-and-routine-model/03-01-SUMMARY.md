---
phase: 03-foundation-and-routine-model
plan: 01
subsystem: database
tags: [routine-model, activity-slot, welford, deque, serialization, tdd, pure-python]

# Dependency graph
requires: []
provides:
  - "ActivitySlot: per-slot binary (deque) and numeric (Welford) observation store"
  - "EntityRoutine: 168-slot entity baseline with confidence and daily_activity_rate"
  - "RoutineModel: top-level model with get_or_create, overall_confidence, learning_status"
  - "is_binary_state() module helper for entity type detection"
  - "Full to_dict/from_dict round-trip serialization on all three classes"
affects:
  - "03-02 (coordinator migration/bootstrap): consumes RoutineModel.record() and from_dict()"
  - "04-detection: AcuteDetector and DriftDetector consume expected_gap_seconds and slot_distribution"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Welford online algorithm for numerically stable incremental mean/variance"
    - "deque(maxlen=56) for O(1) auto-evicting sliding window per slot"
    - "dow * 24 + hour flat slot index (0-167)"
    - "ISO timestamp strings for serialization (no datetime objects in storage)"
    - "TDD: RED commit (failing tests) then GREEN commit (implementation)"

key-files:
  created:
    - custom_components/behaviour_monitor/routine_model.py
    - tests/test_routine_model.py
  modified: []

key-decisions:
  - "Population stdev (sqrt(M2/count)) chosen over sample stdev — sufficient for 56-item window"
  - "Sparse slot threshold MIN_SLOT_OBSERVATIONS=4 returns None — favors fewer false positives during cold-start"
  - "ActivitySlot stores only ISO timestamp strings for event_times — no datetime objects avoid HA dependency risk"
  - "expected_gap_seconds returns None for numeric slots (no binary data) — callers use slot type to select correct query"
  - "Test bug auto-fixed: test_expected_gap_seconds_sufficient was spreading events across 6 hour-slots instead of keeping them in slot 0"

patterns-established:
  - "RoutineModel API: get_or_create + record are the two entry points for coordinator wiring"
  - "EntityRoutine.confidence(now) accepts datetime parameter — no internal datetime.now() calls"
  - "RoutineModel.overall_confidence(now=None) defaults to datetime.now(tz=utc) when now not provided"

requirements-completed: [ROUTINE-01, ROUTINE-03]

# Metrics
duration: 4min
completed: 2026-03-13
---

# Phase 3 Plan 01: RoutineModel Summary

**Pure-Python 168-slot per-entity baseline model with Welford numeric stats, deque binary event tracking, proportional confidence, and full JSON round-trip serialization — zero HA imports, 63 tests passing**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-13T19:27:03Z
- **Completed:** 2026-03-13T19:30:37Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- ActivitySlot with deque(maxlen=56) binary event store and Welford online mean/variance for numerics
- EntityRoutine routing state changes to correct slot (dow*24+hour), tracking confidence proportionally, computing daily_activity_rate
- RoutineModel aggregate model with learning_status transitions (inactive/learning/ready at 0.1/0.8 thresholds)
- 63 unit tests covering all behaviors from the plan spec — no HA mocking required
- is_binary_state() module helper for entity type detection (case-insensitive)

## Task Commits

1. **RED: Failing tests for RoutineModel** - `4822bdb` (test)
2. **GREEN: RoutineModel implementation + test fix** - `8dc94b2` (feat)

## Files Created/Modified

- `custom_components/behaviour_monitor/routine_model.py` — ActivitySlot, EntityRoutine, RoutineModel classes with full serialization (422 lines)
- `tests/test_routine_model.py` — 63 unit tests across 9 test classes (559 lines)

## Decisions Made

- Population stdev `sqrt(M2/count)` chosen — appropriate for the bounded 56-item window, avoids division-by-zero for count=1 (returns 0.0 instead)
- Sparse slot guard MIN_SLOT_OBSERVATIONS=4: both expected_gap_seconds() and slot_distribution() return None below this threshold, suppressing detection for cold slots
- ISO timestamp strings stored in deque (not datetime objects) — no HA utility dependency, pure stdlib datetime.fromisoformat() for parsing
- slot_distribution() returns None for binary slots (numeric_count=0), expected_gap_seconds() returns None for numeric slots (event_times empty) — callers dispatch by entity type

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_expected_gap_seconds_sufficient test logic**
- **Found during:** GREEN phase execution
- **Issue:** Test recorded 6 events at `base + timedelta(hours=i)` — each event landed in a different hour-slot (hour 0 through 5). Slot 0 only had 1 event, not 6. expected_gap_seconds(hour=0, dow=0) returned None (1 < MIN_SLOT_OBSERVATIONS=4).
- **Fix:** Changed to `base + timedelta(minutes=i * 10)` — all 6 events stay within the same hour, populating slot 0 with 6 events
- **Files modified:** tests/test_routine_model.py
- **Verification:** 63/63 tests pass after fix
- **Committed in:** 8dc94b2 (GREEN feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in test logic)
**Impact on plan:** Test logic bug would have masked a valid implementation. Fix ensures slot routing is correctly validated.

## Issues Encountered

None beyond the test logic bug documented above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- RoutineModel API is finalized — Phase 4 AcuteDetector and DriftDetector can consume `expected_gap_seconds()` and `slot_distribution()` directly
- Phase 3 Plan 02 (coordinator migration, storage v3, stub sensors, recorder bootstrap) can now wire `RoutineModel.record()` and `RoutineModel.from_dict()` into coordinator async_setup

---
*Phase: 03-foundation-and-routine-model*
*Completed: 2026-03-13*
