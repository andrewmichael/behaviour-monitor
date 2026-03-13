# Phase 1: Coordinator Suppression - Research

**Researched:** 2026-03-13
**Domain:** Home Assistant coordinator notification logic (Python, async, in-memory state management)
**Confidence:** HIGH — all findings are derived from direct code reading of the actual codebase

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Per-entity cooldown (Entity A's cooldown does not block Entity B's alerts)
- Default cooldown: 30 minutes
- Cooldown is configurable via config flow options UI (new option field)
- Cooldown resets when the anomaly clears (entity returns to normal) — if entity goes anomalous again after clearing, treat as new event
- Configurable minimum severity level for push notifications via config flow options UI
- Default minimum severity: significant (3.5σ)
- Anomalies below the severity gate update sensor state but do NOT trigger push notifications
- Dedup key: entity_id + anomaly_type — different anomaly types on the same entity are separate alerts
- Ongoing anomalies (same entity+type persisting across update cycles) are suppressed until cooldown expires
- When both statistical and ML paths flag the same entity in the same cycle, merge into a single notification
- Debounce applies in both directions (escalation and de-escalation)
- Welfare debounce cycle count within 3-5 cycle range

### Claude's Discretion
- Cross-path notification merge implementation details
- Welfare debounce cycle count (within 3-5 cycle range)
- Exact config flow UI labels and descriptions for new options
- How to persist per-entity cooldown state (in-memory dict vs coordinator store)

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| NOTIF-01 | Notification cooldown per entity prevents re-alerting the same entity within a configurable time window | Per-entity dict keyed by entity_id, storing last notification datetime; check elapsed time against configurable threshold before calling `_send_notification()` |
| NOTIF-02 | Anomaly deduplication prevents re-alerting for the same ongoing anomaly type on the same entity | Extend cooldown dict to key on `(entity_id, anomaly_type)` tuples; ongoing = same key present and cooldown not yet expired |
| NOTIF-03 | Severity minimum gate only sends notifications for anomalies above a minimum severity threshold | `SEVERITY_THRESHOLDS` already maps severity names to z-scores; filter `stat_anomalies` list before calling `_send_notification()` |
| WELF-01 | Welfare status hysteresis/debounce prevents rapid flapping between normal/concern/alert states | `_last_welfare_status` already exists; add `_welfare_consecutive_cycles: int` counter and `_welfare_pending_status: str` to count confirmations before committing |
</phase_requirements>

---

## Summary

Phase 1 is a pure logic addition to `coordinator.py` — it introduces no new files and touches detection algorithms in neither `analyzer.py` nor `ml_analyzer.py`. The existing codebase already has the primitives required: a severity taxonomy in `const.py` (`SEVERITY_THRESHOLDS`), a welfare status tracker (`_last_welfare_status`), and a global notification timestamp (`_last_notification_time`). The task is to upgrade these partial primitives into a complete suppression layer.

Four suppression mechanisms must be wired in at the notification dispatch point in `_async_update_data()` (lines 540–573 of `coordinator.py`): (1) severity gate — filter anomalies list by z_score before dispatch, (2) per-entity cooldown with deduplication — track last notification time per `(entity_id, anomaly_type)` key, (3) cross-path merge — combine stat and ML anomalies for the same entity into a single call, and (4) welfare debounce — require N consecutive cycles at the new status before calling `_send_welfare_notification()`.

All new state (cooldown dict, welfare counter, pending welfare status) should be in-memory on the coordinator. The cooldown dict should be persisted via the existing `_save_data()` / `async_setup()` storage path so it survives HA restarts. Two new constants and two new config flow fields are required. No sensor output keys change — anomalies below the gate still appear in the `anomalies` list returned from `_async_update_data()`; they are only suppressed at the notification dispatch.

**Primary recommendation:** Add the suppression layer as a private helper method `_should_notify(entity_id, anomaly_type) -> bool` called from `_async_update_data()`, keeping the gate, cooldown, and dedup logic in one testable place.

---

## Standard Stack

