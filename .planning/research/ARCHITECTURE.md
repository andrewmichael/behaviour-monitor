# Architecture Research

**Domain:** Home Assistant custom integration — routine-based anomaly detection (v1.1 Detection Rebuild)
**Researched:** 2026-03-13
**Confidence:** HIGH (full codebase read + official HA developer docs verified)

---

## Current Architecture (What Exists and What It Means for This Milestone)

```
custom_components/behaviour_monitor/
├── __init__.py        # HA entry point — setup/unload, service registration
├── sensor.py          # 14 sensors via CoordinatorEntity (KEEP — stable entity IDs)
├── coordinator.py     # BehaviourMonitorCoordinator — REWRITE ENTIRELY
├── analyzer.py        # PatternAnalyzer (z-score, 672 buckets) — DELETE
├── ml_analyzer.py     # MLPatternAnalyzer (River HST) — DELETE
├── config_flow.py     # Config UI (KEEP, extend for new options)
└── const.py           # Constants and defaults (KEEP, extend)
```

### What the Current Coordinator Does (Everything in One Class)

The existing `BehaviourMonitorCoordinator` is ~1,066 lines. It owns all of these concerns
with no internal boundaries:

- HA event bus subscription (`hass.bus.async_listen(EVENT_STATE_CHANGED, ...)`)
- Statistical pattern recording (`PatternAnalyzer.record_state_change`)
- ML event tracking and periodic retraining (`MLPatternAnalyzer`)
- Anomaly detection (`check_for_anomalies`, `check_anomaly`)
- Notification dispatch — three separate methods (persistent + mobile, statistical + ML + welfare)
- Welfare status debounce logic (3-cycle hysteresis)
- Holiday mode and snooze state
- Persistence (`Store` save/load with two separate storage keys)
- Sensor data dict assembly (`_async_update_data` returns a flat dict)

This is the cause of v1.0's difficulty in tuning: detection logic, notification logic, and HA
wiring are interleaved. The replacement must distribute these concerns into separate components.

---

## Recommended Architecture (v1.1)

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Home Assistant Core                              │
│   async_track_state_change_event    DataUpdateCoordinator    Store       │
└────────────┬────────────────────────────────┬────────────────────────────┘
             │ entity-scoped state events      │ 60s poll (_async_update_data)
             ▼                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│               BehaviourMonitorCoordinator (coordinator.py)                │
│  - _async_setup: loads stored data, subscribes to state changes          │
│  - @callback _handle_state_change: feeds RoutineModel + AcuteDetector   │
│  - _async_update_data (60s): runs DriftDetector, assembles sensor dict  │
│  - Owns: holiday mode, snooze, persistence, service call delegation      │
│  - Delegates all notifications to NotificationManager                   │
└────┬──────────────────┬──────────────────────────┬───────────────────────┘
     │                  │                          │
     ▼                  ▼                          ▼
┌──────────┐    ┌───────────────┐    ┌─────────────────────┐
│ Routine  │    │    Acute      │    │       Drift         │
│  Model   │    │   Detector   │    │     Detector        │
│          │    │              │    │                     │
│ Learns   │    │ Real-time    │    │ Periodic (60s)      │
│ per-     │    │ inactivity   │    │ CUSUM on daily      │
│ entity   │    │ gap check    │    │ activity rates      │
│ baselines│    │ fires on     │    │ per entity;         │
│ from raw │    │ each event   │    │ detects sustained   │
│ history  │    │              │    │ change over days    │
└────┬─────┘    └──────┬───────┘    └──────────┬──────────┘
     │                 │                        │
     └─────────────────┴────────────────────────┘
                       │ AcuteResult / DriftResult
                       ▼
           ┌───────────────────────┐
           │  NotificationManager  │
           │  (notification.py)    │
           │                       │
           │  Cooldown per entity  │
           │  Deduplication        │
           │  Severity gate        │
           │  Welfare debounce     │
           │  Message construction │
           │  Mobile + persistent  │
           └───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              sensor.py — 14 CoordinatorEntity sensors     │
