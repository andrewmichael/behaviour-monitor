# Architecture Research: Activity-Rate Classification

**Domain:** Home Assistant custom integration — activity-rate classification and display formatting (v3.1)
**Researched:** 2026-03-28
**Confidence:** HIGH (full codebase read, all integration points identified from source)

---

## Current Architecture (What Exists)

```
custom_components/behaviour_monitor/
├── __init__.py           # HA entry point, config migration chain (v2->v7), service registration
├── sensor.py             # 11 sensor entity descriptions via CoordinatorEntity
├── coordinator.py        # BehaviourMonitorCoordinator (~377 lines) — orchestrator
├── routine_model.py      # RoutineModel + EntityRoutine + ActivitySlot (pure Python)
├── acute_detector.py     # AcuteDetector — inactivity + unusual-time (pure Python)
├── drift_detector.py     # DriftDetector — bidirectional CUSUM (pure Python)
├── alert_result.py       # AlertResult, AlertType, AlertSeverity (pure Python)
├── config_flow.py        # v7 config with OptionsFlowHandler
└── const.py              # All constants and defaults
```

### Key Data Flow (Relevant to This Milestone)

```
EntityRoutine.record(timestamp, state_value)
        |
        v
ActivitySlot.event_times deque (maxlen=56 per slot, 168 slots)
        |
        +---> ActivitySlot.expected_gap_seconds()  -- median inter-event interval
        +---> ActivitySlot.interval_cv()           -- coefficient of variation
        |
        v
AcuteDetector.check_inactivity(entity_id, routine, now, last_seen)
        |
        +---> expected_gap = routine.expected_gap_seconds(hour, dow)
        +---> cv = routine.interval_cv(hour, dow)
        +---> scalar = clamp(1.0 + cv, min_multiplier, max_multiplier)
        +---> threshold = inactivity_multiplier * scalar * expected_gap
        +---> elapsed >= threshold? -> increment sustained counter
        |
        v
AlertResult with explanation: "{elapsed_hours:.1f}h (typical interval: {typical_hours:.1f}h, ...)"
```

**The problem this milestone solves:** A motion sensor firing every 2 minutes has `expected_gap_seconds() = ~120`. With `inactivity_multiplier=3.0` and even maximum `scalar=10.0`, the threshold is `3.0 * 10.0 * 120 = 3600s = 1 hour`. Any 1-hour gap triggers an alert -- completely normal for someone leaving the house. There is no minimum floor, and the hardcoded hours-based display formatting shows "0.0h" for sub-hour intervals.

---

## Recommended Architecture (v3.1 Integration)

### Design Principle: Classify at the Data Layer, Consume Everywhere

Activity-rate classification is a **property of an entity's learned routine**, not a property of the detector. The tier should be computed from `EntityRoutine` data and stored on `EntityRoutine`, then consumed by `AcuteDetector` (for tier-appropriate thresholds), by `coordinator.py` (for sensor data), and by the config flow (for user override).

### Where Each Piece Lives

| Concern | File | New or Modified | Rationale |
|---------|------|-----------------|-----------|
| `ActivityTier` enum | `const.py` | Modified | Enum + tier boundary constants belong with other constants |
| Tier classification logic | `routine_model.py` | Modified | Pure function on EntityRoutine data; keeps HA-free testability |
| `activity_tier` stored field | `routine_model.py` | Modified | Persisted on EntityRoutine for stability (no flapping) |
| Tier override config key | `const.py` | Modified | New `CONF_ACTIVITY_TIER_OVERRIDES` key |
| Tier override UI | `config_flow.py` | Modified | Per-entity dropdown in options flow |
| Tier-aware inactivity logic | `acute_detector.py` | Modified | Receives tier; applies tier-specific multiplier + floor |
| Display formatting | `acute_detector.py` | Modified | Format explanation string based on interval magnitude |
| Tier in sensor data | `coordinator.py` | Modified | Pass tier info to sensor data dict |
| Tier display sensor | `sensor.py` | Modified | Expose tier as sensor attribute (not new sensor) |
| Config migration v7->v8 | `__init__.py` | Modified | Add `activity_tier_overrides` with empty default |

