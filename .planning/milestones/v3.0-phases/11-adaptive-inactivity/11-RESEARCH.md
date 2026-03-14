# Phase 11: Adaptive Inactivity - Research

**Researched:** 2026-03-14
**Domain:** Statistical variance metrics, per-entity threshold adaptation, Home Assistant config flow and storage migration
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Variance computation:** Per-slot variance at same granularity as `expected_gap` (hour × day-of-week); computed at query time from the existing `event_times` deque; reuse `MIN_SLOT_OBSERVATIONS` (4 events = 3 intervals) as the threshold before variance computation is attempted
- **Fallback for sparse slots:** Per-slot (not per-entity); each slot evaluated independently; when a slot has fewer than `MIN_SLOT_OBSERVATIONS` events fall back to `global_multiplier × expected_gap` (current behaviour); slots with sufficient data use variance-adapted thresholds
- **Threshold bounds (clamping):** Both min and max bounds are user-configurable; defaults min = 1.5×, max = 10×; separate fields 'Min inactivity multiplier' and 'Max inactivity multiplier'; exposed in both initial setup flow and options flow; validation error in HA config UI if user sets min > max (blocks saving)
- **Config UI changes:** Current 'Inactivity multiplier' field — update both label and description to reflect it now scales a learned per-entity value (e.g., rename to 'Inactivity sensitivity scaling', description: 'Scales the auto-learned per-entity threshold. 1.0 = use learned threshold as-is; higher = more tolerant.'); add two new fields: 'Min inactivity multiplier' (default 1.5) and 'Max inactivity multiplier' (default 10.0)
- **Storage migration:** Bump schema version v6 → v7; migration adds `min_inactivity_multiplier=1.5` and `max_inactivity_multiplier=10.0` defaults to existing config entries; existing entries upgrade transparently without user intervention

### Claude's Discretion
- Exact variance metric (CV, std dev of intervals, or other normalized measure)
- Formula mapping variance to per-entity threshold scalar
- Whether numeric entities (temperature, power) participate in variance-adaptive thresholds or always use the fallback
- Internal constant names for min/max config keys
- Test fixture design and coverage strategy

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INAC-01 | The inactivity threshold for each entity is derived from that entity's own observed inter-event variance rather than applying a single global multiplier uniformly | Covered by: variance metric selection, threshold formula, slot-level computation in `ActivitySlot`, `AcuteDetector` hook point, config bounds, migration |
</phase_requirements>

---

## Summary

Phase 11 replaces the single-line threshold calculation `threshold = self._inactivity_multiplier * expected_gap` in `AcuteDetector.check_inactivity()` with a per-slot adaptive calculation. The adaptation uses the coefficient of variation (CV = std dev of intervals / mean of intervals) of the inter-event intervals already stored in `ActivitySlot.event_times`. CV is dimensionless and directly expresses relative timing variability, making it the best match for "tight for regular, loose for irregular" semantics without requiring any new data storage.

The formula maps CV to a per-slot multiplier scalar that is then clamped between user-configurable min and max bounds, and finally scaled by the global inactivity sensitivity scaling factor. All computation happens at query time from the existing `event_times` deque — no new persistence, no schema changes to the stored routine data. The only stored schema change is adding two new config-entry fields for min/max bounds, bumping STORAGE_VERSION and ConfigFlow.VERSION from 6 to 7.

Numeric entities (temperature, power) do not store timestamps in `event_times` — they use the Welford numeric path. They cannot participate in variance-adaptive thresholds because the required inter-event interval data does not exist for them. The correct behaviour is to fall back to the existing `global_multiplier × expected_gap` path for all non-binary slots.