│  Read coordinator.data dict keys — minimal changes        │
│  Entity IDs unchanged (user automations remain intact)   │
└──────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | File | Responsibility | Communicates With |
|-----------|------|----------------|-------------------|
| `BehaviourMonitorCoordinator` | `coordinator.py` | HA lifecycle, event subscription, orchestration, persistence, sensor data dict | All internal components; HA core |
| `RoutineModel` | `routine_model.py` | Learns per-entity baselines from raw state change history (configurable window, default 4 weeks). Pure Python, no HA imports | Coordinator (write); AcuteDetector + DriftDetector (read) |
| `AcuteDetector` | `acute_detector.py` | Detects real-time inactivity threshold breaches by comparing elapsed gap to baseline. Pure Python | Coordinator (results); RoutineModel (read baseline) |
| `DriftDetector` | `drift_detector.py` | Periodic CUSUM on daily activity rates per entity; detects sustained behavior change over days/weeks. Pure Python | Coordinator (results); RoutineModel (read daily rates) |
| `NotificationManager` | `notification.py` | Cooldown tracking, deduplication, severity gate, welfare debounce, message construction, HA service dispatch | Coordinator (called from); HA services |
| `sensor.py` | `sensor.py` | 14 CoordinatorEntity sensors reading `coordinator.data` | Coordinator (read-only) |
| `config_flow.py` | `config_flow.py` | Config UI; option migration for new keys | Coordinator config at startup |
| `const.py` | `const.py` | Constants, defaults | All |

**The critical principle:** `routine_model.py`, `acute_detector.py`, and `drift_detector.py` contain zero HA imports. They are plain Python classes. This makes them fully unit-testable without any HA mock infrastructure.

---

## Recommended File Structure

```
custom_components/behaviour_monitor/
├── __init__.py           # HA entry point (minor changes — service registration stays)
├── sensor.py             # 14 sensors (minor changes — some value_fn lambdas for new keys)
├── coordinator.py        # REWRITTEN — orchestrator only, target <350 lines
├── routine_model.py      # NEW — baseline learning, to_dict/from_dict
├── acute_detector.py     # NEW — inactivity gap threshold engine
├── drift_detector.py     # NEW — CUSUM change point engine
├── notification.py       # NEW (extracted from coordinator) — all notification logic
├── config_flow.py        # EXTENDED — history_window, inactivity_threshold, drift_threshold
└── const.py              # EXTENDED — new constants; ML constants removed
```

### Structure Rationale

- **`coordinator.py` rewritten:** The existing file's 1,066 lines cannot be patched incrementally — detection logic is too entangled with HA wiring. A clean rewrite with all domain logic extracted will produce a maintainable ~300-line orchestrator.
- **`routine_model.py`:** Extracted to own file so it can be built and tested before coordinator wiring is touched. HA-free.
- **`acute_detector.py` / `drift_detector.py`:** Separate files keep the two detection timescales distinct. Both are HA-free. Can be built in parallel.
- **`notification.py`:** Notification logic (currently ~400 lines spread across three coordinator methods) extracted so it can be changed independently of detection logic.
- **Old `analyzer.py` and `ml_analyzer.py`:** Deleted entirely. No migration path for z-score bucket data — it represents a fundamentally different model.

---

## Architectural Patterns

### Pattern 1: Event-Driven Feed with Periodic Scan (Two Timescales)

**What:** The coordinator subscribes to state changes via `async_track_state_change_event`. Each event immediately feeds `RoutineModel` (learning) and `AcuteDetector` (real-time check). `DriftDetector` runs on the 60-second `_async_update_data` poll, not per-event, because drift is inherently slow-moving and its CUSUM computation iterates history.

**When to use:** When detection operates at two distinct timescales — acute (seconds) and drift (days). Collapsing both into one code path creates the same problem as the current architecture.

**Trade-offs:** Acute events fire inline with the state change `@callback`. This is synchronous and must stay fast (< a few milliseconds). Heavy computation — anything iterating stored history — belongs in `_async_update_data`, not the callback.

**Example (coordinator.py sketch):**
```python
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.core import Event, EventStateChangedData, callback

async def _async_setup(self) -> None:
    """One-time init: load persisted data, subscribe to state events."""
    await self._load_persisted_data()
    self._unsub = async_track_state_change_event(
        self.hass,
        list(self._monitored_entities),
        self._handle_state_change,
    )

@callback
def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
    """Fires on each monitored entity state change. Must be fast."""
    if self._holiday_mode or self.is_snoozed():
        return
    entity_id = event.data["entity_id"]
    new_state = event.data["new_state"]
    if new_state is None:
        return
    now = dt_util.now()
    self._routine_model.record(entity_id, now, new_state.state)
    result = self._acute_detector.check(entity_id, now)
    if result.is_anomaly:
        self.hass.async_create_task(
            self._notification_manager.send_acute(result)
        )
    self.async_set_updated_data(self._build_sensor_data())
```