**No new files.** This milestone modifies existing components. The classification logic is small enough (~30 lines) to live as a method on `EntityRoutine` rather than a separate module.

---

## Component Boundaries

### 1. ActivityTier Enum and Constants (`const.py`)

```python
class ActivityTier(str, Enum):
    HIGH = "high"        # >24 events/day typical (motion sensors, power monitors)
    MEDIUM = "medium"    # 4-24 events/day typical (doors, lights)
    LOW = "low"          # <4 events/day typical (garage door, rarely-used rooms)

# Tier classification boundaries (events per day across all observed days)
TIER_HIGH_THRESHOLD: Final = 24    # above this = HIGH
TIER_LOW_THRESHOLD: Final = 4     # below this = LOW; between = MEDIUM

# Tier-specific inactivity parameters
TIER_INACTIVITY_FLOORS: Final = {
    ActivityTier.HIGH: 3600,    # 1 hour minimum -- a person leaving the house is normal
    ActivityTier.MEDIUM: 0,     # no floor -- existing logic is appropriate
    ActivityTier.LOW: 0,        # no floor -- long gaps are expected and already handled
}

TIER_INACTIVITY_MULTIPLIER_BOOST: Final = {
    ActivityTier.HIGH: 2.0,     # double the effective multiplier for high-frequency entities
    ActivityTier.MEDIUM: 1.0,   # no change
    ActivityTier.LOW: 1.0,      # no change
}

# Config key for per-entity tier overrides
CONF_ACTIVITY_TIER_OVERRIDES: Final = "activity_tier_overrides"
DEFAULT_ACTIVITY_TIER_OVERRIDES: Final = {}  # empty = all auto-classified
```

**Rationale for thresholds:** A motion sensor in an active room fires 50-200+ times per day. A door contact fires 4-20 times. A garage door fires 0-4 times. The 24/4 split cleanly separates these categories based on real-world HA usage patterns. These are median daily rates across the observation window, not peak rates.

### 2. Tier Classification on EntityRoutine (`routine_model.py`)

Add a `classify_tier()` method and a persisted `_activity_tier` field:

```python
@dataclass
class EntityRoutine:
    entity_id: str
    is_binary: bool
    slots: list[ActivitySlot] = ...
    history_window_days: int = ...
    first_observation: str | None = None
    _activity_tier: str | None = None  # persisted tier; None = not yet classified

    def classify_tier(self) -> str | None:
        """Compute activity tier from median daily event rate across all observed days.

        Returns tier string ("high"/"medium"/"low") or None if insufficient data.
        Scans all slots' event_times to build per-date event counts, then takes
        the median daily count as the classification signal.
        """
        # Collect per-date event counts across all slots
        date_counts: dict[date, int] = {}
        for slot in self.slots:
            for ts_str in slot.event_times:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    d = dt.date()
                    date_counts[d] = date_counts.get(d, 0) + 1
                except (ValueError, TypeError):
                    pass
        if len(date_counts) < 3:  # need at least 3 days of data
            return None
        med = median(sorted(date_counts.values()))
        if med >= TIER_HIGH_THRESHOLD:
            return ActivityTier.HIGH.value
        if med < TIER_LOW_THRESHOLD:
            return ActivityTier.LOW.value
        return ActivityTier.MEDIUM.value

    @property
    def activity_tier(self) -> str | None:
        """Return the current activity tier, computing if not yet set."""
        if self._activity_tier is None:
            self._activity_tier = self.classify_tier()
        return self._activity_tier

    def reclassify_tier(self) -> None:
        """Force reclassification (called periodically by coordinator)."""
        self._activity_tier = self.classify_tier()
```

**Key design decisions:**

- **Median, not mean:** A single high-activity day should not push a normally quiet entity into the HIGH tier. Median is robust to outliers.
- **Minimum 3 days:** Classification needs enough data to be meaningful. Aligns with `MIN_EVIDENCE_DAYS` used by DriftDetector.
- **Cached with explicit reclassify:** Tier should not flap on every poll cycle. The coordinator calls `reclassify_tier()` once per day (or on config change). Between reclassifications, the cached value is used.
- **Persisted via `to_dict`/`from_dict`:** Tier survives HA restart. No flapping during learning period.

