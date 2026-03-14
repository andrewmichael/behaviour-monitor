---
phase: 06-dead-code-removal
plan: 02
subsystem: tests
tags: [dead-code, tests, cleanup]

requires:
  - 06-01

provides:
  - tests/test_sensor.py without ML stub test methods
  - tests/test_coordinator.py without stub key assertions

affects: [07-config-redesign]

tech-stack:
  added: []
  patterns:
    - "Remove test methods for sensors that no longer exist rather than marking skip"

key-files:
  created: []
  modified:
    - tests/test_sensor.py
    - tests/test_coordinator.py

key-decisions:
  - "TestDeprecatedSensorStubs class deleted entirely — all its methods referenced sensors removed in Plan 01"
  - "ml_status references retained in test_baseline_confidence_extra_attrs — these test the data key, not the removed sensor"

metrics:
  duration: ~2min
  completed: 2026-03-14
---

# Phase 6 Plan 2: Dead Code Removal — Test Alignment Summary

**Removed 17 test methods and 1 test class referencing deprecated ML sensor keys no longer present in SENSOR_DESCRIPTIONS**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-14T11:22:51Z
- **Completed:** 2026-03-14T11:24:22Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Deleted 9 test methods from `TestSensorDescriptions` covering `ml_status`, `ml_training_remaining`, and `cross_sensor_patterns` sensor keys
- Deleted entire `TestDeprecatedSensorStubs` class (14 test methods including all 3 stub groups and a 14-entry count check)
- Removed `ml_status_stub`, `ml_training_stub`, `cross_sensor_stub` from `required_keys` in `test_async_update_data_returns_dict_with_all_keys`
- Deleted `test_async_update_data_ml_status_stub` method from coordinator tests
- Full test suite: 321 passed, 0 failures

## Task Commits

1. **Task 1: Remove ML stub test methods from test_sensor.py** - `ec9e387` (refactor)
2. **Task 2: Update coordinator tests to remove stub key assertions** - `818ead9` (refactor)

## Files Created/Modified

- `tests/test_sensor.py` — Removed 228 lines: deleted `test_cross_sensor_patterns_sensor`, `test_cross_sensor_patterns_extra_attrs`, 5 `test_ml_status_*` methods, `test_ml_training_remaining_sensor`, `test_ml_training_remaining_extra_attrs`, and entire `TestDeprecatedSensorStubs` class
- `tests/test_coordinator.py` — Removed 11 lines: stripped 3 stub keys from required_keys list, deleted `test_async_update_data_ml_status_stub` method

## Decisions Made

- `TestDeprecatedSensorStubs` class deleted entirely rather than leaving empty — no remaining methods once all stub groups removed
- Remaining `ml_status` references in `test_baseline_confidence_extra_attrs` are correct — they test the `baseline_confidence` sensor reading the `ml_status` data key (still emitted by coordinator), not the removed `ml_status` sensor description

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- `tests/test_sensor.py` exists: FOUND
- `tests/test_coordinator.py` exists: FOUND
- Commit `ec9e387` exists: FOUND
- Commit `818ead9` exists: FOUND
- grep for stub keys in tests/: Clean (0 matches)
- Full test suite: 321 passed

---
*Phase: 06-dead-code-removal*
*Completed: 2026-03-14*
