# Home Assistant Owned Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behaviour Monitor stops sending notifications and instead publishes alert lifecycle events, a needs-attention / for-information split, and a panic clear service, with a blueprint for phone delivery.

**Architecture:** The pure core `AlertRouter` stops producing `push`/`push_clear` and produces `event` delivery actions carrying a stable alert id, group, event type and reason. `Engine` passes these through and publishes the split in its snapshot. The coordinator fires them on the HA bus as `behaviour_monitor_alert`, holding them until Home Assistant has started and then sending restart reminders. Entities, services, config and docs follow.

**Tech Stack:** Python 3, Home Assistant custom integration, stdlib-only `core/`, pytest, Black (88), Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-11-08-ha-owned-notifications-design.md`

## Global Constraints

- `core/` stays stdlib only; only `coordinator.py` imports both HA and `core`.
- Event type name: `behaviour_monitor_alert`.
- Event `type` values: `opened`, `escalated`, `reminder`, `cleared`. Reminder `reason` values: `pressed_again`, `restart`, `snooze_ended`.
- Groups: `attention`, `information`, `health`.
- Option `attention_min_severity`, default `"medium"`. Options `push_min_severity` and `push_repeat_s` are gone.
- Config entry version 12. Engine `SCHEMA_VERSION` stays 2 and `STORAGE_VERSION` stays 11 (see Task 1 note); learned state must survive the upgrade.
- Button unique ids stay `{entry_id}_acknowledge` and `{entry_id}_test_notification`; names become "Clear panic" and "Test alert".
- Commits: conventional. The final commit that lands the breaking change uses `feat!:`. Never edit the version in `manifest.json`.
- Run tests with `make test` (or `pytest <path> -v` in the venv); `make lint` must pass before the last commit.

## Review Focus

1. **Panic pressed while snoozed or on holiday** — the panic event must still fire immediately (`opened`, or `reminder`/`pressed_again`), never held. Test in Task 1.
2. **Integration reload while HA is running** (an options change reloads the entry) — open attention alerts get one `restart` reminder each, not zero and not one per poll. Test in Task 3.
3. **`clear_alert` with an id from another site or an already cleared alert** — nothing is cleared, nothing raises, one warning is logged. Test in Task 4.
4. **Upgrade with a real panic open and previously acknowledged** — it is dropped on load (the old code would have closed it on the next submit), and an unacknowledged one survives with its id unchanged. Test in Task 1.
5. **Alert that closes and reopens with the same key** — the second opening gets a new id, and the first opening's `cleared` precedes the second's `opened`. Test in Task 1.

---

### Task 1: Router publishes events instead of pushes

**Files:**
- Modify: `custom_components/behaviour_monitor/core/alert_router.py`
- Test: `tests/core/test_alert_router.py` (rewrite the push-based tests; keep the `_combine` escalation tests, which use `welfare_severity` and `open_alerts`)

**Interfaces:**
- Produces:
  - `RouterConfig(attention_min_severity: Severity = Severity.MEDIUM, timing_promote_days: int = 7)` (no `push_*`).
  - `DeliveryAction(action: str, alert: Alert, event: str | None = None, reason: str | None = None, alert_id: str | None = None, group: str | None = None, cleared_by: str | None = None, test: bool = False)`. `action` is one of `event`, `repair_create`, `repair_delete`, `log`, `log_clear`. For `action == "event"`, `event` is the event type.
  - `alert_id(o) -> str` format: `f"{alert.key}@{raised_at.isoformat()}"`, where `raised_at` is fixed at opening.
  - `AlertRouter.submit(alerts, now, snoozed=False, holiday=False) -> list[DeliveryAction]` (same signature).
  - `AlertRouter.submit_panic(event: ActivityEvent, now) -> list[DeliveryAction]`
  - `AlertRouter.submit_test(now) -> list[DeliveryAction]`
  - `AlertRouter.clear_panic(alert_id: str | None, now: datetime) -> list[DeliveryAction]`
  - `AlertRouter.reminders(reason: str) -> list[DeliveryAction]`
  - `AlertRouter.published() -> list[dict[str, Any]]`: each `alert.to_dict()` plus `"id"` and `"group"`.
  - `AlertRouter.attention_severity -> Severity | None` (max severity in group `attention`); `welfare_severity` and `open_alerts` stay.
  - `acknowledge` is removed.

`_Open` becomes `alert, opened_at, group: str, panic: bool = False, test: bool = False, held: bool = False` (`last_push` and `acknowledged` go).

Rules the tests pin:
- Group on opening: `health` for class HEALTH; `attention` for class WELFARE when panic or severity ≥ `attention_min_severity`; otherwise `information`. On escalation an `information` welfare alert crossing the threshold moves to `attention`. Nothing ever moves out of `attention` while open.
- An existing open alert keeps its original `raised_at` on every re-submit (`dataclasses.replace(alert, raised_at=cur.alert.raised_at)`), so its id never changes.
- `opened` on first sight, `escalated` on any severity rise, both for every class. Statistical alerts also keep their `log` action on open and on rise (not when snoozed); health keeps `repair_create`/`repair_delete` alongside its events.
- Snooze holds back `opened`/`escalated` events only for `attention` alerts that are not panics, setting `held = True`. On the first `submit` with `snoozed=False`, every open `held` alert emits `reminder` with reason `snooze_ended` and `held` resets.
- Holiday drops welfare and statistical alerts as today, and they clear.
- `cleared` always fires on removal, including during snooze and holiday (the `log_clear` suppression stays as is).
- A non-test panic is removed only by `clear_panic`. `submit_panic` for an entity whose panic is already open emits `reminder`/`pressed_again` and changes nothing else.
- `submit_test` opens source `test`, `panic=True, test=True`; every event for it has `test=True`; the next `submit` removes it with `cleared`.
- `clear_panic(None, now)` clears every open non-test panic; `clear_panic(id, now)` clears that one only if it is an open non-test panic, else returns `[]`. Each emits `cleared` with `cleared_by="user"`.
- `reminders(reason)` returns one `reminder` per open `attention` alert, skipping test alerts.
- Persistence: `to_dict` writes `group`, `panic`, `test`, `held`. `from_dict` reads both shapes: when `group` is missing it derives it with the opening rule; an entry with `panic` and `acknowledged` true is dropped (the old router would have closed it on the next submit); `last_push`/`acknowledged` are ignored otherwise. This is the store migration, which is why `STORAGE_VERSION` does not change (bumping it would hit `_EngineStore._async_migrate_func`, which discards everything).

- [ ] **Step 1: Write the failing tests**

```python
def _ev(acts, event=None):
    return [(a.event, a.alert.key) for a in acts
            if a.action == "event" and (event is None or a.event == event)]

