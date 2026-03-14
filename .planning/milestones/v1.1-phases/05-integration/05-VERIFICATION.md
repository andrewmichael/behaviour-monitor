---
phase: 05-integration
verified: 2026-03-13T22:30:00Z
status: passed
score: 11/11 must-haves verified
---

# Phase 5: Integration Verification Report

**Phase Goal:** Detection engines are wired into a rebuilt coordinator under 350 lines, all 14 sensor entity IDs remain stable and return safe defaults, and the config flow exposes history window, inactivity multiplier, and drift sensitivity options with graceful migration from v1.0 config entries
**Verified:** 2026-03-13T22:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Coordinator under 350 lines wires RoutineModel, AcuteDetector, DriftDetector | VERIFIED | coordinator.py is 348 lines; imports all three engines at lines 16-28; calls check_inactivity, check_unusual_time, drift_detector.check at lines 177-179 |
| 2  | coordinator.data is never None on first refresh — always returns a dict with all required keys | VERIFIED | _async_update_data wraps all logic in try/except returning _build_safe_defaults; _build_safe_defaults confirmed to contain all 22 expected keys |
| 3  | All 14 sensor entity IDs remain stable | VERIFIED | 14 BehaviourMonitorSensorDescription entries present in sensor.py with keys: last_activity, activity_score, anomaly_detected, baseline_confidence, daily_activity_count, cross_sensor_patterns, ml_status, welfare_status, routine_progress, time_since_activity, entity_status_summary, statistical_training_remaining, ml_training_remaining, last_notification |
| 4  | Config flow shows inactivity_multiplier number field (1.5-10.0, step 0.5) | VERIFIED | config_flow.py lines 98-107: NumberSelector with min=1.5, max=10.0, step=0.5 |
| 5  | Config flow shows drift_sensitivity dropdown (high/medium/low) | VERIFIED | config_flow.py lines 108-128: SelectSelector with DROPDOWN mode, three sensitivity options |
| 6  | Old ML options removed from config flow UI | VERIFIED | grep for enable_ml, ml_learning_period, retrain_period, cross_sensor_window in config_flow.py returns empty |
| 7  | Existing v1.0/v2/v3 config entries migrate to v4 without error, receiving default values for new keys | VERIFIED | __init__.py lines 60-103: chained migration blocks, v<3 adds history_window_days, v<4 removes old sigma/ML keys and adds inactivity_multiplier=3.0, drift_sensitivity="medium" |
| 8  | routine_reset service call clears DriftDetector state for the specified entity | VERIFIED | coordinator.py lines 323-326: async_routine_reset calls _drift_detector.reset_entity(entity_id); registered in __init__.py line 174-179 |
| 9  | CUSUMState persists across HA restarts via storage v4 format | VERIFIED | coordinator.py lines 127-137: _save_data writes cusum_states dict; lines 106-107: async_setup restores CUSUMState.from_dict per entity |
| 10 | sensor.py has no coord.analyzer references | VERIFIED | grep for coord.analyzer in sensor.py returns empty; baseline_confidence extra_attrs_fn reads data.get("learning_status", "learning") at line 82 |
| 11 | Full test suite passes | VERIFIED | 343 tests pass, 0 failures |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/behaviour_monitor/const.py` | CONF_INACTIVITY_MULTIPLIER, CONF_DRIFT_SENSITIVITY, SERVICE_ROUTINE_RESET, STORAGE_VERSION=4 | VERIFIED | All four constants present at lines 23-24, 126, 43 |
| `custom_components/behaviour_monitor/__init__.py` | v3->v4 migration removing old keys and adding new defaults | VERIFIED | version=4 at line 95; _OLD_KEYS_REMOVED_V4 tuple; setdefault for inactivity_multiplier and drift_sensitivity |
| `custom_components/behaviour_monitor/config_flow.py` | VERSION=4, inactivity_multiplier + drift_sensitivity fields, no ML/sigma fields | VERIFIED | VERSION=4 at line 187; _build_data_schema includes both new fields; no ML imports |
| `custom_components/behaviour_monitor/coordinator.py` | Under 350 lines, wires all three detection engines | VERIFIED | 348 lines; imports RoutineModel, AcuteDetector, DriftDetector, AlertResult |
| `custom_components/behaviour_monitor/sensor.py` | No coord.analyzer references, reads coordinator.data | VERIFIED | learning_status read from data dict at line 82; no coord.analyzer anywhere |
| `tests/test_coordinator.py` | Covers init, detection, notifications, suppression, routine_reset, persistence (200+ lines) | VERIFIED | 880 lines, 63 tests covering all required scenarios |
| `tests/test_config_flow.py` | Covers inactivity_multiplier and drift_sensitivity in both flows | VERIFIED | 424 lines, 12 occurrences of inactivity_multiplier/drift_sensitivity in tests |
| `tests/test_init.py` | Covers v3->v4 migration, service registration | VERIFIED | 658 lines; test_migrate_v3_upgrades_to_v4, test_async_setup_entry_registers_routine_reset_service confirmed present |
| `tests/conftest.py` | mock_config_entry with v4 data keys and version=4 | VERIFIED | version=4 at line 407; history_window_days, inactivity_multiplier, drift_sensitivity at lines 410-412 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| config_flow.py | const.py | `from .const import CONF_INACTIVITY_MULTIPLIER, CONF_DRIFT_SENSITIVITY` | WIRED | Lines 28-50 import both constants; used in _build_data_schema |
| __init__.py | const.py | imports CONF_INACTIVITY_MULTIPLIER, CONF_DRIFT_SENSITIVITY for migration | WIRED | Lines 13-16 import both; used in setdefault at lines 89-90 |
| coordinator.py | routine_model.py | `from .routine_model import RoutineModel` | WIRED | Line 28; self._routine_model instantiated and used throughout |
| coordinator.py | acute_detector.py | `self._acute_detector.check_inactivity` | WIRED | Lines 16, 177: import and call both check methods |
| coordinator.py | drift_detector.py | `self._drift_detector.check` | WIRED | Lines 27, 179, 324: import, check call, reset_entity call |
| coordinator.py | alert_result.py | `from .alert_result import AlertResult` | WIRED | Line 17; used in _run_detection return type, _handle_alerts |
| coordinator.py | const.py | `CONF_INACTIVITY_MULTIPLIER` read from entry.data | WIRED | Lines 18-26: import; line 72: float(d.get(CONF_INACTIVITY_MULTIPLIER, ...)) |
| sensor.py | coordinator.py | value_fn lambdas read coordinator.data | WIRED | All 14 sensor value_fn lambdas read from data dict; extra_attrs_fn reads data keys not coordinator methods |
| tests/test_coordinator.py | coordinator.py | `from.*coordinator import BehaviourMonitorCoordinator` | WIRED | Line 11: confirmed import |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| INFRA-03 | 05-01, 05-02, 05-03 | Config flow UI includes options for history window length, inactivity alert multiplier, and drift sensitivity | SATISFIED | config_flow.py _build_data_schema includes CONF_HISTORY_WINDOW_DAYS (NumberSelector, 7-90 days), CONF_INACTIVITY_MULTIPLIER (NumberSelector, 1.5-10.0), CONF_DRIFT_SENSITIVITY (SelectSelector, high/medium/low); migration to v4 adds defaults for existing entries; 22 test_config_flow.py tests verify round-trips |

No orphaned requirements: INFRA-03 is the sole requirement declared across all three plans and is fully satisfied.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| coordinator.py | `_pycache_` contains stale .pyc for deleted analyzer.py and ml_analyzer.py | Info | No runtime impact; pycache files are regenerated automatically; no .py source files remain |

No blocker or warning anti-patterns found in source files. The two RuntimeWarning entries in the test output ("coroutine async_request_refresh was never awaited") are test environment mock artifacts, not production code issues.

### Human Verification Required

#### 1. Config Flow UI Rendering

**Test:** Load integration options in a running Home Assistant instance. Navigate to Settings > Devices & Services > Behaviour Monitor > Configure.
**Expected:** Form shows inactivity_multiplier number box (1.5-10.0, step 0.5) and drift_sensitivity dropdown with three labelled options (High/Medium/Low). No ML fields visible.
**Why human:** HA UI rendering requires a browser and running HA instance; cannot verify visually from code alone.

#### 2. Existing v1.0 Config Entry Load After Upgrade

**Test:** Install v1.1 over a Home Assistant instance that has a v1.0 config entry (version=2 or version=3 in the config entry store).
**Expected:** HA starts without errors in logs; integration loads successfully with migrated config entry at version=4; all 14 sensors populate.
**Why human:** End-to-end migration requires a real HA startup with a pre-existing config entry; test environment uses mocks.

### Gaps Summary

No gaps. All automated checks pass. Two human verification items are flagged for UI rendering and live migration confirmation, which cannot be verified programmatically.

---

## Detailed Findings

### Coordinator Line Count

coordinator.py is exactly 348 lines — within the 350-line budget. The file wires all three detection engines cleanly.

### Sensor Entity ID Stability

All 14 sensor keys match the v1.0 entity ID set (cross_sensor_patterns, ml_status, ml_training_remaining preserved as deprecated stubs per INFRA-02). Unique IDs are constructed as `{entry_id}_{description.key}` — unchanged from v1.0.

### Safe Defaults Coverage

_build_safe_defaults returns all 22 coordinator.data keys. _async_update_data wraps the hot path in try/except that returns safe defaults on any error, including when the coordinator is in holiday_mode or snoozed (lines 160-161).

### Migration Chain

__init__.py implements sequential migration guards: `if version < 3` block runs first (adds history_window_days, removes ML keys), then `if version < 4` block runs (removes remaining sigma/ML keys, adds inactivity_multiplier and drift_sensitivity defaults). A v2 entry therefore goes through both blocks in a single async_migrate_entry call, ending at version=4. A v4 entry skips both blocks (no-op).

### Dead Code Removal

analyzer.py, ml_analyzer.py, test_analyzer.py, test_ml_analyzer.py are confirmed deleted. Only stale .pyc files remain in __pycache__ directories (harmless). No source file in custom_components/ or tests/ imports PatternAnalyzer or MLPatternAnalyzer.

---

_Verified: 2026-03-13T22:30:00Z_
_Verifier: Claude (gsd-verifier)_
