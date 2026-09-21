"""Tests for the sensor platform reading the Engine snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

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
        "open_alerts": [{"key": "welfare:house:inactivity"}],
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
    "last_notification": {"timestamp": NOW.isoformat(), "kind": "inactivity"},
    "display_rooms": {"Test House Kitchen": "Kitchen"},
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
        "last_notification",
    ]


def test_welfare_and_house_values_and_display_rooms():
    assert _desc("welfare_status").value_fn(SNAP) == "medium"
    attrs = _desc("welfare_status").extra_attrs_fn(MagicMock(), SNAP)
    assert attrs["reasons"] == ["No activity in Kitchen"]
    assert _desc("house_activity").value_fn(SNAP) == 7200
    h = _desc("house_activity").extra_attrs_fn(MagicMock(), SNAP)
    assert (
        h["last_room"] == "Kitchen"
        and h["rooms_today"] == ["Kitchen"]
        and h["expected_gap_s"] == 600.0
    )


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
    assert _desc("last_notification").value_fn(SNAP) == NOW
    assert _desc("last_notification").value_fn({}) is None


def test_device_info_uses_version_constant(mock_config_entry):
    from custom_components.behaviour_monitor.const import VERSION

    info = device_info(mock_config_entry, "Test House")
    assert info["sw_version"] == VERSION and info["name"] == "Test House"


@pytest.mark.asyncio
async def test_setup_entry_adds_nine_sensors(mock_hass, mock_config_entry):
    coordinator = MagicMock()
    coordinator.data = SNAP
    coordinator.site_name = "Test House"
    mock_hass.data = {"behaviour_monitor": {mock_config_entry.entry_id: coordinator}}
    added = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, added)
    entities = added.call_args.args[0]
    assert len(entities) == 9 and all(
        isinstance(e, BehaviourMonitorSensor) for e in entities
    )
    assert entities[0].native_value == "medium"
