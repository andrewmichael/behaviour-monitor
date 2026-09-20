"""Tests for the Home Assistant coordinator around the core Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator
from custom_components.behaviour_monitor.core.alert_router import DeliveryAction
from custom_components.behaviour_monitor.core.alerts import Alert, AlertClass, Severity
from custom_components.behaviour_monitor.core.events import Category

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)


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
    mock_hass.bus.async_listen.assert_any_call(
        "state_changed", coordinator._handle_state_changed
    )


@pytest.mark.asyncio
async def test_state_change_feeds_engine_and_panic_pushes(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch(
        "custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW
    ):
        event = SimpleNamespace(
            data={
                "entity_id": "binary_sensor.panic",
                "old_state": _state("binary_sensor.panic", "off"),
                "new_state": _state("binary_sensor.panic", "on"),
            }
        )
        coordinator._handle_state_changed(event)
        await coordinator._flush_actions()
    calls = [c.args[:2] for c in mock_hass.services.async_call.await_args_list]
    assert ("notify", "mobile_app_phone") in calls
    assert ("persistent_notification", "create") in calls
    assert coordinator.data is None or coordinator.data["welfare"]["status"] in (
        "learning",
        "critical",
    )


@pytest.mark.asyncio
async def test_delivery_actions_map_to_services_issues_and_logbook(
    coordinator, mock_hass
):
    from homeassistant.helpers import issue_registry as ir

    ir.async_create_issue.reset_mock()
    ir.async_delete_issue.reset_mock()
    welfare = Alert(
        AlertClass.WELFARE, "house", "inactivity", Severity.HIGH, "No activity", NOW
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
            DeliveryAction("push", welfare),
            DeliveryAction("repair_create", health),
            DeliveryAction("log", stat),
        ],
        NOW,
    )
    notify = [
        c
        for c in mock_hass.services.async_call.await_args_list
        if c.args[:2] == ("notify", "mobile_app_phone")
    ]
    assert (
        notify
        and notify[0].args[2]["title"] == "Test House welfare"
        and notify[0].args[2]["message"] == "No activity"
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
    assert coordinator.last_notification == {
        "timestamp": NOW.isoformat(),
        "kind": "inactivity",
    }
    await coordinator._perform(
        [
            DeliveryAction("push_clear", welfare),
            DeliveryAction("repair_delete", health),
        ],
        NOW,
    )
    ir.async_delete_issue.assert_called_once()
    assert ("persistent_notification", "dismiss") in [
        c.args[:2] for c in mock_hass.services.async_call.await_args_list
    ]


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
async def test_holiday_snooze_ack_reset_roundtrip(coordinator):
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
    await coordinator.async_acknowledge()
    saved = coordinator._store._data
    assert saved["engine"]["schema"] == 2 and saved["site"] == "Test House"


@pytest.mark.asyncio
async def test_test_panic_pushes_without_learning(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    before = coordinator._engine.to_dict()["house"]
    await coordinator.async_test_panic()
    assert ("notify", "mobile_app_phone") in [
        c.args[:2] for c in mock_hass.services.async_call.await_args_list
    ]
    assert coordinator._engine.to_dict()["house"] == before


@pytest.mark.asyncio
async def test_registry_update_reresolves_rooms(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    from homeassistant.helpers import entity_registry as er

    er.async_get(mock_hass).areas["a_bed"] = SimpleNamespace(name="Back Bedroom")
    await coordinator._async_registry_updated(SimpleNamespace(data={}))
    assert {s.room for s in coordinator.entity_specs} >= {"Back Bedroom"}
