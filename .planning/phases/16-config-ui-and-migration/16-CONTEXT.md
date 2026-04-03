# Phase 16: Config UI and Migration - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a global tier override setting to the HA config UI (SelectSelector dropdown), add config migration v7 to v8 that injects the new key with a default, and wire the override into the coordinator so it takes effect on entity tier assignment. This is the final phase of v3.1.

</domain>

<decisions>
## Implementation Decisions

### Tier Override UI Design
- **D-01:** Claude's Discretion — choose the dropdown options for the global tier override. Research recommends Auto/High/Medium/Low matching ActivityTier values. Follow the existing `drift_sensitivity` SelectSelector pattern.

### Migration v7 to v8 Strategy
- **D-02:** Claude's Discretion — choose the migration approach. The override is a NEW additive key (not replacing existing values), so simple `setdefault()` to 'auto' is likely sufficient. Must bump both ConfigFlow.VERSION and STORAGE_VERSION to 8 simultaneously (established pattern from Phase 9).

### Override Application Point
- **D-03:** Claude's Discretion — choose where the override takes effect. Research recommends coordinator overrides activity_tier after classification runs, preserving diagnostic data. Alternative: skip classification entirely when override is set.

### Claude's Discretion
- Dropdown options (D-01): Auto/High/Medium/Low vs fewer options
- Migration approach (D-02): simple setdefault vs more complex
- Override application point (D-03): post-classification override vs skip classification
- Config key name (e.g. `CONF_ACTIVITY_TIER_OVERRIDE`)
- Placement in the options flow schema (where in the field order)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Config Flow (target file)
- `custom_components/behaviour_monitor/config_flow.py` — Options flow, SelectSelector pattern for drift_sensitivity, schema builder function, ConfigFlow.VERSION

### Init / Migration (target file)
- `custom_components/behaviour_monitor/__init__.py` — async_migrate_entry() with v2-v7 migration chain, STORAGE_VERSION, setdefault pattern

### Constants (new key needed)
- `custom_components/behaviour_monitor/const.py` — CONF_* keys, DEFAULT_* values, STORAGE_VERSION, ActivityTier enum

### Coordinator (override wiring)
- `custom_components/behaviour_monitor/coordinator.py` — reads config entry data, daily reclassification block, activity_tier usage

### Research
- `.planning/research/SUMMARY.md` — Phase 5 section on config UI and migration, Pitfall 3 (migration drops user values), Pitfall 10 (storage version missed)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SelectSelector(SelectSelectorConfig(options=[...], mode=SelectSelectorMode.DROPDOWN))`: Pattern already used for drift_sensitivity — copy for tier override
- `setdefault()` migration pattern: Used consistently in v2-v7 chain
- `ActivityTier` enum in const.py: Values match dropdown option strings ("high", "medium", "low")

### Established Patterns
- ConfigFlow.VERSION and STORAGE_VERSION bumped together (Phase 9 decision)
- Options flow schema builder function at line 96 of config_flow.py
- Migration chain in __init__.py: sequential `if config_entry.version < N:` blocks
- Config entry data accessed via `entry.data.get(CONF_KEY, DEFAULT)`

### Integration Points
- `const.py`: Add `CONF_ACTIVITY_TIER_OVERRIDE`, `DEFAULT_ACTIVITY_TIER_OVERRIDE = "auto"`, bump STORAGE_VERSION to 8
- `config_flow.py`: Add tier override to options schema, bump ConfigFlow.VERSION to 8
- `__init__.py`: Add v7→v8 migration block
- `coordinator.py`: Read override from config, apply after classification

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Research estimates ~50 lines across config_flow.py, __init__.py, and const.py.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 16-config-ui-and-migration*
*Context gathered: 2026-04-03*
