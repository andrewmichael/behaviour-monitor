# Architecture Patterns

**Domain:** Cross-entity correlation and startup tier rehydration for Home Assistant anomaly detection integration
**Researched:** 2026-04-03
**Confidence:** HIGH (analysis derived from complete codebase reading; no external dependencies or novel patterns)

---

## Current Architecture (What Exists)

```
custom_components/behaviour_monitor/
├── __init__.py           # HA entry point, config migration chain (v2->v8), service registration
├── sensor.py             # 11 sensor entity descriptions via CoordinatorEntity
├── coordinator.py        # BehaviourMonitorCoordinator — orchestrator
├── routine_model.py      # RoutineModel + EntityRoutine + ActivitySlot (pure Python)
├── acute_detector.py     # AcuteDetector — inactivity + unusual-time (pure Python)
├── drift_detector.py     # DriftDetector — bidirectional CUSUM (pure Python)
├── alert_result.py       # AlertResult, AlertType, AlertSeverity (pure Python)
├── config_flow.py        # v8 config with OptionsFlowHandler
└── const.py              # All constants and defaults
```

### Existing Detector Pattern

All detectors follow this contract:
- Pure Python, zero HA imports
- Take domain objects (`EntityRoutine`, `datetime`) as inputs
- Return `AlertResult` or `None`
- Maintain internal state (cycle counters, accumulators)
- Serialize via `to_dict()`/`from_dict()`
- Wired by coordinator, which owns instances and feeds data

### Existing Data Flow

```
state_changed event
      |
      v
coordinator._handle_state_changed()
      |
      +---> routine_model.record(entity_id, timestamp, state_value)
      +---> self._last_seen[entity_id] = now
      +---> async_request_refresh()
      |
      v
coordinator._async_update_data()
      |
      +---> daily rollover: classify_tier() for all entities
      +---> _run_detection(now)
      |       |
      |       +---> per entity:
      |       |       acute_detector.check_inactivity()
      |       |       acute_detector.check_unusual_time()
      |       |       drift_detector.check()
      |       |
      |       +---> return list[AlertResult]
      |
      +---> _handle_alerts(alerts)
      +---> _build_sensor_data(alerts)
```

---

## Recommended Architecture (v4.0 Integration)

### High-Level View

Cross-entity correlation is a **new detector class** (`CorrelationDetector`) that follows the identical pattern as `AcuteDetector` and `DriftDetector`. The coordinator wires it into the existing detection loop. Startup tier rehydration is a surgical fix inside coordinator.

```
                       coordinator.py
                      +-------------------+
                      |                   |
  state_changed ----->| RoutineModel      |
  events              | (per-entity)      |
                      |                   |
                      | CorrelationDetector|<-- record_event() on each state change
                      |   (cross-entity)  |
                      |                   |
                      | _run_detection()  |
                      |   |               |
                      |   +-> AcuteDetector.check_inactivity()
                      |   +-> AcuteDetector.check_unusual_time()
                      |   +-> DriftDetector.check()
                      |   +-> CorrelationDetector.check()    <-- NEW
                      |                   |
                      | alerts ---------->| _handle_alerts()
                      |                   |
                      | sensor_data ----->| _build_sensor_data()
                      |   includes:       |
                      |   cross_sensor_patterns (populated)  <-- NEW
                      +-------------------+
```

### Component Boundaries

| Component | Responsibility | New/Modified | Communicates With |
|-----------|---------------|--------------|-------------------|
| `correlation_detector.py` | Learn co-occurrence patterns; detect broken correlations | **NEW FILE** | Reads `last_seen` dict; produces `AlertResult` |
| `coordinator.py` | Wire CorrelationDetector; persist correlation state; startup tier rehydration | MODIFIED | `correlation_detector.py`, HA storage |
| `alert_result.py` | Add `CORRELATION_BREAK` to `AlertType` enum | MODIFIED | All detectors |
| `const.py` | Add correlation constants and config keys | MODIFIED | All modules |
| `sensor.py` | Expose correlation groups via existing `cross_sensor_patterns` key | MODIFIED (minimal) | `coordinator.py` data dict |
| `config_flow.py` | Add correlation window config option | MODIFIED | `const.py` |
| `__init__.py` | Config migration v8 -> v9 | MODIFIED | `const.py` |