### Core (already in use — no new dependencies)
| Component | Version/Location | Purpose | Notes |
|-----------|-----------------|---------|-------|
| `coordinator.py` | existing | Notification dispatch | All changes land here |
| `const.py` | existing | Constants and defaults | Add 2 new CONF_ / DEFAULT_ pairs |
| `config_flow.py` | existing | Options UI | Add 2 new fields to OptionsFlow |
| `SEVERITY_THRESHOLDS` | `const.py` line 74 | Maps severity names to z-score thresholds | Already maps `significant -> 3.5` |
| `dt_util.now()` | HA helper, already imported | Timezone-aware "now" | Use for cooldown arithmetic |

### No New Dependencies
This phase requires zero new Python packages. All logic uses stdlib `datetime`, `timedelta`, and existing HA patterns.

---

## Architecture Patterns

### Recommended State Layout (new fields on coordinator)

```python
# In __init__:
self._notification_cooldowns: dict[tuple[str, str], datetime] = {}
# key = (entity_id, anomaly_type), value = last notification time

self._welfare_consecutive_cycles: int = 0
self._welfare_pending_status: str | None = None
# tracks candidate new welfare status before it's confirmed
```

### Pattern 1: Severity Gate (NOTIF-03)

**What:** Filter the anomaly list to only those at or above the configured minimum severity before calling `_send_notification()`.

**Where it inserts:** Replace the bare `if stat_anomalies:` check at line 560 of `coordinator.py`.

**How severity comparison works:** `SEVERITY_THRESHOLDS` maps name to z-score float. The `AnomalyResult.severity` field is already a string (`"minor"`, `"moderate"`, `"significant"`, `"critical"`). Compare z_score against the configured threshold directly — this avoids any ordering-by-name fragility.

```python
# Source: const.py lines 74-79 (direct read)
SEVERITY_THRESHOLDS: Final = {
    SEVERITY_MINOR: 1.5,
    SEVERITY_MODERATE: 2.5,
    SEVERITY_SIGNIFICANT: 3.5,
    SEVERITY_CRITICAL: 4.5,
}

# Gate filter (insert before _send_notification call):
min_severity_threshold = SEVERITY_THRESHOLDS.get(
    self._min_notification_severity, 3.5
)
notifiable_anomalies = [
    a for a in stat_anomalies
    if a.z_score >= min_severity_threshold
]
# notifiable_anomalies sent to _send_notification()
# stat_anomalies (unfiltered) still goes into the returned data dict
```

**Sensor state is unaffected** because `stat_anomalies` flows unmodified into the `return {..., "anomalies": [...]}` dict at line 598. Only the notification call uses the filtered list.

### Pattern 2: Per-Entity Cooldown + Deduplication (NOTIF-01, NOTIF-02)

**What:** Track last notification time per `(entity_id, anomaly_type)` key. Suppress notification if key is present and cooldown has not expired.

**Cooldown reset on clear:** Each update cycle, remove entries from `_notification_cooldowns` where the entity_id is no longer in the current anomaly list. This means clearing = eligibility reset.

```python
# Source: coordinator.py _async_update_data pattern (direct read)
cooldown_seconds = self._notification_cooldown * 60  # stored in minutes
now = dt_util.now()

def _within_cooldown(entity_id: str, anomaly_type: str) -> bool:
    key = (entity_id, anomaly_type)
    last = self._notification_cooldowns.get(key)
    if last is None:
        return False
    return (now - last).total_seconds() < cooldown_seconds

def _record_notified(entity_id: str, anomaly_type: str) -> None:
    self._notification_cooldowns[(entity_id, anomaly_type)] = now

# Filter to only anomalies not in cooldown:
notifiable = [
    a for a in notifiable_after_gate
    if not _within_cooldown(a.entity_id, a.anomaly_type)
]
# After sending, record each notified anomaly:
for a in notifiable:
    _record_notified(a.entity_id, a.anomaly_type)

# Clear cooldowns for entities that are no longer anomalous (reset on clear):
active_keys = {(a.entity_id, a.anomaly_type) for a in stat_anomalies}
self._notification_cooldowns = {
    k: v for k, v in self._notification_cooldowns.items()
    if k in active_keys
}
```

### Pattern 3: Cross-Path Merge (NOTIF-01 + dedup across stat/ML)

**What:** When stat and ML both flag the same entity_id in the same cycle, suppress the ML notification for that entity and include a merged note in the stat notification (or simply skip the ML call for matched entities).