### 3. Tier-Aware AcuteDetector (`acute_detector.py`)

The `check_inactivity` method gains two new behaviors based on tier:

```python
def check_inactivity(
    self,
    entity_id: str,
    routine: EntityRoutine,
    now: datetime,
    last_seen: datetime | None,
) -> AlertResult | None:
    # ... existing guards ...

    # Tier-aware threshold computation
    tier = routine.activity_tier  # may be None during learning
    tier_enum = ActivityTier(tier) if tier else ActivityTier.MEDIUM

    # Base threshold (existing logic)
    if cv is not None:
        raw_scalar = 1.0 + cv
        scalar = max(self._min_multiplier, min(self._max_multiplier, raw_scalar))
        threshold = self._inactivity_multiplier * scalar * expected_gap
    else:
        threshold = self._inactivity_multiplier * expected_gap

    # Tier-specific adjustments
    multiplier_boost = TIER_INACTIVITY_MULTIPLIER_BOOST[tier_enum]
    floor = TIER_INACTIVITY_FLOORS[tier_enum]
    threshold = max(threshold * multiplier_boost, floor)

    # ... rest of existing logic (elapsed comparison, sustained evidence, alert creation) ...

    # Display formatting (see section 5)
    elapsed_fmt = _format_duration(elapsed)
    typical_fmt = _format_duration(expected_gap)

    return AlertResult(
        ...,
        explanation=(
            f"{entity_id}: no activity for {elapsed_fmt} "
            f"(typical interval: {typical_fmt}, "
            f"{severity_ratio:.1f}x over threshold)"
        ),
        details={
            ...,
            "activity_tier": tier,
        },
    )
```

**Why the tier modifies AcuteDetector rather than RoutineModel:** The tier is a classification of the entity. The threshold adjustment is a detection policy. These are separate concerns. RoutineModel answers "what is this entity's pattern?" AcuteDetector answers "is this entity behaving anomalously right now?" The tier bridges them by informing the detector's policy.

**Why multiplier boost AND floor (not just floor):**
- Floor alone: A HIGH entity with `expected_gap=2min` and `multiplier=3.0` gets threshold `max(360s, 3600s) = 3600s`. Good. But an entity with `expected_gap=30min` gets `max(5400s, 3600s) = 5400s` -- the floor has no effect and the threshold is still potentially too tight for high-frequency entities.
- Boost alone: Doubles the threshold from `360s` to `720s` -- still only 12 minutes, still too aggressive.
- Both: `max(720s, 3600s) = 3600s`. The floor catches very-high-frequency entities; the boost catches moderately-high ones.

### 4. Tier Override in Config Flow (`config_flow.py`)

Add a per-entity tier override to the options flow. This is a dict mapping `entity_id -> tier_string`, stored in config entry data.

```python
# In _build_data_schema(), add after existing fields:
vol.Optional(
    CONF_ACTIVITY_TIER_OVERRIDES,
    default=DEFAULT_ACTIVITY_TIER_OVERRIDES,
): ObjectSelector(
    ObjectSelectorConfig()  # Free-form dict; see note below
)
```

**UI approach:** HA's config flow does not natively support a "per-entity key-value map" selector. Two practical options:

1. **Option A (recommended): Separate step in options flow.** Add an `async_step_tier_overrides` that shows monitored entities with their auto-detected tier and a dropdown to override. This is the cleanest UX -- users see current classification and can change it.

2. **Option B: TextSelector with JSON.** Store overrides as a JSON string. Functional but poor UX for non-technical users.

