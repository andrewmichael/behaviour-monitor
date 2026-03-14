---
phase: 09-alert-suppression
plan: 02
subsystem: notifications
tags: [alert-suppression, config-flow, homeassistant, migration, tdd]

# Dependency graph
requires:
  - phase: 09-01
    provides: CONF_ALERT_REPEAT_INTERVAL and DEFAULT_ALERT_REPEAT_INTERVAL constants in const.py
provides:
  - CONF_ALERT_REPEAT_INTERVAL field in options/config schema (NumberSelector, 30-1440 min)
  - v5->v6 migration adding alert_repeat_interval=240 to existing config entries
  - BehaviourMonitorConfigFlow.VERSION == 6
  - STORAGE_VERSION == 6
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Schema parameter pattern: each configurable field has a corresponding _default parameter in _build_data_schema"
    - "Migration chain: each version bump uses setdefault to add new keys without overwriting existing values"

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/config_flow.py
    - custom_components/behaviour_monitor/__init__.py
    - custom_components/behaviour_monitor/const.py
    - tests/test_config_flow.py
    - tests/test_init.py

key-decisions:
  - "STORAGE_VERSION and ConfigFlow.VERSION both bumped to 6 simultaneously to keep storage and config entry versions aligned"
  - "alert_repeat_interval placed after notification_cooldown in schema — groups notification-related fields together"

patterns-established:
  - "Version bump pattern: add migration block in __init__.async_migrate_entry + bump VERSION in ConfigFlow + bump STORAGE_VERSION in const.py in a single task"

requirements-completed: [SUPR-02, SUPR-01]

# Metrics
duration: 6min
completed: 2026-03-14
---

# Phase 09 Plan 02: Alert Suppression — Config Flow and Migration Summary

**alert_repeat_interval wired into HA options UI with NumberSelector (30-1440 min) and v5->v6 migration silently upgrades existing installations to default 240 minutes**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-14T18:12:52Z
- **Completed:** 2026-03-14T18:18:16Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Added `CONF_ALERT_REPEAT_INTERVAL` field to config/options schema as a NumberSelector (min=30, max=1440, step=30, unit=minutes)
- Options flow pre-fills current value from `entry.data` with `DEFAULT_ALERT_REPEAT_INTERVAL` fallback; `updated_data.update(user_input)` propagates submitted value automatically
- Added v5->v6 migration block using `setdefault` — existing entries without the key get 240 minutes; entries with custom value are preserved
- Bumped `BehaviourMonitorConfigFlow.VERSION` and `STORAGE_VERSION` to 6
- 349 total tests passing (8 new tests added, 7 existing tests updated for v6 reality)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for alert_repeat_interval in config flow** - `01aafe9` (test)
2. **Task 1 GREEN: Add alert_repeat_interval field to config_flow.py** - `8b43594` (feat)
3. **Task 2 RED: Failing tests for v5->v6 migration and VERSION=6** - `9ba0cea` (test)
4. **Task 2 GREEN: Add v5->v6 migration and bump schema VERSION to 6** - `613730c` (feat)

_Note: TDD tasks have multiple commits (test RED -> feat GREEN)_

## Files Created/Modified
- `custom_components/behaviour_monitor/config_flow.py` - Added CONF_ALERT_REPEAT_INTERVAL import, alert_repeat_interval_default parameter, NumberSelector field in schema, current value read in options flow, VERSION bumped to 6
- `custom_components/behaviour_monitor/__init__.py` - Added CONF_ALERT_REPEAT_INTERVAL import, v5->v6 migration block
- `custom_components/behaviour_monitor/const.py` - STORAGE_VERSION bumped from 5 to 6
- `tests/test_config_flow.py` - 5 new tests for alert_repeat_interval schema/options flow; test_version_is_5 renamed to test_version_is_6
- `tests/test_init.py` - 3 new TestMigrateEntryV5ToV6 tests; updated 7 existing migration tests for v6 chain (call counts, version numbers)

## Decisions Made
- STORAGE_VERSION and ConfigFlow.VERSION both bumped to 6 simultaneously — the plan explicitly required both to stay aligned
- alert_repeat_interval placed in schema after notification_cooldown to keep notification-related fields grouped

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing migration tests to reflect new v5->v6 migration step**
- **Found during:** Task 2 (GREEN phase — running full test suite after implementation)
- **Issue:** Seven existing tests in test_init.py and test_config_flow.py expected version=5 as the terminal migration version, expected specific call counts (e.g., 3 calls from v2), and checked `call_args` (last call) for v5-specific data — all invalid after adding v5->v6 step
- **Fix:** Updated test names and assertions: terminal version=5 -> version=6; call counts +1; v4->v5 data assertions now use `call_args_list[0]` instead of `call_args`
- **Files modified:** tests/test_init.py, tests/test_config_flow.py
- **Verification:** All 349 tests pass
- **Committed in:** `613730c` (Task 2 implementation commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — existing tests described superseded behavior after migration chain extended)
**Impact on plan:** Required correction for test suite validity. Tests now accurately describe the current migration chain ending at v6.

## Issues Encountered
None — implementation followed the plan specification exactly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Alert repeat interval is now fully user-configurable via HA options UI
- STORAGE_VERSION and ConfigFlow.VERSION both at 6
- Existing installations auto-migrated to v6 with alert_repeat_interval=240 on next HA start
- Phase 09 complete — coordinator suppression (Plan 01) and config/migration (Plan 02) are both done

---
*Phase: 09-alert-suppression*
*Completed: 2026-03-14*

## Self-Check: PASSED

- FOUND: custom_components/behaviour_monitor/config_flow.py
- FOUND: custom_components/behaviour_monitor/__init__.py
- FOUND: custom_components/behaviour_monitor/const.py
- FOUND: tests/test_config_flow.py
- FOUND: tests/test_init.py
- FOUND: .planning/phases/09-alert-suppression/09-02-SUMMARY.md
- FOUND commit: 01aafe9 (Task 1 RED — failing config flow tests)
- FOUND commit: 8b43594 (Task 1 GREEN — config flow implementation)
- FOUND commit: 9ba0cea (Task 2 RED — failing migration tests)
- FOUND commit: 613730c (Task 2 GREEN — migration + VERSION bump)
- All 349 tests passing
