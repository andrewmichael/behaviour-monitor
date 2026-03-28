# Technology Stack — v3.1 Activity-Rate Classification

**Project:** Behaviour Monitor v3.1
**Researched:** 2026-03-28
**Confidence:** HIGH
**Scope:** Stack additions/changes needed for activity-rate classification, tier-based detection logic, config UI tier override, and alert display formatting. Existing stack (RoutineModel, AcuteDetector, DriftDetector, coordinator, config flow v7, storage v7) is validated and not re-evaluated.

---

## Summary Decision

**No new dependencies.** All v3.1 features are implementable with Python stdlib arithmetic and string formatting on data already stored in `EntityRoutine.slots[*].event_times` deques. The existing Home Assistant selector framework (`SelectSelector`) provides the config UI widget. Config migration follows the established `setdefault` pattern (v8). No new storage files are needed -- tier classification is computed at runtime from existing persisted data, consistent with the v3.0 decision to "compute CV at query time, no new storage."

---

## Recommended Stack

### Core Technologies (Unchanged)

| Technology | Version | Purpose | v3.1 Role |
|------------|---------|---------|-----------|
| Python stdlib `statistics` | 3.11+ (HA-bundled) | `median`, `mean`, `stdev` | Reused for event rate computation across slots |
| Python stdlib `collections.deque` | stdlib | Bounded event storage per slot | Source data for rate classification (already holds up to 56 timestamps per slot) |
| Python stdlib `datetime` | stdlib | Timestamp parsing and interval math | Already used in `ActivitySlot.expected_gap_seconds()` |
| Python stdlib `enum` | stdlib | Enum types | New `ActivityTier` enum (HIGH/MEDIUM/LOW) |
| `homeassistant.helpers.selector.SelectSelector` | HA-bundled | Config UI dropdown | Tier override selector, identical pattern to existing `CONF_DRIFT_SENSITIVITY` |
| `homeassistant.helpers.storage.Store` | HA-bundled | JSON persistence | No changes -- tier is computed, not stored separately |
| `voluptuous` | HA-bundled | Schema validation | Config flow schema for new tier override field |

### New Internal Components (Zero External Dependencies)

| Component | Location | What It Does | Data Source |
|-----------|----------|-------------|-------------|
| `ActivityTier` enum | `const.py` | `HIGH`, `MEDIUM`, `LOW` tier values | -- |
| `EntityRoutine.compute_activity_tier()` | `routine_model.py` | Count total events across all populated slots, divide by time span to get events/hour, classify against thresholds | Existing `event_times` deques in `ActivitySlot` |
| Tier-aware threshold in `check_inactivity` | `acute_detector.py` | Apply `max(threshold, absolute_floor)` for high-frequency entities | `compute_activity_tier()` result passed in or computed |
| `_format_duration()` helper | `coordinator.py` or new `formatting.py` | `"Xm"` when < 1h, `"Xh Ym"` otherwise | Replaces inline formatting in `_build_sensor_data` and `check_inactivity` explanation |
| Config tier override field | `config_flow.py` | `SelectSelector` with auto/high/medium/low | User input stored in config entry data |
| v7-to-v8 migration | `__init__.py` | `setdefault(CONF_ACTIVITY_TIER_OVERRIDE, "auto")` | Existing migration chain pattern |

---

## Integration Points

### 1. Constants (`const.py`)

New constants needed:

```python
# Activity tier classification
CONF_ACTIVITY_TIER_OVERRIDE: Final = "activity_tier_override"
ACTIVITY_TIER_AUTO: Final = "auto"
ACTIVITY_TIER_HIGH: Final = "high"
ACTIVITY_TIER_MEDIUM: Final = "medium"
ACTIVITY_TIER_LOW: Final = "low"
DEFAULT_ACTIVITY_TIER: Final = ACTIVITY_TIER_AUTO

# Tier classification thresholds (events per hour, entity-wide average)
TIER_HIGH_THRESHOLD: Final = 6.0    # >6 events/hour = high-frequency
TIER_LOW_THRESHOLD: Final = 0.5     # <0.5 events/hour = low-frequency
# Between 0.5 and 6.0 = medium-frequency

# High-frequency entity detection overrides
HIGH_FREQ_MULTIPLIER_BOOST: Final = 2.0    # extra multiplier on top of base
HIGH_FREQ_MIN_FLOOR_SECONDS: Final = 300   # 5-minute absolute minimum inactivity threshold
```

**Confidence:** HIGH -- internal constants, no dependency implications.

