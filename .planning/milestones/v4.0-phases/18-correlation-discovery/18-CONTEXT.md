# Phase 18: Correlation Discovery - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `CorrelationDetector` as a new pure-Python file (`correlation_detector.py`), wire it into the coordinator for event recording and daily PMI batch computation, expose discovered correlation groups via the `cross_sensor_patterns` sensor attribute, and persist/restore correlation state. This phase does NOT implement break alerting — that's Phase 19.

</domain>

<decisions>
## Implementation Decisions

### File Structure
- **D-01:** New file `correlation_detector.py` following the established detector pattern (pure Python, zero HA imports, independently testable). Matches `acute_detector.py` and `drift_detector.py`.

### Co-occurrence Recording
- **D-02:** Claude's Discretion — choose the best approach for recording entity events. Research recommends `record_event(entity_id, timestamp)` called on each state change, with daily batch PMI computation. Alternative: record only in coordinator update cycle.

### Sensor Attribute Format
- **D-03:** Claude's Discretion — choose the format for `cross_sensor_patterns`. Research recommends flat list of pairs with strength and count. Alternative: pre-computed grouped clusters.

### Persistence Scope
- **D-04:** Claude's Discretion — choose what state to persist. Research recommends learned pairs + raw counts (enables PMI recomputation on startup). Alternative: learned pairs only (smaller storage but loses recomputation ability).

### Claude's Discretion
- Co-occurrence recording approach (D-02): on state_changed vs coordinator update cycle
- Sensor attribute format (D-03): flat pairs vs grouped clusters
- Persistence scope (D-04): counts + pairs vs pairs only
- CorrelationDetector public API (methods, constructor params)
- Whether to expose a `correlation_groups` property or method
- How to bound storage growth (max pairs, max entities)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### New File
- `custom_components/behaviour_monitor/correlation_detector.py` — NEW FILE to create

### Phase 17 Foundation
- `custom_components/behaviour_monitor/const.py` — MIN_CO_OCCURRENCES=10, PMI_THRESHOLD=1.0, CONF_CORRELATION_WINDOW, DEFAULT_CORRELATION_WINDOW=120
- `custom_components/behaviour_monitor/alert_result.py` — AlertType.CORRELATION_BREAK (used in Phase 19, but defined)

### Existing Detector Patterns
- `custom_components/behaviour_monitor/acute_detector.py` — detector contract pattern (pure Python, constructor, check methods, no HA imports)
- `custom_components/behaviour_monitor/drift_detector.py` — detector with to_dict()/from_dict() persistence pattern

### Coordinator Integration
- `custom_components/behaviour_monitor/coordinator.py` — _handle_state_changed(), _async_update_data(), _build_sensor_data() with cross_sensor_patterns: [], persistence in async_setup/save

### Research
- `.planning/research/SUMMARY.md` — Phase 18 section on correlation discovery
- `.planning/research/ARCHITECTURE.md` — CorrelationDetector architecture, data flow, integration points
- `.planning/research/STACK.md` — PMI algorithm details, bounded deques, lazy pair creation

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DriftDetector.to_dict()`/`from_dict()`: Persistence pattern to replicate
- `_handle_state_changed()`: Hook point for recording events (line 175 of coordinator.py)
- `_today_date` day-change block: Hook point for daily batch PMI computation
- `cross_sensor_patterns: []`: Pre-existing placeholder in `_build_sensor_data()` (line 325)
- `self._store`: HA Store for persistence — coordinator already persists routine_model and cusum_states

### Established Patterns
- Pure Python detectors: zero HA imports, datetime passed as parameter, constructor takes config values
- Persistence: detector exposes `to_dict()`/`from_dict()`, coordinator calls them during save/load in `async_setup()` and `_save_data()`
- Daily batch: classify_tier() runs in day-change block — correlation recomputation follows same pattern

### Integration Points
- `coordinator.__init__()`: Instantiate CorrelationDetector with correlation_window from config
- `_handle_state_changed()`: Call `detector.record_event(entity_id, now)` for correlation tracking
- `_async_update_data()` day-change block: Call daily batch recomputation
- `_build_sensor_data()`: Populate `cross_sensor_patterns` from detector
- `async_setup()` / `_save_data()`: Load/save correlation state alongside routine_model

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Research estimates CorrelationDetector at ~150-200 lines.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 18-correlation-discovery*
*Context gathered: 2026-04-04*