**Primary recommendation:** Add `interval_cv()` to `ActivitySlot`, compute adaptive threshold in `AcuteDetector.check_inactivity()` at the existing line 79 hook point, expose min/max config fields, and migrate with a v6→v7 block.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `statistics` stdlib | 3.11+ | `stdev()` and `mean()` on the intervals list | Already imported in `routine_model.py` (`median`); no new deps |
| `math.sqrt` | stdlib | Population stdev alternative if needed | Already imported in `routine_model.py` |
| voluptuous | bundled with HA | Config flow schema validation | Already used throughout `config_flow.py` |
| HA `NumberSelector` | HA 2024.x | Min/max multiplier UI fields | Already used for `CONF_INACTIVITY_MULTIPLIER` field |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python `statistics.stdev` | stdlib | Sample std dev of intervals list | Use when `len(intervals) >= 2`; raises `StatisticsError` on single-element lists — must guard |
| Python `statistics.mean` | stdlib | Mean of intervals list | Use as denominator for CV |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CV (std dev / mean) | Raw std dev of intervals | Raw std dev is not dimensionless — a 10-minute std dev means something very different for a 1-hour entity vs a 10-hour entity; CV normalises for scale |
| CV | Inter-quartile range ratio | IQR is more robust to outliers but harder to explain; deque is bounded at 56 samples so outlier risk is low; CV is simpler |
| `statistics.stdev` (sample) | Population stdev (`sqrt(M2/n)`) | Sample stdev is already used for confidence intervals in `slot_distribution()`; sample stdev is preferable for small bounded samples |

**Installation:** No new packages needed.

---

## Architecture Patterns

### Recommended Project Structure
No new files required. All changes are within existing files:

```
custom_components/behaviour_monitor/
├── routine_model.py     # Add ActivitySlot.interval_cv() method
├── acute_detector.py    # Replace threshold line with adaptive formula
├── const.py             # Add CONF_MIN_INACTIVITY_MULTIPLIER, CONF_MAX_INACTIVITY_MULTIPLIER + defaults
├── config_flow.py       # Add two new NumberSelector fields; add min>max validation; update label/desc
└── __init__.py          # v6→v7 migration block

tests/
├── test_routine_model.py   # New tests for ActivitySlot.interval_cv()
├── test_acute_detector.py  # New tests for adaptive threshold behaviour
├── test_config_flow.py     # New tests for min>max validation
└── test_init.py            # New test for v6→v7 migration
```

### Pattern 1: Coefficient of Variation for Inter-Event Intervals

**What:** CV = std_dev(intervals) / mean(intervals). Returns a dimensionless ratio expressing relative variability. CV ≈ 0 means highly regular; CV ≈ 1 means high jitter (std dev equals mean); CV > 1 means highly erratic.

**When to use:** Whenever the slot has at least `MIN_SLOT_OBSERVATIONS` events (which means at least 3 intervals). This is the same guard already used for `expected_gap_seconds()`.

**Example:**
```python
# In ActivitySlot — computed from the same event_times deque
def interval_cv(self) -> float | None:
    """Return coefficient of variation of inter-event intervals.

    Returns None when the slot has fewer than MIN_SLOT_OBSERVATIONS events
    (same guard as expected_gap_seconds).
    Returns 0.0 when all intervals are identical (perfectly regular).
    """
    if len(self.event_times) < MIN_SLOT_OBSERVATIONS:
        return None
    try:
        times = sorted(datetime.fromisoformat(ts) for ts in self.event_times)
    except (ValueError, TypeError):
        return None
    intervals = [(times[i+1] - times[i]).total_seconds() for i in range(len(times) - 1)]
    if len(intervals) < 2:
        return None  # Need at least 2 intervals for std dev
    from statistics import mean, stdev
    m = mean(intervals)
    if m == 0.0:
        return 0.0
    return stdev(intervals) / m
```

### Pattern 2: Adaptive Threshold Formula

**What:** Map CV to a per-slot multiplier scalar, clamp to [min_bound, max_bound], then scale by the global sensitivity factor.

**When to use:** At the `AcuteDetector.check_inactivity()` hook point, when the slot has sufficient data for variance computation.

The formula `adaptive_scalar = 1.0 + cv` transforms CV directly into a multiplier:
- CV = 0.0 (perfectly regular) → scalar = 1.0 (tight: threshold = 1.0 × expected_gap, then scaled by global_multiplier)
- CV = 0.5 (moderately variable) → scalar = 1.5
- CV = 2.0 (very erratic) → scalar = 3.0

