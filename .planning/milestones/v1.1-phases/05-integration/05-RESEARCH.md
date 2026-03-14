# Phase 5: Integration - Research

**Researched:** 2026-03-13
**Domain:** Home Assistant coordinator rebuild, config flow migration, notification wiring — integrating Phase 3/4 detection engines into HA platform
**Confidence:** HIGH (all findings are based on direct source code inspection of this repository plus established HA patterns already used in the codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- All 14 sensor entity IDs must remain stable — coordinator.data dict keys preserved
- activity_score, anomaly_detected, welfare_status, and other sensor keys must be populated from RoutineModel + AcuteDetector + DriftDetector instead of PatternAnalyzer + MLPatternAnalyzer
- Coordinator target: under 350 lines (currently 1,213 lines)
- Existing suppression logic preserved: holiday mode, snooze, per-entity notification cooldown, welfare debounce (3-cycle hysteresis)
- coordinator.data must never be None on first refresh
- New options to add: history_window_days (already migrated in Phase 3), inactivity_multiplier, drift_sensitivity
- Old ML options to handle: enable_ml, ml_learning_period, retrain_period, cross_sensor_window
- Old sensitivity dropdown (sigma-based) needs adaptation — no z-scores in v1.1
- Existing config entries must load without error and receive sensible defaults for new options
- Config migration pattern: dict copy + pop, never mutate config_entry.data directly
- AlertResult.explanation provides human-readable text for notification body
- Both acute and drift alerts use the configured notification service (or persistent_notification fallback)
- analyzer.py (z-score PatternAnalyzer) and ml_analyzer.py (River ML) are fully replaced by new engines
- Old test files (test_analyzer.py, test_ml_analyzer.py, test_coordinator.py) test dead code paths

### Claude's Discretion
- activity_score sensor mapping (RoutineModel.confidence vs daily activity ratio vs other)
- anomaly_detected semantics (union of acute+drift vs acute-only vs other)
- Coordinator internal structure to stay under 350 lines
- welfare_status derivation from AlertSeverity
- ML option removal strategy (strip from UI vs show as deprecated)
- Drift sensitivity presentation (dropdown matching sensitivity pattern vs other)
- Inactivity multiplier control type (number box vs preset dropdown)
- Old sensitivity dropdown fate (repurpose vs remove)
- Acute vs drift notification format differentiation
- Notification cooldown strategy (shared per entity vs independent per alert type)
- min_notification_severity gate adaptation (map to AlertSeverity vs remove)
- analyzer.py / ml_analyzer.py removal timing (this phase vs later)
- Old test file lifecycle (delete and replace vs keep alongside)
- Unused constant cleanup in const.py

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-03 | Config flow UI includes options for history window length, inactivity alert multiplier, and drift sensitivity | Config flow currently has no inactivity_multiplier or drift_sensitivity fields. Migration v3→v4 needed to add them with defaults. Selectors already used: NumberSelector for history_window, SelectSelector for sensitivity levels — same patterns apply to new fields. |
</phase_requirements>

---

## Summary

Phase 5 is a surgical replacement of the coordinator's analysis backend and a config flow simplification. The new detection engines (RoutineModel, AcuteDetector, DriftDetector, AlertResult) are fully built and tested in isolation. The coordinator currently imports PatternAnalyzer and MLPatternAnalyzer — those 1,213 lines need to collapse to under 350 by discarding the dual-analyzer pattern and wiring the three new engines directly.

The config flow currently exposes six ML-specific options (enable_ml, ml_learning_period, retrain_period, cross_sensor_window) that are obsolete, plus a sigma-based sensitivity dropdown that has no meaning in v1.1. Those must be removed and replaced with two new options (inactivity_multiplier, drift_sensitivity). The existing config entry version is 3; adding new keys requires a v3→v4 migration using the established `dict copy + setdefault` pattern from Phase 3.

All 14 sensor entity IDs are stable. The `sensor.py` value_fn lambdas read from coordinator.data keys — those keys must exist in the rebuilt dict. Five sensor keys currently draw from PatternAnalyzer methods that have no direct equivalent in the new engines; each needs a mapping decision. Three sensors are already deprecated stubs (ml_status, ml_training_remaining, cross_sensor_patterns) — they stay unchanged.

**Primary recommendation:** Write the new coordinator from scratch as a clean 300-line file rather than patching the 1,213-line version. Preserve every coordinator.data key that sensor.py references. Remove PatternAnalyzer and MLPatternAnalyzer imports entirely.

---

## Standard Stack

### Core (already in use — no new dependencies)
| Component | Source | Purpose | Notes |
|-----------|--------|---------|-------|
| `RoutineModel` | `routine_model.py` | Per-entity baseline learning | `overall_confidence()`, `learning_status()`, `record()`, `to_dict()`/`from_dict()` |
| `AcuteDetector` | `acute_detector.py` | Inactivity + unusual-time detection | `check_inactivity(entity_id, routine, now, last_seen)`, `check_unusual_time(entity_id, routine, now)` |
| `DriftDetector` | `drift_detector.py` | CUSUM-based drift detection | `check(entity_id, routine, today, now)`, `reset_entity(entity_id)` |
| `AlertResult` | `alert_result.py` | Structured result from detectors | `.explanation`, `.severity` (AlertSeverity enum), `.alert_type`, `.to_dict()` |
| `DataUpdateCoordinator` | HA helper | Periodic refresh + sensor wiring | Existing pattern, unchanged |
| `Store` | HA helper | Persistence | Existing v3 storage format, needs cusum_states added for v4 |

### Supporting
| Component | Source | Purpose |
|-----------|--------|---------|
| `CUSUM_PARAMS` | `const.py` | Maps sensitivity string to (k, h) tuple — already defined |
| `DEFAULT_INACTIVITY_MULTIPLIER` | `const.py` | 3.0 — already defined |
| `WELFARE_DEBOUNCE_CYCLES` | `const.py` | 3 — preserved unchanged |
| `SNOOZE_DURATIONS` | `const.py` | Snooze options — preserved |

### New constants needed in const.py
| Constant | Value | Purpose |
|----------|-------|---------|
| `CONF_INACTIVITY_MULTIPLIER` | `"inactivity_multiplier"` | Config key for AcuteDetector |
| `CONF_DRIFT_SENSITIVITY` | `"drift_sensitivity"` | Config key for DriftDetector |
| `SERVICE_ROUTINE_RESET` | `"routine_reset"` | Service name string |

---

## Architecture Patterns

### Coordinator Structure (target: under 350 lines)

The current 1,213-line coordinator has three logical zones:

1. **ML/analyzer plumbing** (lines 52–200, ~150 lines): imports, PatternAnalyzer, MLPatternAnalyzer, ML config reading — DELETE entirely
2. **Suppression + service methods** (lines ~200–580, ~380 lines): holiday mode, snooze, `_should_notify`, notification cooldown — PRESERVE, minor edits
3. **Data update + notification sending** (lines ~580–1,200, ~620 lines): `_async_update_data`, `_send_notification`, `_send_ml_notification`, `_send_welfare_notification`, sensor data dict — REWRITE

The target structure is three collaborating private methods called from `_async_update_data`:

```
_async_update_data()
  ├── _run_detection(now) → list[AlertResult]       # AcuteDetector + DriftDetector per entity
  ├── _handle_alerts(alerts, now) → None             # suppression + notification
  └── _build_sensor_data(alerts, now) → dict         # populate all 14 sensor keys
```

### Recommended File Structure (coordinator.py, ~300 lines)

```
__init__           # ~40 lines: engines + config init
async_setup        # ~50 lines: load storage, bootstrap, subscribe
async_shutdown     # ~10 lines: unsubscribe, save
_save_data         # ~30 lines: v4 format with cusum_states
_handle_state_changed  # ~30 lines: record to routine_model, refresh
_async_update_data # ~60 lines: calls _run_detection, _handle_alerts, _build_sensor_data
_run_detection     # ~30 lines: loop entities, call detectors, return AlertResult list
_handle_alerts     # ~30 lines: suppression gate, send_notification calls
_build_sensor_data # ~30 lines: populate all 14 coordinator.data keys
_send_notification # ~20 lines: persistent_notification + configured services
# holiday/snooze service methods: ~20 lines total
```

### Pattern 1: Engine Instantiation from Config

```python
# Source: const.py + direct inspection of AcuteDetector/DriftDetector __init__ signatures
self._acute_detector = AcuteDetector(
    inactivity_multiplier=float(
        entry.data.get(CONF_INACTIVITY_MULTIPLIER, DEFAULT_INACTIVITY_MULTIPLIER)
    )
)
self._drift_detector = DriftDetector(
    sensitivity=entry.data.get(CONF_DRIFT_SENSITIVITY, SENSITIVITY_MEDIUM)
)
```

### Pattern 2: Per-entity Detection Loop

```python
# Source: direct inspection of AcuteDetector and DriftDetector public APIs
alerts: list[AlertResult] = []
now = dt_util.now()
today = now.date()

for entity_id in self._monitored_entities:
    routine = self._routine_model._entities.get(entity_id)
    if routine is None:
        continue
    last_seen = self._last_seen.get(entity_id)  # maintained in _handle_state_changed

    result = self._acute_detector.check_inactivity(entity_id, routine, now, last_seen)
    if result:
        alerts.append(result)

    result = self._acute_detector.check_unusual_time(entity_id, routine, now)
    if result:
        alerts.append(result)

    result = self._drift_detector.check(entity_id, routine, today, now)
    if result:
        alerts.append(result)
```

Note: AcuteDetector needs a `last_seen` dict — the coordinator must track when each entity last changed state.

### Pattern 3: coordinator.data Keys — Mapping Table

These are the keys sensor.py's `value_fn` lambdas read from `coordinator.data`. All must exist and never be None on first refresh.

| coordinator.data key | Sensor | Current source | New source |
|---------------------|--------|---------------|------------|
| `last_activity` | Last Activity | `analyzer.get_last_activity_time()` | `self._last_seen` max timestamp |
| `activity_score` | Activity Score | `analyzer.calculate_activity_score()` | `routine_model.overall_confidence() * 100` (Claude discretion) |
| `anomaly_detected` | Anomaly Detected | bool from stat+ml anomalies | `len(active_alerts) > 0` |
| `anomalies` | anomaly_detected attrs | list of dicts | `[a.to_dict() for a in active_alerts]` |
| `confidence` | Baseline Confidence | `analyzer.get_confidence()` | `routine_model.overall_confidence() * 100` |
| `daily_count` | Daily Activity Count | `analyzer.get_total_daily_count()` | sum of today's events across entities (tracked in coordinator) |
| `welfare` | Welfare Status | `analyzer.get_welfare_status()` dict | Derived from `active_alerts` severity (Claude discretion) |
| `routine` | Routine Progress | `analyzer.get_routine_progress()` dict | Can keep structure; data from routine_model |
| `activity_context` | Time Since Activity | `analyzer.get_time_since_activity_context()` | Computed from `self._last_seen` + `routine.expected_gap_seconds` |
| `entity_status` | Entity Status Summary | `analyzer.get_entity_status()` list | Built from per-entity alert state |
| `stat_training` | Statistical Training Remaining | `analyzer.get_training_time_remaining()` | From `routine_model.overall_confidence()` + first_observation |
| `last_notification` | Last Notification | coordinator state | Preserved unchanged |
| `holiday_mode` | (switch/select) | coordinator state | Preserved unchanged |
| `snooze_active` | (switch/select) | coordinator state | Preserved unchanged |
| `ml_status_stub` | ml_status sensor | static | `"Removed in v1.1"` (unchanged) |
| `ml_training_stub` | ml_training_remaining | static | `"N/A"` (unchanged) |
| `cross_sensor_stub` | cross_sensor_patterns | static | `0` (unchanged) |
| `learning_status` | (not a sensor, internal) | routine_model | `routine_model.learning_status()` |
| `baseline_confidence` | Baseline Confidence attrs | routine_model | `round(routine_model.overall_confidence() * 100, 1)` |

### Pattern 4: Config Flow Migration v3 → v4

```python
# Source: __init__.py async_migrate_entry (Phase 3 pattern)
# v3→v4: remove old sensitivity/ML keys, add inactivity_multiplier + drift_sensitivity
_KEYS_REMOVED_V4 = (
    "enable_ml",
    "ml_learning_period",
    "retrain_period",
    "cross_sensor_window",
    "sensitivity",          # sigma-based — no longer meaningful
    "learning_period",      # PatternAnalyzer learning period — replaced by history_window_days
)

async def async_migrate_entry(hass, config_entry):
    if config_entry.version < 4:
        new_data = dict(config_entry.data)
        for key in _KEYS_REMOVED_V4:
            new_data.pop(key, None)
        new_data.setdefault(CONF_HISTORY_WINDOW_DAYS, DEFAULT_HISTORY_WINDOW_DAYS)
        new_data.setdefault(CONF_INACTIVITY_MULTIPLIER, DEFAULT_INACTIVITY_MULTIPLIER)
        new_data.setdefault(CONF_DRIFT_SENSITIVITY, SENSITIVITY_MEDIUM)
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=4)
    return True
```

**Note on sensitivity vs learning_period:** `CONF_SENSITIVITY` and `CONF_LEARNING_PERIOD` are referenced in the existing config flow but map to PatternAnalyzer. They can be removed since AcuteDetector uses inactivity_multiplier and DriftDetector uses drift_sensitivity. The old `min_notification_severity` field could be remapped to AlertSeverity or removed — this is Claude's discretion.

### Pattern 5: Config Flow New Options Schema

```python
# Source: config_flow.py existing SelectSelector and NumberSelector patterns
vol.Required(
    CONF_INACTIVITY_MULTIPLIER, default=current_inactivity_multiplier
): NumberSelector(NumberSelectorConfig(min=1.5, max=10.0, step=0.5, mode=NumberSelectorMode.BOX)),

vol.Required(
    CONF_DRIFT_SENSITIVITY, default=current_drift_sensitivity
): SelectSelector(SelectSelectorConfig(
    options=[
        {"value": "high", "label": "High (sensitive to small shifts)"},
        {"value": "medium", "label": "Medium (balanced) — recommended"},
        {"value": "low", "label": "Low (major shifts only)"},
    ],
    mode=SelectSelectorMode.DROPDOWN,
)),
```

### Pattern 6: Storage v4 Format — Add cusum_states

The DriftDetector maintains CUSUMState per entity. These must persist across restarts, otherwise drift detection resets on every HA restart.

```python
# CUSUMState.to_dict() / from_dict() already implemented in drift_detector.py
storage_data = {
    "routine_model": self._routine_model.to_dict(),
    "cusum_states": {
        entity_id: state.to_dict()
        for entity_id, state in self._drift_detector._states.items()
    },
    "coordinator": {
        # ... existing coordinator state keys unchanged ...
    },
}
```

On load:
```python
if "cusum_states" in stored_data:
    for entity_id, state_dict in stored_data["cusum_states"].items():
        self._drift_detector._states[entity_id] = CUSUMState.from_dict(state_dict)
```

### Pattern 7: routine_reset Service Registration

```python
# Source: __init__.py existing service registration pattern (holiday, snooze)
SERVICE_ROUTINE_RESET = "routine_reset"

async def handle_routine_reset(call: ServiceCall) -> None:
    entity_id = call.data["entity_id"]
    await coordinator.async_routine_reset(entity_id)

hass.services.async_register(
    DOMAIN,
    SERVICE_ROUTINE_RESET,
    handle_routine_reset,
    schema=vol.Schema({
        vol.Required("entity_id"): str,
    }),
)
```

In coordinator:
```python
async def async_routine_reset(self, entity_id: str) -> None:
    self._drift_detector.reset_entity(entity_id)
    _LOGGER.warning("routine_reset called for %s", entity_id)
    self.hass.bus.async_fire(f"{DOMAIN}_routine_reset", {"entity_id": entity_id})
    await self._save_data()
```

### Pattern 8: Suppression Logic Preservation

The current `_should_notify` signature uses `(entity_id: str, anomaly_type: str)`. AlertResult.alert_type is an `AlertType` enum (str subclass). The cooldown key becomes `(entity_id, alert_type.value)`.

```python
def _should_notify(self, alert: AlertResult) -> bool:
    key = (alert.entity_id, alert.alert_type.value)
    last = self._notification_cooldowns.get(key)
    if last is None:
        return True
    return (dt_util.now() - last).total_seconds() >= self._notification_cooldown * 60
```

Holiday mode and snooze gates remain at the top of `_async_update_data`:
```python
if self._holiday_mode or self.is_snoozed():
    # Still build safe sensor data, but skip detection + notifications
    return self._build_safe_defaults()
```

### Pattern 9: Notification Format for AlertResult

```python
# Source: AlertResult fields — explanation (human-readable), severity, alert_type, entity_id
async def _send_notification(self, alerts: list[AlertResult]) -> None:
    title = f"Behaviour Monitor: {len(alerts)} alert(s)"
    lines = [f"- [{a.severity.value.upper()}] {a.explanation}" for a in alerts]
    message = "\n".join(lines)

    await self.hass.services.async_call(
        "persistent_notification", "create",
        {"title": title, "message": message, "notification_id": f"{DOMAIN}_alert"},
    )
    for svc in self._notify_services:
        domain, service = svc.split(".", 1)
        await self.hass.services.async_call(domain, service, {"title": title, "message": message})
```

### Anti-Patterns to Avoid

- **Accessing `routine_model._entities` from outside coordinator**: Only the coordinator should access internals. Use `routine_model.get_or_create()` or `routine_model.record()` via the public API. Exception: loading cusum_states from storage.
- **Returning None from `_async_update_data`**: DataUpdateCoordinator sets `self.data = result` — if None, sensors break. Always return a dict even during holidays/snooze.
- **Mutating config_entry.data directly**: Use `hass.config_entries.async_update_entry()` — established in Phase 3.
- **Forgetting `await asyncio.sleep(0)` in bootstrap loops**: The per-entity stagger in bootstrap prevents blocking the event loop. Preserve it.
- **Tracking `last_seen` as datetime without timezone**: dt_util.now() returns tz-aware datetime. Store tz-aware datetimes in `_last_seen` dict.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Drift accumulation | Custom shift detection | DriftDetector.check() already built | Phase 4 complete |
| Inactivity thresholds | Custom interval math | AcuteDetector.check_inactivity() | Phase 4 complete |
| Alert data structure | Custom dicts | AlertResult + to_dict() | Consistent serialization, enum values |
| Config entry persistence | Custom file I/O | HA Store class | Already used in this coordinator |
| Notification dispatch | Direct HTTP calls | hass.services.async_call | Handles retries, logging |
| State change subscription | Polling | hass.bus.async_listen(EVENT_STATE_CHANGED) | Already used in coordinator |

---

## Common Pitfalls

### Pitfall 1: coordinator.data = None on first refresh
**What goes wrong:** If `_async_update_data` raises during bootstrap, DataUpdateCoordinator sets `self.data = None`. All 14 sensors then return None (which HA interprets as "unavailable").
**Why it happens:** Old coordinator had the same risk; the new one must be equally defensive.
**How to avoid:** Wrap `_async_update_data` body in try/except; always return a valid dict even on error. Use `_build_safe_defaults()` returning a dict of safe values for all 14 keys.
**Warning signs:** Sensor showing "unavailable" immediately after HA restart.

### Pitfall 2: `last_seen` dict missing on first run
**What goes wrong:** `check_inactivity` receives `last_seen=None`, which is handled correctly (returns None). But the coordinator also uses `last_seen` to populate the `last_activity` sensor key. If `_last_seen` is never initialised before `_async_update_data` runs, a KeyError occurs.
**How to avoid:** Initialise `self._last_seen: dict[str, datetime] = {}` in `__init__`. Populate from stored coordinator state on `async_setup`.

### Pitfall 3: CUSUMState not persisted — drift resets on restart
**What goes wrong:** DriftDetector._states is only in memory. On HA restart, all CUSUM accumulators reset to 0. A genuine multi-day drift trend appears to vanish.
**How to avoid:** Include `cusum_states` in storage v4 format (see Pattern 6 above). Load on async_setup.

### Pitfall 4: Config flow VERSION not bumped when adding new keys
**What goes wrong:** HA will not call `async_migrate_entry` unless `CONFIG_VERSION` in the config flow class is incremented. v1.0 users won't get the new defaults.
**How to avoid:** Bump `BehaviourMonitorConfigFlow.VERSION = 4` to match the migration target. Also bump `STORAGE_VERSION` in const.py if storage format changes.
**Warning signs:** New config keys missing from existing entries; coordinator throws KeyError on `.get()` calls.

### Pitfall 5: Sensor lambda references `coord.analyzer` — attribute deleted in new coordinator
**What goes wrong:** sensor.py line 83 reads `coord.analyzer.is_learning_complete()` in `extra_attrs_fn` for the `baseline_confidence` sensor. Deleting `self._analyzer` without updating sensor.py causes AttributeError.
**How to avoid:** Add a `learning_complete` property to the new coordinator that delegates to `routine_model.learning_status() == "ready"`. Or update the `extra_attrs_fn` lambda to use coordinator.data keys instead of calling coordinator methods.
**Warning signs:** AttributeError in sensor entity log on refresh.

### Pitfall 6: Stale ML imports break the module
**What goes wrong:** coordinator.py currently imports `from .ml_analyzer import ML_AVAILABLE, MLAnomalyResult, MLPatternAnalyzer, StateChangeEvent`. If ml_analyzer.py is deleted before coordinator.py is rewritten, the module fails to import, taking down the entire integration.
**How to avoid:** Rewrite coordinator.py completely before deleting ml_analyzer.py and analyzer.py.

### Pitfall 7: welfare_status sensor needs a dict with specific keys
**What goes wrong:** sensor.py's welfare_status `value_fn` reads `data.get("welfare", {}).get("status", "unknown")` and `extra_attrs_fn` reads `reasons`, `summary`, `recommendation`, `entity_count_by_status`. If the new `welfare` dict is missing any of these keys, sensors show unexpected defaults.
**How to avoid:** Always produce a `welfare` dict with all expected keys, even when empty:
```python
{"status": "ok", "reasons": [], "summary": "", "recommendation": "", "entity_count_by_status": {}}
```

### Pitfall 8: daily_count must reset at midnight
**What goes wrong:** The current `daily_count` sensor has `state_class=SensorStateClass.TOTAL_INCREASING`. If the coordinator increments a global counter without resetting at midnight, the history graph will never reset.
**How to avoid:** Track `_today_count: int` and `_today_date: date` in the coordinator. Reset `_today_count` when `dt_util.now().date() != self._today_date`.

---

## Code Examples

### Welfare Derivation from AlertSeverity (Claude's Discretion — Recommended Approach)

```python
# Map AlertResult severity to welfare status string
# This replaces analyzer.get_welfare_status()
def _derive_welfare(self, active_alerts: list[AlertResult]) -> dict:
    if not active_alerts:
        return {"status": "ok", "reasons": [], "summary": "No active alerts",
                "recommendation": "", "entity_count_by_status": {}}

    max_severity = max(
        (AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH).index(a.severity)
        for a in active_alerts
    )

    status_map = {0: "check_recommended", 1: "concern", 2: "alert"}
    status = status_map.get(max_severity, "ok")
    reasons = [a.explanation for a in active_alerts]
    return {
        "status": status,
        "reasons": reasons,
        "summary": f"{len(active_alerts)} active alert(s)",
        "recommendation": "Check on the monitored person" if status == "alert" else "",
        "entity_count_by_status": {},  # simplified; can be enriched
    }
```

### Safe Defaults Dict

```python
# Always return a valid dict — never None
def _build_safe_defaults(self) -> dict[str, Any]:
    return {
        "last_activity": None,
        "activity_score": 0.0,
        "anomaly_detected": False,
        "anomalies": [],
        "confidence": 0.0,
        "daily_count": 0,
        "welfare": {"status": "unknown", "reasons": [], "summary": "",
                    "recommendation": "", "entity_count_by_status": {}},
        "routine": {"progress_percent": 0, "expected_by_now": 0, "actual_today": 0,
                    "expected_full_day": 0, "status": "unknown", "summary": ""},
        "activity_context": {"time_since_formatted": "Unknown", "time_since_seconds": None,
                             "typical_interval_seconds": None, "typical_interval_formatted": "",
                             "concern_level": 0, "status": "unknown", "context": ""},
        "entity_status": [],
        "stat_training": {"complete": False, "formatted": "Learning...",
                          "days_remaining": None, "days_elapsed": None,
                          "total_days": None, "first_observation": None},
        "ml_status": {"enabled": False},
        "cross_sensor_patterns": [],
        "last_notification": {"timestamp": None, "type": None},
        "holiday_mode": self._holiday_mode,
        "snooze_active": self.is_snoozed(),
        "snooze_until": self._snooze_until.isoformat() if self._snooze_until else None,
        "ml_status_stub": "Removed in v1.1",
        "ml_training_stub": "N/A",
        "cross_sensor_stub": 0,
        "learning_status": self._routine_model.learning_status(),
        "baseline_confidence": round(self._routine_model.overall_confidence() * 100, 1),
    }
```

### min_notification_severity Adaptation (Claude's Discretion — Recommended)

The existing `CONF_MIN_NOTIFICATION_SEVERITY` gate used SEVERITY_THRESHOLDS (z-score values). AlertSeverity now has three tiers: LOW, MEDIUM, HIGH. Recommended mapping:

```python
# Map old string values to AlertSeverity for the gate
_SEVERITY_GATE = {
    "minor": AlertSeverity.LOW,
    "moderate": AlertSeverity.LOW,      # minor + moderate both map to LOW gate
    "significant": AlertSeverity.MEDIUM,  # recommended default
    "critical": AlertSeverity.HIGH,
}

def _meets_severity_gate(self, alert: AlertResult) -> bool:
    gate = _SEVERITY_GATE.get(self._min_notification_severity, AlertSeverity.MEDIUM)
    order = [AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH]
    return order.index(alert.severity) >= order.index(gate)
```

---

## State of the Art

| Old Approach | Current (v1.1) Approach | Impact |
|--------------|------------------------|--------|
| PatternAnalyzer (z-score, 672 buckets) | RoutineModel (168 HOD×DOW slots, event deques) | Bootstraps from recorder, O(1) per-slot checks |
| MLPatternAnalyzer (River HalfSpaceTrees) | DriftDetector (CUSUM, pure Python stdlib) | No external dependency, deterministic |
| Dual-analyzer coordinator (~1200 lines) | Single-engine coordinator (target ~300 lines) | Dramatically simpler, testable |
| Config: sensitivity (sigma) + learning_period | Config: inactivity_multiplier + drift_sensitivity | Semantically meaningful to users |
| Storage v3: routine_model + coordinator | Storage v4: routine_model + cusum_states + coordinator | Drift accumulation survives restart |

**Deprecated/removed:**
- `analyzer.py`: PatternAnalyzer, AnomalyResult — replaced by new engines
- `ml_analyzer.py`: MLPatternAnalyzer, MLAnomalyResult, StateChangeEvent, ML_AVAILABLE — removed
- `SENSITIVITY_THRESHOLDS` in const.py: z-score sigma values — obsolete
- `ML_CONTAMINATION`, `ML_EMA_ALPHA`, `MIN_SAMPLES_FOR_ML`, `MIN_CROSS_SENSOR_OCCURRENCES`, `MAX_VARIANCE_MULTIPLIER`, `MIN_BUCKET_OBSERVATIONS` in const.py — all ML/z-score related, can be removed

---

## Open Questions

1. **sensor.py `baseline_confidence` extra_attrs_fn calls `coord.analyzer.is_learning_complete()`**
   - What we know: Line 83 of sensor.py passes `coord.analyzer` directly to `extra_attrs_fn`
   - What's unclear: Should `is_learning_complete` become a coordinator property, or should the lambda be updated to read from coordinator.data?
   - Recommendation: Add `@property def learning_complete(self) -> bool: return self._routine_model.learning_status() == "ready"` to the new coordinator. Less sensor.py churn.

2. **routine_progress sensor keys**
   - What we know: sensor.py reads `data.get("routine", {}).get("progress_percent", 0)` and `expected_by_now`, `actual_today`, `expected_full_day`, `status`, `summary`
   - What's unclear: The RoutineModel doesn't have a `get_routine_progress()` equivalent — PatternAnalyzer had this, the new engines don't
   - Recommendation: Compute it in `_build_sensor_data` using routine_model data: actual_today = count of today's events, expected_by_now = sum of expected events across entities for current time-of-day

3. **`stat_training` sensor keys**
   - What we know: sensor.py reads `days_remaining`, `days_elapsed`, `total_days`, `first_observation`, `complete`, `formatted`
   - What's unclear: RoutineModel tracks `first_observation` per EntityRoutine but not globally
   - Recommendation: Derive global `first_observation` from the oldest `entity.first_observation` across all entities; derive `days_elapsed` from that; `complete` = `learning_status() == "ready"`

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, see `tests/`) |
| Config file | `setup.cfg` or `pytest.ini` if present; HA mocks via `conftest.py` |
| Quick run command | `venv/bin/python -m pytest tests/test_coordinator.py tests/test_config_flow.py tests/test_init.py -x -q` |
| Full suite command | `make test` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-03a | Config flow shows inactivity_multiplier field | unit | `venv/bin/python -m pytest tests/test_config_flow.py -k "inactivity_multiplier" -x` | ❌ Wave 0 |
| INFRA-03b | Config flow shows drift_sensitivity field | unit | `venv/bin/python -m pytest tests/test_config_flow.py -k "drift_sensitivity" -x` | ❌ Wave 0 |
| INFRA-03c | Existing v1.0/v3 entries migrate to v4 without error | unit | `venv/bin/python -m pytest tests/test_init.py -k "migrate" -x` | ❌ Wave 0 |
| INFRA-03d (implied) | coordinator.data is never None on first refresh | unit | `venv/bin/python -m pytest tests/test_coordinator.py -k "first_refresh or safe_defaults" -x` | ❌ Wave 0 |
| INFRA-03e (implied) | All 14 sensor entity IDs populate without error | unit | `venv/bin/python -m pytest tests/test_sensor.py -x` | ✅ exists, needs update |
| INFRA-03f (implied) | AcuteDetector + DriftDetector results drive notifications | unit | `venv/bin/python -m pytest tests/test_coordinator.py -k "notification" -x` | ❌ Wave 0 |
| INFRA-03g (implied) | routine_reset service clears DriftDetector state | unit | `venv/bin/python -m pytest tests/test_coordinator.py -k "routine_reset" -x` | ❌ Wave 0 |
| INFRA-03h (implied) | Suppression logic (holiday, snooze, cooldown) preserved | unit | `venv/bin/python -m pytest tests/test_coordinator.py -k "holiday or snooze or cooldown" -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `venv/bin/python -m pytest tests/test_coordinator.py tests/test_config_flow.py -x -q`
- **Per wave merge:** `make test`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_coordinator.py` — rewrite for new coordinator (old tests reference `coord.analyzer`, `coord.ml_analyzer`, ML_AVAILABLE — all deleted)
- [ ] `tests/test_config_flow.py` — update for removed ML options and new inactivity_multiplier / drift_sensitivity options
- [ ] `tests/test_init.py` — add test for v3→v4 migration with new keys
- [ ] `conftest.py` `mock_config_entry` — update fixture to remove ML keys, add inactivity_multiplier and drift_sensitivity

