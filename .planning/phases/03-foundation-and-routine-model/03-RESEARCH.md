# Phase 3: Foundation and Routine Model - Research

**Researched:** 2026-03-13
**Domain:** Home Assistant storage migration, stub entity deprecation, per-entity routine baseline model, HA recorder bootstrap
**Confidence:** HIGH (stack, patterns, migration); MEDIUM (recorder API currency — verified by cross-referencing HA core history_stats integration source)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Continue versioning scheme: STORAGE_VERSION = 3
- Must not crash HA on upgrade from v1.0
- ml_status, ml_training_remaining, cross_sensor_patterns kept as stub entities with safe default states
- Log a deprecation warning once per startup ("sensor X is deprecated and will be removed in a future version")
- 168 slots (hour-of-day x day-of-week) per entity, configurable rolling history window (default 4 weeks)
- Use whatever history is available at bootstrap, even if less than the full configured window
- Mark confidence proportionally (e.g., 10 days of 28 = lower confidence, wider tolerances)
- Re-bootstrap behavior and load strategy at Claude's discretion

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

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | System migrates from v2 z-score storage format to new routine format and cleans up orphaned ML storage files | Storage migration pattern section; async_migrate_entry hook; try/except deserialization; ML Store cleanup |
| INFRA-02 | ML-specific sensor entities (ml_status, ml_training_remaining, cross_sensor_patterns) preserved as deprecated stubs with safe default states | Stub state value recommendations; coordinator.data contract; deprecation log pattern |
| ROUTINE-01 | System learns per-entity behavior baselines using 168 hour-of-day x day-of-week slots from configurable rolling history window (default 4 weeks) | EntityRoutine/RoutineModel design; ActivitySlot structure; deque(maxlen) storage; to_dict/from_dict serialization |
| ROUTINE-02 | System bootstraps routine model from existing HA recorder history on first load | Verified recorder API: state_changes_during_period via get_instance().async_add_executor_job; staggered load strategy |
| ROUTINE-03 | System uses event frequency/timing for binary entities and value distributions for numeric entities | Binary: event count + inter-event interval per slot; Numeric: (mean, stdev, count) per slot; detection-ready API design |
</phase_requirements>

---

## Summary

Phase 3 creates the data layer that all detection engines in Phase 4 consume. It has three non-overlapping work streams: (1) storage migration from v2 to v3 format with graceful handling of old z-score data and ML file cleanup, (2) stubbing the three deprecated ML sensor entities so they return defined states rather than going unavailable, and (3) building the `RoutineModel` — a pure-Python, HA-free class that learns per-entity baselines from 168 hour-of-day x day-of-week slots and can bootstrap from HA recorder history.

The migration work is straightforward: detect old format by key presence, log and discard, carry forward coordinator state. The ML stub work is a sensor.py and coordinator.data change. The RoutineModel is the core deliverable — it defines the API that `AcuteDetector` and `DriftDetector` (Phase 4) will consume, so its interface must be correct before those detectors are written.

The one area requiring extra care is the recorder bootstrap. Research against HA 2025 core confirms the stable API is `state_changes_during_period` (not `get_significant_states`), called via `get_instance(hass).async_add_executor_job(...)`. This is the same pattern used by HA's own `history_stats` built-in integration. The bootstrap must not block HA startup — a staggered entity-by-entity load with short yields is the recommended approach for 5–20 entities.

**Primary recommendation:** Build RoutineModel as a pure-Python HA-free class first, test it fully, then wire the migration and bootstrap into the coordinator. This phase produces no user-visible detection changes — it only guarantees the baseline data is ready for Phase 4.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `collections.deque` | stdlib | Fixed-size sliding window for per-slot observations | O(1) append/eviction with `maxlen`; ideal for 56-item rolling window per slot |
| Python stdlib `statistics` | 3.11 (HA ships 3.11) | `mean()`, `stdev()`, `NormalDist` for slot statistics | Zero install cost; `NormalDist.zscore()` available directly; Phase 4 detectors consume it |
| Python stdlib `dataclasses` | stdlib | `EntityRoutine`, `ActivitySlot` data models | Consistent with existing `analyzer.py`/`ml_analyzer.py` pattern; `to_dict`/`from_dict` simple |
| Python stdlib `datetime` | stdlib | Hour-of-day, day-of-week bucketing; ISO timestamp storage | Already throughout codebase |
| `homeassistant.components.recorder` | HA internal | Bootstrap: query past state history via `state_changes_during_period` | Stable interface used by HA core integrations; `recorder` dependency already in manifest.json |
| `homeassistant.helpers.storage.Store` | HA internal | Persist RoutineModel to `.storage/` JSON | Already used for v1.0 storage; same pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `homeassistant.util.dt` | HA internal | Timezone-aware `now()`, UTC conversion | All timestamp operations in coordinator; `dt_util.now()` throughout |
| `unittest.mock` + `freezegun` | test deps | Time freezing for deterministic routine model tests | Any test that exercises temporal logic (slot assignment, pruning, confidence) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `state_changes_during_period` | `get_significant_states` | Both exist in `homeassistant.components.recorder.history`. `state_changes_during_period` returns ALL state changes per entity and is the current pattern in HA core (2025). `get_significant_states` returns only "significant" state changes (filtered by state class) — unsuitable for binary entities like motion/door where all transitions matter. |
| `deque(maxlen=56)` per slot | Single list + manual pruning | `deque` auto-evicts oldest items at O(1); no manual pruning needed. List-based requires O(n) pruning scan or size checks |
| `(mean, stdev, count)` per numeric slot | raw value list | Pre-aggregated stats are O(1) to update and O(1) to query; raw lists grow unbounded within the slot window |