def _panic(eid="binary_sensor.p", ts=T0):
    return ActivityEvent(eid, Category.PANIC, EventKind.PANIC, "Hall", ts, bypass=True)

def test_open_escalate_clear_events_keep_one_id():
    r = AlertRouter(RouterConfig())
    a1 = r.submit([_house(Severity.MEDIUM, T0)], T0)
    a2 = r.submit([_house(Severity.HIGH, T0 + timedelta(minutes=1))], T0 + timedelta(minutes=1))
    assert r.submit([_house(Severity.HIGH, T0 + timedelta(minutes=2))], T0 + timedelta(minutes=2)) == []
    a3 = r.submit([], T0 + timedelta(minutes=3))
    assert [x.event for x in a1 + a2 + a3] == ["opened", "escalated", "cleared"]
    assert len({x.alert_id for x in a1 + a2 + a3}) == 1
    assert a1[0].alert_id == f"welfare:house:inactivity@{T0.isoformat()}"

def test_reopened_key_gets_new_id_after_clear():
    r = AlertRouter(RouterConfig())
    first = r.submit([_house(Severity.MEDIUM, T0)], T0)[0].alert_id
    cleared = r.submit([], T0 + timedelta(minutes=1))
    t2 = T0 + timedelta(minutes=2)
    second = r.submit([_house(Severity.MEDIUM, t2)], t2)[0].alert_id
    assert cleared[0].alert_id == first and second != first

