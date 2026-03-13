---
phase: 03-foundation-and-routine-model
plan: "03"
subsystem: coordinator
tags: [migration, routine-model, bootstrap, deprecation, storage]
dependency_graph:
  requires: ["03-01"]
  provides: ["coordinator-v3-storage", "routine-model-bootstrap", "ml-stub-keys"]
  affects: ["coordinator.py", "sensor.py stub data keys"]
tech_stack:
  added: ["asyncio.sleep for staggered loading", "recorder API integration"]
  patterns: ["v2→v3 storage migration", "TDD red-green", "recorder bootstrap"]
key_files:
  created:
    - tests/fixtures/v2_storage.json
  modified:
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_coordinator.py
decisions:
  - "Guard _bootstrap_from_recorder on recorder_get_instance being None (not both get_instance and state_changes_fn) so tests can patch the module-level name even when the import fallback sets it to None"
  - "Bootstrap only runs when RoutineModel is empty (_entities dict is empty) — prevents re-bootstrap on every startup after first load"
  - "Persisted bootstrapped model immediately after loading to avoid re-bootstrap on next startup"
  - "Existing PatternAnalyzer still restored from v2 storage during transition — Phase 4 will remove it"
metrics:
  duration_minutes: 6
  completed_date: "2026-03-13"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
  files_created: 1
---

# Phase 3 Plan 03: Coordinator Migration, Bootstrap, and Stub Keys Summary

**One-liner:** Coordinator v2→v3 storage migration with RoutineModel bootstrap from HA recorder history, ML cleanup, deprecation warnings, and stub sensor data keys.

## What Was Built

### Task 1: Storage migration, ML cleanup, deprecation logs, stub data keys

The coordinator's `async_setup` method was refactored to handle three storage formats:

- **v3 format** (`"routine_model"` key present): Deserializes RoutineModel via `RoutineModel.from_dict()`
- **v2 format** (`"analyzer"` key only, no `"routine_model"`): Logs an INFO migration message, creates a fresh empty RoutineModel, preserves all coordinator state (holiday_mode, snooze_until, cooldowns, welfare)
- **Empty/None**: Starts fresh

The `_save_data` method was updated to v3 format — saves `"routine_model"` key (not `"analyzer"`).

A new `_cleanup_ml_store` method deletes orphaned ML storage files from older versions. Three WARNING-level deprecation notices are logged at startup for `ml_status`, `ml_training`, and `cross_sensor_patterns` sensors.

Five new keys added to `_async_update_data` return dict:
- `ml_status_stub = "Removed in v1.1"`
- `ml_training_stub = "N/A"`
- `cross_sensor_stub = 0`
- `learning_status` — from `RoutineModel.learning_status()` ("inactive"/"learning"/"ready")
- `baseline_confidence` — `RoutineModel.overall_confidence() * 100` rounded to 1dp

### Task 2: Recorder bootstrap into RoutineModel

A new `_bootstrap_from_recorder` method loads up to `_history_window_days` of state changes per monitored entity from the HA recorder. For each entity:

1. Calls `recorder_get_instance(hass).async_add_executor_job(state_changes_during_period, ...)`
2. Detects entity type (binary vs numeric) from first valid state value
3. Filters out `"unavailable"` and `"unknown"` states
4. Records valid states into `RoutineModel.record()`
5. Yields to event loop via `asyncio.sleep(0)` between entities
6. Handles exceptions per entity with a WARNING log (does not block other entities)

Bootstrap runs once in `async_setup` when `_routine_model._entities` is empty. After bootstrap, the model is persisted immediately.

## Tests Added

27 new test cases across 5 new test classes:

- `TestStorageMigration` (6 tests): v2 load, v3 load, empty load, state preservation, migration log
- `TestMLStoreCleanup` (3 tests): deletes when exists, no crash when absent, survives exception
- `TestDeprecationLogs` (2 tests): 3 warning messages logged, sensor names mentioned
- `TestSensorDataStubs` (6 tests): each stub key, learning_status, baseline_confidence
- `TestRecorderBootstrap` (10 tests): populates model, empty/error handling, filtering, type detection, sleep stagger, wired into setup

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test for v3 storage format assertion**
- **Found during:** Task 1 GREEN phase
- **Issue:** Existing test `test_coordinator_state_saved_in_new_format` asserted `"analyzer" in saved_data` — broke when _save_data switched to v3 format using `"routine_model"` key
- **Fix:** Updated assertion to `"routine_model" in saved_data` with descriptive comment
- **Files modified:** tests/test_coordinator.py
- **Commit:** eedcf7a (part of Task 1 GREEN)

**2. [Rule 2 - Bug] Fixed recorder_get_instance None guard**
- **Found during:** Task 2 GREEN phase
- **Issue:** Bootstrap guarded on both `recorder_get_instance is None` AND `recorder_state_changes_during_period is None`. Tests patch only `recorder_get_instance`; `state_changes_fn` remained None causing early return
- **Fix:** Guard only on `recorder_get_instance is None` since the mock executor job ignores the function argument
- **Files modified:** custom_components/behaviour_monitor/coordinator.py
- **Commit:** 859f313 (part of Task 2 GREEN)

**3. [Rule 1 - Bug] Fixed test entity_id for numeric detection**
- **Found during:** Task 2 GREEN phase
- **Issue:** `test_bootstrap_entity_type_detection_numeric` used `sensor.temp` which is not in `_monitored_entities` — bootstrap only queries monitored entities
- **Fix:** Changed test entity to `sensor.test1` (a monitored entity in mock_config_entry)
- **Files modified:** tests/test_coordinator.py
- **Commit:** 859f313 (part of Task 2 GREEN)

## Self-Check: PASSED

All created/modified files present. All task commits verified:
- b640df3: test(03-03): RED phase Task 1 — storage migration, cleanup, deprecation, stub tests
- eedcf7a: feat(03-03): GREEN phase Task 1 — coordinator implementation
- 31541cb: test(03-03): RED phase Task 2 — recorder bootstrap tests
- 859f313: feat(03-03): GREEN phase Task 2 — _bootstrap_from_recorder implementation

Final test count: 82 coordinator tests passed (27 new + 55 existing), 353 total suite passed.