**Installation:**
```bash
# No new pip dependencies required.
# Python stdlib only. manifest.json unchanged.
```

---

## Architecture Patterns

### Recommended Project Structure for Phase 3 Deliverables

```
custom_components/behaviour_monitor/
├── const.py              # EXTENDED: STORAGE_VERSION=3, new config keys, ML constants removed
├── routine_model.py      # NEW: ActivitySlot, EntityRoutine, RoutineModel (pure Python, zero HA imports)
├── coordinator.py        # MODIFIED: migration logic in async_setup, ML Store cleanup, stub data keys
├── sensor.py             # MODIFIED: stub value_fn for ml_status, ml_training_remaining, cross_sensor_patterns
└── __init__.py           # MODIFIED: async_migrate_entry hook for config entry key cleanup
```

### Pattern 1: Storage Migration — Detect by Key, Discard, Carry Forward

**What:** On `async_setup`, load the Store. If the loaded data contains `"analyzer"` key but no `"routine_model"` key, the data is v2 format. Log an info message and start with an empty RoutineModel. Carry forward the `"coordinator"` sub-dict (holiday mode, snooze, cooldowns, welfare state) because these are format-agnostic.

**Recommendation:** Discard old z-score data (do not backup). Discarding is simpler, is safe, and avoids polluting storage. The z-score data is useless to the new engine. Users accept a cold-start period for the routine model — this is expected and surfaced via the learning status sensor.

**When to use:** Always, in `async_setup` before any model initialization.

**Example:**
```python
# Source: Architecture research + existing coordinator.py async_setup pattern
async def _async_setup(self) -> None:
    """One-time init: load persisted data, subscribe to state events."""
    stored = await self._store.async_load()
    if stored:
        if "analyzer" in stored and "routine_model" not in stored:
            # v2 format: old z-score data — cannot migrate, start fresh
            _LOGGER.info(
                "Behaviour Monitor: v2 pattern data detected on upgrade. "
                "Starting fresh routine model — detection will activate after "
                "sufficient history is collected."
            )
            coordinator_state = stored.get("coordinator", {})
            self._restore_coordinator_state(coordinator_state)
            # routine_model stays as default empty RoutineModel
        elif "routine_model" in stored:
            # v3 format: load normally
            self._routine_model = RoutineModel.from_dict(stored["routine_model"])
            coordinator_state = stored.get("coordinator", {})
            self._restore_coordinator_state(coordinator_state)

    # Clean up orphaned ML store if it exists
    await self._cleanup_ml_store()
```

### Pattern 2: ML Storage Cleanup

**Recommendation:** Delete the ML storage file on first setup after upgrade. Do not leave it on disk. Users who downgrade will lose ML data — this is acceptable and expected. The ML file wastes space and confuses anyone inspecting `.storage/`.

```python
# Source: Architecture research
async def _cleanup_ml_store(self) -> None:
    """Remove orphaned ML storage file from v1.0."""
    ml_store = Store(self.hass, STORAGE_VERSION, f"{STORAGE_KEY}_ml.{self._entry.entry_id}")
    try:
        existing = await ml_store.async_load()
        if existing is not None:
            await ml_store.async_remove()
            _LOGGER.info("Behaviour Monitor: Removed orphaned ML storage file (ML features removed in v1.1)")
    except Exception:
        pass  # Not critical — ignore if removal fails
```

### Pattern 3: async_migrate_entry for Config Entry Key Cleanup

**What:** HA calls `async_migrate_entry` in `__init__.py` when `STORAGE_VERSION` in the config entry differs from the installed version. This is the hook for cleaning up dead config keys.

**Important:** ConfigEntry data must never be mutated directly. Use `hass.config_entries.async_update_entry()`.

**Return value:** Return `True` if migration succeeded (entry remains enabled). Return `False` only if the entry is genuinely unrecoverable — this disables the integration for the user. Always prefer returning `True` with fresh defaults over `False`.

```python
# Source: HA Developer Docs — config_entries_index
async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry to new format."""
    _LOGGER.debug("Migrating config entry from version %s", config_entry.version)

    if config_entry.version < 3:
        # Remove ML-specific keys; add new routine model keys with defaults
        new_data = dict(config_entry.data)
        new_data.pop("enable_ml", None)
        new_data.pop("retrain_period", None)
        new_data.pop("ml_learning_period", None)
        new_data.pop("cross_sensor_window", None)
        # Add new keys with safe defaults
        new_data.setdefault("history_window_days", DEFAULT_HISTORY_WINDOW_DAYS)
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=3
        )
        _LOGGER.info("Behaviour Monitor: Config entry migrated to v3 — ML options removed")

    return True
```

