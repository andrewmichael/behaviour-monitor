"""Tests for the sensor platform reading the Engine snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from custom_components.behaviour_monitor.sensor import (
    SENSOR_DESCRIPTIONS,
    BehaviourMonitorSensor,
    async_setup_entry,
    device_info,
)

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
SNAP = {
    "site": "Test House",
    "welfare": {
        "status": "medium",
        "reasons": ["No activity in Test House Kitchen"],
        "attention": [
            {
                "id": "a@1",
                "group": "attention",
                "explanation": "Quiet in Test House Kitchen",
            }
        ],
        "information": [
            {
                "id": "i@1",
                "group": "information",
                "explanation": "Test House Kitchen busy",
            }
        ],
    },
    "house": {
        "last_activity": NOW.isoformat(),
        "last_room": "Test House Kitchen",
        "gap_s": 7200.0,
        "expected_s": 600.0,
        "rooms_today": ["Test House Kitchen"],
        "daily_count": 12,
    },
    "anomalies": [{"key": "statistical:sensor.kettle_power:routine_missed"}],
    "health": {
        "states": {"binary_sensor.k": "ok", "binary_sensor.p": "unavailable"},
        "dropouts_today": 1,
        "alerts": [{"key": "health:binary_sensor.p:unavailable"}],
    },
    "learning": {
        "confidence": 100.0,
        "days_seen": 14,
        "days_remaining": 0,
        "first_observation": None,
        "models": {"house": 1.0},
    },
    "entities": {
        "binary_sensor.k": {
            "category": "motion",
            "room": "Test House Kitchen",
            "last_seen": None,
            "expected_hours": [8],
            "health": "ok",
        }
    },
    "chains": [{"name": "A → B", "rooms": ["A", "B"], "hop_median_s": [240.0]}],
    "display_rooms": {"Test House Kitchen": "Kitchen"},
    "snoozed": True,
}


def _desc(key):
    return next(d for d in SENSOR_DESCRIPTIONS if d.key == key)


def test_sensor_keys():
    assert [d.key for d in SENSOR_DESCRIPTIONS] == [
        "welfare_status",
        "house_activity",
        "anomaly",
        "device_health",
        "learning",
        "entity_status",
        "last_activity",
        "daily_activity_count",
    ]


def test_welfare_and_house_values_and_display_rooms():
    assert _desc("welfare_status").value_fn(SNAP) == "medium"
    attrs = _desc("welfare_status").extra_attrs_fn(MagicMock(), SNAP)
    assert attrs["reasons"] == ["No activity in Kitchen"]
    assert set(attrs) >= {"reasons", "attention", "information", "snoozed"}
    assert attrs["snoozed"] is True
    assert "open_alerts" not in attrs
    assert attrs["attention"][0]["explanation"] == "Quiet in Kitchen"
    assert attrs["information"][0]["explanation"] == "Kitchen busy"
    assert _desc("house_activity").value_fn(SNAP) == 7200
    h = _desc("house_activity").extra_attrs_fn(MagicMock(), SNAP)
    assert (
        h["last_room"] == "Kitchen"
        and h["rooms_today"] == ["Kitchen"]
        and h["expected_gap_s"] == 600.0
    )


def test_welfare_status_snoozed_defaults_to_false():
    snap = {k: v for k, v in SNAP.items() if k != "snoozed"}
    attrs = _desc("welfare_status").extra_attrs_fn(MagicMock(), snap)
    assert attrs["snoozed"] is False


def test_anomaly_health_learning_entity_status():
    assert _desc("anomaly").value_fn(SNAP) == 1
    assert _desc("device_health").value_fn(SNAP) == "unavailable"
    assert (
        _desc("device_health").extra_attrs_fn(MagicMock(), SNAP)["dropouts_today"] == 1
    )
    assert _desc("learning").value_fn(SNAP) == 100.0
    assert _desc("entity_status").value_fn(SNAP) == "1 monitored, 0 down"
    es = _desc("entity_status").extra_attrs_fn(MagicMock(), SNAP)["entities"]
    assert es["binary_sensor.k"]["room"] == "Kitchen"


def test_timestamps_and_count():
    assert _desc("last_activity").value_fn(SNAP) == NOW
    assert _desc("last_activity").value_fn({"house": {}}) is None
    assert _desc("daily_activity_count").value_fn(SNAP) == 12


def test_device_info_uses_version_constant(mock_config_entry):
    from custom_components.behaviour_monitor.const import VERSION

    info = device_info(mock_config_entry, "Test House")
    assert info["sw_version"] == VERSION and info["name"] == "Test House"


@pytest.mark.asyncio
async def test_setup_entry_adds_eight_sensors_and_removes_last_notification(
    mock_hass, mock_config_entry
):
    coordinator = MagicMock()
    coordinator.data = SNAP
    coordinator.site_name = "Test House"
    mock_hass.data = {"behaviour_monitor": {mock_config_entry.entry_id: coordinator}}
    added = MagicMock()
    registry = MagicMock()
    registry.async_get_entity_id.return_value = "sensor.test_house_last_notification"
    with patch("custom_components.behaviour_monitor.sensor.er") as er:
        er.async_get.return_value = registry
        await async_setup_entry(mock_hass, mock_config_entry, added)
    registry.async_get_entity_id.assert_called_once_with(
        "sensor", "behaviour_monitor", f"{mock_config_entry.entry_id}_last_notification"
    )
    registry.async_remove.assert_called_once_with("sensor.test_house_last_notification")
    entities = added.call_args.args[0]
    assert len(entities) == 8 and all(
        isinstance(e, BehaviourMonitorSensor) for e in entities
    )
    assert entities[0].native_value == "medium"


@pytest.mark.asyncio
async def test_setup_entry_without_stale_entry_removes_nothing(
    mock_hass, mock_config_entry
):
    coordinator = MagicMock()
    coordinator.data = SNAP
    coordinator.site_name = "Test House"
    mock_hass.data = {"behaviour_monitor": {mock_config_entry.entry_id: coordinator}}
    registry = MagicMock()
    registry.async_get_entity_id.return_value = None
    with patch("custom_components.behaviour_monitor.sensor.er") as er:
        er.async_get.return_value = registry
        await async_setup_entry(mock_hass, mock_config_entry, MagicMock())
    registry.async_remove.assert_not_called()
