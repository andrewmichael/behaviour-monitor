# Phase 5: Integration - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the Phase 3-4 detection engines (RoutineModel, AcuteDetector, DriftDetector) into the Home Assistant integration — rebuild coordinator under 350 lines, update config flow with new options and remove dead ML options, preserve all 14 sensor entity IDs with safe defaults, register routine_reset service, and connect alert results to notifications with existing suppression logic preserved.

</domain>

<decisions>
## Implementation Decisions

### Coordinator Data Mapping
- All 14 sensor entity IDs must remain stable — coordinator.data dict keys preserved
- activity_score, anomaly_detected, welfare_status, and other sensor keys must be populated from RoutineModel + AcuteDetector + DriftDetector instead of PatternAnalyzer + MLPatternAnalyzer
- Coordinator target: under 350 lines (currently 1,213 lines)
- Existing suppression logic preserved: holiday mode, snooze, per-entity notification cooldown, welfare debounce (3-cycle hysteresis)
- coordinator.data must never be None on first refresh

### Config Flow Simplification
- New options to add: history_window_days (already migrated in Phase 3), inactivity_multiplier, drift_sensitivity
- Old ML options to handle: enable_ml, ml_learning_period, retrain_period, cross_sensor_window
- Old sensitivity dropdown (sigma-based) needs adaptation — no z-scores in v1.1
- Existing config entries must load without error and receive sensible defaults for new options
- Config migration pattern established in Phase 3: dict copy + pop, never mutate config_entry.data directly

### Notification Formatting
- AlertResult.explanation provides human-readable text for notification body
- Both acute and drift alerts use the configured notification service (or persistent_notification fallback)
- Existing suppression logic fully preserved: holiday mode blocks all, snooze blocks all, cooldown per entity

### Old Code Removal
- analyzer.py (z-score PatternAnalyzer) and ml_analyzer.py (River ML) are fully replaced by new engines
- Old test files (test_analyzer.py, test_ml_analyzer.py, test_coordinator.py) test dead code paths
- const.py has unused ML constants (ML_CONTAMINATION, ML_EMA_ALPHA, MIN_SAMPLES_FOR_ML, etc.)
- Old SEVERITY_THRESHOLDS (sigma-based) and SENSITIVITY_THRESHOLDS may need evaluation for continued relevance

### Claude's Discretion
- activity_score sensor mapping (RoutineModel.confidence vs daily activity ratio vs other)
- anomaly_detected semantics (union of acute+drift vs acute-only vs other)
- Coordinator internal structure to stay under 350 lines
- welfare_status derivation from AlertSeverity
- ML option removal strategy (strip from UI vs show as deprecated)
- Drift sensitivity presentation (dropdown matching sensitivity pattern vs other)
- Inactivity multiplier control type (number box vs preset dropdown)
- Old sensitivity dropdown fate (repurpose vs remove)
- Acute vs drift notification format differentiation
- Notification cooldown strategy (shared per entity vs independent per alert type)
- min_notification_severity gate adaptation (map to AlertSeverity vs remove)
- analyzer.py / ml_analyzer.py removal timing (this phase vs later)
- Old test file lifecycle (delete and replace vs keep alongside)
- Unused constant cleanup in const.py

</decisions>

<specifics>
## Specific Ideas

- This is the final phase of v1.1 — everything must work end-to-end after this
- Welfare monitoring context: notifications are the primary user-facing output, they must be trustworthy
- The 350-line coordinator target comes from the phase goal in ROADMAP.md
- Phase 3's async_migrate_entry already handles v2→v3 migration; Phase 5 may need v3→v4 if config flow adds new keys
- routine_reset service registration follows existing pattern from holiday/snooze services in __init__.py

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `routine_model.py`: RoutineModel, EntityRoutine, ActivitySlot — baseline API (Phase 3)
- `acute_detector.py`: AcuteDetector with check_inactivity, check_unusual_time (Phase 4)
- `drift_detector.py`: DriftDetector with bidirectional CUSUM, CUSUMState (Phase 4)
- `alert_result.py`: AlertResult, AlertType, AlertSeverity with to_dict() (Phase 4)
- `__init__.py`: Service registration pattern (holiday, snooze) — extend with routine_reset
- `sensor.py`: 14 sensor descriptions with value_fn lambdas — contract must be preserved
- `config_flow.py`: BehaviourMonitorConfigFlow + OptionsFlow with selector patterns

### Established Patterns
- Coordinator extends DataUpdateCoordinator — _async_update_data returns dict consumed by sensors
- Store class for persistence — same pattern for new serialization
- Config flow uses voluptuous schemas with HA selectors (NumberSelector, SelectSelector, etc.)
- Service registration in async_setup_entry with vol.Schema for parameters
- Deprecated sensor stubs return safe defaults (Phase 3)

### Integration Points
- `__init__.py` → creates coordinator, calls async_setup() + async_config_entry_first_refresh()
- `sensor.py` → reads coordinator.data via value_fn/extra_attrs_fn lambdas
- `config_flow.py` → provides CONF_* keys read by coordinator
- `const.py` → shared constants imported by all modules
- `manifest.json` → already declares recorder dependency for bootstrap

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-integration*
*Context gathered: 2026-03-13*