---

## New Component: CorrelationDetector

### Design Principles

1. **Same pattern as existing detectors** -- pure Python, no HA imports, returns `AlertResult`
2. **Symmetric pairs** -- correlation between A and B is one relationship. Use `frozenset` keys.
3. **Lazy discovery** -- only track pairs where co-occurrence has actually been observed
4. **Sustained-evidence gating** -- same pattern as `AcuteDetector`; no single-cycle false positives
5. **Conservative defaults** -- high co-occurrence threshold before a pair is "learned"

### Internal State

```python
@dataclass
class CorrelationPair:
    """Tracks co-occurrence statistics for a pair of entities."""
    entities: tuple[str, str]         # Sorted pair of entity IDs
    co_occurrences: int = 0           # Times both fired within window
    solo_counts: dict[str, int] = field(default_factory=dict)
    first_observed: str | None = None # ISO timestamp

    @property
    def total_events(self) -> int:
        return self.co_occurrences + sum(self.solo_counts.values())

    @property
    def co_occurrence_rate(self) -> float:
        total = self.total_events
        if total == 0:
            return 0.0
        return self.co_occurrences / total


class CorrelationDetector:
    """Detects broken co-occurrence patterns between entity pairs.

    Pure Python stdlib only. Zero Home Assistant imports.
    """

    def __init__(
        self,
        co_occurrence_window_seconds: int = 300,  # 5 minutes
        min_observations: int = 20,
        min_co_occurrence_rate: float = 0.7,
        sustained_cycles: int = SUSTAINED_EVIDENCE_CYCLES,
    ) -> None:
        self._window = co_occurrence_window_seconds
        self._min_obs = min_observations
        self._min_rate = min_co_occurrence_rate
        self._sustained_cycles = sustained_cycles
        self._pairs: dict[tuple[str, str], CorrelationPair] = {}
        self._break_cycles: dict[tuple[str, str], int] = {}  # sustained evidence counters

    def record_event(
        self,
        entity_id: str,
        timestamp: datetime,
        all_last_seen: dict[str, datetime],
    ) -> None:
        """Record an event and update co-occurrence counts for all pairs."""

    def check(
        self,
        now: datetime,
        last_seen: dict[str, datetime],
    ) -> list[AlertResult]:
        """Check all learned correlation pairs for broken correlations."""

    def get_correlation_groups(self) -> list[dict[str, Any]]:
        """Return discovered groups for sensor attributes."""

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorrelationDetector: ...
```

### Why This Shape

**Why a separate detector class, not embedded in RoutineModel?**
- `RoutineModel` is per-entity. Correlation is inherently cross-entity.
- The detector pattern is proven: stateless check function, internal cycle counters, returns `AlertResult`.
- Testable in isolation with zero HA mocking.

**Why frozenset/sorted-tuple keys instead of ordered pairs?**
- A correlating with B is the same relationship as B correlating with A.
- Halves the state space. Simplifies lookup.
- Serialization: store as sorted list of two entity IDs.

**Why lazy discovery (not pre-computing all pairs)?**
- With N entities, there are N*(N-1)/2 theoretical pairs. For 20 entities, that is 190 pairs. Most are noise.
- Only pairs where an actual co-occurrence has been observed get tracked.
- Typical install: 20 monitored entities yield 10-30 observed pairs, not 190.

**Why 5-minute co-occurrence window?**
- Human routine sequences (enter room, turn on light, start kettle) complete within 1-5 minutes.
- Wider windows (15+ min) create spurious correlations between independent activities.
- Configurable via config flow for users with different needs.

**Why NOT slot-aware (hour-of-day) co-occurrence for v4.0?**
- Slot-level correlation requires much more data to reach statistical confidence (each slot needs `min_observations` independently).
- Global co-occurrence rate is already useful for welfare monitoring.
- Can add slot-level refinement in a future milestone if needed.

---

## Startup Tier Rehydration Fix

### The Bug

The tier classification block in `_async_update_data` runs when `self._today_date != now.date()`:

```python
async def _async_update_data(self) -> dict[str, Any]:
    now = dt_util.now()
    if self._today_date != now.date():
        self._today_count = 0
        self._today_date = now.date()
        for r in self._routine_model._entities.values():
            r.classify_tier(now)
        # ...
```