Option A implementation sketch:
```python
async def async_step_init(self, user_input=None) -> ConfigFlowResult:
    # ... existing options logic ...
    # Add a "Configure activity tiers" menu item
    return self.async_show_menu(
        step_id="init",
        menu_options=["settings", "activity_tiers"],
    )

async def async_step_activity_tiers(self, user_input=None) -> ConfigFlowResult:
    if user_input is not None:
        # user_input is {entity_id: tier_string} for each monitored entity
        overrides = {k: v for k, v in user_input.items() if v != "auto"}
        updated_data = dict(self._config_entry.data)
        updated_data[CONF_ACTIVITY_TIER_OVERRIDES] = overrides
        self.hass.config_entries.async_update_entry(self._config_entry, data=updated_data)
        return self.async_create_entry(title="", data={})

    # Build schema: one SelectSelector per monitored entity
    coordinator = self.hass.data[DOMAIN][self._config_entry.entry_id]
    schema_dict = {}
    for eid in coordinator.monitored_entities:
        routine = coordinator._routine_model._entities.get(eid)
        auto_tier = routine.activity_tier if routine else None
        current_override = self._config_entry.data.get(
            CONF_ACTIVITY_TIER_OVERRIDES, {}
        ).get(eid, "auto")
        schema_dict[vol.Optional(eid, default=current_override)] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": "auto", "label": f"Auto ({auto_tier or 'learning'})"},
                    {"value": "high", "label": "High frequency"},
                    {"value": "medium", "label": "Medium frequency"},
                    {"value": "low", "label": "Low frequency"},
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
    return self.async_show_form(
        step_id="activity_tiers",
        data_schema=vol.Schema(schema_dict),
    )
```

**Important:** The options flow currently uses a single `async_step_init` without menus. Adding a multi-step flow with `async_show_menu` changes the UX pattern. This is a moderate-complexity change to config_flow.py but follows standard HA patterns.

**Alternative (simpler, recommended for v3.1):** Skip the separate step. Add tier overrides as a single `TextSelector` with format instructions, or defer the override UI to a future milestone and ship auto-classification only. The auto-classification itself solves the primary false-positive problem; override is a refinement.

### 5. Display Formatting (`acute_detector.py`)

Add a module-level helper for human-readable duration formatting:

```python
def _format_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string.

    Uses minutes for intervals < 1 hour, hours+minutes for >= 1 hour.
    """
    total_seconds = int(seconds)
    if total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes}m"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes}m"
```

This replaces the current hardcoded `f"{elapsed_hours:.1f}h"` and `f"{typical_hours:.1f}h"` formatting in `check_inactivity`.

**Also fix coordinator.py:** The `_build_sensor_data` method has identical hardcoded hours formatting for `time_since_formatted` and `typical_interval_formatted`. Extract to a shared utility or import `_format_duration` from `acute_detector`. Since `acute_detector` is pure Python (no HA imports), importing from it is safe. Alternatively, place the helper in a new `formatting.py` or in `routine_model.py` as a module-level function.

**Recommendation:** Place `_format_duration` in `routine_model.py` as a module-level utility. Both `acute_detector.py` and `coordinator.py` already import from `routine_model`. This avoids a new file and keeps the import graph clean.

### 6. Coordinator Integration (`coordinator.py`)

Changes to the coordinator are minimal:

```python
# In __init__:
self._tier_overrides: dict[str, str] = dict(
    d.get(CONF_ACTIVITY_TIER_OVERRIDES, DEFAULT_ACTIVITY_TIER_OVERRIDES)
)

# In _handle_state_changed (after routine_model.record):
# Apply tier override if configured
if eid in self._tier_overrides:
    routine = self._routine_model._entities.get(eid)
    if routine:
        routine._activity_tier = self._tier_overrides[eid]

# In _async_update_data (once per day logic, reuse existing _today_date check):
if self._today_date != now.date():
    # Reclassify tiers daily (unless overridden)
    for eid in self._monitored_entities:
        if eid not in self._tier_overrides:
            routine = self._routine_model._entities.get(eid)
            if routine:
                routine.reclassify_tier()

# In _build_sensor_data: add tier info to entity_status entries
"entity_status": [
    {
        "entity_id": e,
        "status": "active" if e in self._last_seen else "unknown",
        "last_seen": self._last_seen[e].isoformat() if e in self._last_seen else None,
        "activity_tier": (
            self._routine_model._entities[e].activity_tier
            if e in self._routine_model._entities else None
        ),
    }
    for e in self._monitored_entities
],
```

### 7. Sensor Exposure (`sensor.py`)

No new sensor entities. Tier is exposed as an attribute on the existing `entity_status_summary` sensor:

