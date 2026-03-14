# Phase 11: Adaptive Inactivity - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Derive per-entity inactivity thresholds from each entity's own observed inter-event variance. Entities with consistent timing patterns get tighter thresholds; entities with irregular timing get looser thresholds. The global inactivity multiplier continues to function as a scaling factor applied on top of the per-entity learned threshold. Per-entity manual sensitivity UI is explicitly out of scope — INAC-01 auto-learns it.

</domain>

<decisions>
## Implementation Decisions

### Variance computation
- Per-slot variance (same granularity as `expected_gap` — hour × day-of-week)
- Computed at query time from the existing `event_times` deque in `ActivitySlot` — no new storage required
- Reuse `MIN_SLOT_OBSERVATIONS` (4 events = 3 intervals) as the threshold before variance computation is attempted

### Fallback for sparse slots
- Per-slot (not per-entity): each slot is evaluated independently
- When a slot has fewer than `MIN_SLOT_OBSERVATIONS` events: fall back to `global_multiplier × expected_gap` (current behavior)
- Slots with sufficient data use variance-adapted thresholds; sparse slots behave exactly as today

### Threshold bounds (clamping)
- Both min and max bounds are user-configurable
- Defaults: min = 1.5×, max = 10×
- Separate fields in the config UI: 'Min inactivity multiplier' and 'Max inactivity multiplier'
- Exposed in **both** the initial setup flow and the options flow
- Validation error in the HA config UI if user sets min > max (blocks saving)

### Config UI changes
- Current 'Inactivity multiplier' field: update **both label and description** to reflect it now scales a learned per-entity value (e.g., rename to 'Inactivity sensitivity scaling', description: 'Scales the auto-learned per-entity threshold. 1.0 = use learned threshold as-is; higher = more tolerant.')
- Add two new fields: 'Min inactivity multiplier' (default 1.5) and 'Max inactivity multiplier' (default 10.0)

### Storage migration
- Bump schema version v6 → v7
- Migration adds `min_inactivity_multiplier=1.5` and `max_inactivity_multiplier=10.0` defaults to existing config entries
- Existing entries upgrade transparently without user intervention

### Claude's Discretion
- Exact variance metric (CV, std dev of intervals, or other normalized measure)
- Formula mapping variance to per-entity threshold scalar
- Whether numeric entities (temperature, power) participate in variance-adaptive thresholds or always use the fallback
- Internal constant names for min/max config keys
- Test fixture design and coverage strategy

</decisions>

<specifics>
## Specific Ideas

- The intent is "tight for regular entities, loose for irregular ones" — a cat door that fires every 2h reliably should alert sooner than a presence sensor that fires erratically between 30m and 8h
- Min 1.5× default prevents near-false-positive thresholds on hyper-regular entities; max 10× default prevents completely silent thresholds on erratic entities

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ActivitySlot.event_times`: bounded deque (max 56 timestamps) — median gap already computed from this; std dev of intervals can be added in the same method or a new `interval_stdev_seconds()` method
- `ActivitySlot.expected_gap_seconds()`: existing query method computing median interval — variance can live alongside this pattern
- `AcuteDetector.check_inactivity()`: the hook point is line 79: `threshold = self._inactivity_multiplier * expected_gap` — per-entity adaptation replaces this line

### Established Patterns
- Per-slot computation: `routine.expected_gap_seconds(now.hour, now.weekday())` — variance uses same (hour, dow) lookup
- Sparse slot guard: `if expected_gap is None` returns early — same guard covers variance fallback
- Config migration: dict copy + `setdefault`, never mutate `config_entry.data` directly (Phase 3 pattern)
- Schema version bump: `STORAGE_VERSION` and `ConfigFlow.VERSION` bumped together (Phase 9 pattern)

### Integration Points
- `AcuteDetector.__init__`: will need to accept min/max multiplier bounds alongside the global multiplier
- `coordinator.py` line 76: constructs `AcuteDetector(float(d.get(CONF_INACTIVITY_MULTIPLIER, DEFAULT_INACTIVITY_MULTIPLIER)))` — needs updating to pass bounds
- `config_flow.py`: options schema needs 3 updated/new fields; validation for min > max goes in `async_step_options`
- `__init__.py`: v6→v7 migration block adds two new defaults

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 11-adaptive-inactivity*
*Context gathered: 2026-03-14*