On startup, `_today_date` is `None`, so this condition is `True` and tiers get classified on the first `_async_update_data` call. This appears correct. However, there is a race condition:

**In `_handle_state_changed`:**
```python
if self._today_date != now.date():
    self._today_count, self._today_date = 0, now.date()
```

If a state change event arrives BEFORE the first `_async_update_data` call (which happens -- `async_setup` registers the listener before `async_config_entry_first_refresh`), `_today_date` gets set to today. Then when `_async_update_data` first runs, `self._today_date == now.date()` is `True`, and the tier classification block is SKIPPED. Tiers remain `None` until midnight.

### Recommended Fix

```python
class BehaviourMonitorCoordinator:
    def __init__(self, ...):
        ...
        self._tiers_initialized: bool = False  # NEW

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()

        # Daily rollover (existing)
        if self._today_date != now.date():
            self._today_count = 0
            self._today_date = now.date()
            self._classify_all_tiers(now)

        # Startup rehydration (NEW)
        elif not self._tiers_initialized:
            self._classify_all_tiers(now)

        # ... rest of method unchanged

    def _classify_all_tiers(self, now: datetime) -> None:
        """Classify activity tiers for all entities, applying override if set."""
        for r in self._routine_model._entities.values():
            r.classify_tier(now)
        if self._activity_tier_override != "auto":
            override_tier = ActivityTier(self._activity_tier_override)
            for r in self._routine_model._entities.values():
                r._activity_tier = override_tier
        self._tiers_initialized = True
```

**Why `_tiers_initialized` flag instead of calling `classify_tier` in `async_setup`?**
- `async_setup` runs before `async_config_entry_first_refresh`. Calling `dt_util.now()` there works, but classification logically belongs in the update cycle where it can be tested alongside other update behavior.
- The flag approach is consistent with the existing `_today_date` guard pattern.
- No new persistence needed -- the flag resets on every restart, which is the desired behavior.
- The fix is 5 lines of code. Minimal risk.

---

## AlertType Extension

```python
class AlertType(str, Enum):
    INACTIVITY = "inactivity"
    UNUSUAL_TIME = "unusual_time"
    DRIFT = "drift"
    CORRELATION_BREAK = "correlation_break"  # NEW
```

This integrates with existing systems with zero changes:
- **Alert suppression:** Uses `f"{a.entity_id}|{a.alert_type.value}"` as key -- naturally extends.
- **Notification cooldown:** Same key pattern.
- **Severity gating:** `AlertResult.severity` is already checked by `_handle_alerts`.
- **Sensor data:** `AlertResult.to_dict()` serializes the new type value automatically.

**Which entity_id for a pair alert?** Use the entity that fired WITHOUT its expected companion. If entity A fires but expected companion B does not, the alert's `entity_id` is A. This maps cleanly to existing per-entity alert suppression.

---

## Coordinator Modifications

### __init__ (Modified)

```python
def __init__(self, hass, entry):
    ...
    self._correlation_detector = CorrelationDetector(
        co_occurrence_window_seconds=int(
            d.get(CONF_CORRELATION_WINDOW, DEFAULT_CORRELATION_WINDOW)
        ),
    )
    self._tiers_initialized: bool = False
```

### async_setup (Modified)

```python
async def async_setup(self) -> None:
    stored = await self._store.async_load()
    if stored:
        if "routine_model" in stored:
            self._routine_model = RoutineModel.from_dict(stored["routine_model"])
        for eid, sd in stored.get("cusum_states", {}).items():
            self._drift_detector._states[eid] = CUSUMState.from_dict(sd)
        # NEW: restore correlation state
        if "correlation_state" in stored:
            self._correlation_detector = CorrelationDetector.from_dict(
                stored["correlation_state"]
            )
        # ... rest unchanged
```

### _handle_state_changed (Modified)

```python
@callback
def _handle_state_changed(self, event: Event) -> None:
    ...
    now, sv = dt_util.now(), str(ns.state)
    self._routine_model.record(...)
    self._last_seen[eid] = now

    # NEW: feed correlation detector
    self._correlation_detector.record_event(eid, now, self._last_seen)

    # ... rest unchanged
```