def test_groups_threshold_panic_and_sticky_attention():
    r = AlertRouter(RouterConfig(attention_min_severity=Severity.HIGH))
    acts = r.submit([_house(Severity.MEDIUM), _note(), _health()], T0)
    groups = {a.alert.key: a.group for a in acts if a.action == "event"}
    assert groups == {"welfare:house:inactivity": "information",
                      "statistical:sensor.kettle:routine_missed": "information",
                      "health:binary_sensor.k:unavailable": "health"}
    up = r.submit([_house(Severity.HIGH), _note(), _health()], T0 + timedelta(minutes=1))
    assert [(a.event, a.group) for a in up if a.alert.kind == "inactivity"] == [("escalated", "attention")]
    r.submit([_house(Severity.MEDIUM), _note(), _health()], T0 + timedelta(minutes=2))
    assert {p["key"]: p["group"] for p in r.published()}["welfare:house:inactivity"] == "attention"
    p = r.submit_panic(_panic(), T0)
    assert p[0].group == "attention"  # panic is attention whatever the threshold

def test_snooze_holds_attention_then_reminds_but_never_holds_panic():
    r = AlertRouter(RouterConfig())
    assert _ev(r.submit([_house(Severity.HIGH)], T0, snoozed=True)) == []
    assert _ev(r.submit_panic(_panic(), T0)) == [("opened", "welfare:binary_sensor.p:panic")]
    again = r.submit_panic(_panic(ts=T0 + timedelta(minutes=1)), T0 + timedelta(minutes=1))
    assert [(a.event, a.reason) for a in again] == [("reminder", "pressed_again")]
    acts = r.submit([_house(Severity.HIGH)], T0 + timedelta(minutes=5))
    assert [(a.event, a.reason, a.alert.key) for a in acts] == [
        ("reminder", "snooze_ended", "welfare:house:inactivity")]
    assert r.submit([_house(Severity.HIGH)], T0 + timedelta(minutes=6)) == []

def test_cleared_fires_during_snooze_and_holiday():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.HIGH), _note()], T0)
    acts = r.submit([], T0 + timedelta(minutes=1), holiday=True)
    assert sorted(_ev(acts, "cleared")) == [("cleared", "statistical:sensor.kettle:routine_missed"),
                                            ("cleared", "welfare:house:inactivity")]
    assert [a for a in acts if a.action == "log_clear"] == []

def test_panic_stays_until_cleared_by_user():
    r = AlertRouter(RouterConfig())
    pid = r.submit_panic(_panic(), T0)[0].alert_id
    assert _ev(r.submit([], T0 + timedelta(hours=5), holiday=True)) == []
    assert r.clear_panic("welfare:house:inactivity@x", T0) == []
    acts = r.clear_panic(pid, T0 + timedelta(hours=6))
    assert [(a.event, a.cleared_by, a.alert_id) for a in acts] == [("cleared", "user", pid)]
    assert r.open_alerts == []

def test_clear_panic_without_id_clears_all_real_panics_not_test():
    r = AlertRouter(RouterConfig())
    r.submit_panic(_panic("binary_sensor.a"), T0)
    r.submit_panic(_panic("binary_sensor.b"), T0)
    r.submit_test(T0)
    acts = r.clear_panic(None, T0 + timedelta(minutes=1))
    assert sorted(a.alert.source for a in acts) == ["binary_sensor.a", "binary_sensor.b"]

def test_test_alert_flags_events_and_never_touches_real_panic():
    r = AlertRouter(RouterConfig())
    r.submit_panic(_panic(), T0)
    t = r.submit_test(T0 + timedelta(minutes=1))
    assert [(a.event, a.test) for a in t] == [("opened", True)]
    c = r.submit([], T0 + timedelta(minutes=2))
    assert [(a.event, a.test, a.alert.source) for a in c] == [("cleared", True, "test")]
    assert [a.key for a in r.open_alerts] == ["welfare:binary_sensor.p:panic"]
    assert [a.alert.source for a in r.reminders("restart")] == ["binary_sensor.p"]

def test_reminders_cover_open_attention_only():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.HIGH), _note(), _health()], T0)
    assert [(a.event, a.reason, a.alert.key) for a in r.reminders("restart")] == [
        ("reminder", "restart", "welfare:house:inactivity")]