### Pattern 2: Routine Model as Pure-Python Stateful Component with Persistence

**What:** `RoutineModel` stores per-entity observation history as plain Python data (lists of `(iso_timestamp, state_value)` tuples within the configured history window). It provides `expected_gap_seconds(entity_id)` and `daily_activity_rate(entity_id, date)` to detectors. It serializes to/from dict for HA `Store`. No external library dependencies.

**When to use:** Any stateful detection component that needs to survive HA restarts. The existing `PatternAnalyzer.to_dict()` / `from_dict()` is the direct precedent — carry that pattern forward.

**Trade-offs:** Raw event storage grows with history window and entity count. A 4-week window with 50 events/day across 15 entities is ~21,000 records — roughly 2MB of JSON at worst. This is well within HA storage norms. If entity count grows large, switch from raw events to daily-rate bins (one float per entity per day).

**Example (routine_model.py sketch):**
```python
@dataclass
class EntityRoutine:
    entity_id: str
    observations: list[tuple[str, str]]  # (iso_timestamp, state_value)
    history_window_days: int = 28

    def prune(self, now: datetime) -> None:
        """Remove observations older than history_window_days."""
        cutoff = (now - timedelta(days=self.history_window_days)).isoformat()
        self.observations = [(ts, s) for ts, s in self.observations if ts >= cutoff]

    def expected_gap_seconds(self) -> float:
        """Median gap between consecutive observations."""
        ...

    def daily_rate(self, target_date: date) -> float:
        """Count of state changes recorded on target_date."""
        ...

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityRoutine: ...
```

### Pattern 3: CUSUM for Drift Detection (Pure Python, No Dependencies)

**What:** The drift detector maintains a per-entity CUSUM statistic over daily activity rates. CUSUM (Cumulative Sum) is standard change-point detection with O(n) complexity per entity per cycle, where n is the number of days in the history window (28 by default). No external library required — the algorithm is ~15 lines of arithmetic.

**When to use:** Detecting sustained directional changes in a rate signal. Ideal for "person normally active 40 times/day but has been averaging 10 for the past week." Not suitable for detecting single acute events.

**Trade-offs:** CUSUM has a single tunable parameter (the drift threshold `k`) that must be calibrated. Too low: false positives on normal weekly variation. Too high: misses real drift. This threshold should be exposed in config flow so users can tune it. Start with k = 0.5 standard deviations from the baseline mean.

**Example (drift_detector.py sketch):**
```python
@dataclass
class DriftResult:
    entity_id: str
    is_drift: bool
    direction: str  # "lower" or "higher"
    cusum_score: float
    days_detected: int
    description: str

class DriftDetector:
    def __init__(self, threshold_k: float = 0.5, min_days: int = 3) -> None:
        self._k = threshold_k
        self._min_days = min_days
        self._cusum_pos: dict[str, float] = {}
        self._cusum_neg: dict[str, float] = {}
        self._drift_days: dict[str, int] = {}

    def check(self, entity_id: str, routine: EntityRoutine, today: date) -> DriftResult:
        """Run one CUSUM step for entity_id using today's rate vs baseline."""
        baseline = routine.expected_daily_rate()
        actual = routine.daily_rate(today)
        delta = actual - baseline
        s_pos = max(0, self._cusum_pos.get(entity_id, 0) + delta - self._k)
        s_neg = max(0, self._cusum_neg.get(entity_id, 0) - delta - self._k)
        self._cusum_pos[entity_id] = s_pos
        self._cusum_neg[entity_id] = s_neg
        ...
```

### Pattern 4: Coordinator as Thin Orchestrator

**What:** The new `coordinator.py` owns only HA integration concerns: entry lifecycle (`_async_setup`, `async_shutdown`), event subscription setup/teardown, `_async_update_data` that calls drift detector and assembles sensor data dict, holiday mode, snooze, and delegation to `NotificationManager`. All domain logic lives in separate classes.

**When to use:** Always, for HA integrations beyond a trivial size.

**Trade-offs:** More files, more explicit wiring in the coordinator constructor. The payoff: detection logic is unit-testable without mocking `hass`, `ConfigEntry`, or `Store`. The coordinator tests only need to verify orchestration (correct calls made in correct order), not algorithm correctness.

---

## Data Flow

### Acute Detection Flow (Event-Driven)