```python
# In the entity_status_summary description's extra_attrs_fn:
extra_attrs_fn=lambda coord, data: {
    ATTR_ENTITY_STATUS: data.get("entity_status", []),
    # Each entity_status entry now includes "activity_tier" key
},
```

This preserves the 11-sensor count and avoids sensor entity ID changes.

### 8. Config Migration (`__init__.py`)

```python
# Add v7->v8 migration:
if config_entry.version < 8:
    new_data = dict(config_entry.data)
    new_data.setdefault(CONF_ACTIVITY_TIER_OVERRIDES, DEFAULT_ACTIVITY_TIER_OVERRIDES)
    hass.config_entries.async_update_entry(config_entry, data=new_data, version=8)
    _LOGGER.info(
        "Behaviour Monitor: Config entry migrated to v8 -- activity tier overrides added"
    )
```

Also bump `BehaviourMonitorConfigFlow.VERSION = 8` and `STORAGE_VERSION` if storage schema changes (it does -- `EntityRoutine.to_dict` now includes `_activity_tier`).

**Storage migration:** No special handling needed. `EntityRoutine.from_dict` already uses `.get()` with defaults for missing keys. Adding `_activity_tier` to `to_dict`/`from_dict` is backward-compatible -- old storage simply has no `_activity_tier` key, which defaults to `None` (triggers auto-classification on next load).

---

## Data Flow: Complete Tier-Aware Inactivity Check

```
EntityRoutine (168 slots of event_times)
        |
        +---> classify_tier() [called once/day by coordinator]
        |     Scans all event_times, builds date->count map, takes median
        |     Returns "high" / "medium" / "low" / None
        |     Cached in _activity_tier field (persisted)
        |
        +---> expected_gap_seconds(hour, dow) [called per check]
        +---> interval_cv(hour, dow) [called per check]
        |
        v
AcuteDetector.check_inactivity(entity_id, routine, now, last_seen)
        |
        +---> tier = routine.activity_tier
        +---> base_threshold = inactivity_multiplier * adaptive_scalar * expected_gap
        +---> boosted_threshold = base_threshold * TIER_INACTIVITY_MULTIPLIER_BOOST[tier]
        +---> final_threshold = max(boosted_threshold, TIER_INACTIVITY_FLOORS[tier])
        +---> elapsed >= final_threshold? sustained evidence? -> AlertResult
        |
        v
AlertResult.explanation uses _format_duration() for human-readable output
        |  "no activity for 45m (typical interval: 2m, 3.1x over threshold)"
        |  instead of: "no activity for 0.8h (typical interval: 0.0h, ...)"
```

---

## Integration Points Summary

| Touchpoint | File | Change Type | Lines (est.) |
|------------|------|-------------|-------------|
| `ActivityTier` enum + constants | `const.py` | Add | ~25 |
| `classify_tier()`, `activity_tier` property, `reclassify_tier()` | `routine_model.py` | Add methods to EntityRoutine | ~40 |
| `_activity_tier` in `to_dict`/`from_dict` | `routine_model.py` | Modify serialization | ~6 |
| `_format_duration()` utility | `routine_model.py` | Add module-level function | ~12 |
| Tier-aware threshold (boost + floor) | `acute_detector.py` | Modify `check_inactivity` | ~10 |
| Duration formatting in explanation | `acute_detector.py` | Modify explanation string | ~4 |
| Duration formatting in sensor data | `coordinator.py` | Modify `_build_sensor_data` | ~6 |
| Tier override from config | `coordinator.py` | Add to `__init__`, apply in handlers | ~15 |
| Daily reclassification | `coordinator.py` | Add to `_async_update_data` | ~8 |
| Tier in entity_status dict | `coordinator.py` | Modify `_build_sensor_data` | ~5 |
| Tier override step | `config_flow.py` | Add optional step (or defer) | ~40 |
| Config migration v7->v8 | `__init__.py` | Add migration block | ~10 |
| New config constant | `const.py` | Add key + default | ~3 |
| Translations | `translations/en.json` | Add tier labels | ~10 |

**Total estimated: ~195 lines of new/modified code** (excluding tests).

---

## Suggested Build Order

