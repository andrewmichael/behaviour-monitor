# Phase 3: Foundation and Routine Model - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Migrate from v2 z-score storage to v3 routine format, stub deprecated ML sensors, and build the per-entity baseline learning engine (168 hour-of-day x day-of-week slots). Bootstrap from HA recorder history. Detection engines (acute, drift) are Phase 4 — this phase delivers the routine model API they consume.

</domain>

<decisions>
## Implementation Decisions

### Storage Migration
- Continue versioning scheme: STORAGE_VERSION = 3
- Old z-score data handling and ML file cleanup at Claude's discretion — pick the safest approach
- Must not crash HA on upgrade from v1.0

### Deprecated Sensors
- ml_status, ml_training_remaining, cross_sensor_patterns kept as stub entities with safe default states (Claude picks appropriate values)
- Log a deprecation warning once per startup ("sensor X is deprecated and will be removed in a future version")
- Plan to remove these sensors entirely in v1.2+

### Routine Model
- 168 slots (hour-of-day x day-of-week) per entity, configurable rolling history window (default 4 weeks)
- Binary entities (motion, doors): Claude decides metric(s) — event count, inter-event interval, or both — based on what detection engines need
- Numeric entities (temperature, power): Claude decides storage format — mean/stddev, min/max/mean, or similar — based on what detection engines need
- Sparse slot handling at Claude's discretion — optimize for minimizing false positives (minimum observation floor, neighbor blending, or hybrid)
- Learning-state surfacing at Claude's discretion — make it clearly visible to users that detection is inactive during learning

### Recorder Bootstrap
- Use whatever history is available, even if less than the full configured window — don't wait for full window to activate
- Mark confidence proportionally (e.g., 10 days of 28 = lower confidence, wider tolerances)
- Re-bootstrap behavior and load strategy (parallel vs staggered) at Claude's discretion — balance startup speed with HA responsiveness

### Claude's Discretion
- Old z-score data: discard vs backup
- ML storage files: delete vs leave
- Deprecated sensor stub state values
- Binary entity metric choice (count, interval, or both)
- Numeric entity storage format
- Sparse slot strategy
- Learning-state display mechanism
- Bootstrap load strategy (parallel vs staggered)
- Re-bootstrap on missing/corrupt data behavior

</decisions>

<specifics>
## Specific Ideas

- User's primary concern is false positives — every discretionary decision should favor conservative, low-FP defaults
- This is a welfare monitoring integration — "detection inactive" must be clearly surfaced, never invisible silence
- The routine model API must be clean enough for Phase 4's acute and drift detectors to consume without coupling to HA internals

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `const.py`: STORAGE_KEY, STORAGE_VERSION, severity levels, welfare statuses, snooze/holiday constants — most will be kept or extended
- `sensor.py`: 14 sensor descriptions with value_fn lambdas reading from coordinator.data dict — contract must be preserved
- `__init__.py`: Service registration pattern (holiday, snooze) — will be extended with routine_reset in Phase 4
- `.storage/` persistence via HA Store class — same pattern for new format

### Established Patterns
- Coordinator.data is a dict consumed by sensor value_fn lambdas — new coordinator must supply same keys
- Two Store instances currently (main + ml) — consolidate to one in v3
- `async_setup()` called manually from __init__.py — research notes suggest migrating to `_async_setup()`

### Integration Points
- `__init__.py` creates coordinator and calls `async_setup()` + `async_config_entry_first_refresh()`
- sensor.py reads coordinator.data via value_fn/extra_attrs_fn
- Config flow provides CONF_MONITORED_ENTITIES, CONF_SENSITIVITY, CONF_LEARNING_PERIOD, etc.
- Recorder component (`get_significant_states`) for bootstrap — dependency already declared in manifest.json

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-foundation-and-routine-model*
*Context gathered: 2026-03-13*