```
HA entity changes state
        |
        v
async_track_state_change_event callback fires (synchronous @callback)
        |
holiday_mode / snooze check --> return early if suppressed
        |
        v
RoutineModel.record(entity_id, timestamp, state_value)
  - Appends to observations
  - Prunes observations older than history_window_days
        |
        v
AcuteDetector.check(entity_id, now)
  - Reads RoutineModel.expected_gap_seconds(entity_id)
  - Compares (now - last_seen_timestamp) to (expected_gap * inactivity_multiplier)
  - Returns AcuteResult(is_anomaly, entity_id, elapsed, threshold, description)
        |
  if AcuteResult.is_anomaly:
        v
  hass.async_create_task(NotificationManager.send_acute(result))
  - Cooldown check: was acute alert sent for this entity recently?
  - If not: dispatch persistent_notification + mobile notification
        |
        v
coordinator.async_set_updated_data(self._build_sensor_data())
  - All 14 CoordinatorEntity sensors refresh from updated dict
```

### Drift Detection Flow (Periodic)

```
60-second DataUpdateCoordinator poll
        |
        v
_async_update_data() called
        |
        v
DriftDetector.check_all(routine_model, today)
  - For each entity: compute today's rate vs baseline
  - Run CUSUM step: update S_pos and S_neg
  - If CUSUM score exceeds threshold for min_days consecutive: is_drift=True
  - Returns list[DriftResult]
        |
  if any DriftResult.is_drift:
        v
  NotificationManager.send_drift(results)
  - Dedup: same entity drift already notified recently?
  - If not: dispatch notification
        |
        v
Build and return sensor data dict (see Sensor Data Contract below)
        |
        v
All 14 CoordinatorEntity sensors refresh
```

### Persistence Flow

```
HA startup
        |
        v
_async_setup() (called automatically by async_config_entry_first_refresh)
  - Load Store: behaviour_monitor.{entry_id}.json
  - If "routine_model" key present: RoutineModel.from_dict(data["routine_model"])
  - If "coordinator" key present: restore holiday_mode, snooze_until, cooldowns
  - If old format ("analyzer" key present): log warning, start fresh routine model
  - Subscribe to state change events
        |
        v
Normal operation (each 60s cycle)
        |
        v
_async_update_data() ends with: await self._save_data()
  - Store: {"routine_model": model.to_dict(), "coordinator": {...}}
        |
        v
HA shutdown
        |
        v
async_shutdown()
  - Unsubscribe from events
  - Final _save_data() call
```

---

## Integration Points

### HA Core: What Changes

| Concern | Current (v1.0) | v1.1 | Notes |
|---------|---------------|------|-------|
| Event subscription | `hass.bus.async_listen(EVENT_STATE_CHANGED, ...)` | `async_track_state_change_event(hass, entity_list, callback)` | Old API deprecated, removed in HA 2025.5. New API is entity-scoped and more efficient. |
| Coordinator init hook | Custom `async_setup()` called manually in `__init__.py` | `_async_setup()` (HA lifecycle method) | Introduced HA 2024.8. Called automatically by `async_config_entry_first_refresh`. Cleaner separation of init from updates. |
| Data push to sensors | `hass.async_create_task(self.async_request_refresh())` on each event | `async_set_updated_data(data)` on each event | `async_request_refresh` triggers a full `_async_update_data` cycle (unnecessary for event-driven updates). `async_set_updated_data` pushes data directly to sensors. Reserve `_async_update_data` for drift detection and periodic saves. |
| Storage keys | Two stores: `behaviour_monitor.{id}` and `behaviour_monitor_ml.{id}` | One store: `behaviour_monitor.{id}` | ML store eliminated. Increment `STORAGE_VERSION`. |
| Services | `enable_holiday_mode`, `disable_holiday_mode`, `snooze`, `clear_snooze` | Same | No change to service API. |

### Sensor Data Contract (coordinator.data dict)

The 14 sensors in `sensor.py` read from `coordinator.data` via `value_fn` lambdas. Keys that must survive unchanged (sensor entity IDs depend on `description.key`, not on the data dict keys, so data dict keys can change as long as `value_fn` lambdas are updated):