def test_round_trip_keeps_ids_groups_and_held():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.HIGH), _health()], T0, snoozed=True)
    r2 = AlertRouter.from_dict(r.to_dict(), RouterConfig())
    assert r2.published() == r.published()
    assert [a.reason for a in r2.submit([_house(Severity.HIGH), _health()], T0)] == ["snooze_ended"]

def test_loads_v11_router_state():
    old = {"open": {
        "welfare:binary_sensor.p:panic": {"alert": Alert(AlertClass.WELFARE, "binary_sensor.p", "panic", Severity.CRITICAL, "p", T0).to_dict(),
            "opened_at": T0.isoformat(), "last_push": T0.isoformat(), "acknowledged": False, "panic": True},
        "welfare:binary_sensor.q:panic": {"alert": Alert(AlertClass.WELFARE, "binary_sensor.q", "panic", Severity.CRITICAL, "q", T0).to_dict(),
            "opened_at": T0.isoformat(), "last_push": T0.isoformat(), "acknowledged": True, "panic": True},
        "welfare:house:inactivity": {"alert": _house(Severity.LOW).to_dict(),
            "opened_at": T0.isoformat(), "last_push": None, "acknowledged": False, "panic": False}}}
    r = AlertRouter.from_dict(old, RouterConfig())
    pub = {p["key"]: p for p in r.published()}
    assert set(pub) == {"welfare:binary_sensor.p:panic", "welfare:house:inactivity"}
    assert pub["welfare:binary_sensor.p:panic"]["id"] == f"welfare:binary_sensor.p:panic@{T0.isoformat()}"
    assert pub["welfare:house:inactivity"]["group"] == "information"
```

Keep `test_note_escalates_open_house_alert_by_one_level`, `test_notes_from_entities_silent_today_do_not_escalate`, `test_two_notes_open_low_welfare_without_house_alert`, `test_chain_timing_drift_promotes_after_days` unchanged. Delete `test_welfare_push_threshold_repeat_and_clear`, `test_severity_rise_pushes_immediately_and_ack_stops_repeats`, `test_panic_is_immediate_critical_and_survives_submit_until_ack`, `test_test_push_never_touches_a_real_panic`, `test_snooze_suppresses_delivery_but_keeps_state_and_holiday_drops_alerts`, `test_holiday_clears_silently`, `test_round_trip`; update `test_health_becomes_repair_and_statistical_becomes_log` only for the new `RouterConfig`.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/core/test_alert_router.py -v`
Expected: FAIL (`RouterConfig` has no `attention_min_severity`, `DeliveryAction` has no `event`).

- [ ] **Step 3: Implement the interfaces above in `core/alert_router.py`**

- [ ] **Step 4: Run them to verify they pass**

Run: `pytest tests/core/test_alert_router.py -v`
Expected: PASS. `tests/core/test_engine.py` and the scenario tests may now fail; Task 2 fixes them.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/alert_router.py tests/core/test_alert_router.py
git commit -m "refactor(core): router emits alert events with stable ids and groups"
```

---

### Task 2: Engine passes events through and publishes the split

**Files:**
- Modify: `custom_components/behaviour_monitor/core/engine.py` (`from_options`, `acknowledge`, `snapshot`, new pass-throughs)
- Modify: `scripts/replay.py:100-106` (print `a.event or a.action`, include `reason`)
- Test: `tests/core/test_engine.py`, `tests/core/test_replay_scenarios.py`

**Interfaces:**
- Consumes: Task 1 router API.
- Produces:
  - `EngineConfig.from_options` reads `attention_min_severity` (default `"medium"`) into `RouterConfig`.
  - `Engine.clear_panic(alert_id: str | None, now: datetime) -> list[DeliveryAction]`
  - `Engine.reminders(reason: str) -> list[DeliveryAction]`
  - `Engine.acknowledge` removed.
  - Snapshot `welfare`: `status` computed from `attention_severity` (same `learning`/`degraded`/`ok` rules), `reasons` = attention explanations, `attention` and `information` = `router.published()` filtered by group. `open_alerts` removed. `anomalies` and `health.alerts` unchanged.

- [ ] **Step 1: Update the failing tests**

In `tests/core/test_replay_scenarios.py`, `_pushes` becomes "welfare `opened`/`reminder` events": `[(t, a.alert) for t, a in tl if a.action == "event" and a.event in ("opened", "reminder") and a.group == "attention"]`. `test_panic_press_pushes_critical_once_then_repeats` becomes `test_panic_press_opens_once_and_stays_open`: one `opened` for the panic and no `cleared` in the timeline. The replay CLI test asserts `"opened" in out and "panic" in out`. In `tests/core/test_engine.py` replace `a.action == "push"` with the same attention-event predicate. Add:

```python
def test_snapshot_splits_attention_and_information():
    e = _engine_with_low_and_high_welfare()  # build from existing helpers: one HIGH house alert, one LOW routine_agreement
    s = e.snapshot(NOW)["welfare"]
    assert [a["group"] for a in s["attention"]] == ["attention"]
    assert all(a["group"] == "information" for a in s["information"])
    assert "open_alerts" not in s and s["reasons"] == [s["attention"][0]["explanation"]]