After clamping: `scalar = clamp(adaptive_scalar, min_bound, max_bound)`

Final threshold: `threshold = global_multiplier × scalar × expected_gap`

**Why this formula:** It is linear, intuitive, and the defaults (min=1.5, max=10) bound the meaningful range. At min=1.5, even a clock-regular entity must be inactive for 1.5× its typical interval before alerting — this prevents near-false-positives on hyper-regular sensors. At max=10, no entity ever needs to be absent for more than 10 typical intervals, which keeps thresholds from becoming completely silent.

**Example:**
```python
# In AcuteDetector.check_inactivity() — replaces line 79
cv = routine.interval_cv(now.hour, now.weekday())
if cv is not None:
    raw_scalar = 1.0 + cv
    scalar = max(self._min_multiplier, min(self._max_multiplier, raw_scalar))
    threshold = self._inactivity_multiplier * scalar * expected_gap
else:
    # Sparse slot or numeric entity — fall back to current behaviour
    threshold = self._inactivity_multiplier * expected_gap
```

### Pattern 3: Config Entry Migration (v6 → v7)

**What:** Following the established `async_migrate_entry` cascade pattern in `__init__.py`.

**When to use:** Adding two new config keys with defaults. Dict copy + `setdefault`, never mutate `config_entry.data` directly.

**Example:**
```python
if config_entry.version < 7:
    new_data = dict(config_entry.data)
    new_data.setdefault(CONF_MIN_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER)
    new_data.setdefault(CONF_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MAX_INACTIVITY_MULTIPLIER)
    hass.config_entries.async_update_entry(config_entry, data=new_data, version=7)
    _LOGGER.info("Behaviour Monitor: Config entry migrated to v7 — adaptive inactivity bounds added")
```

### Pattern 4: Min > Max Validation in Options Flow

**What:** Voluptuous validator or manual check in `async_step_init` after `user_input is not None`.

**When to use:** When the user submits the options form with min > max.

**Example:**
```python
if user_input is not None:
    min_val = float(user_input.get(CONF_MIN_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER))
    max_val = float(user_input.get(CONF_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MAX_INACTIVITY_MULTIPLIER))
    if min_val > max_val:
        errors["base"] = "inactivity_min_exceeds_max"
```

The same check must be replicated in `async_step_user` (initial setup flow) per the locked decision.

### Anti-Patterns to Avoid

- **Storing CV in persistence:** Don't add `interval_cv` to `ActivitySlot.to_dict()`. CV is always computed at query time from the already-stored `event_times`. Persisting it creates a stale-value risk.
- **Per-entity (not per-slot) CV:** Don't aggregate CV across all slots for an entity. Each slot is evaluated independently — the locked decision is explicit on this.
- **Applying variance to numeric entities:** Numeric entities use the Welford accumulator path (`numeric_count`, `numeric_mean`, `numeric_m2`) and do not store timestamps. `event_times` is empty for numeric slots. Any code path touching `interval_cv()` for a numeric entity will return `None` from the `len(self.event_times) < MIN_SLOT_OBSERVATIONS` guard, which routes correctly to the fallback. No special-casing is needed beyond the existing guard.
- **Calling `statistics.stdev` on a single-element list:** `stdev([x])` raises `StatisticsError`. Always guard with `len(intervals) >= 2`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Standard deviation | Custom incremental variance accumulator | `statistics.stdev` from stdlib | Stdlib handles edge cases, already imported via `median`; deque is bounded (max 56 samples) so performance is irrelevant |
| Voluptuous cross-field validation | Custom post-schema dict check | Manual validation in `async_step_init` body (same pattern as `no_entities_selected` check) | Voluptuous cross-field validators are complex; the existing pattern for `no_entities_selected` is simple and tested |
| Config field clamping | Runtime clamp in HA UI | `NumberSelector` `min`/`max` params for the input range; runtime clamp in `AcuteDetector.__init__` | HA UI enforces range on input; runtime clamp is a safety net for programmatic updates |

