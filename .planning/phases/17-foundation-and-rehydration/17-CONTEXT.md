# Phase 17: Foundation and Rehydration - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix the tier classification retry bug (rehydration), define all correlation constants upfront in const.py, add config migration v8→v9 with correlation window default, and add correlation window NumberSelector to the config UI. This phase does NOT implement correlation discovery or detection — those are Phases 18-20.

</domain>

<decisions>
## Implementation Decisions

### Rehydration Fix
- **D-01:** Only set `_tier_classified_date` when classification actually succeeds (confidence >= 0.8 and a real tier is assigned). If confidence is too low and `_activity_tier` remains `None`, leave the date guard unset so `classify_tier()` retries on the next coordinator update cycle. This is a ~1 line change in `routine_model.py`'s `classify_tier()` method.

### Correlation Constants Scope
- **D-02:** Define ALL correlation constants upfront in Phase 17: `AlertType.CORRELATION_BREAK`, `CONF_CORRELATION_WINDOW`, `DEFAULT_CORRELATION_WINDOW`, `MIN_CO_OCCURRENCES`, `PMI_THRESHOLD`. Downstream phases (18-20) just import — no const.py changes needed later.

### Correlation Window UI Control
- **D-03:** Use `NumberSelector` for the correlation time window. Range: 30-600 seconds. Default: 120 seconds (2 minutes). Unit: seconds. This matches the existing numeric config patterns (history window, inactivity multiplier).

### Claude's Discretion
- Exact placement of correlation constants in const.py (grouping, section header)
- Whether AlertType.CORRELATION_BREAK needs a new severity level or uses existing LOW
- Config migration v8→v9 implementation details (follows established setdefault pattern)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Rehydration Fix Target
- `custom_components/behaviour_monitor/routine_model.py` — classify_tier() method, _tier_classified_date guard, _activity_tier assignment

### Constants Target
- `custom_components/behaviour_monitor/const.py` — ActivityTier enum, CONF_* keys, DEFAULT_* values, STORAGE_VERSION
- `custom_components/behaviour_monitor/alert_result.py` — AlertType enum (add CORRELATION_BREAK)

### Config Flow Target
- `custom_components/behaviour_monitor/config_flow.py` — NumberSelector pattern (see CONF_HISTORY_WINDOW_DAYS), schema builder, ConfigFlow.VERSION
- `custom_components/behaviour_monitor/__init__.py` — async_migrate_entry() v2-v8 chain

### Research
- `.planning/research/SUMMARY.md` — Phase 17 section on foundation, rehydration fix approach
- `.planning/research/STACK.md` — Tier rehydration analysis (lines 193-195), correlation constants

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `NumberSelector(NumberSelectorConfig(min=N, max=M, step=S, unit_of_measurement="seconds"))`: Used for history_window_days — same pattern for correlation window
- `setdefault()` migration chain: Established v2→v8, extend to v9
- `AlertType` enum in alert_result.py: Add CORRELATION_BREAK member

### Established Patterns
- Config VERSION and STORAGE_VERSION bumped simultaneously (Phase 9, 11, 16 pattern)
- Constants grouped by section with comment headers in const.py
- classify_tier() sets `_tier_classified_date = now.date()` unconditionally — the bug to fix

### Integration Points
- `routine_model.py:classify_tier()` — conditional date guard fix
- `const.py` — new correlation constants section
- `alert_result.py` — new AlertType member
- `config_flow.py` — new NumberSelector field, VERSION bump to 9
- `__init__.py` — new v8→v9 migration block, STORAGE_VERSION in const.py to 9

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

*Phase: 17-foundation-and-rehydration*
*Context gathered: 2026-04-03*