def test_from_options_reads_attention_threshold():
    cfg = EngineConfig.from_options({"attention_min_severity": "high"})
    assert cfg.router.attention_min_severity is Severity.HIGH
```

If no helper fits, drive the engine's router directly in the test (`e._router.submit([...], NOW)`); it is a snapshot test, not a detection test.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/core -v`
Expected: the new and updated tests FAIL.

- [ ] **Step 3: Implement the engine changes and the replay print**

- [ ] **Step 4: Run the core suite**

Run: `pytest tests/core -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/engine.py scripts/replay.py tests/core
git commit -m "refactor(core): engine publishes attention and information groups"
```

---

### Task 3: Coordinator fires bus events and handles startup

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py`
- Modify: `custom_components/behaviour_monitor/const.py` (add `EVENT_ALERT: Final = "behaviour_monitor_alert"`)
- Test: `tests/test_coordinator.py`, `tests/conftest.py` (`mock_hass.state = CoreState.running`; drop `notify_service` from `mock_config_entry.data`; `version = 12`)

**Interfaces:**
- Consumes: Task 2 engine API, `DeliveryAction` fields from Task 1.
- Produces:
  - `BehaviourMonitorCoordinator.async_clear_alert(alert_id: str | None) -> bool` — True when anything was cleared.
  - Bus event `EVENT_ALERT` with data: `entry_id, site, type, id, group, class, kind, severity, source, room, message, raised_at, test`, plus `reason` on `reminder` and `cleared_by` on a user clear. `room` is `alert.details.get("room")`; `message` is `self._render(alert.explanation)`.
- Removed: `_push`, `_notify_service`, the persistent notification calls, `_notification_id`, `_last_notification` (and its store key and snapshot key), `last_notification` property, `async_acknowledge`.

Startup: in `async_setup`, `self._started = self.hass.state is CoreState.running`. While not started, `_perform` appends event payloads to `self._held_events` instead of firing. If not started, listen once for `EVENT_HOMEASSISTANT_STARTED`; the handler fires held payloads in order, then fires `engine.reminders("restart")` for every id that had no held `opened`, and sets `_started`. If already started (an integration reload), fire the restart reminders at the end of `async_setup`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_panic_fires_opened_event_and_no_notify(coordinator, mock_hass):
    # same setup as the old test_state_change_feeds_engine_and_panic_pushes
    ...
    fired = [c.args for c in mock_hass.bus.async_fire.call_args_list if c.args[0] == "behaviour_monitor_alert"]
    assert len(fired) == 1
    d = fired[0][1]
    assert (d["type"], d["group"], d["kind"], d["severity"], d["site"]) == ("opened", "attention", "panic", "critical", "Test House")
    assert d["id"].startswith("welfare:binary_sensor.panic:panic@") and d["test"] is False
    assert not [c for c in mock_hass.services.async_call.await_args_list if c.args[0] in ("notify", "persistent_notification")]
    data = await coordinator._async_update_data()
    assert [a["kind"] for a in data["welfare"]["attention"]] == ["panic"]
    assert "last_notification" not in data

async def test_events_held_until_started_then_restart_reminders(coordinator, mock_hass):
    mock_hass.state = CoreState.starting
    # setup with one open HIGH welfare alert restored from a stored router, and a panic pressed during startup
    ...
    assert not [c for c in mock_hass.bus.async_fire.call_args_list if c.args[0] == "behaviour_monitor_alert"]
    await started_listener(None)  # the callback registered for EVENT_HOMEASSISTANT_STARTED
    types = [(c.args[1]["type"], c.args[1].get("reason"), c.args[1]["kind"]) for c in mock_hass.bus.async_fire.call_args_list if c.args[0] == "behaviour_monitor_alert"]
    assert types == [("opened", None, "panic"), ("reminder", "restart", "inactivity")]

async def test_reload_while_running_sends_one_reminder_per_attention_alert(coordinator, mock_hass):
    # state running; stored router has one open HIGH welfare alert and one statistical
    ...
    reminders = [c.args[1] for c in mock_hass.bus.async_fire.call_args_list if c.args[0] == "behaviour_monitor_alert" and c.args[1]["type"] == "reminder"]
    assert [(r["reason"], r["kind"]) for r in reminders] == [("restart", "inactivity")]
    await coordinator._async_update_data()
    assert len([c for c in mock_hass.bus.async_fire.call_args_list if c.args[0] == "behaviour_monitor_alert" and c.args[1]["type"] == "reminder"]) == 1

async def test_clear_alert_clears_panic_and_reports(coordinator, mock_hass):
    ...  # press panic, take its id from the fired event
    assert await coordinator.async_clear_alert("nope@x") is False
    assert await coordinator.async_clear_alert(pid) is True
    last = mock_hass.bus.async_fire.call_args_list[-1].args[1]
    assert (last["type"], last["cleared_by"], last["id"]) == ("cleared", "user", pid)
```