### _run_detection (Modified)

```python
def _run_detection(self, now: datetime) -> list[AlertResult]:
    alerts: list[AlertResult] = []
    d = now.date()
    for eid in self._monitored_entities:
        if (r := self._routine_model._entities.get(eid)) is None:
            continue
        alerts.extend(x for x in (
            self._acute_detector.check_inactivity(eid, r, now, self._last_seen.get(eid)),
            self._acute_detector.check_unusual_time(eid, r, now),
            self._drift_detector.check(eid, r, d, now),
        ) if x is not None)

    # NEW: cross-entity correlation check (runs once per cycle, not per-entity)
    alerts.extend(
        self._correlation_detector.check(now, self._last_seen)
    )
    return alerts
```

### _save_data (Modified)

```python
async def _save_data(self) -> None:
    await self._store.async_save({
        "routine_model": self._routine_model.to_dict(),
        "cusum_states": {e: s.to_dict() for e, s in self._drift_detector._states.items()},
        "correlation_state": self._correlation_detector.to_dict(),  # NEW
        "coordinator": { ... },
    })
```

### _build_sensor_data (Modified)

The existing `cross_sensor_patterns` key (currently hardcoded as `[]`) gets populated:

```python
"cross_sensor_patterns": self._correlation_detector.get_correlation_groups(),
```

Entity status entries get correlation info:

```python
"entity_status": [
    {
        "entity_id": e,
        "status": "active" if e in self._last_seen else "unknown",
        "last_seen": self._last_seen[e].isoformat() if e in self._last_seen else None,
        "activity_tier": r.activity_tier.value if (r := ...) and r.activity_tier else None,
        "correlated_with": self._correlation_detector.get_correlated_entities(e),  # NEW
    }
    for e in self._monitored_entities
],
```

### _build_safe_defaults

No change needed -- `cross_sensor_patterns: []` is already present.

---

## Persistence Design

### Same Store File

Correlation state persists alongside existing data in `.storage/behaviour_monitor.{entry_id}.json`. No new Store instance.

**Why same file?**
- Existing pattern uses one `Store` per config entry. Adding a second Store adds complexity for no benefit.
- Correlation state is small: one dict per observed pair, typically 10-30 pairs.
- Atomic save: all state is consistent at save time.
- Forward-compatible: `stored.get("correlation_state")` returns `None` for old storage files, causing the detector to start fresh (correct behavior).

### Serialization Format

```json
{
    "routine_model": { ... },
    "cusum_states": { ... },
    "correlation_state": {
        "co_occurrence_window_seconds": 300,
        "min_observations": 20,
        "min_co_occurrence_rate": 0.7,
        "pairs": {
            "binary_sensor.kitchen_motion|binary_sensor.kettle_power": {
                "entities": ["binary_sensor.kettle_power", "binary_sensor.kitchen_motion"],
                "co_occurrences": 47,
                "solo_counts": {
                    "binary_sensor.kitchen_motion": 12,
                    "binary_sensor.kettle_power": 3
                },
                "first_observed": "2026-03-15T07:23:00+00:00"
            }
        }
    },
    "coordinator": { ... }
}
```

**Pair key format:** Sorted entity IDs joined by `|`. Deterministic, human-readable in storage files.

---

## Sensor Modifications

### No New Sensor Entities

The milestone says "expose discovered correlation groups as sensor attributes." This is done by:

1. Populating the existing `cross_sensor_patterns` key in sensor data (currently `[]`)
2. Adding `correlated_with` to each `entity_status` entry

This preserves the 11-sensor stability constraint and avoids breaking user automations.

### Data Shape for cross_sensor_patterns

```python
[
    {
        "entities": ["binary_sensor.kitchen_motion", "binary_sensor.kettle_power"],
        "co_occurrence_rate": 0.78,
        "total_observations": 62,
        "status": "active",  # or "broken" if correlation is currently violated
    },
    ...
]
```

---

## Config Migration: v8 -> v9

```python
# In __init__.py
if config_entry.version < 9:
    new_data = dict(config_entry.data)
    new_data.setdefault(CONF_CORRELATION_WINDOW, DEFAULT_CORRELATION_WINDOW)
    hass.config_entries.async_update_entry(config_entry, data=new_data, version=9)
    _LOGGER.info(
        "Behaviour Monitor: Config entry migrated to v9 -- correlation window added"
    )
```

