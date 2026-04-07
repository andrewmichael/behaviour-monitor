# Phase 20: Correlation Lifecycle - Context

**Gathered:** 2026-04-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Add stale correlation pair decay (auto-prune when entities stop co-occurring) and cleanup when monitored entities are removed from config. This is the final phase of v4.0.

</domain>

<decisions>
## Implementation Decisions

### Stale Pair Decay
- **D-01:** Claude's Discretion — choose the best decay approach. Research recommends removing pairs whose PMI drops below threshold during daily recompute (natural, no new timers). Alternative: time-based removal after N days of no co-occurrence.

### Entity Removal Cleanup
- **D-02:** Claude's Discretion — choose how to clean up when entities are removed from config. Research recommends a `remove_entity(entity_id)` method on CorrelationDetector called by coordinator when monitored_entities changes.

### Decay Aggressiveness
- **D-03:** Claude's Discretion — choose how aggressively to prune. Options: match history_window_days (28 days default), faster 7-day window, or PMI-threshold based (no explicit time limit).

### Claude's Discretion
- All three areas deferred to Claude's judgment
- Whether to also prune `_entity_event_counts` for removed entities
- Whether to also clear `_break_cycles` for removed entities
- How coordinator detects entity removal (config reload vs explicit diff)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### CorrelationDetector (target)
- `custom_components/behaviour_monitor/correlation_detector.py` — _pairs dict, _learned_pairs set, _entity_event_counts, _break_cycles, recompute(), to_dict()/from_dict()

### Coordinator (integration)
- `custom_components/behaviour_monitor/coordinator.py` — _monitored_entities list, _correlation_detector instance, daily recompute call

### Research
- `.planning/research/SUMMARY.md` — Phase 20 on correlation lifecycle
- `.planning/research/PITFALLS.md` — Stale pair growth, entity removal edge cases

</canonical_refs>

<code_context>
## Existing Code Insights

### Integration Points
- `CorrelationDetector.recompute()`: Natural hook for decay — already iterates all pairs daily
- `coordinator._monitored_entities`: Source of truth for which entities are active
- `coordinator.__init__()`: Reads config, could diff against stored state to detect removals
- `_save_data()` / `async_setup()`: Persistence cycle — cleanup should happen before save

### Established Patterns
- Daily batch computation in day-change block
- `to_dict()`/`from_dict()` for state persistence
- Config-driven entity list from `entry.data`

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

*Phase: 20-correlation-lifecycle*
*Context gathered: 2026-04-06*
