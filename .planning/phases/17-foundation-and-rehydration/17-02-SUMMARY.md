---
phase: 17-foundation-and-rehydration
plan: 02
subsystem: config
tags: [correlation, config-flow, migration, constants]

# Dependency graph
requires:
  - phase: none
    provides: existing const.py, config_flow.py, __init__.py patterns
provides:
  - CONF_CORRELATION_WINDOW and DEFAULT_CORRELATION_WINDOW constants
  - MIN_CO_OCCURRENCES and PMI_THRESHOLD correlation constants
  - AlertType.CORRELATION_BREAK enum member
  - STORAGE_VERSION bumped to 9
  - ConfigFlow.VERSION bumped to 9
  - v8->v9 config migration with correlation_window default
  - Correlation window NumberSelector in config UI (30-600s, default 120)
affects: [18-correlation-detection, 19-correlation-alerts, 20-correlation-sensors]

# Tech tracking
tech-stack:
  added: []
  patterns: [setdefault migration chain, NumberSelector config field]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/alert_result.py
    - custom_components/behaviour_monitor/config_flow.py
    - custom_components/behaviour_monitor/__init__.py
    - tests/test_config_flow.py
    - tests/test_init.py

key-decisions:
  - "PMI_THRESHOLD set to 1.0 (medium-confidence, tunable via const.py)"
  - "Correlation window range 30-600s with step=10 matches user expectation for seconds-scale config"

patterns-established:
  - "v8->v9 migration follows identical setdefault pattern as all prior migrations"

requirements-completed: [CFG-01, CFG-02]

# Metrics
duration: 7min
completed: 2026-04-03
---

# Phase 17 Plan 02: Config and Constants Summary

**Correlation constants, AlertType.CORRELATION_BREAK, config UI NumberSelector (30-600s), and v8->v9 migration chain with 459 tests passing**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-03T20:54:41Z
- **Completed:** 2026-04-03T21:01:22Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments
- All correlation constants defined in const.py (CONF_CORRELATION_WINDOW, DEFAULT_CORRELATION_WINDOW, MIN_CO_OCCURRENCES, PMI_THRESHOLD)
- AlertType.CORRELATION_BREAK added to alert_result.py enum
- Config UI shows correlation window NumberSelector with 30-600s range, step 10, default 120
- v8->v9 migration injects correlation_window default for existing installs
- ConfigFlow.VERSION and STORAGE_VERSION both bumped to 9
- 10 new tests added; all 459 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add correlation constants and AlertType.CORRELATION_BREAK** - `50743a6` (feat)
2. **Task 2: Add correlation window to config UI and v8->v9 migration with tests** - `59d0381` (feat)

## Files Created/Modified
- `custom_components/behaviour_monitor/const.py` - Added correlation constants section, bumped STORAGE_VERSION to 9
- `custom_components/behaviour_monitor/alert_result.py` - Added CORRELATION_BREAK to AlertType enum
- `custom_components/behaviour_monitor/config_flow.py` - Added correlation window NumberSelector, bumped VERSION to 9, options flow support
- `custom_components/behaviour_monitor/__init__.py` - Added v8->v9 migration block with setdefault
- `tests/test_config_flow.py` - Added 4 new tests for correlation window schema and round-trip
- `tests/test_init.py` - Added TestMigrateEntryV8ToV9 class (4 tests), updated all version assertions to v9

## Decisions Made
- PMI_THRESHOLD set to 1.0 as a medium-confidence tunable constant (documented in const.py comments)
- Correlation window step set to 10 seconds for user-friendly increments

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all constants and config fields are fully wired.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All correlation constants importable for downstream phases (18-20)
- AlertType.CORRELATION_BREAK ready for detection engine use
- Config migration chain complete through v9
- Config UI ready for user configuration of correlation window

---
*Phase: 17-foundation-and-rehydration*
*Completed: 2026-04-03*
