---
phase: 09-alert-suppression
plan: 01
subsystem: notifications
tags: [alert-suppression, coordinator, homeassistant, storage, tdd]

# Dependency graph
requires: []
provides:
  - CONF_ALERT_REPEAT_INTERVAL and DEFAULT_ALERT_REPEAT_INTERVAL constants in const.py
  - _alert_suppression dict in coordinator tracking active alert timestamps
  - Clear-on-resolve behaviour removes suppression entries when conditions clear
  - Suppression state persisted to and restored from HA storage coordinator block
  - 8 new TestAlertSuppression tests covering all suppression edge cases
affects:
  - 09-02 (storage migration plan — STORAGE_VERSION bump, alert_suppression field)
  - config_flow (may expose alert_repeat_interval as user-configurable option)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fire-once-then-throttle: first alert fires, subsequent fires suppressed for _alert_repeat_interval minutes"
    - "Clear-on-resolve: each _handle_alerts cycle prunes suppression keys absent from current alert set"
    - "Key pattern: entity_id|alert_type.value (e.g. sensor.x|inactivity)"

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/const.py
    - custom_components/behaviour_monitor/coordinator.py
    - tests/test_coordinator.py

key-decisions:
  - "Keep _notification_cooldowns dict intact (not removed) to avoid breaking existing tests and external tooling; new _alert_suppression is the active suppression gate"
  - "DEFAULT_ALERT_REPEAT_INTERVAL = 240 minutes (4 hours) — prevents same-condition spam while ensuring eventual re-notification"
  - "Clear-on-resolve happens before notification gate check, ensuring re-triggers fire immediately after a condition disappears and returns"
  - "STORAGE_VERSION left at 5 — migration owned by Plan 02"

patterns-established:
  - "Suppression pattern: build current_keys set, prune stale suppression entries, check _alert_suppression in _ok(), record on send"

requirements-completed: [SUPR-01, SUPR-03]

# Metrics
duration: 3min
completed: 2026-03-14
---

# Phase 09 Plan 01: Alert Suppression — Constants and Coordinator Summary

**Fire-once-then-throttle alert suppression with clear-on-resolve using _alert_suppression dict keyed by entity_id|alert_type, persisted to HA storage**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-14T15:28:42Z
- **Completed:** 2026-03-14T15:31:56Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added `CONF_ALERT_REPEAT_INTERVAL` and `DEFAULT_ALERT_REPEAT_INTERVAL` constants (240 minutes / 4 hours)
- Implemented fire-once-then-throttle suppression: alerts fire once, then are suppressed for the repeat interval while the condition stays active
- Implemented clear-on-resolve: when a condition disappears from detection results, its suppression key is deleted so re-triggers fire immediately
- Suppression state serialised/deserialised in HA storage (coordinator block, `alert_suppression` key)
- 8 `TestAlertSuppression` tests cover all cases; 341 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add CONF_ALERT_REPEAT_INTERVAL constants to const.py** - `cfa4e27` (feat)
2. **Task 2: TDD RED — failing TestAlertSuppression tests** - `aa37548` (test)
3. **Task 2: Implement alert suppression in coordinator.py** - `8c7c413` (feat)

_Note: TDD tasks have multiple commits (test RED → feat GREEN)_

## Files Created/Modified
- `custom_components/behaviour_monitor/const.py` - Added CONF_ALERT_REPEAT_INTERVAL and DEFAULT_ALERT_REPEAT_INTERVAL constants
- `custom_components/behaviour_monitor/coordinator.py` - Added _alert_repeat_interval, _alert_suppression; updated _handle_alerts with suppression logic; persist/restore in storage
- `tests/test_coordinator.py` - Added TestAlertSuppression (8 tests); updated 2 cooldown tests to use new mechanism

## Decisions Made
- Kept `_notification_cooldowns` dict in place (not removed): it's retained for backward compatibility and existing tests still reference it; the new `_alert_suppression` is the active gate in `_ok()`
- `DEFAULT_ALERT_REPEAT_INTERVAL = 240` (4 hours): aligns with plan spec, prevents notification fatigue while ensuring eventual re-notification for sustained issues
- Clear-on-resolve runs at top of `_handle_alerts` (before the early-return guards), ensuring stale entries are always pruned even when notifications are disabled
- `STORAGE_VERSION` stays at 5 — migration work is explicitly deferred to Plan 02

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated TestCoordinatorNotificationSuppression cooldown tests to use _alert_suppression**
- **Found during:** Task 2 (GREEN phase — running full test suite)
- **Issue:** `test_cooldown_suppresses_repeat_notification` and `test_cooldown_expires_and_allows_retry` were setting `_notification_cooldowns` to test suppression, but the new `_ok()` function uses `_alert_suppression` instead. Tests failed after the coordinator update.
- **Fix:** Updated both tests to pre-set `_alert_suppression` and use `_alert_repeat_interval` values matching the new suppression mechanism
- **Files modified:** tests/test_coordinator.py
- **Verification:** All 76 coordinator tests pass after fix
- **Committed in:** `8c7c413` (Task 2 implementation commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - existing test incompatible with new suppression mechanism)
**Impact on plan:** Required fix for test correctness. The old tests were testing the now-superseded `_notification_cooldowns` gate; updating them to test the equivalent behaviour via `_alert_suppression` is the correct outcome.

## Issues Encountered
None — implementation followed the plan specification exactly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Alert suppression logic is complete and tested
- Plan 02 can proceed to bump STORAGE_VERSION and add migration for existing storage data that lacks the `alert_suppression` key
- Config flow (future plan) can expose `alert_repeat_interval` as a user-configurable option

---
*Phase: 09-alert-suppression*
*Completed: 2026-03-14*
