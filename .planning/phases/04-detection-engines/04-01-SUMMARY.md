---
phase: 04-detection-engines
plan: 01
subsystem: detection
tags: [alert-result, acute-detector, inactivity, unusual-time, tdd, pure-python]

# Dependency graph
requires:
  - phase: 03-foundation
    provides: "EntityRoutine, ActivitySlot, MIN_SLOT_OBSERVATIONS, routine.confidence(), expected_gap_seconds()"

provides:
  - "AlertResult dataclass with to_dict() JSON serialization"
  - "AlertType enum (INACTIVITY, UNUSUAL_TIME, DRIFT) as str enum"
  - "AlertSeverity enum (LOW, MEDIUM, HIGH) as str enum"
  - "AcuteDetector with check_inactivity and check_unusual_time methods"
  - "Detection constants in const.py: DEFAULT_INACTIVITY_MULTIPLIER, SUSTAINED_EVIDENCE_CYCLES, MIN_EVIDENCE_DAYS, MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME, CUSUM_PARAMS"

affects:
  - "04-02-drift-detector (uses AlertResult, AlertType, AlertSeverity)"
  - "05-coordinator (wires AcuteDetector into polling loop)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sustained evidence: 3 consecutive cycles before any alert fires"
    - "Per-entity cycle counters reset to zero on condition clear (Pitfall 2)"
    - "Confidence gate: check_unusual_time requires confidence >= 0.3 (Pitfall 6)"
    - "Severity based on elapsed/threshold ratio: LOW (<3x), MEDIUM (3x-5x), HIGH (5x+)"

key-files:
  created:
    - custom_components/behaviour_monitor/alert_result.py
    - custom_components/behaviour_monitor/acute_detector.py
    - tests/test_alert_result.py
    - tests/test_acute_detector.py
  modified:
    - custom_components/behaviour_monitor/const.py

key-decisions:
  - "Severity ratio measured against threshold (3x expected_gap), not against expected_gap directly — LOW at 1x-3x threshold, MEDIUM at 3x-5x, HIGH at 5x+"
  - "AlertType and AlertSeverity inherit from str, Enum for direct JSON serialization without .value conversion"
  - "AcuteDetector holds per-entity cycle counters in dicts, reset on every not-met condition path to prevent stale state"
  - "check_unusual_time only checks current slot (now.hour, now.weekday()), not all slots — unusual activity at THIS time"

patterns-established:
  - "Sustained evidence pattern: every detection method increments a per-entity counter and only fires after sustained_cycles consecutive triggers"
  - "AlertResult is the universal output type for all detectors; coordinator consumes AlertResult objects uniformly"
  - "Pure-Python detector modules: zero HA imports verified by grep in tests"

requirements-completed: [ACUTE-01, ACUTE-02, ACUTE-03]

# Metrics
duration: 5min
completed: 2026-03-13
---

# Phase 4 Plan 1: Alert Types and Acute Detector Summary

**Pure-Python AcuteDetector with sustained-evidence inactivity and unusual-time detection consuming Phase 3 RoutineModel API, backed by AlertResult/AlertType/AlertSeverity shared types**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-13T20:46:34Z
- **Completed:** 2026-03-13T20:51:05Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Delivered `alert_result.py` with `AlertResult` dataclass, `AlertType` and `AlertSeverity` str enums; `to_dict()` produces JSON-safe dicts for coordinator consumption
- Extended `const.py` with detection constants: `DEFAULT_INACTIVITY_MULTIPLIER=3.0`, `SUSTAINED_EVIDENCE_CYCLES=3`, `MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME=0.3`, `CUSUM_PARAMS` dict for drift detector
- Implemented `AcuteDetector.check_inactivity` with 3-cycle sustained evidence, counter reset on clear, and severity tiers
- Implemented `AcuteDetector.check_unusual_time` with confidence gate (>= 0.3), sparse-slot detection, and 3-cycle sustained evidence
- 57 TDD tests across two test files; zero HA imports confirmed in both new modules