| Data Key | Status | Notes |
|----------|--------|-------|
| `last_activity` | KEEP | ISO timestamp of last state change across all entities |
| `activity_score` | KEEP | 0–100 score derived from routine model |
| `anomaly_detected` | KEEP | True if any acute or drift anomaly is active |
| `daily_count` | KEEP | Total state changes today |
| `welfare` | KEEP | Welfare status dict (ok/check/concern/alert + reasons) |
| `routine` | KEEP | Routine progress dict |
| `activity_context` | KEEP | Time since last activity with context |
| `entity_status` | KEEP | Per-entity status list |
| `last_notification` | KEEP | Timestamp + type of last sent notification |
| `holiday_mode` | KEEP | bool |
| `snooze_active` | KEEP | bool |
| `snooze_until` | KEEP | ISO timestamp or null |
| `anomalies` | REPLACE | Split into `acute_anomalies` + `drift_anomalies` |
| `ml_status` | REMOVE | ML eliminated; `sensor.py` ml_status sensor needs new value |
| `cross_sensor_patterns` | REMOVE | ML eliminated |
| `stat_training` | REPLACE | Replace with `learning_status` dict |
| `ml_training` | REMOVE | ML eliminated |

**Affected sensors requiring `value_fn` updates:** `ml_status`, `cross_sensor_patterns`, `baseline_confidence`, `statistical_training_remaining`, `ml_training_remaining`, `anomaly_detected` (for new anomaly list keys).

### Storage Migration

| Old Storage Key | v1.1 Treatment |
|-----------------|----------------|
| `analyzer` (672-bucket z-score data) | Discard — cannot migrate to routine model format |
| `coordinator.last_notification_time` | Carry forward |
| `coordinator.last_notification_type` | Carry forward |
| `coordinator.last_welfare_status` | Carry forward |
| `coordinator.holiday_mode` | Carry forward |
| `coordinator.snooze_until` | Carry forward |
| `coordinator.notification_cooldowns` | Carry forward |
| `coordinator.welfare_consecutive_cycles` | Carry forward |
| `coordinator.welfare_pending_status` | Carry forward |
| `_ml.{entry_id}` store | Delete (River ML removed) |

Migration logic in `_async_setup`: if loaded data has `"analyzer"` key and no `"routine_model"` key, log an info message that pattern history is starting fresh, carry forward coordinator state keys. Increment `STORAGE_VERSION` to 3 to force fresh schema.

---

## Build Order

Dependencies run strictly bottom-up: const → pure models → pure detectors → notification → coordinator → sensor + config flow.

| Step | What | Why This Order |
|------|------|----------------|
| 1 | `const.py` — add new config keys (`CONF_HISTORY_WINDOW`, `CONF_INACTIVITY_MULTIPLIER`, `CONF_DRIFT_THRESHOLD`), remove ML constants, update defaults | Everything imports const. Must be first. |
| 2 | `routine_model.py` — `EntityRoutine`, `RoutineModel` with `to_dict`/`from_dict` | Pure Python. Detectors depend on this. Fully testable immediately. |
| 3 | `acute_detector.py` — `AcuteResult`, `AcuteDetector` | Depends on RoutineModel only. Pure Python. |
| 4 | `drift_detector.py` — `DriftResult`, `DriftDetector` with CUSUM | Depends on RoutineModel only. Pure Python. Steps 3 and 4 can be built in parallel. |
| 5 | `notification.py` — `NotificationManager` extracted from coordinator | Depends on AcuteResult, DriftResult types. Needs HA service calls, so mock `hass` in tests. |
| 6 | `coordinator.py` — rewritten as orchestrator | Wires together all above. Tests verify orchestration, not algorithm correctness. |
| 7 | `sensor.py` — update `value_fn` and `extra_attrs_fn` lambdas for changed data keys | Depends on coordinator data dict shape being stable. |
| 8 | `config_flow.py` — add new option forms for history window and thresholds | Can be done in parallel with step 7. Does not block detection. |

**Why pure model/detector files precede the coordinator:** Steps 2–5 produce fully-tested HA-free classes. The coordinator (step 6) then injects these as dependencies. This means the coordinator test can use real model/detector instances rather than mocks, reducing test complexity.

---

## Anti-Patterns

### Anti-Pattern 1: Everything in the Coordinator

**What people do:** Grow detection algorithms, notification formatting, and debounce state inside the coordinator class because it already has access to `hass`, `ConfigEntry`, and `Store`.

**Why it's wrong:** The current 1,066-line coordinator is the result. Unit testing requires a mocked `hass` object for every test. Unrelated changes conflict. The single class cannot be incrementally replaced.

**Do this instead:** The coordinator is an orchestrator only. It calls into `RoutineModel`, `AcuteDetector`, `DriftDetector`, and `NotificationManager`. Target: coordinator under 350 lines. All detection logic is in HA-free classes.