**Simplest correct approach:** Build a set of entity_ids that were already notified via stat path. Skip ML anomalies whose entity_id is in that set.

```python
# After sending stat notifications:
stat_notified_entities = {a.entity_id for a in notifiable_stat}

# Before sending ML notifications:
ml_to_notify = [
    a for a in notifiable_ml
    if a.entity_id not in stat_notified_entities
]
if ml_to_notify:
    await self._send_ml_notification(ml_to_notify)
```

**Note:** ML anomalies can have `entity_id = None` (cross-sensor anomalies). These are never suppressed by the entity-based dedup — they pass through unconditionally.

### Pattern 4: Welfare Debounce (WELF-01)

**What:** Require N consecutive update cycles showing the same new welfare status before firing `_send_welfare_notification()`.

**Cycle count decision:** Use N=3 (3 minutes at the 60-second update interval). This satisfies the "3-5 cycle" constraint and is the lowest value that filters single-cycle noise while keeping alert latency under 5 minutes.

**Both-directions debounce:** The pending/counter mechanism applies for escalation (ok → concern) and de-escalation (concern → ok) equally.

```python
# Source: coordinator.py lines 569-573 (direct read), extended:
welfare_status = self._analyzer.get_welfare_status()
current_welfare = welfare_status.get("status", "ok")

if current_welfare != self._last_welfare_status:
    # Status changed — start or continue counting
    if current_welfare == self._welfare_pending_status:
        self._welfare_consecutive_cycles += 1
    else:
        # New candidate status, reset counter
        self._welfare_pending_status = current_welfare
        self._welfare_consecutive_cycles = 1

    if self._welfare_consecutive_cycles >= WELFARE_DEBOUNCE_CYCLES:
        await self._send_welfare_notification(welfare_status)
        self._last_welfare_status = current_welfare
        self._welfare_consecutive_cycles = 0
        self._welfare_pending_status = None
else:
    # Status stable — reset any pending debounce
    self._welfare_consecutive_cycles = 0
    self._welfare_pending_status = None
```

**Constant to add to `const.py`:**

```python
WELFARE_DEBOUNCE_CYCLES: Final = 3  # consecutive cycles before welfare notification fires
```

### Recommended Project Structure (unchanged)

```
custom_components/behaviour_monitor/
├── __init__.py           # unchanged
├── sensor.py             # unchanged
├── coordinator.py        # PRIMARY CHANGE: suppression layer in _async_update_data()
├── analyzer.py           # unchanged
├── ml_analyzer.py        # unchanged
├── config_flow.py        # ADD: 2 new fields in OptionsFlow (and initial ConfigFlow)
└── const.py              # ADD: CONF_NOTIFICATION_COOLDOWN, CONF_MIN_NOTIFICATION_SEVERITY,
                          #       DEFAULT_NOTIFICATION_COOLDOWN, DEFAULT_MIN_NOTIFICATION_SEVERITY,
                          #       WELFARE_DEBOUNCE_CYCLES
```

### Anti-Patterns to Avoid

- **Filtering anomalies from the return dict:** Sensor state must reflect all detected anomalies regardless of notification gate. Only filter the list passed to `_send_notification()`.
- **Global (not per-entity) cooldown:** The existing `_last_notification_time` is global. Do NOT reuse it for cooldown checks — it lacks the entity+type granularity. Leave it as-is for the `last_notification` sensor attribute.
- **Blocking ML cross-sensor anomalies from dedup sweep:** `entity_id` can be `None` for cross-sensor anomalies (line 610 of coordinator: `"entity_id": a.entity_id or "cross-sensor"`). The merge logic must handle `None` cleanly.
- **Storing cooldown dict in ML store:** Keep it in the stat store (`self._store`) inside the existing `coordinator` sub-dict of the storage blob. ML store is for ML model state only.
- **Using string ordering for severity comparison:** `"minor" < "significant"` works alphabetically by accident. Use `SEVERITY_THRESHOLDS` z-score floats for the comparison — explicit and correct.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timezone-aware timestamps | Custom `datetime.now()` | `dt_util.now()` (already imported) | HA's dt_util handles DST transitions; bare `datetime.now()` is naive (no timezone) |
| Severity ranking | Ordered list comparison | `SEVERITY_THRESHOLDS[severity_name]` float comparison | Dictionary already exists; float comparison is unambiguous |
| Config validation | Custom validator | `vol.Optional()` / `vol.Required()` with built-in type coercion in `config_flow.py` | Already the project pattern |
| Persisting new state | New storage file | Extend existing `coordinator` sub-dict in `_save_data()` | Storage infrastructure already handles versioning and async |