### Pattern 4: RoutineModel as Pure-Python Stateful Component

**What:** `RoutineModel` is a plain Python class with zero HA imports. It owns per-entity `EntityRoutine` objects, each containing 168 `ActivitySlot` instances (7 days × 24 hours). It provides the API that Phase 4 detectors consume.

**Binary vs Numeric entity handling:**
- **Binary (motion, door contact):** Each slot stores event count + list of inter-event intervals. The detector needs `expected_gap_seconds(entity_id, hour, dow)` — the median inter-event interval for that slot. Also store `event_count_per_slot` for the daily rate drift detector.
- **Numeric (temperature, power):** Each slot stores `(mean, stdev, count)` updated incrementally using Welford's online algorithm. The detector needs `slot_distribution(entity_id, hour, dow)` returning a `NormalDist` or `(mean, stdev)` tuple.

**Why both count and interval for binary:** Phase 4's `AcuteDetector` needs inter-event interval to check "how long since last event vs typical gap." Phase 4's `DriftDetector` needs daily event count to run CUSUM. Store both to avoid coupling the RoutineModel design to detector implementation details.

**Sparse slot handling:** If a slot has fewer than `MIN_SLOT_OBSERVATIONS = 4` recorded events, mark it as insufficient. Do not emit a detection result for that slot. This is the simplest approach and favors minimizing false positives (the primary user concern). Neighbor blending (averaging adjacent hours) is a premature optimization — implement only if testing reveals unacceptably high cold-start periods.

```python
# Source: Architecture research / STACK.md code examples
from collections import deque
from dataclasses import dataclass, field
from statistics import NormalDist, mean, median, stdev
from typing import Any

MIN_SLOT_OBSERVATIONS: int = 4  # Minimum events in a slot before detection activates
SLOTS_PER_ENTITY: int = 168     # 7 days × 24 hours

@dataclass
class ActivitySlot:
    """Per-entity, per-hour-of-day-x-day-of-week activity observations."""
    # Binary entities: event timestamps (for interval calculation) and count
    event_times: deque = field(default_factory=lambda: deque(maxlen=56))
    # Numeric entities: Welford online stats (mean, M2, count)
    numeric_sum: float = 0.0
    numeric_sum_sq: float = 0.0
    numeric_count: int = 0

    @property
    def is_sufficient(self) -> bool:
        return len(self.event_times) >= MIN_SLOT_OBSERVATIONS or self.numeric_count >= MIN_SLOT_OBSERVATIONS

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivitySlot": ...


@dataclass
class EntityRoutine:
    entity_id: str
    is_binary: bool
    slots: list[ActivitySlot] = field(default_factory=lambda: [ActivitySlot() for _ in range(SLOTS_PER_ENTITY)])
    history_window_days: int = 28
    first_observation: str | None = None  # ISO timestamp

    def slot_index(self, hour: int, dow: int) -> int:
        """Return slot index for hour (0-23) and day-of-week (0=Monday)."""
        return dow * 24 + hour

    def record(self, timestamp: "datetime", state_value: str) -> None:
        """Record a state change observation into the appropriate slot."""
        ...

    def expected_gap_seconds(self, hour: int, dow: int) -> float | None:
        """Median inter-event interval for this slot. None if insufficient data."""
        ...

    def daily_activity_rate(self, target_date: "date") -> float:
        """Total state changes recorded on target_date."""
        ...

    def confidence(self, now: "datetime") -> float:
        """0.0–1.0 confidence based on observation history vs window."""
        ...

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityRoutine": ...


class RoutineModel:
    def __init__(self, history_window_days: int = 28) -> None: ...

    def get_or_create(self, entity_id: str, is_binary: bool) -> EntityRoutine: ...
    def record(self, entity_id: str, timestamp: "datetime", state_value: str, is_binary: bool) -> None: ...
    def overall_confidence(self) -> float: ...
    def learning_status(self) -> str:
        """Return one of: 'inactive', 'learning', 'ready'"""
        ...

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoutineModel": ...
```

### Pattern 5: Recorder Bootstrap

**What:** On first setup (or when `routine_model` is absent from storage), query HA recorder history for up to `history_window_days` of past state data for each monitored entity. Replay those state changes into the RoutineModel before starting live monitoring.

**Verified API (HA 2025):** Use `state_changes_during_period` from `homeassistant.components.recorder.history`, called via `get_instance(hass).async_add_executor_job(...)`. This is the same pattern used by HA's built-in `history_stats` integration in 2025 core. The function returns `dict[entity_id, list[State]]`.

**Do NOT use `get_significant_states`:** This function filters to "significant" state changes based on state class configuration. For binary sensors (motion, door), it may skip ON→OFF transitions that lack a state class — causing gaps in the interval history. `state_changes_during_period` returns all recorded state changes.

