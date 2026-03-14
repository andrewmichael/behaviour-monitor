---
phase: 11-adaptive-inactivity
plan: "02"
subsystem: config-flow
tags: [config-flow, migration, tdd, adaptive-inactivity, translations]
dependency_graph:
  requires: [11-01]
  provides: [config-ui-min-max-fields, v6-to-v7-migration, storage-version-7]
  affects: [coordinator, analyzer]
tech_stack:
  added: []
  patterns: [tdd-red-green, config-migration-cascade, voluptuous-schema, cross-field-validation]
key_files:
  created: []
  modified:
    - custom_components/behaviour_monitor/config_flow.py
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/__init__.py
    - custom_components/behaviour_monitor/translations/en.json
    - tests/test_config_flow.py
    - tests/test_init.py
decisions:
  - "VERSION and STORAGE_VERSION both bumped to 7 in same task (consistent with Phase 9 pattern)"
  - "Existing migration test names updated to reflect v7 endpoint rather than creating parallel v6 tests"
metrics:
  duration: "~5 minutes"
  completed: "2026-03-14"
  tasks_completed: 2
  files_modified: 6
---

# Phase 11 Plan 02: Config Flow Min/Max Fields, Validation, and v6->v7 Migration Summary

Config flow updated with min/max inactivity multiplier fields, cross-field validation, renamed label, and transparent v6->v7 migration using setdefault semantics.

## What Was Built

### Task 1: Config flow — new fields, label update, min>max validation, translations (TDD)

Added two new `NumberSelector` fields to `_build_data_schema()`:
- `CONF_MIN_INACTIVITY_MULTIPLIER` (min=0.5, max=5.0, step=0.5)
- `CONF_MAX_INACTIVITY_MULTIPLIER` (min=2.0, max=20.0, step=0.5)

Added cross-field min>max validation in both `async_step_user` and `async_step_init`. When `min > max`, `errors["base"] = "inactivity_min_exceeds_max"` is returned before the entity check.

`BehaviourMonitorConfigFlow.VERSION` bumped from 6 to 7.

`translations/en.json` updated:
- `config.step.user.data`: Added `inactivity_multiplier` ("Inactivity sensitivity scaling"), `min_inactivity_multiplier`, `max_inactivity_multiplier` labels
- `config.step.user.data_description`: Added descriptions for all three new/renamed fields
- `options.step.init.data`: Added same three labels (no descriptions block per plan spec)

### Task 2: v6->v7 migration block and STORAGE_VERSION bump (TDD)

`STORAGE_VERSION` bumped from 6 to 7 in `const.py`.

`__init__.py` updated with:
- New imports: `CONF_MIN/MAX_INACTIVITY_MULTIPLIER`, `DEFAULT_MIN/MAX_INACTIVITY_MULTIPLIER`
- New migration block after the v5->v6 block:
  ```python
  if config_entry.version < 7:
      new_data.setdefault(CONF_MIN_INACTIVITY_MULTIPLIER, 1.5)
      new_data.setdefault(CONF_MAX_INACTIVITY_MULTIPLIER, 10.0)
      hass.config_entries.async_update_entry(config_entry, data=new_data, version=7)
  ```

Existing migration tests updated throughout (v2, v3, v4, v5 cascade endpoints updated from v6 to v7).

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 6524b44 | feat(11-02): config flow new min/max fields, min>max validation, VERSION=7 |
| 2 | 10b43d0 | feat(11-02): v6->v7 migration block and STORAGE_VERSION bump |

## Verification

```
403 passed, 3 warnings
```

- `python -m pytest tests/test_config_flow.py -k min_exceeds_max` — 2 passed
- `python -m pytest tests/test_init.py -k v7` — 6 passed
- Full suite: 403 passed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing migration tests to reflect new v7 cascade endpoint**
- **Found during:** Task 2 GREEN phase
- **Issue:** Seven existing tests asserted migration ended at v6 (call counts and version numbers). With the v6->v7 block added, these became incorrect.
- **Fix:** Updated test names and assertions to expect v7 as the final migration version, and updated call counts accordingly (e.g., v5 entry now gets 2 update calls: v5->v6 and v6->v7).
- **Files modified:** tests/test_init.py
- **Commit:** 10b43d0

## Decisions Made

- VERSION and STORAGE_VERSION both bumped to 7 in the same task (Task 2), consistent with Phase 9 pattern of keeping storage and config entry versions aligned.
- Existing migration test names updated to reflect the v7 endpoint rather than adding parallel duplicate tests.

## Self-Check

Checking files exist and commits are present.
