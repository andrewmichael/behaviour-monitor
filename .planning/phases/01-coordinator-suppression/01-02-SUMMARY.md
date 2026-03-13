---
phase: 01-coordinator-suppression
plan: 02
subsystem: coordinator
tags: [coordinator, notifications, suppression, cooldown, severity-gate, welfare-debounce, cross-path-dedup]

# Dependency graph
requires:
  - phase: 01-coordinator-suppression
    plan: 01
    provides: "CONF_NOTIFICATION_COOLDOWN, CONF_MIN_NOTIFICATION_SEVERITY, WELFARE_DEBOUNCE_CYCLES constants, SEVERITY_THRESHOLDS, 13 TDD red-phase suppression test scaffolds"
provides:
  - "_should_notify() helper: per-entity (entity_id, anomaly_type) cooldown gate"
  - "Severity gate in _async_update_data: filters stat anomalies below min z-score threshold before notifying"
  - "Per-entity cooldown: _notification_cooldowns dict with (entity_id, anomaly_type) key"
  - "Cooldown reset on clear: removes cooldown entries when entity returns to normal"
  - "Cross-path merge: deduplicates ML notifications when stat path already notified the same entity in same cycle"
  - "Welfare debounce: requires WELFARE_DEBOUNCE_CYCLES (3) consecutive cycles at new status before firing"
  - "Full persistence: cooldown dict and welfare debounce state survive HA restart"
affects:
  - "All consumers of coordinator notifications — notifications now trustworthy and non-spammy"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Suppression gate pattern: filter → record → prune on each update cycle"
    - "Per-entity cooldown key: (entity_id, anomaly_type) tuple in _notification_cooldowns dict"
    - "Severity gate uses SEVERITY_THRESHOLDS z-score floats (not string ordering)"
    - "Cross-path dedup via stat_notified_entities set before ML dispatch"
    - "Welfare debounce via consecutive-cycles counter + pending status tracking"

key-files:
  created: []
  modified:
    - "custom_components/behaviour_monitor/coordinator.py"

key-decisions:
  - "notifiable_anomalies variable initialized before stat block so it is always in scope for ML cross-path dedup"
  - "Cooldown pruning happens after stat notification dispatch (not before) to ensure correct active_keys set"
  - "ML anomalies also subject to per-entity cooldown check after cross-path dedup"
  - "Welfare debounce applies symmetrically to both escalation and de-escalation directions"

patterns-established:
  - "Notification suppression pattern: severity gate -> cooldown filter -> dispatch -> record -> prune"
  - "_should_notify() is the single gate; all notification paths call it"
  - "Sensor state dict (return value of _async_update_data) always contains all stat_anomalies unfiltered"

requirements-completed: [NOTIF-01, NOTIF-02, NOTIF-03, WELF-01]

# Metrics
duration: 20min
completed: 2026-03-13
---

# Phase 1 Plan 02: Coordinator Suppression Implementation Summary

**Full notification suppression layer: severity gate, per-entity cooldown with deduplication, cross-path merge, and welfare debounce — all 13 TDD tests green**

## Performance

- **Duration:** 20 min
- **Started:** 2026-03-13T11:40:00Z
- **Completed:** 2026-03-13T12:00:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Added `_should_notify()` helper with per-entity (entity_id, anomaly_type) cooldown tracking
- Implemented severity gate using SEVERITY_THRESHOLDS z-score values (not string ordering); stat_anomalies still flows unfiltered into return dict for sensor state
- Implemented per-entity cooldown with `_notification_cooldowns` dict; reset when entity clears
- Implemented cross-path dedup: ML notifications suppressed when stat path already notified the same entity_id in the same update cycle
- Implemented welfare debounce: `_welfare_consecutive_cycles` counter requires WELFARE_DEBOUNCE_CYCLES=3 consecutive cycles at new status before notification fires
- Added full persistence: cooldown dict and debounce state serialized in `_save_data()` and restored in `async_setup()`
- All 13 suppression tests pass; 55 coordinator tests pass; 223 total suite tests pass

## Task Commits

1. **Task 1: Add suppression state, config loading, and persistence** - `dccd41f` (feat)
2. **Task 2: Implement suppression logic in _async_update_data** - `686898e` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `custom_components/behaviour_monitor/coordinator.py` - Added _should_notify(), suppression state fields, config loading, persistence, and full suppression logic in _async_update_data()

## Decisions Made

- `notifiable_anomalies` initialized to empty list before stat block so it is always in scope for the ML cross-path dedup step regardless of whether stat learning is complete
- Cooldown pruning uses `active_keys = {(a.entity_id, a.anomaly_type) for a in stat_anomalies}` — the unfiltered set, ensuring reset fires even when stat_learning_complete is False
- ML anomalies also go through `_should_notify` after cross-path dedup (belt-and-suspenders for ML-only repeat suppression)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Fixed pre-existing F541 lint issue in coordinator.py**
- **Found during:** Task 2 (lint verification pass)
- **Issue:** `triggered_text = f"**Triggered Sensors:**\n" + ...` — spurious `f` prefix on string with no placeholders (ruff F541)
- **Fix:** Removed `f` prefix from the string literal in `_send_welfare_notification`
- **Files modified:** custom_components/behaviour_monitor/coordinator.py
- **Verification:** `ruff check custom_components/behaviour_monitor/coordinator.py` passes clean
- **Committed in:** 686898e (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (pre-existing lint in touched file)
**Impact on plan:** Minimal — one-line cleanup. No scope creep.

## Issues Encountered

None — plan executed cleanly against the TDD scaffolds from Plan 01.

## Next Phase Readiness

- Notification suppression layer is complete and tested
- Phase 1 is now fully implemented: constants + config flow (Plan 01) + suppression logic (Plan 02)
- Phase 2 (analyzer tightening) can proceed; coordinator notifications are now trustworthy baseline

---
*Phase: 01-coordinator-suppression*
*Completed: 2026-03-13*
