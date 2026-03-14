---
phase: 05-integration
plan: 01
subsystem: config
tags: [home-assistant, config-flow, migration, const]

# Dependency graph
requires:
  - phase: 04-detection-engines
    provides: CUSUM_PARAMS, DriftDetector, AcuteDetector — v1.1 detection constants already in const.py
provides:
  - CONF_INACTIVITY_MULTIPLIER, CONF_DRIFT_SENSITIVITY, SERVICE_ROUTINE_RESET constants in const.py
  - STORAGE_VERSION=4 in const.py
  - v3->v4 config migration removing old sigma/ML keys and adding new v1.1 defaults
  - BehaviourMonitorConfigFlow.VERSION=4 with inactivity_multiplier + drift_sensitivity fields
  - routine_reset service registered/unregistered in __init__.py
  - conftest mock_config_entry with v4 data keys
affects: [05-02, coordinator, sensor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Migration chaining: v2->v3->v4 in single async_migrate_entry; each block guards on version < N"
    - "Shared schema builder: _build_data_schema() helper reduces duplication between config and options flows"

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/__init__.py
    - custom_components/behaviour_monitor/config_flow.py
    - tests/conftest.py
    - tests/test_init.py
    - tests/test_config_flow.py

key-decisions:
  - "Legacy constants (SENSITIVITY_THRESHOLDS, ML_CONTAMINATION, etc.) retained in const.py until old analyzer/coordinator are replaced in Plan 02 — removes would break old files not yet replaced"
  - "Shared _build_data_schema() helper for both initial config and options flow to avoid schema duplication"
  - "Migration guards: both v<3 and v<4 blocks run independently in one call, enabling v2->v4 in a single entry migration"

patterns-established:
  - "Config migration: dict copy + pop pattern, setdefault for new keys, never mutate config_entry.data directly"
  - "Service registration: async handler defined inline, registered/unregistered symmetrically in setup/unload"

requirements-completed:
  - INFRA-03

# Metrics
duration: 5min
completed: 2026-03-13
---

# Phase 5 Plan 01: Config Infrastructure v1.1 Summary

**Config flow rewritten for v1.1: ML/sigma fields replaced by inactivity_multiplier + drift_sensitivity selectors, STORAGE_VERSION bumped to 4, v3->v4 migration chain added, and routine_reset service wired into __init__.py**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-13T21:32:39Z
- **Completed:** 2026-03-13T21:37:10Z
- **Tasks:** 3
- **Files modified:** 6 (3 source + 2 test + conftest)

## Accomplishments
- const.py has CONF_INACTIVITY_MULTIPLIER, CONF_DRIFT_SENSITIVITY, SERVICE_ROUTINE_RESET and STORAGE_VERSION=4
- __init__.py migrates v2/v3 entries to v4 (removing old sigma/ML keys, adding new defaults), registers routine_reset service
- config_flow.py VERSION=4 shows only v1.1 fields (no ML/sigma); conftest fixture uses v4 data keys
- All 442 tests pass (5 test fixes required for updated migration version and schema)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add new config constants and clean up obsolete ML constants in const.py** - `8bed71f` (feat)
2. **Task 2: Extend config migration to v4 and register routine_reset service in __init__.py** - `6e4c9b2` (feat)
3. **Task 3: Rewrite config flow with v1.1 options and update conftest fixture** - `349970b` (feat)

## Files Created/Modified
- `custom_components/behaviour_monitor/const.py` - Added CONF_INACTIVITY_MULTIPLIER, CONF_DRIFT_SENSITIVITY, SERVICE_ROUTINE_RESET; STORAGE_VERSION=4; legacy constants retained for backward compat with old analyzer/coordinator
- `custom_components/behaviour_monitor/__init__.py` - v3->v4 migration block, routine_reset service register/unregister
- `custom_components/behaviour_monitor/config_flow.py` - VERSION=4, new field set, _build_data_schema() helper
- `tests/conftest.py` - mock_config_entry updated to v4 data keys with self.version=4
- `tests/test_init.py` - Updated 4 tests for v4 migration (storage version, migration chain, v3->v4 behavior)
- `tests/test_config_flow.py` - Updated test_step_init_preserves_defaults for v4 keys

## Decisions Made
- Legacy constants (SENSITIVITY_THRESHOLDS, ML_CONTAMINATION, MAX_VARIANCE_MULTIPLIER, etc.) retained in const.py. The plan intended them removed, but old `analyzer.py`, `coordinator.py`, and `ml_analyzer.py` still import them and will be replaced in Plan 02. Removing them now would break all tests. They are marked in a "Legacy" section for removal in Plan 02.
- Introduced `_build_data_schema()` helper function to avoid duplicating the full schema between `async_step_user` and `async_step_init`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Retained legacy constants that old analyzer/coordinator still reference**
- **Found during:** Task 1 (const.py cleanup)
- **Issue:** Removing SENSITIVITY_THRESHOLDS, ML_CONTAMINATION, MAX_VARIANCE_MULTIPLIER, MIN_BUCKET_OBSERVATIONS, etc. caused ImportError in analyzer.py and ml_analyzer.py which import them; these files are v1.0 code not yet replaced
- **Fix:** Re-added removed constants in a clearly marked "Legacy" section of const.py; they will be removed when Plan 02 replaces coordinator/analyzer
- **Files modified:** custom_components/behaviour_monitor/const.py
- **Verification:** `make test` passes (442 tests)
- **Committed in:** 8bed71f (Task 1 commit)

**2. [Rule 1 - Bug] Fixed 5 test failures caused by updated migration version**
- **Found during:** Task 3 (final test run)
- **Issue:** Tests asserting STORAGE_VERSION==3, migration version==3, and "v3 makes no changes" all broke because version is now 4
- **Fix:** Updated test assertions to match v4 migration behavior: storage version 4, two migration calls for v2 entry, v3 entry migrates to v4, new test_migrate_v4_makes_no_changes
- **Files modified:** tests/test_init.py, tests/test_config_flow.py
- **Verification:** All 442 tests pass
- **Committed in:** 349970b (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes essential for correctness. Legacy constants are explicitly marked for removal in Plan 02.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 02 (coordinator rewrite) can read CONF_INACTIVITY_MULTIPLIER, CONF_DRIFT_SENSITIVITY from config entries
- Plan 02 should remove legacy constants block from const.py when replacing coordinator.py and analyzer.py
- routine_reset service wired; Plan 02 needs to implement `coordinator.async_routine_reset(entity_id)`

## Self-Check: PASSED

All files verified present and all commits verified in git history.

---
*Phase: 05-integration*
*Completed: 2026-03-13*
