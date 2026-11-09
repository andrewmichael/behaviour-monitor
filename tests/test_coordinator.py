"""Tests for the Home Assistant coordinator around the core Engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator
from custom_components.behaviour_monitor.core.alert_router import (
    AlertRouter,
    DeliveryAction,
)
from custom_components.behaviour_monitor.core.alerts import Alert, AlertClass, Severity
from custom_components.behaviour_monitor.core.events import Category
from custom_components.behaviour_monitor.core.engine import SCHEMA_VERSION

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
EVENT = "behaviour_monitor_alert"


def _fired(mock_hass) -> list[dict]:
    return [
        c.args[1] for c in mock_hass.bus.async_fire.call_args_list if c.args[0] == EVENT
    ]


def _press_panic(coordinator) -> None:
    coordinator._handle_state_changed(
        SimpleNamespace(
            data={
                "entity_id": "binary_sensor.panic",
                "old_state": _state("binary_sensor.panic", "off"),
                "new_state": _state("binary_sensor.panic", "on"),
            }
        )
    )


def _store_router(coordinator, alerts: list[Alert]) -> None:
    """Store an engine whose router holds these alerts open, built the real way."""
    router = AlertRouter(coordinator._config.router)
    router.submit(alerts, NOW)
    engine = coordinator._engine.to_dict()
    engine["router"] = router.to_dict()
    coordinator._store._data = {
        "site": "Test House",
        "entity_ids": [s.entity_id for s in coordinator.entity_specs],
        "engine": engine,
    }
    coordinator._store._stored_version = coordinator._store.version


def _still_at_home() -> Alert:
    return Alert(
        AlertClass.WELFARE,
        "whereabouts",
        "still_at_home",
        Severity.HIGH,
        "No activity",
        NOW - timedelta(hours=1),
    )


def _state(entity_id: str, state: str, name: str | None = None):
    return SimpleNamespace(
        entity_id=entity_id,
        state=state,
        attributes={"friendly_name": name} if name else {},
    )


@pytest.fixture
def coordinator(mock_hass, mock_config_entry):
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(mock_hass)
    reg.entities.clear()
    reg.devices.clear()
    reg.areas.clear()
    reg.entities["binary_sensor.kitchen_motion"] = SimpleNamespace(
        area_id="a_kitchen", device_id=None
    )
    reg.entities["binary_sensor.bed_motion"] = SimpleNamespace(
        area_id=None, device_id="dev_bed"
    )
    reg.devices["dev_bed"] = SimpleNamespace(area_id="a_bed")
    reg.areas["a_kitchen"] = SimpleNamespace(name="Test House Kitchen")
    reg.areas["a_bed"] = SimpleNamespace(name="Bedroom")
    mock_hass.states.get = lambda eid: (
        _state(eid, "off", "Front door Door")
        if eid == "binary_sensor.front_door"
        else None
    )
    return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)


def test_specs_resolve_rooms_from_entity_then_device_then_name(coordinator):
    rooms = {s.entity_id: s.room for s in coordinator.entity_specs}
    assert rooms["binary_sensor.kitchen_motion"] == "Test House Kitchen"
    assert rooms["binary_sensor.bed_motion"] == "Bedroom"
    assert rooms["binary_sensor.front_door"] == "Front door Door"
    assert rooms["sensor.kettle_power"] == "sensor.kettle_power"
    cats = {s.entity_id: s.category for s in coordinator.entity_specs}
    assert cats["binary_sensor.panic"] is Category.PANIC


def test_unset_bedrooms_resolve_to_suggestions(mock_hass, mock_config_entry):
    """Unset bedrooms become the rooms named "bedroom", or none at all."""
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(mock_hass)
    reg.entities.clear()
    reg.devices.clear()
    reg.areas.clear()
    reg.entities["binary_sensor.kitchen_motion"] = SimpleNamespace(
        area_id="a_kitchen", device_id=None
    )
    reg.entities["binary_sensor.bed_motion"] = SimpleNamespace(
        area_id="a_bed", device_id=None
    )
    reg.areas["a_kitchen"] = SimpleNamespace(name="Kitchen")
    reg.areas["a_bed"] = SimpleNamespace(name="Mum's room")
    mock_hass.states.get = lambda eid: None
    coordinator = BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
    assert coordinator._config.whereabouts.bedrooms == frozenset()

    reg.areas["a_bed"] = SimpleNamespace(name="Back Bedroom")
    coordinator = BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
    assert coordinator._config.whereabouts.bedrooms == frozenset({"Back Bedroom"})

    # A chosen list, even an empty one, is used as it is.
    mock_config_entry.options = {"bedrooms": ["Kitchen"]}
    coordinator = BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
    assert coordinator._config.whereabouts.bedrooms == frozenset({"Kitchen"})


def test_display_room_strips_site_prefix(coordinator):
    assert coordinator.display_room("Test House Kitchen") == "Kitchen"
    assert coordinator.display_room("test house Bedroom") == "Bedroom"
    assert coordinator.display_room("Bedroom") == "Bedroom"
    assert coordinator.display_room("Test Houseboat") == "Test Houseboat"


@pytest.mark.asyncio
async def test_setup_bootstraps_from_recorder_and_subscribes(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()) as boot:
        await coordinator.async_setup()
    boot.assert_awaited_once()
    assert set(boot.await_args.args[0]) == {
        s.entity_id for s in coordinator.entity_specs
    }
    subscribed = {c.args[0] for c in mock_hass.bus.async_listen.call_args_list}
    assert {
        "state_changed",
        "entity_registry_updated",
        "area_registry_updated",
        "device_registry_updated",
    } <= subscribed
    for event in (
        "entity_registry_updated",
        "area_registry_updated",
        "device_registry_updated",
    ):
        mock_hass.bus.async_listen.assert_any_call(
            event, coordinator._async_registry_updated
        )
    mock_hass.bus.async_listen.assert_any_call(
        "state_changed", coordinator._handle_state_changed
    )


@pytest.mark.asyncio
async def test_panic_fires_opened_event_and_no_notify(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ):
        _press_panic(coordinator)
        await coordinator._flush_actions()
    fired = _fired(mock_hass)
    assert len(fired) == 1
    d = fired[0]
    assert (d["type"], d["group"], d["kind"], d["severity"], d["site"]) == (
        "opened",
        "attention",
        "panic",
        "critical",
        "Test House",
    )
    assert d["id"].startswith("welfare:binary_sensor.panic:panic@")
    assert d["test"] is False
    assert d["entry_id"] == "test_entry_id"
    assert d["class"] == "welfare" and d["source"] == "binary_sensor.panic"
    assert d["raised_at"] == NOW.isoformat()
    assert "reason" not in d and "cleared_by" not in d
    assert not [
        c
        for c in mock_hass.services.async_call.await_args_list
        if c.args[0] in ("notify", "persistent_notification")
    ]
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ):
        data = await coordinator._async_update_data()
    # The panic is open on the router, so it shows up as a welfare reason even
    # while the models are still learning.
    assert data["welfare"]["status"] == "learning"
    assert any("panic" in reason for reason in data["welfare"]["reasons"])
    assert [a["kind"] for a in data["welfare"]["attention"]] == ["panic"]
    assert "last_notification" not in data


@pytest.mark.asyncio
async def test_events_held_until_started_then_restart_reminders(coordinator, mock_hass):
    from homeassistant.core import CoreState

    mock_hass.state = CoreState.starting
    _store_router(coordinator, [_still_at_home()])
    await coordinator.async_setup()
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ):
        _press_panic(coordinator)
        await coordinator._flush_actions()
    assert _fired(mock_hass) == []
    listens = [
        c.args
        for c in mock_hass.bus.async_listen_once.call_args_list
        if c.args[0] == "homeassistant_started"
    ]
    assert len(listens) == 1
    started_listener = listens[0][1]
    await started_listener(None)
    types = [(d["type"], d.get("reason"), d["kind"]) for d in _fired(mock_hass)]
    assert types == [
        ("opened", None, "panic"),
        ("reminder", "restart", "still_at_home"),
    ]
    # Once started, events go straight out.
    await coordinator.async_test_panic()
    assert _fired(mock_hass)[-1]["test"] is True


@pytest.mark.asyncio
async def test_started_during_setup_releases_held_events(coordinator, mock_hass):
    """homeassistant_started can fire while setup is awaiting; nothing may stay held."""
    from homeassistant.core import CoreState

    from custom_components.behaviour_monitor.core.events import (
        ActivityEvent,
        EventKind,
    )

    mock_hass.state = CoreState.starting
    _store_router(coordinator, [_still_at_home()])
    coordinator._store._data["entity_ids"].remove("binary_sensor.panic")

    async def boot(_ids):
        # A panic raised while starting is held; then HA finishes starting
        # before setup has registered for homeassistant_started.
        panic = ActivityEvent(
            "binary_sensor.panic",
            Category.PANIC,
            EventKind.PANIC,
            "Hall",
            NOW,
            bypass=True,
        )
        await coordinator._perform(
            coordinator._engine._router.submit_panic(panic, NOW), NOW
        )
        assert _fired(mock_hass) == []
        mock_hass.state = CoreState.running

    with patch.object(coordinator, "_bootstrap_entities", side_effect=boot):
        await coordinator.async_setup()
    mock_hass.bus.async_listen_once.assert_not_called()
    types = [(d["type"], d.get("reason"), d["kind"]) for d in _fired(mock_hass)]
    assert types == [
        ("opened", None, "panic"),
        ("reminder", "restart", "still_at_home"),
    ]
    await coordinator.async_test_panic()
    assert _fired(mock_hass)[-1]["test"] is True


@pytest.mark.asyncio
async def test_reload_while_running_sends_one_reminder_per_attention_alert(
    coordinator, mock_hass
):
    stat = Alert(
        AlertClass.STATISTICAL,
        "sensor.kettle_power",
        "routine_missed",
        Severity.LOW,
        "missed",
        NOW - timedelta(hours=1),
    )
    _store_router(coordinator, [_still_at_home(), stat])
    await coordinator.async_setup()
    mock_hass.bus.async_listen_once.assert_not_called()
    reminders = [d for d in _fired(mock_hass) if d["type"] == "reminder"]
    assert [(r["reason"], r["kind"]) for r in reminders] == [
        ("restart", "still_at_home")
    ]
    await coordinator._async_update_data()
    assert len([d for d in _fired(mock_hass) if d["type"] == "reminder"]) == 1


@pytest.mark.asyncio
async def test_clear_alert_clears_panic_and_reports(coordinator, mock_hass, caplog):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ):
        _press_panic(coordinator)
        await coordinator._flush_actions()
    pid = _fired(mock_hass)[0]["id"]
    with caplog.at_level("WARNING"):
        assert await coordinator.async_clear_alert("nope@x") is False
    assert "nope@x" not in caplog.text
    assert await coordinator.async_clear_alert(pid) is True
    last = mock_hass.bus.async_fire.call_args_list[-1].args[1]
    assert (last["type"], last["cleared_by"], last["id"]) == ("cleared", "user", pid)
    assert coordinator._engine.snapshot(NOW)["welfare"]["attention"] == []
    assert await coordinator.async_clear_alert(None) is False


@pytest.mark.asyncio
async def test_delivery_actions_map_to_events_issues_and_logbook(
    coordinator, mock_hass
):
    from homeassistant.helpers import issue_registry as ir

    ir.async_create_issue.reset_mock()
    ir.async_delete_issue.reset_mock()
    coordinator._started = True
    welfare = Alert(
        AlertClass.WELFARE,
        "whereabouts",
        "still_at_home",
        Severity.HIGH,
        "No activity in Test House Kitchen",
        NOW,
        {"room": "Test House Kitchen"},
    )
    health = Alert(
        AlertClass.HEALTH,
        "binary_sensor.kitchen_motion",
        "unavailable",
        Severity.MEDIUM,
        "down",
        NOW,
    )
    stat = Alert(
        AlertClass.STATISTICAL,
        "sensor.kettle_power",
        "routine_missed",
        Severity.LOW,
        "missed",
        NOW,
    )
    await coordinator._perform(
        [
            DeliveryAction(
                "event", welfare, event="opened", alert_id="w1", group="attention"
            ),
            DeliveryAction("repair_create", health),
            DeliveryAction("log", stat),
        ],
        NOW,
    )
    mock_hass.bus.async_fire.assert_any_call(
        EVENT,
        {
            "entry_id": "test_entry_id",
            "site": "Test House",
            "type": "opened",
            "id": "w1",
            "group": "attention",
            "class": "welfare",
            "kind": "still_at_home",
            "severity": "high",
            "source": "whereabouts",
            "room": "Test House Kitchen",
            "message": "No activity in Kitchen",
            "raised_at": NOW.isoformat(),
            "test": False,
        },
    )
    ir.async_create_issue.assert_called_once()
    assert (
        ir.async_create_issue.call_args.args[2]
        == "health_test_entry_id_health:binary_sensor.kitchen_motion:unavailable"
    )
    mock_hass.bus.async_fire.assert_any_call(
        "logbook_entry",
        {"name": "Test House", "message": "missed", "domain": "behaviour_monitor"},
    )
    await coordinator._perform(
        [
            DeliveryAction(
                "event",
                welfare,
                event="reminder",
                reason="snooze_ended",
                alert_id="w1",
                group="attention",
            ),
            DeliveryAction(
                "event", health, event="cleared", alert_id="h1", group="health"
            ),
            DeliveryAction("repair_delete", health),
        ],
        NOW,
    )
    ir.async_delete_issue.assert_called_once()
    reminder, cleared = _fired(mock_hass)[-2:]
    assert (reminder["type"], reminder["reason"]) == ("reminder", "snooze_ended")
    assert (cleared["type"], cleared["group"], cleared["room"]) == (
        "cleared",
        "health",
        None,
    )
    assert "cleared_by" not in cleared
    assert not mock_hass.services.async_call.await_args_list


@pytest.mark.asyncio
async def test_update_data_returns_snapshot_with_site(coordinator):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ):
        data = await coordinator._async_update_data()
    assert data["site"] == "Test House"
    assert data["welfare"]["status"] == "learning"
    assert set(data["entities"]) == {s.entity_id for s in coordinator.entity_specs}


@pytest.mark.asyncio
async def test_poll_saves_the_store_at_most_every_five_minutes(coordinator):
    """The last poll time reaches the store even when nothing changes."""
    now = "custom_components.behaviour_monitor.coordinator.dt_util.now"
    with patch(now, return_value=NOW), patch.object(
        coordinator, "_bootstrap_entities", new=AsyncMock()
    ):
        await coordinator.async_setup()
    with patch.object(coordinator._store, "async_save", new=AsyncMock()) as save:
        with patch(now, return_value=NOW + timedelta(minutes=1)):
            await coordinator._async_update_data()
        save.assert_not_called()
        with patch(now, return_value=NOW + timedelta(minutes=6)):
            await coordinator._async_update_data()
        save.assert_awaited_once()
        with patch(now, return_value=NOW + timedelta(minutes=7)):
            await coordinator._async_update_data()
        save.assert_awaited_once()
    assert (
        save.await_args.args[0]["engine"]["meta"]["last_poll"]
        == (NOW + timedelta(minutes=6)).isoformat()
    )


@pytest.mark.asyncio
async def test_holiday_snooze_reset_roundtrip(coordinator):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    await coordinator.async_enable_holiday_mode()
    assert coordinator.holiday_mode is True
    await coordinator.async_disable_holiday_mode()
    assert coordinator.holiday_mode is False
    await coordinator.async_snooze("2_hours")
    assert (
        coordinator.is_snoozed() and coordinator.get_snooze_duration_key() == "2_hours"
    )
    await coordinator.async_clear_snooze()
    assert not coordinator.is_snoozed()
    await coordinator.async_reset_learning("binary_sensor.kitchen_motion")
    await coordinator.async_reset_learning()
    saved = coordinator._store._data
    assert saved["engine"]["schema"] == SCHEMA_VERSION and saved["site"] == "Test House"


@pytest.mark.asyncio
async def test_test_panic_pushes_without_learning(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    before = coordinator._engine.to_dict()["house"]
    await coordinator.async_test_panic()
    fired = _fired(mock_hass)
    assert [(d["type"], d["test"]) for d in fired] == [("opened", True)]
    assert not mock_hass.services.async_call.await_args_list
    assert coordinator._engine.to_dict()["house"] == before


@pytest.mark.asyncio
async def test_test_panic_leaves_a_real_panic_open(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    from custom_components.behaviour_monitor.core.events import (
        ActivityEvent,
        Category,
        EventKind,
    )

    now = datetime.now(timezone.utc)
    real = ActivityEvent(
        "binary_sensor.panic", Category.PANIC, EventKind.PANIC, "Hall", now, bypass=True
    )
    await coordinator._perform(coordinator._engine._router.submit_panic(real, now), now)
    await coordinator.async_test_panic()
    open_real = [
        o
        for o in coordinator._engine._router._open.values()
        if o.alert.source == "binary_sensor.panic"
    ]
    assert len(open_real) == 1
    fired = _fired(mock_hass)
    assert [(d["type"], d["test"], d["source"]) for d in fired] == [
        ("opened", False, "binary_sensor.panic"),
        ("opened", True, "test"),
    ]


@pytest.mark.asyncio
async def test_registry_update_reresolves_rooms(coordinator, mock_hass):
    """Renaming an area renames the room; moving one sensor must not."""
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(mock_hass)

    # Same area id, new name: a genuine rename, so the learning follows it.
    reg.areas["a_bed"] = SimpleNamespace(name="Back Bedroom")
    with patch.object(coordinator._engine, "rename_room") as rename:
        await coordinator._async_registry_updated(SimpleNamespace(data={}))
    rename.assert_called_once_with("Bedroom", "Back Bedroom")
    assert {s.room for s in coordinator.entity_specs} >= {"Back Bedroom"}

    # Different area id: the sensor moved. Renaming here would merge the two
    # rooms' learning, so only this entity's room may change.
    reg.devices["dev_bed"] = SimpleNamespace(area_id="a_kitchen")
    with patch.object(coordinator._engine, "rename_room") as rename:
        await coordinator._async_registry_updated(SimpleNamespace(data={}))
    rename.assert_not_called()
    rooms = {s.entity_id: s.room for s in coordinator.entity_specs}
    assert rooms["binary_sensor.bed_motion"] == "Test House Kitchen"
    assert "Back Bedroom" not in set(rooms.values())


@pytest.mark.asyncio
async def test_area_rename_renames_bedroom_option(
    coordinator, mock_hass, mock_config_entry
):
    """A renamed bedroom area keeps its place in the bedrooms option."""
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    from homeassistant.helpers import entity_registry as er

    mock_config_entry.options = {"learning_days": 10, "bedrooms": ["Bedroom", "Den"]}
    reg = er.async_get(mock_hass)
    reg.areas["a_bed"] = SimpleNamespace(name="Back Bedroom")
    await coordinator._async_registry_updated(SimpleNamespace(data={}))
    mock_hass.config_entries.async_update_entry.assert_called_once_with(
        mock_config_entry,
        options={"learning_days": 10, "bedrooms": ["Back Bedroom", "Den"]},
    )

    # A rename of a room that is not a bedroom leaves the option alone.
    mock_hass.config_entries.async_update_entry.reset_mock()
    mock_config_entry.options = {"bedrooms": ["Back Bedroom"]}
    reg.areas["a_kitchen"] = SimpleNamespace(name="Test House Scullery")
    await coordinator._async_registry_updated(SimpleNamespace(data={}))
    mock_hass.config_entries.async_update_entry.assert_not_called()

    # Unset bedrooms stay unset, but the entry reloads so the rooms named
    # "bedroom" are worked out again.
    mock_config_entry.options = {}
    mock_hass.config_entries.async_reload.reset_mock()
    reg.areas["a_bed"] = SimpleNamespace(name="Front Bedroom")
    await coordinator._async_registry_updated(SimpleNamespace(data={}))
    mock_hass.config_entries.async_update_entry.assert_not_called()
    mock_hass.config_entries.async_reload.assert_called_once_with(
        mock_config_entry.entry_id
    )


@pytest.mark.asyncio
async def test_shutdown_stops_both_timers(coordinator):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    await coordinator.async_shutdown()
    coordinator._saver.async_shutdown.assert_called_once()
    assert coordinator.shutdown_called is True
    assert coordinator._store._data is not None


@pytest.mark.asyncio
async def test_setup_survives_recorder_not_loaded(coordinator, mock_hass):
    """recorder_get_instance raises KeyError when the recorder is absent."""
    with patch(
        "custom_components.behaviour_monitor.coordinator.recorder_get_instance",
        side_effect=KeyError("recorder"),
    ):
        await coordinator.async_setup()
    mock_hass.bus.async_listen.assert_any_call(
        "state_changed", coordinator._handle_state_changed
    )
    assert coordinator._store._data["engine"]["schema"] == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_setup_survives_corrupt_engine_section(coordinator):
    coordinator._store._data = {
        "engine": {"schema": SCHEMA_VERSION, "house": "not a dict"}
    }
    coordinator._store._stored_version = coordinator._store.version
    with patch.object(
        coordinator, "_bootstrap_entities", new=AsyncMock()
    ) as boot, patch(
        "custom_components.behaviour_monitor.coordinator.Engine.from_dict",
        side_effect=ValueError("bad store"),
    ):
        await coordinator.async_setup()
    # Fresh engine, and every entity treated as new so history is replayed.
    assert set(boot.await_args.args[0]) == {
        s.entity_id for s in coordinator.entity_specs
    }
    assert coordinator._engine.to_dict()["schema"] == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_setup_discards_old_store_version(coordinator):
    """A v10 store must be migrated away, not blow up setup."""
    coordinator._store._data = {
        "engine": {"schema": 1, "house": {"days": 99}},
        "site": "Old House",
        "entity_ids": ["binary_sensor.kitchen_motion"],
    }
    coordinator._store._stored_version = 10
    # The override is what keeps HA from raising NotImplementedError here.
    assert await coordinator._store._async_migrate_func(10, 0, {"a": 1}) == {}
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()) as boot:
        await coordinator.async_setup()
    # Everything is new again, because the old store was discarded wholesale.
    assert set(boot.await_args.args[0]) == {
        s.entity_id for s in coordinator.entity_specs
    }
    assert coordinator._engine.to_dict()["schema"] == SCHEMA_VERSION
    assert coordinator._store._data["site"] == "Test House"


def _row(state: str, when: datetime):
    return SimpleNamespace(state=state, last_changed=when)


def _recorder_instance(rows):
    return SimpleNamespace(async_add_executor_job=AsyncMock(return_value=rows))


@pytest.mark.asyncio
async def test_bootstrap_replays_recorder_rows(coordinator):
    eid = "binary_sensor.kitchen_motion"
    rows = {
        eid: [
            _row("on", NOW - timedelta(hours=4)),
            _row("off", NOW - timedelta(hours=3, minutes=58)),
            _row("unavailable", NOW - timedelta(hours=3)),
            _row("on", NOW - timedelta(hours=2)),
            _row("off", NOW - timedelta(hours=1, minutes=58)),
        ]
    }
    instance = _recorder_instance(rows)
    with patch(
        "custom_components.behaviour_monitor.coordinator.recorder_get_instance",
        return_value=instance,
    ), patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ), patch.object(
        coordinator._engine,
        "handle_state",
        wraps=coordinator._engine.handle_state,
    ) as handled:
        await coordinator._bootstrap_entities([eid])
    call = instance.async_add_executor_job.await_args
    assert call.args[4] == eid and isinstance(call.args[4], str)
    assert coordinator._engine.snapshot(NOW)["entities"][eid]["last_seen"] is not None
    # The historic dropout never reaches the engine, and the row after it is
    # replayed as a first sighting rather than a restore from unavailable.
    assert [(c.args[1], c.args[2]) for c in handled.call_args_list] == [
        (None, "on"),
        ("on", "off"),
        (None, "on"),
        ("on", "off"),
    ]


@pytest.mark.asyncio
async def test_bootstrap_replays_all_entities_in_time_order(coordinator):
    """History from several sensors is merged by time, not replayed per sensor:
    a model that drops events older than its current interval would otherwise
    learn from the first sensor only."""
    kitchen, bed = "binary_sensor.kitchen_motion", "binary_sensor.bed_motion"
    rows = {
        kitchen: [
            _row("on", NOW - timedelta(hours=5)),
            _row("off", NOW - timedelta(hours=3)),
            _row("unavailable", NOW - timedelta(hours=2, minutes=30)),
            _row("on", NOW - timedelta(hours=1)),
        ],
        bed: [
            _row("on", NOW - timedelta(hours=4)),
            _row("off", NOW - timedelta(hours=2)),
        ],
    }
    instance = _recorder_instance(rows)
    with patch(
        "custom_components.behaviour_monitor.coordinator.recorder_get_instance",
        return_value=instance,
    ), patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ), patch.object(
        coordinator._engine,
        "handle_state",
        wraps=coordinator._engine.handle_state,
    ) as handled:
        await coordinator._bootstrap_entities([kitchen, bed])
    assert [
        (c.args[0], c.args[1], c.args[2], c.args[3]) for c in handled.call_args_list
    ] == [
        (kitchen, None, "on", NOW - timedelta(hours=5)),
        (bed, None, "on", NOW - timedelta(hours=4)),
        (kitchen, "on", "off", NOW - timedelta(hours=3)),
        (bed, "on", "off", NOW - timedelta(hours=2)),
        (kitchen, None, "on", NOW - timedelta(hours=1)),
    ]
    assert all(c.kwargs == {"learn_only": True} for c in handled.call_args_list)


@pytest.mark.asyncio
async def test_bootstrap_actions_are_queued_for_delivery(coordinator):
    alert = Alert(
        AlertClass.WELFARE,
        "whereabouts",
        "still_at_home",
        Severity.HIGH,
        "No activity",
        NOW,
    )
    action = DeliveryAction("event", alert, event="opened", alert_id="a1")
    instance = _recorder_instance({})
    with patch(
        "custom_components.behaviour_monitor.coordinator.recorder_get_instance",
        return_value=instance,
    ), patch.object(coordinator._engine, "poll", return_value=[action]):
        await coordinator.async_setup()
    assert [a for a, _ in coordinator._pending] == [action]


@pytest.mark.asyncio
async def test_stale_engine_schema_triggers_full_bootstrap(coordinator):
    """A store from an older schema must replay history, not start blank."""
    coordinator._store._data = {
        "site": "Test House",
        "entity_ids": [s.entity_id for s in coordinator.entity_specs],
        "engine": {"schema": 1, "house": {}},
    }
    coordinator._store._stored_version = coordinator._store.version
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()) as boot:
        await coordinator.async_setup()
    # Every entity is replayed, even though the store listed them all as known.
    boot.assert_awaited_once()
    assert set(boot.await_args.args[0]) == {
        s.entity_id for s in coordinator.entity_specs
    }


def _record_data_at_fire(coordinator, mock_hass) -> list[tuple[dict, object]]:
    """Capture what the entities hold at the moment each alert event is fired."""
    seen: list[tuple[dict, object]] = []

    def fire(event_type, data=None, *args, **kwargs):
        if event_type == EVENT:
            seen.append((data, coordinator.data))

    mock_hass.bus.async_fire.side_effect = fire
    return seen


def _attention_ids(data) -> list[str]:
    if not isinstance(data, dict):
        return []
    return [a["id"] for a in data["welfare"]["attention"]]


@pytest.mark.asyncio
async def test_panic_is_published_before_its_event_fires(coordinator, mock_hass):
    """The blueprint looks the id up on the sensor as soon as the event lands.

    A refresh requested through the debouncer can be up to 10 s late, so the
    snapshot must already be on the entities when the opened event fires.
    """
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    seen = _record_data_at_fire(coordinator, mock_hass)
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ), patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
        _press_panic(coordinator)
        await coordinator._flush_actions()
    assert [p["type"] for p, _ in seen] == ["opened"]
    payload, data_at_fire = seen[0]
    assert payload["id"] in _attention_ids(data_at_fire)
    assert data_at_fire["site"] == "Test House"
    assert "display_rooms" in data_at_fire


@pytest.mark.asyncio
async def test_test_panic_is_published_before_its_event_fires(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    seen = _record_data_at_fire(coordinator, mock_hass)
    with patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
        await coordinator.async_test_panic()
    assert [(p["type"], p["test"]) for p, _ in seen] == [("opened", True)]
    payload, data_at_fire = seen[0]
    assert payload["id"] in _attention_ids(data_at_fire)


@pytest.mark.asyncio
async def test_clear_alert_is_published_before_its_event_fires(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ):
        _press_panic(coordinator)
        await coordinator._flush_actions()
    pid = _fired(mock_hass)[0]["id"]
    seen = _record_data_at_fire(coordinator, mock_hass)
    with patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
        assert await coordinator.async_clear_alert(pid) is True
    assert [p["type"] for p, _ in seen] == ["cleared"]
    assert seen[0][1] is not None
    assert pid not in _attention_ids(seen[0][1])


@pytest.mark.asyncio
async def test_publish_failure_never_blocks_the_event(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ), patch.object(coordinator._engine, "snapshot", side_effect=RuntimeError("boom")):
        _press_panic(coordinator)
        await coordinator._flush_actions()
    assert [d["type"] for d in _fired(mock_hass)] == ["opened"]


@pytest.mark.asyncio
async def test_poll_path_does_not_publish_twice(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch.object(coordinator, "async_set_updated_data") as publish:
        await coordinator._async_update_data()
    publish.assert_not_called()


@pytest.mark.asyncio
async def test_held_panic_is_published_before_release(coordinator, mock_hass):
    from homeassistant.core import CoreState

    mock_hass.state = CoreState.starting
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ):
        _press_panic(coordinator)
        await coordinator._flush_actions()
    seen = _record_data_at_fire(coordinator, mock_hass)
    started = next(
        c.args[1]
        for c in mock_hass.bus.async_listen_once.call_args_list
        if c.args[0] == "homeassistant_started"
    )
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ):
        await started(None)
    assert [p["type"] for p, _ in seen] == ["opened"]
    assert seen[0][0]["id"] in _attention_ids(seen[0][1])


# ------------------------------------------------------------- low battery


def _add_batteries(mock_hass) -> None:
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(mock_hass)
    reg.entities["binary_sensor.panic"] = SimpleNamespace(
        area_id=None, device_id="dev_panic"
    )
    # On the panic device: a binary low-battery flag (wrong domain), a
    # temperature sensor (wrong class) and two battery sensors.
    reg.entities["binary_sensor.panic_battery_low"] = SimpleNamespace(
        area_id=None, device_id="dev_panic", device_class="battery"
    )
    reg.entities["sensor.panic_temperature"] = SimpleNamespace(
        area_id=None, device_id="dev_panic", original_device_class="temperature"
    )
    reg.entities["sensor.panic_button_hall_battery"] = SimpleNamespace(
        area_id=None, device_id="dev_panic", original_device_class="battery"
    )
    reg.entities["sensor.zz_panic_battery"] = SimpleNamespace(
        area_id=None, device_id="dev_panic", device_class="battery"
    )
    reg.entities["sensor.bed_battery"] = SimpleNamespace(
        area_id=None,
        device_id="dev_bed",
        device_class="battery",
        original_device_class=None,
    )


def _battery_change(coordinator, entity_id: str, state: str) -> None:
    coordinator._handle_state_changed(
        SimpleNamespace(
            data={
                "entity_id": entity_id,
                "old_state": _state(entity_id, "50"),
                "new_state": _state(entity_id, state),
            }
        )
    )


def test_battery_sensor_on_the_same_device_is_discovered(mock_hass, coordinator):
    # The fixture's coordinator was built before the batteries were added.
    assert coordinator._batteries == {}
    _add_batteries(mock_hass)
    coordinator = BehaviourMonitorCoordinator(mock_hass, coordinator._entry)
    assert coordinator._batteries == {
        "sensor.panic_button_hall_battery": ["binary_sensor.panic"],
        "sensor.bed_battery": ["binary_sensor.bed_motion"],
    }


@pytest.mark.asyncio
async def test_registry_update_rediscovers_battery_sensors(mock_hass, coordinator):
    _add_batteries(mock_hass)
    await coordinator._async_registry_updated(SimpleNamespace(data={}))
    assert coordinator._batteries["sensor.bed_battery"] == ["binary_sensor.bed_motion"]


def test_battery_state_change_feeds_the_monitored_entity(mock_hass, coordinator):
    _add_batteries(mock_hass)
    coordinator = BehaviourMonitorCoordinator(mock_hass, coordinator._entry)
    with patch(
        "custom_components.behaviour_monitor.coordinator.Engine.record_battery"
    ) as rec:
        _battery_change(coordinator, "sensor.panic_button_hall_battery", "15")
        for bad in ("unavailable", "unknown", "low"):
            _battery_change(coordinator, "sensor.panic_button_hall_battery", bad)
        _battery_change(coordinator, "sensor.unrelated_battery", "5")
    rec.assert_called_once()
    eid, level, _ts = rec.call_args.args
    assert eid == "binary_sensor.panic"
    assert level == 15.0 and isinstance(level, float)


@pytest.mark.asyncio
async def test_setup_reads_current_battery_levels(mock_hass, coordinator):
    _add_batteries(mock_hass)
    levels = {"sensor.panic_button_hall_battery": "9", "sensor.bed_battery": "unknown"}
    mock_hass.states.get = lambda eid: (
        _state(eid, levels[eid]) if eid in levels else None
    )
    coordinator = BehaviourMonitorCoordinator(mock_hass, coordinator._entry)
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()), patch(
        "custom_components.behaviour_monitor.coordinator.Engine.record_battery"
    ) as rec:
        await coordinator.async_setup()
    assert [c.args[:2] for c in rec.call_args_list] == [("binary_sensor.panic", 9.0)]


def test_user_device_class_overrides_original_and_entities_without_device_skip(
    mock_hass, coordinator
):
    from homeassistant.helpers import entity_registry as er

    _add_batteries(mock_hass)
    reg = er.async_get(mock_hass)
    # The user reclassified the bed battery as something else.
    reg.entities["sensor.bed_battery"] = SimpleNamespace(
        area_id=None,
        device_id="dev_bed",
        device_class="voltage",
        original_device_class="battery",
    )
    # A monitored entity with a registry entry but no device.
    reg.entities["binary_sensor.front_door"] = SimpleNamespace(
        area_id=None, device_id=None
    )
    coordinator = BehaviourMonitorCoordinator(mock_hass, coordinator._entry)
    assert coordinator._batteries == {
        "sensor.panic_button_hall_battery": ["binary_sensor.panic"]
    }


def _open_battery_kinds(coordinator) -> list[str]:
    return [
        a.source
        for a in coordinator._engine._router.open_alerts
        if a.kind == "battery_low"
    ]


@pytest.mark.asyncio
async def test_battery_alert_clears_when_its_battery_sensor_goes_away(
    mock_hass, coordinator
):
    from homeassistant.helpers import entity_registry as er

    _add_batteries(mock_hass)
    coordinator = BehaviourMonitorCoordinator(mock_hass, coordinator._entry)
    _battery_change(coordinator, "sensor.bed_battery", "10")
    coordinator._engine.poll(NOW)
    assert _open_battery_kinds(coordinator) == ["binary_sensor.bed_motion"]
    await coordinator._save()

    reg = er.async_get(mock_hass)
    del reg.entities["sensor.bed_battery"]
    await coordinator._async_registry_updated(SimpleNamespace(data={}))
    coordinator._engine.poll(NOW + timedelta(minutes=1))
    assert _open_battery_kinds(coordinator) == []

    # A restart from the store saved while it was open keeps it cleared.
    store = coordinator._store._data
    for _ in range(2):
        restarted = BehaviourMonitorCoordinator(mock_hass, coordinator._entry)
        restarted._store._data = store
        with patch.object(restarted, "_bootstrap_entities", new=AsyncMock()):
            await restarted.async_setup()
        restarted._engine.poll(NOW + timedelta(minutes=2))
        assert _open_battery_kinds(restarted) == []
        await restarted._save()
        store = restarted._store._data