Rewrite `test_delivery_actions_map_to_services_issues_and_logbook` for `event` actions (an `event` action fires `behaviour_monitor_alert` with the rendered message; repair and logbook assertions stay). Update `test_holiday_snooze_ack_reset_roundtrip` (drop ack), `test_test_panic_pushes_without_learning` and `test_test_panic_leaves_a_real_panic_open` (assert `test: True` events instead of notify calls), and the stored-state fixture at `tests/test_coordinator.py:425` (no `last_notification`). Build stored router state with `AlertRouter.to_dict()` rather than by hand.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_coordinator.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the coordinator changes**

- [ ] **Step 4: Run the coordinator and core tests**

Run: `pytest tests/test_coordinator.py tests/core -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py custom_components/behaviour_monitor/const.py tests/test_coordinator.py tests/conftest.py
git commit -m "refactor: coordinator fires behaviour_monitor_alert events instead of pushing"
```

---

### Task 4: Entities and services

**Files:**
- Modify: `custom_components/behaviour_monitor/button.py`, `sensor.py`, `__init__.py` (services), `services.yaml`, `const.py` (`SERVICE_CLEAR_ALERT = "clear_alert"`, remove `SERVICE_ACKNOWLEDGE`), `translations/en.json` (entity names, services)
- Test: `tests/test_button.py`, `tests/test_sensor.py`, `tests/test_init.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `async_clear_alert`, `async_test_panic` from Task 3.
- Produces:
  - `ClearPanicButton` (unique id `{entry_id}_acknowledge`, name "Clear panic", icon `mdi:alarm-light-off`) → `coordinator.async_clear_alert(None)`.
  - `TestAlertButton` (unique id `{entry_id}_test_notification`, name "Test alert") → `coordinator.async_test_panic()`.
  - Service `behaviour_monitor.clear_alert`, schema `{vol.Optional("alert_id"): str}`. Calls every coordinator; when an `alert_id` was given and none returned True, `_LOGGER.warning("No open panic with id %s", alert_id)`. Service `acknowledge` is removed from registration, unload, and `services.yaml`.
  - Welfare Status attributes: `reasons`, `attention`, `information` (each alert dict's `explanation` passed through `_render`), no `open_alerts`.
  - Last Notification sensor removed (eight sensors). `sensor.async_setup_entry` removes the registry entry with unique id `{entry_id}_last_notification` if present (`er.async_get(hass).async_get_entity_id("sensor", DOMAIN, uid)` then `async_remove`).

- [ ] **Step 1: Write the failing tests**

```python
async def test_clear_panic_button_clears_all_panics(mock_hass, mock_config_entry):
    ...
    await button.async_press()
    coordinator.async_clear_alert.assert_awaited_once_with(None)
    assert button.unique_id == "test_entry_id_acknowledge" and button.name == "Clear panic"

