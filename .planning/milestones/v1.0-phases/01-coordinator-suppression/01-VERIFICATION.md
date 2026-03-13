---
phase: 01-coordinator-suppression
verified: 2026-03-13T12:30:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 1: Coordinator Suppression Verification Report

**Phase Goal:** Suppress duplicate and low-severity notifications — severity gate, per-entity cooldown, cross-path dedup, welfare debounce
**Verified:** 2026-03-13T12:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | An anomaly that persists across multiple update cycles sends at most one notification per cooldown window | VERIFIED | `_should_notify()` at line 774 gates on `_notification_cooldowns[(entity_id, anomaly_type)]`; `test_cooldown_suppresses_repeat` passes |
| 2 | When both statistical and ML paths flag the same entity in the same cycle, exactly one notification is sent | VERIFIED | `stat_notified_entities` set excludes ML duplicates at lines 636-643; `test_cross_path_dedup` passes |
| 3 | Minor-severity anomalies below the minimum severity threshold update sensor state but do not trigger push notifications | VERIFIED | `notifiable_anomalies` filtered by z-score threshold at lines 603-609; return dict uses unfiltered `stat_anomalies`; `test_severity_gate_suppresses` and `test_severity_gate_sensor_state_unaffected` both pass |
| 4 | Welfare status transitions require 3 consecutive cycles at the new status before a notification fires | VERIFIED | `_welfare_consecutive_cycles` counter at lines 667-683, gated on `WELFARE_DEBOUNCE_CYCLES = 3`; `test_welfare_debounce_no_notify_first_cycle` and `test_welfare_debounce_notifies_after_n_cycles` both pass |
| 5 | Cooldown state survives HA restart via persistence in `_save_data`/`_restore` | VERIFIED | `_save_data()` serializes `notification_cooldowns` dict as ISO strings at lines 369-372; `async_setup()` restores at lines 257-265 |
| 6 | New constants for cooldown, severity gate, and welfare debounce exist in const.py | VERIFIED | All 5 constants present: `CONF_NOTIFICATION_COOLDOWN`, `CONF_MIN_NOTIFICATION_SEVERITY`, `DEFAULT_NOTIFICATION_COOLDOWN=30`, `DEFAULT_MIN_NOTIFICATION_SEVERITY="significant"`, `WELFARE_DEBOUNCE_CYCLES=3` |
| 7 | Config flow options UI exposes cooldown duration and minimum severity fields in both flows | VERIFIED | `CONF_NOTIFICATION_COOLDOWN` NumberSelector (5-240 min) and `CONF_MIN_NOTIFICATION_SEVERITY` SelectSelector present in both `async_step_user` (lines 180-213) and `OptionsFlow.async_step_init` (lines 378-410) |
| 8 | 13 suppression test methods exist and pass | VERIFIED | All 13 methods confirmed in `TestCoordinatorNotificationSuppression`; 223 total tests pass, 2 skipped |
| 9 | Cooldown resets when entity returns to normal | VERIFIED | `active_keys` pruning at lines 626-631 removes cooldown entries for entities no longer anomalous; `test_cooldown_resets_on_clear` passes |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/behaviour_monitor/const.py` | CONF_NOTIFICATION_COOLDOWN, CONF_MIN_NOTIFICATION_SEVERITY, DEFAULT_NOTIFICATION_COOLDOWN, DEFAULT_MIN_NOTIFICATION_SEVERITY, WELFARE_DEBOUNCE_CYCLES | VERIFIED | All 5 constants present with correct values (line 18-19, 49-50, 85) |
| `custom_components/behaviour_monitor/config_flow.py` | Cooldown and severity options in both ConfigFlow and OptionsFlow | VERIFIED | Both flows contain NumberSelector for cooldown and SelectSelector for severity |
| `custom_components/behaviour_monitor/coordinator.py` | `_should_notify`, severity gate, per-entity cooldown, cross-path merge, welfare debounce | VERIFIED | All suppression mechanisms implemented; `_should_notify` at line 774 |
| `tests/test_coordinator.py` | 13 test methods for suppression behaviors | VERIFIED | `TestCoordinatorNotificationSuppression` class with all 13 methods present and passing |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `config_flow.py` | `const.py` | imports `CONF_NOTIFICATION_COOLDOWN`, `CONF_MIN_NOTIFICATION_SEVERITY`, defaults | WIRED | Lines 35-36, 43-44 confirm import; both constants used in schema definitions |
| `coordinator.py` | `const.py` | imports `CONF_NOTIFICATION_COOLDOWN`, `WELFARE_DEBOUNCE_CYCLES`, `SEVERITY_THRESHOLDS` | WIRED | Lines 22-48 confirm all 6 suppression-related constants imported |
| `coordinator._async_update_data` | `coordinator._should_notify` | gate check before `_send_notification` and `_send_ml_notification` | WIRED | Lines 612-616 call `_should_notify` for stat path; lines 645-652 for ML path |
| `coordinator._save_data` | `_notification_cooldowns` dict | serialization of cooldown dict to storage JSON | WIRED | Lines 369-372 serialize dict; lines 257-265 restore it |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| NOTIF-01 | 01-01, 01-02 | Per-entity cooldown prevents re-alerting the same entity within a configurable time window | SATISFIED | `_notification_cooldowns[(entity_id, anomaly_type)]` dict + `_should_notify()` implement per-entity cooldown; `test_cooldown_suppresses_repeat` passes |
| NOTIF-02 | 01-01, 01-02 | Anomaly deduplication prevents re-alerting for the same ongoing anomaly type on the same entity; cross-path dedup | SATISFIED | Same `_should_notify()` key `(entity_id, anomaly_type)` prevents same-type repeat; `stat_notified_entities` prevents cross-path duplicates; `test_cross_path_dedup` and `test_dedup_different_types_separate` pass |
| NOTIF-03 | 01-01, 01-02 | Severity minimum gate only sends notifications for anomalies above a minimum severity threshold | SATISFIED | `SEVERITY_THRESHOLDS.get(self._min_notification_severity, 3.5)` filters `notifiable_anomalies` before dispatch; unfiltered list flows to sensor state return; `test_severity_gate_suppresses` and `test_severity_gate_passes_above_threshold` pass |
| WELF-01 | 01-01, 01-02 | Welfare status hysteresis/debounce prevents rapid flapping between states | SATISFIED | `_welfare_consecutive_cycles` counter + `_welfare_pending_status` implement N=3 cycle debounce in both escalation and de-escalation directions; 4 welfare debounce tests pass |

**All 4 requirements satisfied. No orphaned requirements for Phase 1.**

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_config_flow.py` | 5 | Unused `patch` import (F401) | Warning | Pre-existing; introduced by Phase 1 Plan 01 but not cleaned up in committed code (working tree has fix unstaged) |
| `tests/test_config_flow.py` | 27 | Unused `DEFAULT_MIN_NOTIFICATION_SEVERITY` import (F401) | Warning | Added by Phase 1 but unused in committed code |
| `tests/test_config_flow.py` | 31 | Unused `DOMAIN` import (F401) | Warning | Pre-existing import not cleaned up |
| `tests/conftest.py` | 8 | Unused `patch` import (F401) | Warning | Pre-existing; not cleaned despite SUMMARY claiming lint fixed |
| `tests/conftest.py` | 22 | Unused `mock_ha_components` assignment (F841) | Warning | Pre-existing; not cleaned despite SUMMARY claiming lint fixed |