**Threshold rationale:** A motion sensor in a busy hallway fires 10-20+ times/hour (high). A front door opens 2-5 times/hour (medium). A lock changes 0.1-0.3 times/hour (low). The 6.0 and 0.5 boundaries separate these clusters. These are starting values that can be tuned with real data.

### 2. Rate Classification (`routine_model.py`)

New method on `EntityRoutine`:

```python
def compute_activity_tier(self) -> str:
    """Classify entity into high/medium/low activity tier based on observed event rate."""
    total_events = 0
    populated_slots = 0
    for slot in self.slots:
        n = len(slot.event_times)
        if n > 0:
            total_events += n
            populated_slots += 1
    if populated_slots == 0:
        return ACTIVITY_TIER_MEDIUM  # default when no data
    # Each slot represents 1 hour; events_per_hour = total / populated_slots
    events_per_hour = total_events / populated_slots
    if events_per_hour > TIER_HIGH_THRESHOLD:
        return ACTIVITY_TIER_HIGH
    if events_per_hour < TIER_LOW_THRESHOLD:
        return ACTIVITY_TIER_LOW
    return ACTIVITY_TIER_MEDIUM
```

**Why this approach works:** Each of the 168 `ActivitySlot` instances maps to one hour-of-day x day-of-week. The `event_times` deque holds up to 56 timestamps per slot. Counting total events across populated slots and dividing by the number of populated slots gives events-per-active-hour, which is the correct metric for classification (it ignores hours when the entity is never active, avoiding dilution from overnight slots).

**Confidence:** HIGH -- simple arithmetic on existing data structures. No parsing needed beyond `len()`.

### 3. Tier-Aware Detection (`acute_detector.py`)

The `check_inactivity` method gains tier awareness. Two changes:

1. **Accept tier parameter** (or compute it from the routine):
   ```python
   def check_inactivity(self, entity_id, routine, now, last_seen, tier="medium"):
   ```

2. **Apply absolute floor for high-frequency tier:**
   ```python
   # After computing threshold from multiplier * scalar * expected_gap:
   if tier == ACTIVITY_TIER_HIGH:
       threshold = max(threshold, HIGH_FREQ_MIN_FLOOR_SECONDS)
       threshold *= HIGH_FREQ_MULTIPLIER_BOOST
   ```

**Why the floor matters:** A motion sensor with a 30-second median gap and 3x multiplier produces a 90-second threshold. This fires after just 1.5 minutes of inactivity -- too aggressive. The 5-minute floor prevents this class of false positive entirely. The additional multiplier boost (2x) further widens the threshold for high-frequency entities because their short gaps make the base multiplier insufficient.

**Why not change low-frequency behavior:** Low-frequency entities (doors, locks) already have large expected gaps (hours), so their thresholds are naturally conservative. No adjustment needed.

**Confidence:** HIGH -- single conditional branch addition to existing threshold computation.

### 4. Display Formatting

Two locations need changes. Both are string formatting, no external libraries.

**`acute_detector.py` explanation strings (line 116-125):**
Currently: `f"{elapsed_hours:.1f}h"` always, even when elapsed is 3 minutes.
Change to: minutes when < 1 hour, hours otherwise.

**`coordinator.py` `_build_sensor_data` (lines 283-288):**
Currently: `f"{h}h {m}m ago"` with fallback to `f"{m}m ago"` only when h==0.
This already works correctly for the `time_since` display (the `if h else` branch handles it). But the `typical_interval_formatted` on line 288 uses the same pattern and should be consistent.

**Recommended approach:** Extract a shared `_format_duration(seconds: float) -> str` helper to avoid duplicating the < 1h logic in multiple locations. Place it in a small utility or at module level in coordinator.py.

```python
def _format_duration(seconds: float) -> str:
    """Format seconds as 'Xm' (< 1h) or 'Xh Ym' (>= 1h)."""
    if seconds < 3600:
        return f"{int(seconds) // 60}m"
    h, m = int(seconds) // 3600, (int(seconds) % 3600) // 60
    return f"{h}h {m}m"
```

**Confidence:** HIGH -- pure string formatting.

### 5. Config Flow (`config_flow.py`)

Add `CONF_ACTIVITY_TIER_OVERRIDE` to `_build_data_schema`, using the exact same `SelectSelector` + `SelectSelectorConfig` pattern as `CONF_DRIFT_SENSITIVITY`:

```python
vol.Required(
    CONF_ACTIVITY_TIER_OVERRIDE, default=activity_tier_default
): SelectSelector(
    SelectSelectorConfig(
        options=[
            {"value": "auto", "label": "Auto-detect (recommended)"},
            {"value": "high", "label": "High frequency (motion, power monitors)"},
            {"value": "medium", "label": "Medium frequency"},
            {"value": "low", "label": "Low frequency (doors, locks)"},
        ],
        mode=SelectSelectorMode.DROPDOWN,
    )
)
```