**Key insight:** All the building blocks already exist. This phase is wiring, not inventing.

---

## Common Pitfalls

### Pitfall 1: `statistics.stdev` on a Single Interval
**What goes wrong:** If `event_times` has exactly `MIN_SLOT_OBSERVATIONS` (4) events, there are exactly 3 intervals. `stdev([a, b, c])` works fine. But if timestamps are malformed and only 1 valid interval is parsed, `stdev([x])` raises `StatisticsError`.
**Why it happens:** `MIN_SLOT_OBSERVATIONS` guards the count of timestamps, not the count of valid parsed intervals.
**How to avoid:** Guard `len(intervals) >= 2` after parsing the intervals list, before calling `stdev`.
**Warning signs:** `StatisticsError` in logs during inactivity checks.

### Pitfall 2: CV = 0 When All Timestamps Are Identical
**What goes wrong:** If an entity fires at precisely the same time every week, all intervals are equal, `stdev = 0`, `CV = 0`. `adaptive_scalar = 1.0 + 0.0 = 1.0`, which is below the default min_bound of 1.5. After clamping, threshold = `global_multiplier × 1.5 × expected_gap` — this is correct behaviour.
**Why it matters:** Confirm in tests that the clamp to `min_bound` is applied even when CV = 0.

### Pitfall 3: Forgetting to Update Both Flows
**What goes wrong:** Adding the two new fields to `_build_data_schema()` but forgetting to read them back in `async_step_init` (options flow) or pass them into `AcuteDetector` in `coordinator.py`.
**How to avoid:** The task decomposition should include coordinator wiring as an explicit step, not an afterthought.

### Pitfall 4: Version Mismatch Between STORAGE_VERSION and ConfigFlow.VERSION
**What goes wrong:** Bumping one but not the other — established in the Phase 9 pattern decision that both must be bumped simultaneously.
**How to avoid:** Both `STORAGE_VERSION` (in `const.py`) and `BehaviourMonitorConfigFlow.VERSION` (in `config_flow.py`) bump to 7 in the same task.

### Pitfall 5: AcuteDetector Missing New Constructor Parameters
**What goes wrong:** `coordinator.py` constructs `AcuteDetector(float(...))` with a single positional arg. After adding `min_multiplier` and `max_multiplier` to `__init__`, the coordinator call site must be updated.
**How to avoid:** Update the coordinator construction call in the same task as updating `AcuteDetector.__init__`.

### Pitfall 6: `interval_cv()` Returns None for Sparse Slots Already Guarded by `expected_gap`
**What goes wrong:** Not a real pitfall — this is correct. The `expected_gap` guard already returns early if `expected_gap is None`, and `interval_cv` uses the same `MIN_SLOT_OBSERVATIONS` guard. If `expected_gap` is not None, the slot is sufficient, and `interval_cv` will also have data. The only case where `interval_cv` returns None when `expected_gap` is not None is if timestamp parsing fails — this routes to the fallback correctly.

---

## Code Examples

### interval_cv on ActivitySlot
```python
# Source: local codebase — mirrors expected_gap_seconds() pattern in routine_model.py
def interval_cv(self) -> float | None:
    if len(self.event_times) < MIN_SLOT_OBSERVATIONS:
        return None
    try:
        times = sorted(datetime.fromisoformat(ts) for ts in self.event_times)
    except (ValueError, TypeError):
        return None
    intervals = [(times[i+1] - times[i]).total_seconds() for i in range(len(times) - 1)]
    if len(intervals) < 2:
        return None
    from statistics import mean, stdev
    m = mean(intervals)
    if m == 0.0:
        return 0.0
    return stdev(intervals) / m
```

### EntityRoutine proxy method
```python
# Mirrors expected_gap_seconds(hour, dow) delegation pattern
def interval_cv(self, hour: int, dow: int) -> float | None:
    return self.slots[self.slot_index(hour, dow)].interval_cv()
```

