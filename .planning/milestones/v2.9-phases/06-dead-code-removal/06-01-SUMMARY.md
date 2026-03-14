---
phase: 06-dead-code-removal
plan: 01
subsystem: integration
tags: [dead-code, constants, sensors, coordinator, cleanup]

requires: []

provides:
  - sensor.py SENSOR_DESCRIPTIONS without three deprecated ML stub entries
  - coordinator.py _async_update_data and _build_safe_defaults without ml_status_stub/ml_training_stub/cross_sensor_stub keys
  - const.py cleaned of 15 legacy constants and 7 unused CONF_* names

affects: [06-02-tests, 07-config-redesign]

tech-stack:
  added: []
  patterns:
    - "Deprecated sensor stubs removed entirely rather than left with deprecation markers"
    - "CONF_* constants only defined for keys actively consumed in v1.1 config flow and coordinator"

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/sensor.py
    - custom_components/behaviour_monitor/coordinator.py
    - custom_components/behaviour_monitor/const.py

key-decisions:
  - "ATTR_ML_STATUS import retained in sensor.py — still consumed by baseline_confidence extra_attrs_fn"
  - "ATTR_CROSS_SENSOR_PATTERNS import removed — only referenced in deleted cross_sensor_patterns description"
  - "ml_status and cross_sensor_patterns data keys kept in coordinator output — consumed by baseline_confidence sensor"

patterns-established:
  - "Stub sensor removal: delete BehaviourMonitorSensorDescription entries and any imports exclusively used by those entries"

requirements-completed: [DEBT-01, DEBT-02, DEBT-03]

duration: 3min
completed: 2026-03-14
---

# Phase 6 Plan 1: Dead Code Removal — Sensor Stubs and Legacy Constants Summary

**Removed 3 deprecated ML sensor descriptions, 3 coordinator stub dict keys, 15 legacy constants, and 7 unused CONF_* names across sensor.py, coordinator.py, and const.py**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-14T07:38:50Z
- **Completed:** 2026-03-14T07:41:18Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Removed cross_sensor_patterns, ml_status, and ml_training_remaining stub sensor descriptions from SENSOR_DESCRIPTIONS
- Stripped ml_status_stub, ml_training_stub, and cross_sensor_stub keys from both coordinator data dicts
- Deleted the legacy constants block (SENSITIVITY_THRESHOLDS, ML_CONTAMINATION, and 13 others) and 7 dead CONF_* names from const.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove three deprecated sensor descriptions from sensor.py** - `27791e6` (refactor)
2. **Task 2: Remove coordinator stub keys from coordinator.py** - `88ba977` (refactor)
3. **Task 3: Remove dead legacy constants and unused CONF_* from const.py** - `9c98b17` (refactor)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `custom_components/behaviour_monitor/sensor.py` - Removed 3 deprecated BehaviourMonitorSensorDescription entries; removed ATTR_CROSS_SENSOR_PATTERNS import
- `custom_components/behaviour_monitor/coordinator.py` - Removed stub keys from _async_update_data and _build_safe_defaults return dicts
- `custom_components/behaviour_monitor/const.py` - Removed legacy constants block (lines 128-163) and 7 unused CONF_* definitions

## Decisions Made

- ATTR_ML_STATUS import kept in sensor.py because baseline_confidence still references it in its extra_attrs_fn
- ml_status and cross_sensor_patterns data keys kept in coordinator output — these feed the baseline_confidence sensor's extra_attrs_fn and are not stubs

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all three files parse cleanly after edits. Lint output shows only pre-existing style warnings (E702/E701 semicolons in coordinator.py) and mypy import-not-found errors for the uninstalled homeassistant package; none are caused by or related to this plan's changes.

## Next Phase Readiness

- Plan 02 (test updates) can now proceed — tests referencing the removed sensor keys and constants will need updating
- const.py has space for the new CONF_* entries required by Phase 7 config redesign

---
*Phase: 06-dead-code-removal*
*Completed: 2026-03-14*