---

## Common Pitfalls

### Pitfall 1: Cooldown dict key collision between stat and ML paths
**What goes wrong:** Stat uses `(entity_id, anomaly_type)` tuples; ML anomaly types like `"isolation_forest"` or `"cross_sensor_pattern"` are different strings from stat types like `"unusual_activity"`. If you use the same dict for both, a stat cooldown for `("sensor.door", "unusual_activity")` will never block an ML cooldown for `("sensor.door", "isolation_forest")`.
**Why it happens:** They look like they should share state but have distinct type namespaces.
**How to avoid:** Decide upfront: (a) use one dict for both paths (no collision since anomaly_type differs), or (b) track stat and ML separately. Option (a) is simpler and correct — different anomaly_types mean different keys, so they don't interfere.
**Warning signs:** Tests show ML notifications firing immediately after stat notifications for the same entity.

### Pitfall 2: Welfare debounce state not reset when status stabilizes
**What goes wrong:** `_welfare_consecutive_cycles` keeps incrementing even when the status matches `_last_welfare_status`, causing a spurious notification when the counter wraps around or an internal logic error.
**Why it happens:** Forgetting the `else` branch that resets the counter when status is stable.
**How to avoid:** The counter and pending status must reset whenever `current_welfare == self._last_welfare_status` (status is stable).
**Warning signs:** Welfare notification fires N cycles after the status has already been reported.

### Pitfall 3: Config entry data vs options
**What goes wrong:** New options set in `OptionsFlow` may not be read in the coordinator because the coordinator reads from `entry.data`, but `OptionsFlow.async_create_entry` writes to `entry.options` by default.
**Why it happens:** HA has two storage locations for config entries. This project uses a non-standard pattern: `OptionsFlow` calls `async_update_entry(data=updated_data)` (line 219 of config_flow.py) to write back to `entry.data`, then returns `async_create_entry(data={})`.
**How to avoid:** Follow the existing pattern exactly. New cooldown and severity fields must be written into `entry.data` the same way current options are. Read them from `entry.data` in the coordinator's `__init__`.
**Warning signs:** Options saved in UI but coordinator still uses defaults.

### Pitfall 4: Cooldown dict lost on HA restart
**What goes wrong:** If the cooldown dict is kept only in memory, a restart clears all per-entity cooldowns and allows immediate re-notification for ongoing anomalies.
**Why it happens:** HA restarts are common (updates, reboots). In-memory only state is ephemeral.
**How to avoid:** Serialize `_notification_cooldowns` into the `coordinator` sub-dict in `_save_data()`. Deserialize in `async_setup()` alongside the existing `last_notification_time` restore. Datetime values must be stored as ISO format strings.
**Warning signs:** User receives duplicate notifications after HA restart.

### Pitfall 5: ML anomaly `entity_id` is None for cross-sensor detections
**What goes wrong:** Using `a.entity_id` as a dict key crashes with `TypeError: unhashable type` or silently groups all cross-sensor anomalies under `None`.
**Why it happens:** `MLAnomalyResult.entity_id` is `Optional[str]` — cross-sensor anomalies set it to `None`.
**How to avoid:** In the merge/dedup logic, only match by entity_id when `entity_id is not None`. Let `None` entity_id anomalies pass through the dedup unchanged.
**Warning signs:** `KeyError` or `TypeError` on ML path when cross-sensor patterns are present.

---

## Code Examples

### Adding new constants to const.py

```python
# Source: const.py lines 8-17 (existing pattern)
CONF_NOTIFICATION_COOLDOWN: Final = "notification_cooldown"
CONF_MIN_NOTIFICATION_SEVERITY: Final = "min_notification_severity"

DEFAULT_NOTIFICATION_COOLDOWN: Final = 30  # minutes
DEFAULT_MIN_NOTIFICATION_SEVERITY: Final = SEVERITY_SIGNIFICANT  # "significant"

WELFARE_DEBOUNCE_CYCLES: Final = 3  # consecutive update cycles (~3 minutes)
```

