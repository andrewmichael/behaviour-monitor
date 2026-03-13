---
phase: 01-coordinator-suppression
plan: 01
subsystem: testing
tags: [coordinator, notifications, suppression, cooldown, severity-gate, welfare-debounce, tdd, config-flow]

# Dependency graph
requires: []
provides:
  - "CONF_NOTIFICATION_COOLDOWN and CONF_MIN_NOTIFICATION_SEVERITY constants in const.py"
  - "DEFAULT_NOTIFICATION_COOLDOWN (30 min) and DEFAULT_MIN_NOTIFICATION_SEVERITY ('significant') defaults"
  - "WELFARE_DEBOUNCE_CYCLES = 3 constant"
  - "Cooldown NumberSelector and severity SelectSelector in both ConfigFlow and OptionsFlow"
  - "13 red-phase suppression test scaffolds in TestCoordinatorNotificationSuppression"
affects:
  - "01-coordinator-suppression plan 02"
  - "coordinator.py (Plan 02 will implement logic these tests drive)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD red-green: test scaffolds written first to define contract, implementation in Plan 02"
    - "Per-entity cooldown key: (entity_id, anomaly_type) tuple for fine-grained suppression"
    - "Severity gate: compares anomaly.severity against configured min threshold before firing notification"
    - "Welfare debounce: N-cycle counter required before welfare status change notification fires"

key-files:
  created: []
  modified:
    - "custom_components/behaviour_monitor/const.py"
    - "custom_components/behaviour_monitor/config_flow.py"
    - "tests/test_coordinator.py"
    - "tests/test_config_flow.py"
    - "tests/conftest.py"

key-decisions:
  - "Severity constant DEFAULT_MIN_NOTIFICATION_SEVERITY uses string literal 'significant' (not SEVERITY_SIGNIFICANT) because defaults are defined before severity constants in const.py"
  - "Config flow fields added as vol.Required (not Optional) to match existing pattern for non-list fields"
  - "WELFARE_DEBOUNCE_CYCLES placed after SEVERITY_THRESHOLDS block as it references the severity domain"
  - "Test scaffolds use patch.object on _send_notification/_send_welfare_notification to assert call counts"
  - "cross_path_dedup test uses type() property patch to work around read-only is_trained property"

patterns-established:
  - "Suppression test pattern: configure coordinator with cooldown/severity via mock_config_entry.data, patch notification methods to AsyncMock, assert call_count"
  - "Config flow round-trip pattern: submit user_input dict, assert async_update_entry.call_args[1]['data'] contains expected value"

requirements-completed: [NOTIF-01, NOTIF-02, NOTIF-03, WELF-01]

# Metrics
duration: 35min
completed: 2026-03-13
---

# Phase 1 Plan 01: Coordinator Suppression Foundation Summary

**5 new constants, cooldown+severity config flow fields, and 13 TDD red-phase suppression test scaffolds that define the notification suppression contract for Plan 02**

## Performance

- **Duration:** 35 min
- **Started:** 2026-03-13T11:00:00Z
- **Completed:** 2026-03-13T11:35:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Added 5 constants to const.py: CONF_NOTIFICATION_COOLDOWN, CONF_MIN_NOTIFICATION_SEVERITY, DEFAULT_NOTIFICATION_COOLDOWN (30), DEFAULT_MIN_NOTIFICATION_SEVERITY ("significant"), WELFARE_DEBOUNCE_CYCLES (3)
- Extended ConfigFlow and OptionsFlow with cooldown NumberSelector (5-240 min, step 5) and severity SelectSelector (minor/moderate/significant/critical)
- Added 13 suppression test scaffolds in TestCoordinatorNotificationSuppression covering per-entity cooldown, cross-path dedup, severity gate, and welfare debounce; 5 fail as expected (red phase)

## Task Commits

1. **Task 1: Add suppression constants to const.py** - `d921f26` (feat)
2. **Task 2: Add cooldown and severity fields to config flow** - `8c008e2` (feat)
3. **Task 3: Write failing test scaffolds for 13 suppression behaviors** - `7b2b474` (test)

## Files Created/Modified

- `custom_components/behaviour_monitor/const.py` - Added 5 suppression constants
- `custom_components/behaviour_monitor/config_flow.py` - Added cooldown and severity fields to both flows
- `tests/test_coordinator.py` - Added TestCoordinatorNotificationSuppression class with 13 test methods
- `tests/test_config_flow.py` - Added 5 new config flow tests for the new fields; fixed pre-existing F401 lint issue
- `tests/conftest.py` - Added notification_cooldown and min_notification_severity to mock_config_entry.data

## Decisions Made

- Severity constant DEFAULT_MIN_NOTIFICATION_SEVERITY uses the string literal `"significant"` rather than `SEVERITY_SIGNIFICANT` because defaults are defined before severity constants in const.py (forward reference would fail)
- Config flow fields are vol.Required (not Optional) consistent with existing pattern for scalar fields
- Test scaffolds for behaviors that currently pass trivially (cooldown_per_entity, cooldown_expires, etc.) are valid because they will remain green after Plan 02 implements per-entity cooldown — these test the happy path, not the suppression path
- cross_path_dedup uses `type()` property patching to work around read-only `is_trained` property on MLPatternAnalyzer

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Fixed pre-existing ruff lint issues in touched files**
- **Found during:** Task 3 (lint verification pass)
- **Issue:** `patch` import unused in test_config_flow.py (F401); `snooze_time` unused variable in TestCoordinatorSnooze (F841)
- **Fix:** Removed unused import and assignment — both pre-existing but in files being modified
- **Files modified:** tests/test_config_flow.py, tests/test_coordinator.py
- **Verification:** `ruff check` passes clean on all modified files
- **Committed in:** 7b2b474 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (pre-existing lint cleanup in touched files)
**Impact on plan:** Minimal — removed dead code. No scope creep.

## Issues Encountered

- venv was not set up at execution start; ran `make install-test` to create it
- Direct Python import of the module failed because `homeassistant` isn't installed; used `importlib.util.spec_from_file_location` to verify const.py constants directly
- `is_trained` is a read-only property on MLPatternAnalyzer — used `type()` property patch workaround for `test_cross_path_dedup`

## Next Phase Readiness

- Plan 02 can now implement suppression logic in coordinator.py against the 5 failing test contracts
- The 5 failing tests define precise behavior: cooldown_suppresses_repeat, severity_gate_suppresses, welfare_debounce_no_notify_first_cycle, welfare_debounce_resets_on_revert, welfare_debounce_deescalation
- All 8 currently-passing suppression tests will remain green when Plan 02 adds the new logic (they test complementary happy-path behaviors)

---
*Phase: 01-coordinator-suppression*
*Completed: 2026-03-13*