## Task Commits

Each task was committed atomically:

1. **Task 1: Create alert_result.py shared types and extend const.py** - `b88bf29` (feat)
2. **Task 2: Implement AcuteDetector with TDD** - `a686777` (feat)

## Files Created/Modified

- `custom_components/behaviour_monitor/alert_result.py` - AlertResult dataclass, AlertType/AlertSeverity enums; JSON-safe to_dict()
- `custom_components/behaviour_monitor/acute_detector.py` - AcuteDetector; check_inactivity, check_unusual_time, _inactivity_severity
- `custom_components/behaviour_monitor/const.py` - Added DEFAULT_INACTIVITY_MULTIPLIER, SUSTAINED_EVIDENCE_CYCLES, MIN_EVIDENCE_DAYS, MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME, CUSUM_PARAMS
- `tests/test_alert_result.py` - 28 tests for AlertResult, AlertType, AlertSeverity, and const values
- `tests/test_acute_detector.py` - 29 tests covering all detection paths, severity tiers, counter reset, and HA import guard

## Decisions Made

- **Severity ratio relative to threshold, not expected_gap:** The plan spec `"ratio 2.5x -> LOW"` means 2.5x the threshold (3x expected_gap), not 2.5x the expected_gap. Ratios relative to expected_gap would make LOW fire below the threshold. Using `severity_ratio = elapsed / threshold` yields coherent LOW/MEDIUM/HIGH tiers.
- **str enum inheritance for AlertType/AlertSeverity:** Inheriting from `(str, Enum)` means enum values are already strings; `to_dict()` uses `.value` explicitly for clarity but instances compare equal to their string values — useful for coordinator conditionals.
- **AcuteDetector per-entity counter dicts:** `_inactivity_cycles` and `_unusual_time_cycles` keyed by `entity_id` strings; all not-met code paths explicitly reset to 0 before returning None, eliminating any ghost-counter edge case.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected severity tier boundaries in test**
- **Found during:** Task 2 (severity tier tests)
- **Issue:** Test `test_severity_low_at_2_5x` used `elapsed = 2.5 * expected_gap` which is below the 3x inactivity threshold, so no alert fires. Plan behavior spec `"ratio 2.5x -> LOW"` means 2.5x the threshold, not 2.5x the expected_gap.
- **Fix:** Rewrote severity tests to compute `elapsed = threshold_ratio * threshold` and added `test_severity_boundary_exactly_1x_is_low` to confirm alerting at threshold. Updated `_inactivity_severity` to take `severity_ratio = elapsed / threshold`.
- **Files modified:** `tests/test_acute_detector.py`, `custom_components/behaviour_monitor/acute_detector.py`
- **Verification:** All 29 tests pass including boundary cases at 3.0x and 5.0x
- **Committed in:** a686777 (Task 2 commit)

**2. [Rule 2 - Lint] Removed unused pytest imports from test files**
- **Found during:** Task 2 verification (`make lint`)
- **Issue:** `import pytest` in both `test_alert_result.py` and `test_acute_detector.py` was unused (ruff F401)
- **Fix:** Removed the unused imports
- **Files modified:** `tests/test_alert_result.py`, `tests/test_acute_detector.py`
- **Verification:** `ruff check` on new files passes cleanly
- **Committed in:** a686777 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug in test boundary logic, 1 lint cleanup)
**Impact on plan:** Severity boundary fix ensures correct LOW/MEDIUM/HIGH tier assignment matches the must_haves spec. No scope creep.

## Issues Encountered

None — plan executed as specified aside from the severity ratio interpretation documented above.

## Next Phase Readiness

- `alert_result.py` shared types ready for `drift_detector.py` (plan 04-02) to import and use
- `CUSUM_PARAMS` constants in `const.py` ready for drift detector implementation
- `AcuteDetector` ready for Phase 5 coordinator wiring into the polling loop
- No blockers

---
*Phase: 04-detection-engines*
*Completed: 2026-03-13*