Note: `tests/test_sensor.py` exists and covers the 14 sensors, but its `mock_coordinator` fixture will need updating to supply the new coordinator.data structure.

---

## Sources

### Primary (HIGH confidence)

- Direct inspection of `/custom_components/behaviour_monitor/coordinator.py` (1,213 lines — full read)
- Direct inspection of `/custom_components/behaviour_monitor/sensor.py` — all 14 sensor descriptions and their key dependencies
- Direct inspection of `/custom_components/behaviour_monitor/config_flow.py` — full options flow
- Direct inspection of `/custom_components/behaviour_monitor/const.py` — all constants including new v1.1 detection constants
- Direct inspection of `/custom_components/behaviour_monitor/__init__.py` — service registration patterns, migration pattern
- Direct inspection of `/custom_components/behaviour_monitor/routine_model.py` — RoutineModel public API
- Direct inspection of `/custom_components/behaviour_monitor/acute_detector.py` — AcuteDetector public API
- Direct inspection of `/custom_components/behaviour_monitor/drift_detector.py` — DriftDetector + CUSUMState public API
- Direct inspection of `/custom_components/behaviour_monitor/alert_result.py` — AlertResult, AlertType, AlertSeverity
- Direct inspection of `/tests/conftest.py` — mock infrastructure for test patterns

### Secondary (MEDIUM confidence)

- HA DataUpdateCoordinator pattern: consistent with existing coordinator.py usage (inherited from HA codebase conventions visible in test mocks)
- HA config entry migration: dict copy + setdefault pattern established in Phase 3 `async_migrate_entry` (this repo)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all engines fully implemented, APIs verified by source inspection
- Architecture (coordinator structure): HIGH — current code fully read, 14 sensor keys mapped
- Config flow changes: HIGH — current flow fully read, migration pattern established
- Pitfalls: HIGH — derived from direct sensor.py dependency analysis and coordinator code inspection
- Sensor data mapping: HIGH for stable keys; MEDIUM for welfare/routine/activity_context derivation (computation logic is Claude's discretion)

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable domain; HA coordinator/config_flow APIs are stable; only code changes to this repo would invalidate)