**Bootstrap strategy (staggered, not parallel):**
- Load entities one at a time with a short `asyncio.sleep(0)` yield between each
- This prevents blocking HA's event loop during startup
- For 5–20 monitored entities: total bootstrap adds ~0.5–2s to setup, acceptable
- If recorder returns no data (not running, purged): log a warning, continue with empty model (cold-start)
- If partial data (e.g., 10 of 28 days): load it, set confidence proportionally

```python
# Source: HA core history_stats data.py pattern (verified 2025)
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import state_changes_during_period
import asyncio

async def _bootstrap_from_recorder(self) -> None:
    """Load historical state data into routine model on first setup."""
    from datetime import datetime, timedelta
    from homeassistant.util import dt as dt_util

    now = dt_util.now()
    start = now - timedelta(days=self._history_window_days)

    for entity_id in self._monitored_entities:
        try:
            instance = get_instance(self.hass)
            history_dict = await instance.async_add_executor_job(
                state_changes_during_period,
                self.hass,
                start,
                now,
                entity_id,
                True,   # include_start_time_state
                True,   # no_attributes (faster query)
            )
            states = history_dict.get(entity_id, [])
            is_binary = self._is_binary_entity(entity_id, states)
            for state in states:
                if state.state not in ("unavailable", "unknown", None):
                    self._routine_model.record(
                        entity_id,
                        state.last_changed,
                        state.state,
                        is_binary,
                    )
            _LOGGER.debug(
                "Bootstrap: loaded %d states for %s",
                len(states), entity_id,
            )
        except Exception as err:
            _LOGGER.warning(
                "Bootstrap: failed to load history for %s: %s",
                entity_id, err,
            )
        # Yield to event loop between entities
        await asyncio.sleep(0)
```

### Pattern 6: Deprecated Sensor Stub States

**Recommended stub state values:**

| Sensor key | Stub state | Rationale |
|------------|-----------|-----------|
| `ml_status` | `"Removed in v1.1"` | Explicitly communicates what happened; automations checking for `"Ready"` will not trigger |
| `ml_training_remaining` | `"N/A"` | Neutral; does not imply progress or failure |
| `cross_sensor_patterns` | `0` (integer) | Sensor reports a count; 0 is the natural "nothing" value; does not break automations that check `> 0` |

**One-time deprecation log pattern:**
```python
# Source: CONTEXT.md requirement — log once per startup
import logging
_LOGGER = logging.getLogger(__name__)

# In coordinator __init__ or _async_setup:
_LOGGER.warning(
    "sensor.behaviour_monitor_ml_status is deprecated and will be removed in v1.2. "
    "ML features have been replaced by routine-based detection."
)
```

Log all three deprecation warnings in `_async_setup` once per startup. Use `_LOGGER.warning` (not `info`) so the message is visible in default log levels.

**Coordinator data keys for stubs:**
The three ML sensors read from `coordinator.data` via `value_fn` lambdas. For Phase 3, add these keys to the data dict assembled by `_build_sensor_data()`:

```python
# In _build_sensor_data():
data["ml_status_stub"] = "Removed in v1.1"
data["ml_training_stub"] = "N/A"
data["cross_sensor_stub"] = 0
```

Update the three `value_fn` lambdas in `sensor.py` to read from these stub keys. Do not remove the `SensorEntityDescription` entries — entity removal is a breaking change.

### Pattern 7: Learning Status Surfacing

**The cold-start problem:** After upgrade or fresh install, the RoutineModel has no baseline. Detection is silent. Users must see this explicitly.

**Recommended approach:** Use the existing `statistical_training_remaining` sensor (key `stat_training`) to surface learning status. Map `RoutineModel.learning_status()` to this sensor's `formatted` field and add a `learning_state` key to the data dict.

**Three states:**
- `"inactive"` — fewer than `MIN_SLOT_OBSERVATIONS` in any slot; zero confidence; detection suppressed
- `"learning"` — some slots populated but overall confidence < 80%; detection partially active
- `"ready"` — overall confidence >= 80%; full detection active

**Send a one-time HA persistent notification** on startup when `learning_status == "inactive"` to inform users detection is not yet active. This is the non-silent cold start requirement (Success Criterion 5).