New constants in `const.py`:
```python
# v4.0 config keys
CONF_CORRELATION_WINDOW: Final = "correlation_window"
DEFAULT_CORRELATION_WINDOW: Final = 300  # seconds (5 minutes)

# v4.0 detection constants
CORRELATION_MIN_OBSERVATIONS: Final = 20
CORRELATION_MIN_RATE: Final = 0.7
```

---

## Patterns to Follow

### Pattern 1: Detector Interface
**What:** All detectors are pure Python classes with no HA imports. They take domain objects and datetimes, return `AlertResult`.
**When:** Any new detection logic.
**Example:** `CorrelationDetector` follows this exactly -- `record_event()` for learning, `check()` for detection, `to_dict()`/`from_dict()` for persistence.

### Pattern 2: Sustained Evidence Gating
**What:** Require N consecutive cycles of evidence before firing an alert. Counter resets when condition clears.
**When:** Any detection that runs on a polling cycle.
**Why:** Prevents transient false positives. Proven in `AcuteDetector` with `_inactivity_cycles` and `_unusual_time_cycles` dicts.
**CorrelationDetector applies this:** `_break_cycles` dict tracks consecutive cycles where a learned pair is broken.

### Pattern 3: Coordinator as Wiring Layer
**What:** Coordinator owns detector instances, feeds them data from state changes, collects `AlertResult` objects, handles notifications.
**When:** Always. Detectors never talk to HA directly.

### Pattern 4: Single Store File
**What:** All persistent state goes in one `Store.async_save()` call with a versioned dict.
**When:** Adding new persistent state.
**Why:** Atomic saves, simple recovery, existing pattern. Forward-compatible via `.get()` with defaults.

### Pattern 5: Config Migration via setdefault
**What:** Each version bump adds new keys with `setdefault()`, preserving any user-set values.
**When:** Any new config key.
**Why:** Consistent with v4->v5, v5->v6, v6->v7, v7->v8 migration chain.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Correlation in RoutineModel
**What:** Adding cross-entity logic to `RoutineModel` or `EntityRoutine`.
**Why bad:** `RoutineModel` is per-entity by design. Cross-entity logic would require each entity to know about all other entities, creating circular data dependencies and violating single responsibility.
**Instead:** Separate `CorrelationDetector` that reads from coordinator's `_last_seen` dict.

### Anti-Pattern 2: Eager Pair Discovery
**What:** Pre-creating `CorrelationPair` objects for all N*(N-1)/2 possible pairs at startup.
**Why bad:** With 20 entities, that is 190 pairs. With 50 entities, 1,225. Most are noise. Wastes memory and makes storage bloated.
**Instead:** Lazily create pairs only when a co-occurrence is actually observed. A pair entry is born when entity A fires and entity B's `last_seen` is within the window.

### Anti-Pattern 3: New Sensor Entities for Correlation
**What:** Adding `correlation_groups` or `correlation_status` as new sensor entity IDs.
**Why bad:** Violates the 11-sensor stability constraint. Users have automations built on existing sensor entity IDs.
**Instead:** Populate the existing `cross_sensor_patterns` key (already `[]` in sensor data) and add `correlated_with` to `entity_status` entries.

### Anti-Pattern 4: Persisting Tier Classification
**What:** Serializing `_activity_tier` and `_tier_classified_date` in `EntityRoutine.to_dict()`.
**Why bad:** Tiers are cheap to compute and depend on current data. Persisting creates stale-tier bugs when data changes between restarts. The existing code correctly marks these fields as `init=False, repr=False`.
**Instead:** Recompute on startup (the rehydration fix) and daily thereafter.

### Anti-Pattern 5: Two-Way Correlation Tracking
**What:** Tracking "A co-occurs with B" and "B co-occurs with A" as separate relationships.
**Why bad:** Doubles the state space, doubles the alert potential, and creates confusing duplicate alerts.
**Instead:** Use sorted tuple keys so (A,B) and (B,A) resolve to the same `CorrelationPair`.

---

## Build Order