Note: Ruff reports 10 errors total across the codebase, but only 5 are in Phase 1 modified files. The other 5 (`__init__.py`, `analyzer.py`, `switch.py`, `test_analyzer.py`, `test_sensor.py`) are pre-existing in files not touched by Phase 1. None of the 5 issues in Phase 1 files are blockers — tests pass and logic is correct. The working tree of `test_config_flow.py` already has 2 of the 3 errors fixed but the change is not committed.

No blocker anti-patterns found. Suppression logic has no TODO/placeholder patterns.

---

### Human Verification Required

None required. All suppression behaviors are fully testable programmatically and 223 tests pass.

---

### Summary

Phase 1 goal is fully achieved. All four requirement contracts (NOTIF-01, NOTIF-02, NOTIF-03, WELF-01) are implemented in `coordinator.py`, covered by passing tests, and correctly wired through the config flow and constants.

The only non-blocking issue is 5 ruff lint warnings in test support files (conftest.py and test_config_flow.py), all pre-existing or introduced incidentally during Phase 1 test work. None affect runtime behavior. The working tree has a partial fix for test_config_flow.py that has not been committed.

**Commit evidence:** d921f26 (constants), 8c008e2 (config flow), 7b2b474 (test scaffolds), dccd41f (suppression state/persistence), 686898e (suppression logic) — all verified present in git log.

---

_Verified: 2026-03-13T12:30:00Z_
_Verifier: Claude (gsd-verifier)_