### Anti-Patterns to Avoid
- **Calling `get_significant_states` for binary entity bootstrap:** Filters out state changes for entities without a state class, leaving gaps in interval history. Use `state_changes_during_period` instead.
- **Parallel recorder queries for all entities:** Can saturate the executor thread pool at startup. Stagger with `asyncio.sleep(0)` between entities.
- **Importing HA modules inside `routine_model.py`:** The model must remain HA-free (pure Python) so it can be unit tested without mocking HA. All HA interactions belong in the coordinator.
- **Storing raw State objects in RoutineModel:** State objects hold references to HA internals. Store only `(iso_timestamp, state_value)` primitives in the model.
- **Removing deprecated sensor descriptions from SENSOR_DESCRIPTIONS:** This removes the entity from HA's entity registry. Users lose history, dashboards break. Keep the description; change the `value_fn` to return the stub value.
- **Returning `None` from `_build_sensor_data()`:** All 14 sensors go `unavailable`. Add stub keys for all deprecated sensors before the coordinator is rewritten in Phase 4.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Online mean/variance per slot | Incremental accumulator | Welford's online algorithm (10 lines) or `statistics.mean`/`statistics.stdev` over the slot's observation list | Numerically stable; no floating point drift; stdlib sufficient for ≤56 observations |
| Rolling window auto-eviction | Manual list pruning with index tracking | `collections.deque(maxlen=56)` | O(1) eviction built in; no off-by-one errors; thread-safe for appends |
| Recorder history queries | Raw SQLAlchemy queries on HA DB | `homeassistant.components.recorder.history.state_changes_during_period` | DB schema changes across HA versions; raw queries break silently after HA updates |
| Config entry mutation | `config_entry.data["key"] = value` | `hass.config_entries.async_update_entry(entry, data=new_data)` | HA enforces immutability; direct mutation is silently ignored or raises in newer HA versions |

**Key insight:** The RoutineModel storage serialization is plain Python dicts/lists — no special serialization library. Everything in the model serializes to JSON primitives via `to_dict()`.

---

## Common Pitfalls

### Pitfall 1: Migration Crashes HA on Startup
**What goes wrong:** `RoutineModel.from_dict()` tries to deserialize old z-score `"analyzer"` data. `KeyError` on missing `"slots"` key. `async_setup_entry` raises. Integration appears as "Failed to set up."
**Why it happens:** Developer tests fresh installs but not upgrade paths.
**How to avoid:** Check for `"analyzer"` key in loaded data. If present and `"routine_model"` absent: log info, skip deserialization, start with empty model. Write an integration test loading a v2 fixture file.
**Warning signs:** No test fixture for v2 storage format exists.

### Pitfall 2: `get_significant_states` Skips Binary Entity Transitions
**What goes wrong:** Bootstrap loads partial history for motion sensors and door contacts. Interval calculations are wildly off (intervals appear 10x longer than actual). Acute detector fires on normal gaps.
**Why it happens:** `get_significant_states` filters for "significant" state changes — may omit ON→OFF for sensors without `state_class`. Only affects binary entities.
**How to avoid:** Use `state_changes_during_period` which returns ALL recorded transitions. Verified pattern from HA 2025 core.
**Warning signs:** Bootstrap load count for binary entities is unexpectedly low vs. daily activity count.

### Pitfall 3: Blocking Recorder Query at Startup
**What goes wrong:** Fetching 28 days of state history for 15 entities in parallel saturates the HA executor thread pool. Other integrations experience startup delays. HA may report coordinator timeout.
**Why it happens:** `async_add_executor_job` calls are parallelized without rate control.
**How to avoid:** Load entities one at a time, `await asyncio.sleep(0)` between each. For 15 entities with 28 days of data: adds ~1–2s to setup time, well within acceptable bounds.
**Warning signs:** HA logs show `Platform behaviour_monitor took too long to set up`.

### Pitfall 4: Sensor Entity Disappears After Upgrade
**What goes wrong:** Removing a `SensorEntityDescription` from `SENSOR_DESCRIPTIONS` tuple removes the entity from HA's entity registry. User dashboards and automations referencing `sensor.behaviour_monitor_ml_status` break. Entity registry retains a stale unique_id ghost.
**Why it happens:** Developer correctly removes ML logic but also removes the sensor description as "cleanup."
**How to avoid:** NEVER remove sensor descriptions in the same release that changes the detection engine. Change the `value_fn` to return the stub value. Remove only in v1.2 with a migration release note.
**Warning signs:** Entity count in `SENSOR_DESCRIPTIONS` tuple drops below 14.