Based on dependency analysis. Each step is independently testable.

| Step | What | Depends On | Risk |
|------|------|------------|------|
| 1 | `alert_result.py` -- Add `CORRELATION_BREAK` to `AlertType` | Nothing | Zero -- enum extension |
| 2 | `const.py` -- Add `CONF_CORRELATION_WINDOW`, defaults, detection constants | Nothing | Zero -- new constants |
| 3 | `correlation_detector.py` -- New file, full implementation | Steps 1, 2 | Low -- pure Python, fully testable in isolation |
| 4 | Startup tier rehydration fix in `coordinator.py` | Nothing | Low -- 5 lines, independent of correlation work |
| 5 | `coordinator.py` -- Wire `CorrelationDetector` into `__init__`, `async_setup`, `_handle_state_changed`, `_run_detection`, `_save_data`, `_build_sensor_data` | Steps 1-3 | Medium -- most integration points |
| 6 | `config_flow.py` + `__init__.py` -- Config migration v8->v9, correlation window option | Steps 2, 5 | Low -- follows existing migration pattern |
| 7 | `sensor.py` attribute exposure (minimal -- mostly data flow from step 5) | Step 5 | Low |

**Steps 1-3 and step 4 are fully independent** and can be built in parallel.
**Steps 5-7 depend on steps 1-3.**
**Step 4 can be delivered independently** as a quick bugfix, even before the correlation feature.

---

## Scalability Considerations

| Concern | 5 entities | 20 entities | 50 entities |
|---------|-----------|-------------|-------------|
| Theoretical pairs | 10 | 190 | 1,225 |
| Observed pairs (lazy) | 2-5 | 10-30 | 20-60 |
| Memory per pair | ~200 bytes | ~200 bytes | ~200 bytes |
| Detection time per cycle | <1ms | <5ms | <15ms |
| Storage overhead | ~1KB | ~6KB | ~15KB |

Lazy discovery keeps practical pair counts well below theoretical maximums. The 60-second update cycle gives ample time for correlation checks.

---

## Integration Points Summary

| Touchpoint | File | Change Type | Lines (est.) |
|------------|------|-------------|-------------|
| `CORRELATION_BREAK` enum value | `alert_result.py` | Add 1 line | 1 |
| Correlation constants | `const.py` | Add constants | 10 |
| `CorrelationDetector` + `CorrelationPair` | `correlation_detector.py` | **New file** | ~200 |
| `_tiers_initialized` flag + `_classify_all_tiers` | `coordinator.py` | Add method + flag | 12 |
| Wire correlation detector | `coordinator.py` | Modify 5 methods | 25 |
| Populate `cross_sensor_patterns` | `coordinator.py` | Modify `_build_sensor_data` | 5 |
| Config migration v8->v9 | `__init__.py` | Add migration block | 8 |
| Correlation window option | `config_flow.py` | Add field | 10 |
| Translations | `translations/en.json` | Add labels | 5 |

**Total estimated: ~275 lines of new/modified production code** (excluding tests).

---

## Sources

- Existing codebase analysis (HIGH confidence -- direct code reading of all source files)
- `coordinator.py` lines 118-138: `async_setup` lifecycle and storage restoration
- `coordinator.py` lines 160-178: `_handle_state_changed` -- the race condition site for tier rehydration
- `coordinator.py` lines 180-199: `_async_update_data` -- daily rollover and detection wiring
- `coordinator.py` lines 146-158: `_save_data` -- single Store pattern
- `coordinator.py` lines 201-211: `_run_detection` -- per-entity detector loop
- `acute_detector.py` lines 49-51: sustained evidence counter pattern
- `alert_result.py` lines 14-19: `AlertType` enum (extension point)
- `routine_model.py` lines 381-423: `classify_tier` with once-per-day guard and confidence gate
- `__init__.py` lines 165-177: setup lifecycle (`async_setup` -> `first_refresh`)
- `const.py`: `SUSTAINED_EVIDENCE_CYCLES = 3` (reuse for correlation)
- `sensor.py` line 325 in coordinator: `cross_sensor_patterns: []` (existing empty placeholder)

---

*Architecture research for: behaviour-monitor v4.0 Cross-Entity Correlation*
*Researched: 2026-04-03*
