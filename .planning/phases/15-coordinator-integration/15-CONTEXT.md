# Phase 15: Coordinator Integration - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire tier classification into the coordinator: daily reclassification of all entities, expose tier as sensor attribute in entity_status, and replace duplicated inline duration formatting with format_duration(). This phase does NOT add config UI or migration — that's Phase 16.

</domain>

<decisions>
## Implementation Decisions

### Tier in entity_status Sensor Data
- **D-01:** Claude's Discretion — add `activity_tier` field per entity in the entity_status list. Choose between null or 'unknown' for unclassified entities. This satisfies CLASS-04 (computed tier exposed as sensor attribute).

### Daily Reclassification Hook
- **D-02:** Claude's Discretion — choose the best placement for daily `classify_tier(now)` calls in the coordinator update cycle. The existing `_today_date` day-change block at line 178 of coordinator.py is the natural hook point (recommended by research).

### Duplicated Duration Formatting
- **D-03:** Replace inline h/m formatting in `_build_sensor_data()` (lines 283-288: `ts_fmt`, `typ_fmt`) with `format_duration()` from routine_model. This eliminates the duplicated logic and keeps output consistent with acute_detector's formatted explanations.

### Claude's Discretion
- Tier attribute value for unclassified entities (D-01): null vs 'unknown'
- Reclassification hook placement (D-02): in day-change block vs elsewhere
- Whether to also replace the `"ago"` suffix formatting or just the duration part

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Coordinator (target file)
- `custom_components/behaviour_monitor/coordinator.py` — _async_update_data(), _build_sensor_data(), _today_date day-change block, entity_status list construction, inline duration formatting

### Phase 13 Classification
- `custom_components/behaviour_monitor/routine_model.py` — EntityRoutine.classify_tier(now), activity_tier property, format_duration()

### Phase 14 Detection
- `custom_components/behaviour_monitor/acute_detector.py` — check_inactivity() already reads routine.activity_tier directly (no coordinator wiring needed for detection)

### Sensor (may need tier attribute)
- `custom_components/behaviour_monitor/sensor.py` — BehaviourMonitorSensor reads coordinator data

### Research
- `.planning/research/SUMMARY.md` — Phase 4 section on coordinator integration, Pitfall 7 (override not persisted), Pitfall 8 (reload path)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `format_duration()` in routine_model.py: Ready to replace inline formatting
- `EntityRoutine.classify_tier(now)`: Called once per day to reclassify
- `EntityRoutine.activity_tier`: Property returns ActivityTier | None

### Established Patterns
- `_today_date` day-change block: Coordinator already resets daily counters here — natural reclassification hook
- `entity_status` list: Already contains per-entity dicts with `entity_id`, `status`, `last_seen`
- `_build_sensor_data()`: Central method constructing all sensor attributes
- Inline duration formatting at lines 283-288: `h, m = tsec // 3600, (tsec % 3600) // 60` pattern

### Integration Points
- Day-change block (line 178): Add classify_tier(now) calls for all entities
- entity_status construction (line 306): Add activity_tier field per entity
- Duration formatting (lines 283-288): Replace with format_duration() calls

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

*Phase: 15-coordinator-integration*
*Context gathered: 2026-04-03*