### Adding fields to config_flow.py OptionsFlow

```python
# Source: config_flow.py lines 254-330 (existing vol.Schema pattern)
vol.Optional(
    CONF_NOTIFICATION_COOLDOWN,
    default=current_cooldown,
): NumberSelector(
    NumberSelectorConfig(
        min=5,
        max=240,
        step=5,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="minutes",
    )
),
vol.Optional(
    CONF_MIN_NOTIFICATION_SEVERITY,
    default=current_min_severity,
): SelectSelector(
    SelectSelectorConfig(
        options=[
            {"value": SEVERITY_MINOR, "label": "Minor (1.5σ+)"},
            {"value": SEVERITY_MODERATE, "label": "Moderate (2.5σ+)"},
            {"value": SEVERITY_SIGNIFICANT, "label": "Significant (3.5σ+) — recommended"},
            {"value": SEVERITY_CRITICAL, "label": "Critical (4.5σ+) — very quiet"},
        ],
        mode=SelectSelectorMode.DROPDOWN,
    )
),
```

### Loading new config values in coordinator __init__

```python
# Source: coordinator.py lines 79-81 (existing pattern)
self._notification_cooldown: int = int(
    entry.data.get(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)
)
self._min_notification_severity: str = entry.data.get(
    CONF_MIN_NOTIFICATION_SEVERITY, DEFAULT_MIN_NOTIFICATION_SEVERITY
)
```

### Persisting cooldown dict in _save_data()

```python
# Source: coordinator.py lines 320-338 (existing _save_data pattern)
"coordinator": {
    # ... existing fields ...
    "notification_cooldowns": {
        f"{k[0]}|{k[1]}": v.isoformat()
        for k, v in self._notification_cooldowns.items()
    },
    "welfare_consecutive_cycles": self._welfare_consecutive_cycles,
    "welfare_pending_status": self._welfare_pending_status,
},
```

### Restoring cooldown dict in async_setup()

