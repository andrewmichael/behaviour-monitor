---
phase: 03-foundation-and-routine-model
plan: "02"
subsystem: infra
tags: [home-assistant, config-entry, migration, sensor, deprecation]

requires:
  - phase: 03-01
    provides: RoutineModel with DEFAULT_HISTORY_WINDOW_DAYS=28 constant

provides:
  - STORAGE_VERSION=3 in const.py
  - CONF_HISTORY_WINDOW_DAYS and DEFAULT_HISTORY_WINDOW_DAYS constants
  - async_migrate_entry in __init__.py (v2->v3 config entry migration)
  - Stub value_fns for ml_status, ml_training_remaining, cross_sensor_patterns sensors

affects:
  - 03-03 (coordinator rewrite — coordinator still imports ML constants until Plan 03 removes them)
  - config_flow (history_window_days will be exposed in options flow)

tech-stack:
  added: []
  patterns:
    - HA async_migrate_entry pattern: build new_data dict, pop deprecated keys, setdefault new keys, call async_update_entry with version
    - Deprecated sensor stub: fixed lambda value_fn + extra_attrs_fn with deprecated=True flag

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/__init__.py
    - custom_components/behaviour_monitor/sensor.py
    - tests/test_init.py
    - tests/test_sensor.py

key-decisions:
  - "ML constants NOT removed from const.py in this plan — coordinator.py still imports them; cleanup deferred to Plan 03"
  - "async_migrate_entry uses dict copy + pop pattern, NOT direct mutation of config_entry.data, per HA developer docs"
  - "Deprecated sensor extra_attrs include removal_version=1.2 to give users a forward-looking signal"

patterns-established:
  - "Deprecation stub pattern: value_fn returns fixed sentinel; extra_attrs_fn returns {deprecated: True, removal_version: X.Y}"
  - "Config migration pattern: copy data dict, pop old keys, setdefault new keys, call async_update_entry(version=N)"

requirements-completed: [INFRA-01, INFRA-02]

duration: 4min
completed: 2026-03-13
---

# Phase 03 Plan 02: Migration and Sensor Deprecation Summary

**v2->v3 config entry migration via async_migrate_entry removes 4 ML keys, adds history_window_days=28, and three deprecated ML sensors return safe stub values instead of going unavailable**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-13T19:32:57Z
- **Completed:** 2026-03-13T19:36:18Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Config entry migration: v2 entries auto-upgrade to v3 on HA startup, removing enable_ml/retrain_period/ml_learning_period/cross_sensor_window and adding history_window_days=28
- Three deprecated sensors (ml_status, ml_training_remaining, cross_sensor_patterns) return safe stub values rather than crashing with KeyError on new coordinator data format
- 78 tests passing across test_init.py and test_sensor.py (25 + 53)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: async_migrate_entry and STORAGE_VERSION tests** - `9cbd3bb` (test)
2. **Task 1 GREEN: const.py + __init__.py migration implementation** - `e55fdb5` (feat)
3. **Task 2 RED: deprecated ML sensor stub tests** - `4dc5225` (test)
4. **Task 2 GREEN: sensor.py stub value_fns + test corrections** - `50700a3` (feat)

_Note: TDD tasks have separate test (RED) and implementation (GREEN) commits_

## Files Created/Modified

- `custom_components/behaviour_monitor/const.py` - STORAGE_VERSION 2->3, added CONF_HISTORY_WINDOW_DAYS and DEFAULT_HISTORY_WINDOW_DAYS=28
- `custom_components/behaviour_monitor/__init__.py` - Added async_migrate_entry function with v2->v3 migration logic
- `custom_components/behaviour_monitor/sensor.py` - Stubbed ml_status, ml_training_remaining, cross_sensor_patterns sensor value_fns
- `tests/test_init.py` - Added TestStorageVersion (1 test) and TestMigrateEntry (10 tests)
- `tests/test_sensor.py` - Added TestDeprecatedSensorStubs (14 tests), updated stale ML sensor tests

## Decisions Made

- ML constants (CONF_ENABLE_ML, etc.) kept in const.py for now — coordinator.py still imports them. They will be cleaned up when coordinator is rewritten in Plan 03.
- `async_migrate_entry` uses dict copy + pop pattern, never mutates config_entry.data directly, per HA developer docs.
- Deprecation stubs include `removal_version: "1.2"` in extra attributes to give users a forward signal.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated stale TestSensorDescriptions tests for deprecated sensors**
- **Found during:** Task 2 GREEN (sensor.py stub implementation)
- **Issue:** Pre-existing tests in TestSensorDescriptions tested old ml_status ("Ready", "Disabled", etc.), ml_training_remaining, and cross_sensor_patterns behavior — they now expect the old non-stub return values which conflict with the new stubs
- **Fix:** Updated 9 test assertions in TestSensorDescriptions to match stub behavior (e.g., assert result == "Removed in v1.1" instead of "Ready")
- **Files modified:** tests/test_sensor.py
- **Verification:** All 53 sensor tests pass after update
- **Committed in:** 50700a3 (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - stale test expectations)
**Impact on plan:** Necessary correctness fix — old tests were asserting pre-deprecation sensor behavior. No scope creep.

## Issues Encountered

None — plan executed smoothly with only the expected stale-test cleanup.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03 (coordinator rewrite) can now safely remove ML constants from const.py and rewrite BehaviourMonitorCoordinator to use RoutineModel
- Config entry migration infrastructure is in place — HA will call async_migrate_entry automatically when v1.0 users upgrade
- Deprecated sensor stubs keep HA dashboards stable during the transition

## Self-Check: PASSED

All files and commits verified present.

---
*Phase: 03-foundation-and-routine-model*
*Completed: 2026-03-13*