**Important:** This is a global override, not per-entity. Per-entity sensitivity tuning is explicitly out of scope per PROJECT.md. The "auto" default means the classifier runs; user override replaces auto-detection for ALL entities in the config entry.

**Confidence:** HIGH -- identical to existing drift_sensitivity selector.

### 6. Config Migration (`__init__.py`)

v7 to v8 migration, following the established `setdefault` pattern:

```python
if config_entry.version < 8:
    new_data = dict(config_entry.data)
    new_data.setdefault(CONF_ACTIVITY_TIER_OVERRIDE, ACTIVITY_TIER_AUTO)
    hass.config_entries.async_update_entry(config_entry, data=new_data, version=8)
```

Also update `STORAGE_VERSION` in `const.py` to 8 and `ConfigFlow.VERSION` to 8.

**Confidence:** HIGH -- identical to five previous migrations.

### 7. Coordinator Wiring (`coordinator.py`)

The coordinator needs to:
1. Read `CONF_ACTIVITY_TIER_OVERRIDE` from config entry data in `__init__`
2. In `_run_detection`, determine each entity's effective tier (override or auto-computed)
3. Pass tier to `AcuteDetector.check_inactivity`

**No new coordinator fields needed for persistence** -- tier is either config (already persisted in config entry) or computed (from persisted slot data).

**Confidence:** HIGH -- follows existing pattern of reading config in `__init__` and passing to detectors.

### 8. Sensor Attributes (Optional Enhancement)

Expose each entity's detected tier as an attribute on the `entity_status_summary` sensor. No new sensor entity needed.

```python
# In entity_status extra_attrs_fn, add:
"activity_tier": tier_value  # "high", "medium", or "low"
```

**Confidence:** HIGH -- attribute addition to existing sensor.

---

## What NOT to Add

| Temptation | Why Not | Do Instead |
|------------|---------|------------|
| numpy/scipy for rate statistics | Violates pure-Python constraint; `len(deque)` and division are sufficient | Count `event_times` entries with stdlib |
| Per-entity config storage for tier | Out of scope per PROJECT.md ("Per-entity sensitivity tuning UI -- future milestone") | Global tier override with auto-detect default |
| New sensor entity for tier | Increases sensor count; tier is a detection parameter not a measurement | Expose as attribute on existing `entity_status_summary` sensor |
| Machine learning for tier classification | Violates no-ML constraint; k-means is overkill for 3 tiers | Threshold-based: events/hour > 6 = high, < 0.5 = low |
| Separate `.storage` file for tier data | Adds schema complexity; tier is cheap to recompute from existing slot data | Compute on load from `event_times` deques (< 1ms) |
| Per-entity tier override in config | Config flow would need dynamic entity selector + per-entity dropdown; complex UI for uncertain benefit | Global override; per-entity is a future milestone |

---

## Installation

No changes. No new packages.

```bash
# manifest.json: "requirements": [] remains empty
# No pip install changes
make dev-setup
source venv/bin/activate
make test
```

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| No new dependencies | HIGH | All features are arithmetic/string ops on existing data structures |
| Config flow pattern | HIGH | Identical to 5 previous config additions in this codebase |
| Rate classification approach | HIGH | `len(event_times)` across slots is trivial stdlib |
| Display formatting | HIGH | String formatting only |
| Tier thresholds (6.0 / 0.5) | MEDIUM | Reasonable starting points; may need tuning with real sensor data |
| High-freq floor (300s) | MEDIUM | 5 minutes is conservative; may need adjustment per entity type |
| Storage approach (compute, don't persist) | HIGH | Consistent with v3.0 CV decision; event_times already persisted |

---

## Sources

- Codebase analysis: `const.py`, `routine_model.py` (EntityRoutine, ActivitySlot), `acute_detector.py` (check_inactivity threshold logic), `coordinator.py` (_build_sensor_data formatting), `config_flow.py` (SelectSelector pattern for drift_sensitivity), `__init__.py` (migration chain v2-v7), `sensor.py` (entity_status_summary sensor), `alert_result.py`
- PROJECT.md constraints: "No new dependencies: Pure Python", "Per-entity sensitivity tuning UI -- future milestone"
- Established patterns: config migration chain v2-v7 using `setdefault`, SelectSelector usage for drift_sensitivity, CV compute-at-query-time decision from v3.0 Key Decisions table

---

*Stack research for: Behaviour Monitor v3.1 Activity-Rate Classification*
*Researched: 2026-03-28*
