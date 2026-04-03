---
phase: 16-config-ui-and-migration
plan: 01
subsystem: config
tags: [config-flow, migration, ha-selector, tier-override]

# Dependency graph
requires:
  - phase: 15-coordinator-integration
    provides: classify_tier wiring in coordinator day-change block
provides:
  - CONF_ACTIVITY_TIER_OVERRIDE constant and DEFAULT_ACTIVITY_TIER_OVERRIDE
  - Config v7->v8 migration with setdefault pattern
  - SelectSelector dropdown for tier override in config UI
  - Coordinator override application after classify_tier
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [setdefault migration chain, SelectSelector dropdown for enum-like config]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/__init__.py
    - custom_components/behaviour_monitor/config_flow.py
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_config_flow.py
    - tests/test_init.py
    - tests/test_coordinator.py

key-decisions:
  - "STORAGE_VERSION and ConfigFlow.VERSION both bumped to 8 simultaneously -- consistent with Phase 9 and 11 pattern"
  - "Override applied AFTER classify_tier in day-change block -- diagnostic auto-classification still runs, effective tier is overridden"
  - "SelectSelector with Auto/High/Medium/Low options placed after drift_sensitivity in schema"

patterns-established:
  - "setdefault migration chain v2->v8 with 6 cascading steps"

requirements-completed: [CFG-01, CFG-02]

# Metrics
duration: 8min
completed: 2026-04-03
---

# Phase 16 Plan 01: Config UI and Migration Summary

**Activity tier override SelectSelector in config UI with v7->v8 migration and coordinator wiring**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-03T10:57:46Z
- **Completed:** 2026-04-03T11:05:48Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- CONF_ACTIVITY_TIER_OVERRIDE and DEFAULT_ACTIVITY_TIER_OVERRIDE constants defined in const.py
- Config migration v7->v8 injects activity_tier_override="auto" via setdefault, preserving existing values
- SelectSelector dropdown (Auto/High/Medium/Low) added to config schema and options flow
- Coordinator reads override from config entry and applies it after daily reclassification
- All 449 tests pass including 12 new tests across config_flow, init, and coordinator

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for tier override config UI and migration** - `852904f` (test)
2. **Task 1 GREEN: Add constants, migration, and config UI** - `d366c17` (feat)
3. **Task 2 RED: Failing tests for coordinator tier override** - `264f8f7` (test)
4. **Task 2 GREEN: Wire tier override into coordinator** - `4e9bbd2` (feat)

## Files Created/Modified
- `custom_components/behaviour_monitor/const.py` - Added CONF_ACTIVITY_TIER_OVERRIDE, DEFAULT_ACTIVITY_TIER_OVERRIDE; bumped STORAGE_VERSION to 8
- `custom_components/behaviour_monitor/__init__.py` - Added v7->v8 migration block with setdefault pattern
- `custom_components/behaviour_monitor/config_flow.py` - Added SelectSelector for tier override in schema; VERSION bumped to 8; options flow reads and passes override
- `custom_components/behaviour_monitor/coordinator.py` - Reads override on init; applies after classify_tier in day-change block
- `tests/test_config_flow.py` - Added 3 new tests (version, schema, options flow); updated existing version tests
- `tests/test_init.py` - Added 4 new v7->v8 migration tests; updated all cascade tests for v8 final version
- `tests/test_coordinator.py` - Added 4 new tier override tests (read, default, auto-preserve, high-override)

## Decisions Made
- STORAGE_VERSION and ConfigFlow.VERSION both bumped to 8 simultaneously -- consistent with Phase 9 and 11 pattern
- Override applied AFTER classify_tier in day-change block so diagnostic auto-classification still runs
- SelectSelector with Auto/High/Medium/Low options placed after drift_sensitivity in schema to group detection-related fields

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test assertions for cascade migration counts**
- **Found during:** Task 1 (test writing)
- **Issue:** All existing migration tests that checked final version or call_count needed updating since v7->v8 adds one more step
- **Fix:** Updated all cascade migration tests (v2->v8 = 6 calls, v3->v8 = 5 calls, v4->v8 = 4 calls, v5->v8 = 3 calls, v6->v8 = 2 calls) and switched from `.call_args` to `.call_args_list[index]` where needed
- **Files modified:** tests/test_init.py
- **Verification:** All 449 tests pass

**2. [Rule 1 - Bug] Fixed coordinator test timezone mismatch**
- **Found during:** Task 2 (coordinator tests)
- **Issue:** `_build_sensor_data` raised TypeError on datetime subtraction (offset-naive vs offset-aware) during day-change tests
- **Fix:** Patched `_build_sensor_data` return value in day-change tests to isolate override verification; mocked `classify_tier` for deterministic auto-preserve test
- **Files modified:** tests/test_coordinator.py
- **Verification:** All 4 tier override tests pass

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes necessary for test correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed items above.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data paths are fully wired.

## Next Phase Readiness
- Phase 16 is the final phase of v3.1 milestone
- All config UI, migration, and coordinator wiring complete
- Ready for milestone completion

---
*Phase: 16-config-ui-and-migration*
*Completed: 2026-04-03*