async def test_clear_alert_service_warns_when_no_site_owns_the_id(mock_hass, mock_config_entry, caplog):
    # two coordinators whose async_clear_alert returns False
    await handler(ServiceCall("behaviour_monitor", "clear_alert", {"alert_id": "x@y"}))
    assert "No open panic with id x@y" in caplog.text

def test_welfare_status_has_attention_and_information_rendered():
    ...
    assert set(attrs) >= {"reasons", "attention", "information"} and "open_alerts" not in attrs

async def test_setup_entry_adds_eight_sensors_and_removes_last_notification(mock_hass, mock_config_entry):
    ...
```

Update `test_sensor_keys`, `test_timestamps_and_count` (no `last_notification`), `test_setup_registers_platforms_and_services` and `test_unload_shuts_down_and_removes` (service list has `clear_alert`, not `acknowledge`), and the button tests.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_button.py tests/test_sensor.py tests/test_init.py tests/test_translations.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

- [ ] **Step 4: Run the full suite**

Run: `make test`
Expected: PASS except config flow / migration tests touched in Task 5.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor tests
git commit -m "refactor: clear panic button and clear_alert service replace acknowledge"
```

---

### Task 5: Config flow, options and v12 migration

**Files:**
- Modify: `custom_components/behaviour_monitor/const.py` (`CONFIG_VERSION = 12`; `CONF_ATTENTION_MIN_SEVERITY = "attention_min_severity"` in `OPTION_DEFAULTS` with `"medium"`; remove `CONF_PUSH_REPEAT_S`, `CONF_PUSH_MIN_SEVERITY`, `CONF_NOTIFY_SERVICE`; add `LEGACY_CONF_NOTIFY_SERVICE = "notify_service"`, `ISSUE_NOTIFICATIONS_MOVED = "notifications_moved"`, `BLUEPRINT_URL` pointing at the blueprint in Task 6 on `https://github.com/andrewmichael/behaviour-monitor`)
- Modify: `config_flow.py` (setup step drops notify service; options drop repeat, rename severity select), `__init__.py` (`async_migrate_entry`), `translations/en.json` (setup description stops mentioning pushes; options label "Minimum severity for needs attention"; issue `notifications_moved` text)
- Test: `tests/test_config_flow.py`, `tests/test_init.py`, `tests/test_const.py`

**Interfaces:**
- `async_migrate_entry`: entries below 11 run the existing path, then continue; version 11 → 12 pops `notify_service` from data, sets `options["attention_min_severity"] = options.pop("push_min_severity", "medium")`, pops `push_repeat_s`, and updates the entry to version 12. If the old `notify_service` was non-empty, create issue `f"{ISSUE_NOTIFICATIONS_MOVED}_{entry.entry_id}"`, `is_fixable=False`, `severity=WARNING`, `learn_more_url=BLUEPRINT_URL`, placeholders `site`, `service`.
- Issue text (en.json): title "Behaviour Monitor no longer sends notifications"; description "{site} used to send welfare alerts to {service}. Notifications now come from a Home Assistant automation. Import the Behaviour Monitor notify blueprint (Learn more) and choose {service} to keep receiving them."

- [ ] **Step 1: Write the failing tests**

```python
async def test_migrate_v11_to_v12_moves_options_and_raises_notice(mock_hass, mock_config_entry):
    mock_config_entry.version = 11
    mock_config_entry.data = {**mock_config_entry.data, "notify_service": "notify.mobile_app_phone"}
    mock_config_entry.options = {"push_min_severity": "high", "push_repeat_s": 900, "learning_days": 10}
    assert await async_migrate_entry(mock_hass, mock_config_entry) is True
    kw = mock_hass.config_entries.async_update_entry.call_args.kwargs
    assert "notify_service" not in kw["data"] and kw["version"] == 12
    assert kw["options"] == {"attention_min_severity": "high", "learning_days": 10}
    assert ir.async_create_issue.call_args.args[2] == "notifications_moved_test_entry_id"
    assert ir.async_create_issue.call_args.kwargs["translation_placeholders"]["service"] == "notify.mobile_app_phone"

async def test_migrate_v11_without_notify_service_raises_no_notice(...): ...
async def test_migrate_v10_lands_on_v12(...): ...   # extends the existing v10 test
async def test_migrate_v12_is_noop(...): ...        # replaces test_migrate_v11_is_noop
```