Dependencies run bottom-up. Each step is independently testable.

| Step | What | Depends On | Test Focus |
|------|------|------------|------------|
| 1 | `const.py` -- `ActivityTier` enum, tier thresholds, floor/boost maps, config key | Nothing | Import verification |
| 2 | `routine_model.py` -- `_format_duration()` utility function | Nothing | Unit tests for edge cases (0s, 59s, 60s, 3599s, 3600s, multi-hour) |
| 3 | `routine_model.py` -- `classify_tier()`, `activity_tier`, `reclassify_tier()`, `to_dict`/`from_dict` update | Step 1 (enum import) | Classification with varying event rates; persistence round-trip; None for insufficient data |
| 4 | `acute_detector.py` -- tier-aware threshold (boost + floor) + display formatting | Steps 1, 2, 3 | HIGH-tier entity gets floor applied; MEDIUM/LOW unchanged; formatted strings use minutes when < 1h |
| 5 | `coordinator.py` -- tier override injection, daily reclassification, tier in sensor data, display formatting fix | Steps 1-4 | Integration: override applied; reclassify runs daily; sensor data contains tier |
| 6 | `config_flow.py` -- tier override UI + `__init__.py` migration | Step 5 | Config migration v7->v8; UI renders; overrides saved |
| 7 | `sensor.py` + `translations/en.json` -- tier in entity_status attributes, labels | Step 5 | Sensor attributes include tier |

**Steps 2 and 3 can be combined** into a single phase since they both modify `routine_model.py`.

**Step 6 (config UI) is optional for MVP.** Auto-classification alone solves the primary false-positive problem. Override UI can ship in a follow-up if needed. If deferred, skip the config migration too (no new config key needed if no override).

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Tier Classification Inside AcuteDetector

**What goes wrong:** Putting `classify_tier()` logic inside `AcuteDetector.check_inactivity` so it computes the tier on every check.

**Why bad:** Classification scans all 168 slots' event_times deques -- O(total_events). Running this every 60 seconds per entity is wasteful. The tier changes at most once per day.

**Instead:** Classify once per day on `EntityRoutine`. Cache the result. Detector reads the cached tier.

### Anti-Pattern 2: Adding a New Sensor for Tier

**What goes wrong:** Creating a 12th sensor entity for activity tier display.

**Why bad:** Adds a sensor entity ID that users must discover. Tier is a property of existing entities, not a standalone metric. It also risks the "too many sensors" problem where users feel overwhelmed.

**Instead:** Expose tier as an attribute on the existing `entity_status_summary` sensor, where per-entity information already lives.

### Anti-Pattern 3: Tier Flapping Without Hysteresis

**What goes wrong:** Reclassifying tier on every coordinator update cycle. An entity near the 24 events/day boundary flips between HIGH and MEDIUM with each poll.

**Why bad:** Flapping tier means flapping threshold behavior. An entity could go from floor-protected to non-floor-protected between cycles.

**Instead:** Reclassify once per day. Use median (not mean) of daily rates, which is inherently resistant to single-day outliers. Consider adding hysteresis bands (e.g., transition HIGH->MEDIUM requires dropping below 20, not just below 24) in a future iteration if flapping is observed.

### Anti-Pattern 4: Modifying AlertResult Structure

**What goes wrong:** Adding `activity_tier` as a field on `AlertResult` dataclass.

**Why bad:** Tier is metadata about the entity, not about the alert. `AlertResult.details` dict already handles arbitrary extra data.

**Instead:** Include tier in `details={"activity_tier": tier, ...}` as already shown in the design.

---

## Sources

- Full codebase read: `routine_model.py` (458 lines), `acute_detector.py` (215 lines), `coordinator.py` (377 lines), `config_flow.py` (406 lines), `sensor.py` (252 lines), `const.py` (156 lines), `alert_result.py` (66 lines), `drift_detector.py` (389 lines), `__init__.py` (267 lines)
- Home Assistant SelectSelector docs: verified via codebase usage in existing `config_flow.py`
- PROJECT.md milestone description and constraints

---

*Architecture research for: behaviour-monitor v3.1 Activity-Rate Classification*
*Researched: 2026-03-28*