### Anti-Pattern 2: Using `hass.bus.async_listen(EVENT_STATE_CHANGED)` for Specific Entities

**What people do:** Subscribe to the full `EVENT_STATE_CHANGED` bus and filter by entity_id inside the callback — exactly what the current code does.

**Why it's wrong:** Creates a top-level listener that evaluates every state change in the entire HA instance to discard most of them. This API was deprecated in 2024 and removed in HA 2025.5.

**Do this instead:** `async_track_state_change_event(hass, entity_list, callback)` — entity-scoped, O(1) dispatch for unmonitored entities, current API.

### Anti-Pattern 3: Running CUSUM or History Iteration Inside the @callback

**What people do:** Put drift detection (iterating stored observations) inside the synchronous `@callback` that handles each state change event.

**Why it's wrong:** The `@callback` decorator runs synchronously in HA's event loop. Anything with O(n) over history blocks event processing. At 28 days of history and 15 entities, this is thousands of iterations per state change.

**Do this instead:** Acute check (constant time: compare two timestamps) stays in the callback. CUSUM (iterate daily rates) runs in `_async_update_data`, which is called on the 60-second poll cycle. The split is: if computation is O(1) or O(entity_count), callback is fine; if O(history_days), move to `_async_update_data`.

### Anti-Pattern 4: Calling `async_request_refresh()` on Every State Change

**What people do:** The current code calls `self.hass.async_create_task(self.async_request_refresh())` inside the state change callback to wake up the sensors.

**Why it's wrong:** `async_request_refresh` triggers a full `_async_update_data` cycle — including drift detection and persistence writes. At normal home activity rates (many events per hour), this runs the drift CUSUM on every single event, and triggers a persistence write each time.

**Do this instead:** Use `async_set_updated_data(self._build_sensor_data())` in the callback — pushes updated data directly to sensors without invoking `_async_update_data`. Reserve the 60-second `_async_update_data` poll for drift detection and periodic saves. The `_build_sensor_data()` method is a fast dict assembly with no history iteration.

### Anti-Pattern 5: Storing Opaque Library State in Persistence

**What the previous version did:** Persisted River ML's internal model objects through `MLPatternAnalyzer.to_dict()`. These blobs were library-version-sensitive and unreadable without River installed.

**Why it's wrong:** Removes portability, blocks dependency removal, and makes storage migration impossible when the library changes.

**Do this instead:** The new `RoutineModel` stores only plain Python primitives: ISO timestamp strings and state value strings in a list. Readable by any Python process. Migratable. No external serialization format.

---

## Scaling Considerations

This is a single-home HA integration. "Scaling" means handling more monitored entities without degrading HA responsiveness.

| Scale | Approach |
|-------|----------|
| 1–20 entities (typical) | Raw event storage in `RoutineModel` is fine. Full history in memory. All detection comfortably in <1ms. |
| 20–50 entities | Consider switching to daily-bin storage (one `float` per entity per day) instead of raw event timestamps. Reduces memory from ~100 bytes/event to ~8 bytes/day. |
| 50+ entities | Unlikely for home use. If needed: lazy baseline computation (compute expected_gap only when queried, not on every record call). |

**First bottleneck:** Memory for raw event history. 4-week window, 50 events/day, 20 entities = 56,000 records. At ~120 bytes each (ISO string + short state string): ~6.7MB. Acceptable. At 50 entities: ~17MB — consider binning.

**Second bottleneck:** `_build_sensor_data()` is called on every state change. Keep it a pure dict assembly from pre-computed attributes. Never iterate history inside it.

---

## Sources

- Home Assistant Developer Docs — Fetching data: https://developers.home-assistant.io/docs/integration_fetching_data/
- HA 2024.8 `_async_setup` announcement: https://developers.home-assistant.io/blog/2024/08/05/coordinator_async_setup/
- `async_track_state_change_event` migration (deprecation of `async_track_state_change`, removed HA 2025.5): https://developers.home-assistant.io/blog/2024/04/13/deprecate_async_track_state_change/
- CUSUM algorithm: https://blog.stackademic.com/the-cusum-algorithm-all-the-essential-information-you-need-with-python-examples-f6a5651bf2e5
- Existing codebase — read in full: `coordinator.py` (1,066 lines), `analyzer.py` (830 lines), `ml_analyzer.py`, `sensor.py`, `const.py`, `__init__.py`

---

*Architecture research for: behaviour-monitor v1.1 Detection Rebuild*
*Researched: 2026-03-13*