### AcuteDetector adaptive threshold
```python
# Replaces: threshold = self._inactivity_multiplier * expected_gap
cv = routine.interval_cv(now.hour, now.weekday())
if cv is not None:
    raw_scalar = 1.0 + cv
    scalar = max(self._min_multiplier, min(self._max_multiplier, raw_scalar))
    threshold = self._inactivity_multiplier * scalar * expected_gap
else:
    threshold = self._inactivity_multiplier * expected_gap
```

### AcuteDetector constructor
```python
def __init__(
    self,
    inactivity_multiplier: float = DEFAULT_INACTIVITY_MULTIPLIER,
    sustained_cycles: int = SUSTAINED_EVIDENCE_CYCLES,
    min_multiplier: float = DEFAULT_MIN_INACTIVITY_MULTIPLIER,
    max_multiplier: float = DEFAULT_MAX_INACTIVITY_MULTIPLIER,
) -> None:
    self._inactivity_multiplier = inactivity_multiplier
    self._sustained_cycles = sustained_cycles
    self._min_multiplier = min_multiplier
    self._max_multiplier = max_multiplier
    self._inactivity_cycles: dict[str, int] = {}
    self._unusual_time_cycles: dict[str, int] = {}
```

### Coordinator construction
```python
# coordinator.py line ~76
self._acute_detector = AcuteDetector(
    float(d.get(CONF_INACTIVITY_MULTIPLIER, DEFAULT_INACTIVITY_MULTIPLIER)),
    min_multiplier=float(d.get(CONF_MIN_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER)),
    max_multiplier=float(d.get(CONF_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MAX_INACTIVITY_MULTIPLIER)),
)
```

### Config flow: new fields in `_build_data_schema`
```python
# Two new fields added to schema_dict after CONF_INACTIVITY_MULTIPLIER
vol.Required(
    CONF_MIN_INACTIVITY_MULTIPLIER, default=min_inactivity_multiplier_default
): NumberSelector(NumberSelectorConfig(min=0.5, max=5.0, step=0.5, mode=NumberSelectorMode.BOX)),
vol.Required(
    CONF_MAX_INACTIVITY_MULTIPLIER, default=max_inactivity_multiplier_default
): NumberSelector(NumberSelectorConfig(min=2.0, max=20.0, step=0.5, mode=NumberSelectorMode.BOX)),
```

### Config flow: min > max validation
```python
if user_input is not None:
    min_val = float(user_input.get(CONF_MIN_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER))
    max_val = float(user_input.get(CONF_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MAX_INACTIVITY_MULTIPLIER))
    if min_val > max_val:
        errors["base"] = "inactivity_min_exceeds_max"
    elif not user_input.get(CONF_MONITORED_ENTITIES):
        errors["base"] = "no_entities_selected"
    else:
        # proceed with entry creation / update
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `threshold = multiplier × expected_gap` (uniform global) | `threshold = multiplier × clamp(1 + CV, min, max) × expected_gap` (per-slot adaptive) | Phase 11 | Tight thresholds for regular entities; loose thresholds for erratic entities |
| Single inactivity multiplier config field | Three config fields: sensitivity scaling + min bound + max bound | Phase 11 | User controls sensitivity envelope without per-entity manual tuning |

**Deprecated/outdated:**
- Old label 'Inactivity multiplier': replaced by 'Inactivity sensitivity scaling' with updated description

---

## Open Questions

1. **CV formula for very short deques (3 intervals)**
   - What we know: With exactly 4 events (3 intervals), `statistics.stdev` uses n-1 denominator (Bessel's correction). On 3 observations the sample std dev is noisier than on 56 observations.
   - What's unclear: Whether a small-N penalty is warranted.
   - Recommendation: No penalty. The existing observation cap (56 events) and `MIN_SLOT_OBSERVATIONS` guard already limit noise. Adding a penalty adds complexity for marginal gain; the clamping to min/max bounds is sufficient protection.

2. **Exact NumberSelector range for min/max config fields**
   - What we know: Min bound default = 1.5, max bound default = 10.0.
   - What's unclear: Exactly what UI input range to set on the selectors.
   - Recommendation: Min multiplier selector: min=0.5, max=5.0, step=0.5. Max multiplier selector: min=2.0, max=20.0, step=0.5. These ranges bracket the defaults generously without allowing nonsensical values.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pytest.ini` / `Makefile` |