### Pitfall 5: coordinator.data Missing Stub Keys — Sensors Go Unavailable
**What goes wrong:** Phase 3 adds `routine_model.py` and modifies `async_setup`, but `_build_sensor_data()` in coordinator.py still returns the v1.0 data dict format. `value_fn` lambdas for the three ML sensors read keys that no longer exist. Sensors show `unknown`.
**Why it happens:** The coordinator is not yet fully rewritten (that's Phase 4). Phase 3 must still populate the current data dict keys OR add the stub keys so `value_fn` lambdas don't fail.
**How to avoid:** In Phase 3, add stub keys to `_build_sensor_data()` alongside the existing keys. The coordinator refactor (Phase 4) will remove the old keys. Test that all 14 sensors return non-None values after Phase 3 changes.
**Warning signs:** Any sensor shows `unknown` or `unavailable` in test assertions.

### Pitfall 6: RoutineModel Imports HA Modules
**What goes wrong:** Developer adds `from homeassistant.util.dt import now` inside `routine_model.py` for convenience. Unit tests now require HA mocking. The file is no longer HA-free.
**Why it happens:** Convenience — `dt_util.now()` is already available in the coordinator.
**How to avoid:** Pass `datetime` objects as parameters to all RoutineModel methods. Never import HA inside `routine_model.py`. The test suite for `RoutineModel` must run with zero HA mocks.
**Warning signs:** `routine_model.py` contains any `from homeassistant` import.

---

## Code Examples

Verified patterns from official sources and HA 2025 core inspection:

### Recorder History Query (verified from HA core history_stats data.py, 2025)
```python
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import state_changes_during_period
from homeassistant.util import dt as dt_util
from datetime import timedelta

async def fetch_entity_history(hass, entity_id: str, days: int) -> list:
    """Fetch state change history for one entity."""
    now = dt_util.now()
    start = now - timedelta(days=days)
    instance = get_instance(hass)
    history_dict = await instance.async_add_executor_job(
        state_changes_during_period,
        hass,
        start,
        now,
        entity_id,
        True,  # include_start_time_state
        True,  # no_attributes
    )
    return history_dict.get(entity_id, [])
```

### Config Entry Migration (verified HA Developer Docs pattern)
```python
# In __init__.py
async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry."""
    if config_entry.version < 3:
        new_data = {
            k: v for k, v in config_entry.data.items()
            if k not in {"enable_ml", "retrain_period", "ml_learning_period", "cross_sensor_window"}
        }
        new_data.setdefault("history_window_days", 28)
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=3)
        _LOGGER.info("Migrated config entry to v3")
    return True
```

### Slot Index Calculation (168 slots)
```python
def slot_index(hour: int, dow: int) -> int:
    """
    hour: 0-23 (hour of day)
    dow: 0-6 (0=Monday per Python datetime.weekday())
    Returns: 0-167
    """
    return dow * 24 + hour
```

### Confidence Calculation (proportional to history coverage)
```python
from datetime import datetime, timedelta

def confidence(first_observation: datetime | None, window_days: int, now: datetime) -> float:
    """
    Returns 0.0 if no data, 1.0 if full window covered.
    Proportional between: 10 days of 28 = 0.357
    """
    if first_observation is None:
        return 0.0
    days_elapsed = (now - first_observation).total_seconds() / 86400
    return min(1.0, days_elapsed / window_days)
```

### Deprecated Sensor Data Keys (coordinator.py _build_sensor_data)
```python
def _build_sensor_data(self) -> dict[str, Any]:
    """Build sensor data dict. Stub keys preserve deprecated sensor states."""
    data = {
        # ... all existing v1.0 keys preserved for this phase ...
        # Stub keys for deprecated ML sensors (Phase 3 bridge)
        "ml_status_stub": "Removed in v1.1",
        "ml_training_stub": "N/A",
        "cross_sensor_stub": 0,
        # Learning status from new RoutineModel
        "learning_status": self._routine_model.learning_status(),  # "inactive"|"learning"|"ready"
        "baseline_confidence": round(self._routine_model.overall_confidence() * 100, 1),
    }
    return data
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `hass.bus.async_listen(EVENT_STATE_CHANGED)` global subscription | `async_track_state_change_event(hass, entity_list, callback)` entity-scoped | HA 2024.4 deprecated, HA 2025.5 removed | Old pattern still in codebase — must be replaced in Phase 4 coordinator rewrite. Phase 3 does not touch event subscription. |
| Custom `async_setup()` called manually from `__init__.py` | `_async_setup()` HA lifecycle method (called automatically) | HA 2024.8 | Existing code calls `coordinator.async_setup()` manually. CONTEXT.md notes this should migrate to `_async_setup()`. Phase 3 is the right time to make this change since coordinator.async_setup is being modified anyway. |
| Two Store instances (main + ml) | Single Store: `behaviour_monitor.{entry_id}.json` | v1.1 (this phase) | ML store eliminated; cleanup in Phase 3 |
| 672 time buckets (15-min slots) | 168 hour-of-day x day-of-week slots | v1.1 (this phase) | 4x more data per slot; stable statistics within 2 weeks |
| `get_significant_states` recorder API | `state_changes_during_period` recorder API | HA 2023+ (stable since) | Returns all state transitions, not just "significant" — required for binary entity bootstrap |

**Deprecated/outdated in this codebase:**
- `EVENT_STATE_CHANGED` subscription: deprecated HA 2024.4, removed HA 2025.5. Phase 4 must replace. Phase 3 does not touch.
- `CONF_ENABLE_ML`, `CONF_RETRAIN_PERIOD`, `CONF_ML_LEARNING_PERIOD`, `CONF_CROSS_SENSOR_WINDOW`: Remove from config entry via `async_migrate_entry`.
- `analyzer.py` and `ml_analyzer.py`: Deleted in Phase 3 (or Phase 4 if coordinator still imports them). Phase 3 must ensure `coordinator.py` no longer imports from these files.

---

## Open Questions

1. **Entity type detection (binary vs numeric)**
   - What we know: Binary entities include motion sensors, door contacts, switches. Numeric include temperature, power meters.
   - What's unclear: HA entity state class (`SensorStateClass.MEASUREMENT`) can be used to distinguish numeric, but not all binary sensors have `state_class` set. Some entities may be numeric but represented as string states.
   - Recommendation: Detect entity type from the state values observed during bootstrap: if values are exclusively `"on"/"off"/"open"/"closed"/"locked"/"unlocked"`, treat as binary; otherwise numeric. Fall back to binary if ambiguous. Document this heuristic in code.

2. **When to trigger bootstrap after storage data loss**
   - What we know: On fresh install or corrupt storage, RoutineModel starts empty.
   - What's unclear: Should the coordinator re-bootstrap every time storage is missing, or only on first setup? Re-bootstrapping on every restart would catch storage corruption but adds startup time.
   - Recommendation: Bootstrap whenever `routine_model` key is absent from loaded storage (covers both fresh install and corruption). Persist after bootstrap. If bootstrap itself fails, start with empty model — log warning, don't block startup.

3. **`async_migrate_entry` and STORAGE_VERSION scope**
   - What we know: `STORAGE_VERSION` in `const.py` is used by the Store class to track data format version. `async_migrate_entry` handles config entry version. These are separate versioning schemes.
   - What's unclear: Does `STORAGE_VERSION` need to match `config_entry.version`? In HA, `Store(hass, version, key)` — the version parameter is the store schema version, independent of config entry version.
   - Recommendation: Increment `STORAGE_VERSION` to 3 in `const.py` (controls storage format). Set `config_entry.version = 3` in `async_migrate_entry` (controls config entry format). Keep them in sync for clarity, but understand they are independent mechanisms.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pytest.ini` (exists at project root) |
| Quick run command | `venv/bin/python -m pytest tests/test_routine_model.py -x -q` |
| Full suite command | `venv/bin/python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | Load v2 storage fixture → no crash, empty routine model, coordinator state preserved | integration | `pytest tests/test_coordinator.py::TestStorageMigration -x` | ❌ Wave 0 |
| INFRA-01 | ML storage file deleted on setup after upgrade | unit | `pytest tests/test_coordinator.py::TestMLStoreCleanup -x` | ❌ Wave 0 |
| INFRA-01 | async_migrate_entry removes ML config keys, adds history_window_days | unit | `pytest tests/test_init.py::TestMigrateEntry -x` | ❌ Wave 0 |
| INFRA-02 | ml_status sensor returns "Removed in v1.1" (not unavailable) | unit | `pytest tests/test_sensor.py::TestDeprecatedSensorStubs -x` | ❌ Wave 0 |
| INFRA-02 | ml_training_remaining sensor returns "N/A" | unit | `pytest tests/test_sensor.py::TestDeprecatedSensorStubs -x` | ❌ Wave 0 |
| INFRA-02 | cross_sensor_patterns sensor returns 0 | unit | `pytest tests/test_sensor.py::TestDeprecatedSensorStubs -x` | ❌ Wave 0 |
| INFRA-02 | Deprecation warning logged once per startup for each deprecated sensor | unit | `pytest tests/test_coordinator.py::TestDeprecationLogs -x` | ❌ Wave 0 |
| ROUTINE-01 | slot_index correctly maps (hour, dow) to 0-167 | unit | `pytest tests/test_routine_model.py::TestActivitySlot::test_slot_index -x` | ❌ Wave 0 |
| ROUTINE-01 | ActivitySlot stores event observations; is_sufficient False below MIN_SLOT_OBSERVATIONS | unit | `pytest tests/test_routine_model.py::TestActivitySlot -x` | ❌ Wave 0 |
| ROUTINE-01 | EntityRoutine.record() assigns to correct slot | unit | `pytest tests/test_routine_model.py::TestEntityRoutine::test_record_assigns_correct_slot -x` | ❌ Wave 0 |
| ROUTINE-01 | RoutineModel serializes/deserializes via to_dict/from_dict with full fidelity | unit | `pytest tests/test_routine_model.py::TestRoutineModel::test_round_trip_serialization -x` | ❌ Wave 0 |
| ROUTINE-01 | Sparse slot (< MIN_SLOT_OBSERVATIONS) returns None from expected_gap_seconds | unit | `pytest tests/test_routine_model.py::TestEntityRoutine::test_sparse_slot_returns_none -x` | ❌ Wave 0 |
| ROUTINE-01 | overall_confidence returns 0.0 with no data, 1.0 with full window | unit | `pytest tests/test_routine_model.py::TestRoutineModel::test_confidence -x` | ❌ Wave 0 |
| ROUTINE-01 | learning_status transitions from inactive → learning → ready as observations accumulate | unit | `pytest tests/test_routine_model.py::TestRoutineModel::test_learning_status_transitions -x` | ❌ Wave 0 |
| ROUTINE-02 | Bootstrap replay from synthetic state list populates RoutineModel slots | unit | `pytest tests/test_coordinator.py::TestRecorderBootstrap::test_bootstrap_populates_model -x` | ❌ Wave 0 |
| ROUTINE-02 | Bootstrap with empty recorder response → empty model, no crash | unit | `pytest tests/test_coordinator.py::TestRecorderBootstrap::test_bootstrap_empty_recorder -x` | ❌ Wave 0 |
| ROUTINE-02 | Bootstrap with partial history (14 of 28 days) → confidence ~0.5 | unit | `pytest tests/test_coordinator.py::TestRecorderBootstrap::test_bootstrap_partial_history -x` | ❌ Wave 0 |
| ROUTINE-03 | Binary entity slot stores event times and inter-event intervals | unit | `pytest tests/test_routine_model.py::TestEntityRoutine::test_binary_entity_slot_storage -x` | ❌ Wave 0 |
| ROUTINE-03 | Numeric entity slot stores mean/stdev/count via Welford | unit | `pytest tests/test_routine_model.py::TestEntityRoutine::test_numeric_entity_slot_storage -x` | ❌ Wave 0 |
| ROUTINE-03 | expected_gap_seconds returns median inter-event interval for binary slot | unit | `pytest tests/test_routine_model.py::TestEntityRoutine::test_expected_gap_seconds -x` | ❌ Wave 0 |
| ROUTINE-03 | Entity type auto-detection: on/off states → binary, numeric strings → numeric | unit | `pytest tests/test_routine_model.py::TestEntityRoutine::test_entity_type_detection -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `venv/bin/python -m pytest tests/test_routine_model.py tests/test_coordinator.py -x -q`
- **Per wave merge:** `venv/bin/python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_routine_model.py` — covers ROUTINE-01, ROUTINE-03 (new file; RoutineModel is pure Python, no HA mocking required)
- [ ] `tests/test_coordinator.py::TestStorageMigration` — v2 fixture loading (new test class in existing file)
- [ ] `tests/test_coordinator.py::TestMLStoreCleanup` — ML store deletion (new test class)
- [ ] `tests/test_coordinator.py::TestRecorderBootstrap` — bootstrap from synthetic history (new test class; mock `get_instance` and `state_changes_during_period`)
- [ ] `tests/test_coordinator.py::TestDeprecationLogs` — deprecation warning logging (new test class)
- [ ] `tests/test_init.py::TestMigrateEntry` — async_migrate_entry (new test class in existing file)
- [ ] `tests/test_sensor.py::TestDeprecatedSensorStubs` — stub state values (new test class in existing file)
- [ ] Storage fixture: `tests/fixtures/v2_storage.json` — sample v2 format storage for migration tests

---

## Sources

### Primary (HIGH confidence)
- Existing codebase direct inspection: `coordinator.py`, `sensor.py`, `const.py`, `__init__.py`, `tests/conftest.py` — storage format, coordinator state keys to carry forward, entity contract, test infrastructure
- [Python docs: collections.deque](https://docs.python.org/3/library/collections.html#collections.deque) — `maxlen` auto-eviction confirmed
- [Python docs: statistics.NormalDist](https://docs.python.org/3/library/statistics.html) — `zscore()` method confirmed, Python 3.8+
- HA 2025 core `history_stats/data.py` source (via WebFetch) — `state_changes_during_period` via `get_instance().async_add_executor_job()` confirmed as current stable pattern
- [HA Developer Docs: Config entries](https://developers.home-assistant.io/docs/config_entries_index/) — `async_migrate_entry` signature, `async_update_entry` immutability requirement confirmed
- [HA 2024.8 `_async_setup` announcement](https://developers.home-assistant.io/blog/2024/08/05/coordinator_async_setup/) — lifecycle method confirmed

### Secondary (MEDIUM confidence)
- .planning/research/ARCHITECTURE.md — build order, component boundaries, data flow diagrams
- .planning/research/STACK.md — algorithm decisions, deque pattern, CUSUM formula
- .planning/research/PITFALLS.md — migration failure modes, sensor contract pitfalls

### Tertiary (LOW confidence — for validation)
- `get_significant_states` vs `state_changes_during_period` distinction: derived from reading `history_stats/data.py` source and HA recorder documentation; sufficient confidence for implementation but verify against HA 2025.x changelog if bootstrap produces unexpected results

---

## Metadata

**Confidence breakdown:**
- Storage migration: HIGH — existing code read directly; migrate-by-key-detection pattern confirmed; async_update_entry requirement confirmed from HA docs
- Stub sensor values: HIGH — sensor.py and coordinator.py read directly; value_fn lambda pattern understood
- RoutineModel design: HIGH — STACK.md and ARCHITECTURE.md research; deque/statistics stdlib confirmed; API is pure Python with no external dependencies
- Recorder bootstrap API: MEDIUM-HIGH — `state_changes_during_period` pattern verified from HA 2025 core source; prefer this over `get_significant_states` for binary entities; watch for API changes if upgrading HA version
- Confidence/learning status thresholds: MEDIUM — `MIN_SLOT_OBSERVATIONS=4` from STACK.md research; confidence proportional formula derived from requirements; validate with integration test

**Research date:** 2026-03-13
**Valid until:** 2026-06-13 (90 days; recorder API is stable; check if HA releases a breaking recorder change)
