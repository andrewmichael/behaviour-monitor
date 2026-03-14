---
phase: 07-config-flow-additions
plan: "01"
subsystem: config-flow
tags: [config-flow, constants, migration, storage-version]
dependency_graph:
  requires: []
  provides: [CONF_LEARNING_PERIOD, CONF_TRACK_ATTRIBUTES, v5-migration]
  affects: [config_flow.py, const.py, __init__.py]
tech_stack:
  added: []
  patterns: [voluptuous-schema-extension, ha-migration-pattern]
key_files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/config_flow.py
    - custom_components/behaviour_monitor/__init__.py
decisions:
  - "ATTR_CROSS_SENSOR_PATTERNS removed — confirmed unused after phase 6 cleanup"
  - "New fields placed after CONF_HISTORY_WINDOW_DAYS in schema — grouped with learning configuration"
  - "Expected test failures accepted per plan — test_version_is_4 and migration tests updated in Plan 02"
metrics:
  duration: "~3 minutes"
  completed: "2026-03-14"
---

# Phase 7 Plan 01: Config Flow Additions — Constants and Migration Summary

**One-liner:** Added CONF_LEARNING_PERIOD and CONF_TRACK_ATTRIBUTES to const.py (STORAGE_VERSION=5), exposed both fields in config flow initial setup and options, and added v4->v5 migration that injects defaults into existing installs.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add new constants and bump STORAGE_VERSION in const.py | 94d8cd2 | const.py |
| 2 | Add new fields to config_flow.py (initial setup and options) | ffc566f | config_flow.py |
| 3 | Add v4->v5 migration block to __init__.py | 07365d4 | __init__.py |

## Changes Made

### const.py
- Added `CONF_LEARNING_PERIOD: Final = "learning_period"` and `CONF_TRACK_ATTRIBUTES: Final = "track_attributes"` under new "v2.9 config keys" block
- Added `DEFAULT_LEARNING_PERIOD_DAYS: Final = 7` and `DEFAULT_TRACK_ATTRIBUTES: Final = True` defaults
- Bumped `STORAGE_VERSION` from 4 to 5
- Removed `ATTR_CROSS_SENSOR_PATTERNS` (unused after phase 6 cleanup)

### config_flow.py
- Imported all four new const symbols
- Added `learning_period_default` and `track_attributes_default` keyword params to `_build_data_schema()`
- Added `CONF_LEARNING_PERIOD` (NumberSelector, min=1, max=30, default=7 days) and `CONF_TRACK_ATTRIBUTES` (BooleanSelector) fields after `CONF_HISTORY_WINDOW_DAYS`
- Bumped `BehaviourMonitorConfigFlow.VERSION` from 4 to 5
- Options flow reads both new fields from config entry data and pre-populates schema

### __init__.py
- Imported four new const symbols
- Added `if config_entry.version < 5:` migration block with `setdefault` calls for both new keys
- Block calls `async_update_entry` with `version=5` and logs the migration
- Updated `async_migrate_entry` docstring to include v4->v5 description

## Deviations from Plan

None — plan executed exactly as written.

## Test Impact

Expected failures (per plan — Plan 02 adds updated test coverage):
- `tests/test_config_flow.py::TestBehaviourMonitorConfigFlow::test_version_is_4` — asserts VERSION==4, now 5
- `tests/test_init.py::TestStorageVersion::test_storage_version_is_4` — asserts STORAGE_VERSION==4, now 5
- Several `TestMigrateEntry` tests — v2/v3 entries now also run v5 migration block, altering call count/args

All other tests (21/22 config_flow, 18/28 init) pass unchanged.

## Self-Check: PASSED

- const.py: FOUND
- config_flow.py: FOUND
- __init__.py: FOUND
- 07-01-SUMMARY.md: FOUND
- Commit 94d8cd2: FOUND
- Commit ffc566f: FOUND
- Commit 07365d4: FOUND
