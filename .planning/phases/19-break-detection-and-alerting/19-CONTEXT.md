# Phase 19: Break Detection and Alerting - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Add break detection to CorrelationDetector and wire it into the coordinator alert pipeline. When a learned correlation breaks (entity A fires without correlated companion B within the window), alert after sustained evidence. Deduplicate alerts per triggering entity. This phase does NOT handle correlation lifecycle (decay/cleanup) — that's Phase 20.

</domain>

<decisions>
## Implementation Decisions

### Break Detection Logic
- **D-01:** Add `check_breaks(entity_id, now, last_seen_map)` method to `CorrelationDetector`. Returns list of `AlertResult` objects. Follows the same detector pattern as `AcuteDetector.check_inactivity()`. Coordinator calls it and collects results alongside other alert types.

### Group-Level Deduplication
- **D-02:** One alert per triggering entity. When entity A fires and multiple correlated entities (B, C) are missing, produce ONE `AlertResult` listing all missing companions in the explanation/details. Dedup key is the triggering entity ID, not the pair. Avoids alert spam from dense correlation groups.

### Alert Severity and Suppression
- **D-03:** Correlation breaks use LOW severity, do NOT escalate welfare status (research decision). Uses the existing `_alert_suppression` dict in coordinator with `AlertType.CORRELATION_BREAK` as the suppression key. Same configurable repeat interval as other alert types. Consistent suppression behavior.

### Sustained Evidence
- **D-04:** Use the same sustained-evidence pattern as AcuteDetector — track consecutive miss counts per entity, require `SUSTAINED_EVIDENCE_CYCLES` (3) consecutive misses before firing. Reset counter when the correlation is satisfied.

### Claude's Discretion
- Internal data structure for tracking consecutive miss counts (dict on detector vs coordinator)
- Whether `check_breaks` is called per-event or per-update-cycle
- Exact format of the correlation break explanation string
- Whether to include correlation strength in the AlertResult details

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### CorrelationDetector (target file)
- `custom_components/behaviour_monitor/correlation_detector.py` — record_event(), recompute(), get_correlated_pairs(), get_correlation_groups(), to_dict()/from_dict()

### Alert Infrastructure
- `custom_components/behaviour_monitor/alert_result.py` — AlertResult, AlertType.CORRELATION_BREAK, AlertSeverity
- `custom_components/behaviour_monitor/acute_detector.py` — sustained-evidence pattern (_inactivity_cycles dict, counter increment/reset, threshold check)

### Coordinator Integration
- `custom_components/behaviour_monitor/coordinator.py` — _run_detection(), _alert_suppression dict, _handle_state_changed(), _async_update_data()

### Constants
- `custom_components/behaviour_monitor/const.py` — SUSTAINED_EVIDENCE_CYCLES=3, MIN_CO_OCCURRENCES, PMI_THRESHOLD

### Research
- `.planning/research/SUMMARY.md` — Phase 19 section on break detection
- `.planning/research/PITFALLS.md` — Premature correlation alerts, welfare status corruption

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AcuteDetector._inactivity_cycles`: Sustained-evidence counter pattern to replicate
- `AlertResult(entity_id, alert_type, severity, confidence, explanation, timestamp, details)`: Alert construction pattern
- `_alert_suppression` dict in coordinator: Suppression pattern for fire-once-then-throttle
- `_run_detection()`: Coordinator method that collects alerts from all detectors

### Established Patterns
- Detectors return `AlertResult | None` or `list[AlertResult]`
- Coordinator calls detector methods in `_run_detection()`, collects into flat alert list
- Sustained evidence: counter dict keyed by entity_id, increment on condition met, reset on condition not met, fire alert when counter >= threshold

### Integration Points
- `correlation_detector.py`: Add `check_breaks()` method with sustained-evidence counter
- `coordinator.py:_run_detection()`: Call `check_breaks()` for entities that just fired
- `coordinator.py`: Ensure correlation break alerts go through existing suppression pipeline

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 19-break-detection-and-alerting*
*Context gathered: 2026-04-04*