| Quick run command | `make test` |
| Full suite command | `make test` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INAC-01 | `interval_cv()` returns correct CV on regular intervals | unit | `python -m pytest tests/test_routine_model.py -x -k cv` | ❌ Wave 0 |
| INAC-01 | `interval_cv()` returns correct CV on irregular intervals | unit | `python -m pytest tests/test_routine_model.py -x -k cv` | ❌ Wave 0 |
| INAC-01 | `interval_cv()` returns None for sparse slot | unit | `python -m pytest tests/test_routine_model.py -x -k cv` | ❌ Wave 0 |
| INAC-01 | `interval_cv()` returns None if only 1 interval parseable | unit | `python -m pytest tests/test_routine_model.py -x -k cv` | ❌ Wave 0 |
| INAC-01 | `AcuteDetector` uses adaptive threshold when CV available | unit | `python -m pytest tests/test_acute_detector.py -x -k adaptive` | ❌ Wave 0 |
| INAC-01 | `AcuteDetector` falls back to global multiplier × expected_gap when CV None | unit | `python -m pytest tests/test_acute_detector.py -x -k fallback` | ❌ Wave 0 |
| INAC-01 | Regular entity (low CV) gets tighter threshold than erratic (high CV) | unit | `python -m pytest tests/test_acute_detector.py -x -k compare` | ❌ Wave 0 |
| INAC-01 | Adaptive scalar is clamped to min_multiplier when CV yields lower value | unit | `python -m pytest tests/test_acute_detector.py -x -k clamp_min` | ❌ Wave 0 |
| INAC-01 | Adaptive scalar is clamped to max_multiplier when CV yields higher value | unit | `python -m pytest tests/test_acute_detector.py -x -k clamp_max` | ❌ Wave 0 |
| INAC-01 | Config flow rejects min_multiplier > max_multiplier with error | unit | `python -m pytest tests/test_config_flow.py -x -k min_exceeds_max` | ❌ Wave 0 |
| INAC-01 | v6→v7 migration adds min/max fields to existing config entry | unit | `python -m pytest tests/test_init.py -x -k v7` | ❌ Wave 0 |
| INAC-01 | v7 config entry already at v7 is not re-migrated | unit | `python -m pytest tests/test_init.py -x -k v7` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `make test`
- **Per wave merge:** `make test`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
All new tests must be written in the same tasks that implement the features. No new test infrastructure is required — `tests/conftest.py` and `tests/__init__.py` exist and provide the `mock_hass` / `mock_config_entry` fixtures needed for config flow and init tests.

---

## Sources

### Primary (HIGH confidence)
- Local codebase — `routine_model.py`, `acute_detector.py`, `coordinator.py`, `config_flow.py`, `__init__.py`, `const.py`: direct inspection of the hook points, existing patterns, and data structures
- `.planning/phases/11-adaptive-inactivity/11-CONTEXT.md`: locked decisions and code context provided by domain author

### Secondary (MEDIUM confidence)
- Python `statistics` module docs (stdlib, no version change concern): `stdev()` raises `StatisticsError` on single-element input — confirmed in Python 3.11 stdlib docs

### Tertiary (LOW confidence)
None.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are already in use in the codebase; no new dependencies
- Architecture: HIGH — hook points, patterns, and integration points are directly readable in source
- Pitfalls: HIGH — derived from direct code reading plus established project decisions
- Variance metric (CV choice): MEDIUM — CV is well-suited but the exact scalar formula (1.0 + CV) is Claude's discretion; it is sensible and consistent with the user's described intent but not independently verified against prior art in this specific codebase

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable codebase; no fast-moving dependencies)
