---
phase: 05-integration
plan: 03
subsystem: testing
tags: [sensor, config-flow, migration, pytest, v1.1, cleanup]

# Dependency graph
requires:
  - phase: 05-02
    provides: v1.1 coordinator with learning_status in data contract, no analyzer shim needed

provides:
  - sensor.py with no coord.analyzer references — reads exclusively from coordinator.data
  - test_config_flow.py rewritten for v1.1 schema (inactivity_multiplier, drift_sensitivity, no ML)
  - test_init.py updated with service registration tests (routine_reset + all 5 services)
  - test_sensor.py updated — baseline_confidence extra_attrs reads learning_status from data
  - test_coordinator.py updated — test_initialization checks v1.1 engines directly
  - analyzer.py and ml_analyzer.py deleted (replaced by routine_model + detectors)
  - test_analyzer.py and test_ml_analyzer.py deleted
  - coordinator.py analyzer shim removed (no longer needed)
  - Full test suite: 343 tests pass

affects: [future plans using coordinator data contract, sensor platform, service registration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - sensor extra_attrs reads from coordinator.data keys, not coordinator method calls
    - config flow tests use v4 keys (inactivity_multiplier, drift_sensitivity) not v2 ML keys
    - service registration verified in test_init.py via async_register call_args inspection

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/sensor.py
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_sensor.py
    - tests/test_config_flow.py
    - tests/test_init.py
    - tests/test_coordinator.py
  deleted:
    - custom_components/behaviour_monitor/analyzer.py
    - custom_components/behaviour_monitor/ml_analyzer.py
    - tests/test_analyzer.py
    - tests/test_ml_analyzer.py

key-decisions:
  - "Deleted coord.analyzer shim from coordinator.py once sensor.py was updated to read learning_status from data"
  - "test_config_flow.py completely rewritten with v4 keys — old ML tests tested against config flow that no longer accepts ML options"
  - "test_init.py extended rather than rewritten — existing migration tests already correct, added service registration tests"

patterns-established:
  - "Sensor extra_attrs_fn reads from coordinator.data dict keys — no direct coordinator method calls except monitored_entities property"
  - "Config flow tests use CONF_INACTIVITY_MULTIPLIER and CONF_DRIFT_SENSITIVITY; no ML constants in test assertions"

requirements-completed:
  - INFRA-03

# Metrics
duration: 15min
completed: 2026-03-13
---

# Phase 05 Plan 03: Integration Cleanup and Test Update Summary

**sensor.py coord.analyzer shim removed, test files rewritten for v1.1 schema, old PatternAnalyzer/MLPatternAnalyzer source and test files deleted, full 343-test suite passes**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-13T22:04:49Z
- **Completed:** 2026-03-13T22:09:53Z
- **Tasks:** 2
- **Files modified:** 6 modified, 4 deleted

## Accomplishments

- Fixed `coord.analyzer.is_learning_complete()` reference in sensor.py — now reads `learning_status` from `coordinator.data`
- Rewrote test_config_flow.py: 13 old tests → 22 new tests covering v1.1 fields (inactivity_multiplier, drift_sensitivity), VERSION=4, no ML fields
- Extended test_init.py: added service registration tests for all 5 services (routine_reset, holiday_mode x2, snooze, clear_snooze)
- Updated test_sensor.py and test_coordinator.py to not reference coord.analyzer
- Deleted 4 dead code files: analyzer.py, ml_analyzer.py, test_analyzer.py, test_ml_analyzer.py
- Removed coordinator.py analyzer shim (was labeled "removed in Plan 03")

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix sensor.py coord.analyzer reference** - `be0d44a` (fix)
2. **Task 2: Rewrite test files for v1.1, delete old analyzer code** - `5204e2c` (feat)

**Plan metadata:** (docs commit pending)

## Files Created/Modified

- `custom_components/behaviour_monitor/sensor.py` - Updated baseline_confidence extra_attrs_fn to read from data.learning_status
- `custom_components/behaviour_monitor/coordinator.py` - Removed coord.analyzer shim (2 lines)
- `tests/test_sensor.py` - Updated baseline_confidence extra_attrs test; removed coord.analyzer from mock_coordinator fixture
- `tests/test_config_flow.py` - Complete rewrite: v1.1 schema tests, VERSION=4, inactivity_multiplier/drift_sensitivity round-trips, no ML tests
- `tests/test_init.py` - Added service registration tests for routine_reset and all 5 services
- `tests/test_coordinator.py` - Updated test_initialization to check _routine_model/_acute_detector/_drift_detector attributes
- **Deleted:** `custom_components/behaviour_monitor/analyzer.py`
- **Deleted:** `custom_components/behaviour_monitor/ml_analyzer.py`
- **Deleted:** `tests/test_analyzer.py`
- **Deleted:** `tests/test_ml_analyzer.py`

## Decisions Made

- Removed the `coord.analyzer` shim from coordinator.py immediately after fixing sensor.py — the shim comment explicitly said "removed in Plan 03" and keeping it would be dead code
- Completely rewrote test_config_flow.py rather than patching old tests — the old tests submitted ML keys (enable_ml, retrain_period) that the new config flow never uses; better to have tests that accurately reflect the v1.1 contract
- Extended test_init.py rather than rewriting — existing migration tests (v2→v3→v4) were already correct and comprehensive; only gap was service registration coverage

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed dead coordinator.py analyzer shim**
- **Found during:** Task 2 (after fixing sensor.py)
- **Issue:** coordinator.py had `self.analyzer = type("_S", ...)()` shim that was labeled "removed in Plan 03" — keeping it after sensor.py no longer needs it is dead code and grep would still show "analyzer" references
- **Fix:** Deleted the 2-line shim from coordinator.__init__; updated test_coordinator.py test_initialization to check `_routine_model`, `_acute_detector`, `_drift_detector` instead
- **Files modified:** coordinator.py, tests/test_coordinator.py
- **Verification:** Full test suite still passes (343 tests)
- **Committed in:** 5204e2c (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - dead code removal)
**Impact on plan:** Necessary cleanup; plan explicitly marked the shim for Plan 03 removal.

## Issues Encountered

None — plan executed cleanly with one expected cleanup.

## Next Phase Readiness

- Phase 05 integration complete: sensor.py, coordinator.py, config_flow.py, __init__.py all use v1.1 data contract
- All test files updated for v1.1 architecture
- Old analyzer-era code fully removed (no references to PatternAnalyzer or MLPatternAnalyzer)
- Full test suite (343 tests) passes — integration is complete

---
*Phase: 05-integration*
*Completed: 2026-03-13*