Config flow tests: the setup form has no `notify_service`; the options form has `attention_min_severity` and no `push_repeat_s`.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_init.py tests/test_config_flow.py tests/test_const.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

- [ ] **Step 4: Run the full suite and lint**

Run: `make test && make lint`
Expected: PASS; no ruff or mypy errors.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor tests
git commit -m "refactor: drop notify service and push options; migrate config to v12"
```

---

### Task 6: Blueprint and docs, breaking-change commit

**Files:**
- Create: `blueprints/automation/behaviour_monitor/notify.yaml`
- Create: `tests/test_blueprint.py`
- Modify: `README.md` (Configuration, Options, Entities, Services, Alert Classes; new "Notifications" section and an upgrade note), `CLAUDE.md` (Architecture alert classes line; file structure lists `blueprints/`; config v12)

Blueprint (`mode: parallel`, `max: 20`), triggered by event `behaviour_monitor_alert`. Inputs: `notify_service` (text, required, e.g. `notify.mobile_app_phone`); `groups` (select, multiple, options `attention`, `information`, `health`, default `[attention]`); `repeat_minutes` (number 0–240, default 30, 0 = no repeat); `send_cleared` (boolean, default true); `panic_action` (boolean, default true). Behaviour:
- `opened`, `escalated` or `reminder` in a chosen group → send `{{ trigger.event.data.site }} welfare` / `message`, with `data.tag: id` so a later message replaces the earlier one on the phone. For kind `panic` with `panic_action` on, add an action button `BM_CLEAR_<id>` titled "I'm on it". Then, if `repeat_minutes > 0`, loop: `wait_for_trigger` on `behaviour_monitor_alert` with `type: cleared` and the same `id`, timeout `repeat_minutes`; on timeout send again; on the cleared trigger stop.
- `cleared` in a chosen group with `send_cleared` → send "Cleared: <message>" with the same tag.
- A second trigger on `mobile_app_notification_action` whose action starts with `BM_CLEAR_` calls `behaviour_monitor.clear_alert` with `alert_id` = the rest of the action string.

`tests/test_blueprint.py` loads the YAML with a loader that accepts `!input` and asserts: the event trigger type, the five input names with their defaults, the `clear_alert` service call, and that the wait matches `id`.

README "Notifications": what fires, the event table from the spec, the two groups, the blueprint import button (`https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=<raw URL>`), an example automation for people who would rather write their own, Clear panic and `clear_alert`. The upgrade note: "From the version that ships this change, Behaviour Monitor no longer sends notifications; import the blueprint to keep receiving them." Quote no version number (the tag sets it).

- [ ] **Step 1: Write `tests/test_blueprint.py`**

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_blueprint.py -v`
Expected: FAIL (file not found).

- [ ] **Step 3: Write the blueprint, README and CLAUDE.md changes**

Before finishing, grep for stragglers and fix every hit in code, translations and docs (spec and plan files excepted):
`grep -rniE "notify_service|push_repeat|push_min_severity|acknowledg|last_notification|persistent_notification" custom_components tests README.md CLAUDE.md scripts`

- [ ] **Step 4: Run everything**

Run: `make test && make lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add blueprints tests/test_blueprint.py README.md CLAUDE.md
git commit -m "feat!: Home Assistant owns notifications

Behaviour Monitor no longer sends pushes. It fires behaviour_monitor_alert
events with stable alert ids, splits open alerts into attention and
information, and ships a notify blueprint. The notify service setting,
repeat pushes and Acknowledge are removed; Clear panic and clear_alert
close a panic.

BREAKING CHANGE: notifications now need an automation; import the blueprint."
```