```python
# Source: coordinator.py lines 212-220 (existing restore pattern)
raw_cooldowns = coordinator_state.get("notification_cooldowns", {})
for key_str, dt_str in raw_cooldowns.items():
    parts = key_str.split("|", 1)
    if len(parts) == 2:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        self._notification_cooldowns[(parts[0], parts[1])] = dt

self._welfare_consecutive_cycles = coordinator_state.get(
    "welfare_consecutive_cycles", 0
)
self._welfare_pending_status = coordinator_state.get("welfare_pending_status")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global `_last_notification_time` (one timestamp for all notifications) | Per-entity `_notification_cooldowns` dict keyed by `(entity_id, anomaly_type)` | Phase 1 | Entity A anomaly no longer resets Entity B's cooldown window |
| Any status change fires welfare notification immediately | N-cycle consecutive confirmation required before welfare notification | Phase 1 | Eliminates single-cycle welfare status flapping |
| All anomalies above detection threshold trigger notifications | Only anomalies above configurable severity gate trigger notifications | Phase 1 | Default "significant" gate silences moderate/minor detections |

---

## Open Questions

1. **Should the cooldown dict be pruned of stale entries at each update cycle?**
   - What we know: entries for entities no longer anomalous are cleared by the "reset on clear" logic. But entries could pile up if many entities cycle through anomaly states. In practice, monitored entity counts are small (typically 5-20) so memory is not a concern.
   - What's unclear: whether the active_keys filter should also prune expired-but-kept entries.
   - Recommendation: Apply the `active_keys` filter — clear all cooldown entries whose entity is not currently anomalous. This is the "reset on clear" behavior the user requested.

2. **Should the options flow also have these new fields in the initial ConfigFlow (async_step_user)?**
   - What we know: All current fields appear in both `async_step_user` and `OptionsFlow.async_step_init`. The CONTEXT.md says "new option field" suggesting OptionsFlow only.
   - Recommendation: Add to both flows for consistency with the existing pattern, using defaults in the initial flow.

3. **Should `_send_notification()` be refactored to accept already-filtered lists, or should filtering happen at the call site?**
   - Recommendation: Filter at the call site in `_async_update_data()` — keeps `_send_notification()` a pure dispatch function and makes the suppression logic testable in isolation without calling the full notification method.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (with pytest-asyncio) |
| Config file | none detected — pytest invoked directly |
| Quick run command | `venv/bin/python -m pytest tests/test_coordinator.py -v` |
| Full suite command | `venv/bin/python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NOTIF-01 | Entity A cooldown does not block Entity B | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cooldown_per_entity -x` | ❌ Wave 0 |
| NOTIF-01 | Second notification within cooldown window is suppressed | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cooldown_suppresses_repeat -x` | ❌ Wave 0 |
| NOTIF-01 | Notification fires again after cooldown expires | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cooldown_expires -x` | ❌ Wave 0 |
| NOTIF-01 | Cooldown resets when entity clears (anomaly resolves) | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cooldown_resets_on_clear -x` | ❌ Wave 0 |
| NOTIF-02 | Same entity + different anomaly_type = separate cooldown | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_dedup_different_types_separate -x` | ❌ Wave 0 |
| NOTIF-02 | Stat+ML same entity in same cycle = single notification | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cross_path_dedup -x` | ❌ Wave 0 |
| NOTIF-03 | Anomaly below severity gate does not fire notification | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_severity_gate_suppresses -x` | ❌ Wave 0 |
| NOTIF-03 | Anomaly below severity gate still appears in sensor data | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_severity_gate_sensor_state_unaffected -x` | ❌ Wave 0 |
| NOTIF-03 | Anomaly at or above severity gate fires notification | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_severity_gate_passes_above_threshold -x` | ❌ Wave 0 |
| WELF-01 | Welfare does not notify on first cycle of new status | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_welfare_debounce_no_notify_first_cycle -x` | ❌ Wave 0 |
| WELF-01 | Welfare notifies after N consecutive cycles | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_welfare_debounce_notifies_after_n_cycles -x` | ❌ Wave 0 |
| WELF-01 | Welfare debounce resets if status reverts before N cycles | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_welfare_debounce_resets_on_revert -x` | ❌ Wave 0 |
| WELF-01 | Debounce applies to de-escalation (concern → ok) | unit | `venv/bin/python -m pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_welfare_debounce_deescalation -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `venv/bin/python -m pytest tests/test_coordinator.py -v`
- **Per wave merge:** `venv/bin/python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] All 13 test methods above — add to existing `tests/test_coordinator.py` inside `TestBehaviourMonitorCoordinator`
- [ ] No new test files needed — existing `conftest.py` fixtures (`mock_hass`, `mock_config_entry`, `coordinator`) are sufficient
- [ ] No framework install needed — pytest already in `requirements-dev.txt`

---

## Sources

### Primary (HIGH confidence)
- Direct read of `custom_components/behaviour_monitor/coordinator.py` — notification dispatch at lines 540-573, existing state fields at lines 69-76, `_save_data()` at lines 317-338, `async_setup()` restore at lines 206-245
- Direct read of `custom_components/behaviour_monitor/const.py` — `SEVERITY_THRESHOLDS` at lines 74-79, all `CONF_` and `DEFAULT_` constants at lines 8-46
- Direct read of `custom_components/behaviour_monitor/config_flow.py` — OptionsFlow pattern at lines 188-340, how options merge into entry.data at lines 206-222
- Direct read of `tests/test_coordinator.py` — existing test class structure, fixture usage
- Direct read of `tests/conftest.py` — mock infrastructure, `MockStore`, `mock_config_entry` data shape

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions — implementation choices (per-entity cooldown, N=3-5 welfare cycles, severity=significant default) cross-referenced with codebase
- REQUIREMENTS.md — requirement text for NOTIF-01, NOTIF-02, NOTIF-03, WELF-01

### Tertiary (LOW confidence)
- None — all findings verified from codebase source

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all files read directly, no inference required
- Architecture: HIGH — insertion points identified at exact line numbers, data structures from actual code
- Pitfalls: HIGH — derived from actual code behavior (e.g., None entity_id from line 610, existing global timestamp from line 73)
- Test map: HIGH — test class structure read directly from test_coordinator.py

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable codebase, no external dependencies changing)
