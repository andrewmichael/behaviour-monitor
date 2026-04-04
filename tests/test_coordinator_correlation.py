"""Integration tests for CorrelationDetector wiring in coordinator.

Verifies that coordinator correctly:
- Instantiates CorrelationDetector with config window
- Calls record_event on state changes
- Calls recompute() in daily date-change block
- Persists correlation_state via _save_data / async_setup
- Exposes cross_sensor_patterns and correlated_with in sensor data
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
YESTERDAY = NOW - timedelta(days=1)


def _make_config(
    *,
    correlation_window: int = 180,
    monitored: list[str] | None = None,
) -> dict[str, Any]:
    """Return a minimal config entry data dict."""
    return {
        "monitored_entities": monitored or ["sensor.a", "sensor.b"],
        "history_window_days": 28,
        "enable_notifications": False,
        "notify_services": [],
        "notification_cooldown": 30,
        "min_notification_severity": "significant",
        "inactivity_multiplier": 3.0,
        "min_inactivity_multiplier": 1.5,
        "max_inactivity_multiplier": 10.0,
        "drift_sensitivity": "medium",
        "learning_period": 7,
        "track_attributes": True,
        "alert_repeat_interval": 240,
        "activity_tier_override": "auto",
        "correlation_window": correlation_window,
    }


def _make_hass() -> MagicMock:
    """Return a minimal mock HomeAssistant."""
    hass = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    hass.services.async_call = AsyncMock()
    hass.async_create_task = MagicMock()
    return hass


def _make_entry(data: dict[str, Any]) -> MagicMock:
    """Return a mock ConfigEntry with given data."""
    entry = MagicMock()
    entry.data = data
    entry.entry_id = "test_entry_123"
    return entry


def _make_coordinator(
    *,
    correlation_window: int = 180,
    monitored: list[str] | None = None,
):
    """Create a coordinator with mocked HA dependencies."""
    from custom_components.behaviour_monitor.coordinator import (
        BehaviourMonitorCoordinator,
    )

    hass = _make_hass()
    data = _make_config(
        correlation_window=correlation_window,
        monitored=monitored,
    )
    entry = _make_entry(data)
    coord = BehaviourMonitorCoordinator(hass, entry)
    return coord, hass


# ---------------------------------------------------------------------------
# Test 1: __init__ instantiates CorrelationDetector with config window
# ---------------------------------------------------------------------------


class TestCorrelationInit:
    """CorrelationDetector is instantiated in __init__ with config window."""

    def test_detector_created_with_config_window(self) -> None:
        coord, _ = _make_coordinator(correlation_window=300)
        assert hasattr(coord, "_correlation_detector")
        assert coord._correlation_detector._window_seconds == 300

    def test_detector_default_window_when_not_in_config(self) -> None:
        """When correlation_window is absent from config, default is used."""
        from custom_components.behaviour_monitor.const import (
            DEFAULT_CORRELATION_WINDOW,
        )

        hass = _make_hass()
        data = _make_config()
        del data["correlation_window"]  # Remove to test default
        entry = _make_entry(data)

        from custom_components.behaviour_monitor.coordinator import (
            BehaviourMonitorCoordinator,
        )

        coord = BehaviourMonitorCoordinator(hass, entry)
        assert coord._correlation_detector._window_seconds == DEFAULT_CORRELATION_WINDOW


# ---------------------------------------------------------------------------
# Test 2: _handle_state_changed calls record_event
# ---------------------------------------------------------------------------


class TestCorrelationRecordEvent:
    """_handle_state_changed calls record_event on the correlation detector."""

    def test_state_changed_calls_record_event(self) -> None:
        coord, _ = _make_coordinator()
        coord._correlation_detector = MagicMock()

        event = MagicMock()
        event.data = {
            "entity_id": "sensor.a",
            "new_state": MagicMock(state="on"),
            "old_state": None,
        }

        with patch(
            "custom_components.behaviour_monitor.coordinator.dt_util"
        ) as mock_dt:
            mock_dt.now.return_value = NOW
            coord._handle_state_changed(event)

        coord._correlation_detector.record_event.assert_called_once_with(
            "sensor.a", NOW, coord._last_seen
        )

    def test_unmonitored_entity_no_record_event(self) -> None:
        coord, _ = _make_coordinator()
        coord._correlation_detector = MagicMock()

        event = MagicMock()
        event.data = {"entity_id": "sensor.unmonitored", "new_state": MagicMock(state="on")}

        coord._handle_state_changed(event)
        coord._correlation_detector.record_event.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: _async_update_data date-change calls recompute()
# ---------------------------------------------------------------------------


class TestCorrelationRecompute:
    """Daily date-change block calls recompute()."""

    @pytest.mark.asyncio
    async def test_date_change_calls_recompute(self) -> None:
        coord, _ = _make_coordinator()
        coord._correlation_detector = MagicMock()
        # Set today_date to yesterday so the date-change block triggers
        coord._today_date = YESTERDAY.date()

        with patch(
            "custom_components.behaviour_monitor.coordinator.dt_util"
        ) as mock_dt:
            mock_dt.now.return_value = NOW
            # _async_update_data will enter date-change block
            await coord._async_update_data()

        coord._correlation_detector.recompute.assert_called_once()

    @pytest.mark.asyncio
    async def test_same_day_no_recompute(self) -> None:
        coord, _ = _make_coordinator()
        coord._correlation_detector = MagicMock()
        # Set today_date to today so the date-change block does NOT trigger
        coord._today_date = NOW.date()

        with patch(
            "custom_components.behaviour_monitor.coordinator.dt_util"
        ) as mock_dt:
            mock_dt.now.return_value = NOW
            await coord._async_update_data()

        coord._correlation_detector.recompute.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: _save_data includes correlation_state
# ---------------------------------------------------------------------------


class TestCorrelationPersistence:
    """Persistence: to_dict in _save_data, from_dict in async_setup."""

    @pytest.mark.asyncio
    async def test_save_data_includes_correlation_state(self) -> None:
        coord, _ = _make_coordinator()
        coord._correlation_detector = MagicMock()
        coord._correlation_detector.to_dict.return_value = {"test": "data"}
        coord._store = MagicMock()
        coord._store.async_save = AsyncMock()

        await coord._save_data()

        call_args = coord._store.async_save.call_args[0][0]
        assert "correlation_state" in call_args
        assert call_args["correlation_state"] == {"test": "data"}

    @pytest.mark.asyncio
    async def test_async_setup_restores_correlation_state(self) -> None:
        """async_setup calls from_dict when correlation_state exists."""
        from custom_components.behaviour_monitor.correlation_detector import (
            CorrelationDetector,
        )

        coord, _ = _make_coordinator()
        stored_data = {
            "correlation_state": {
                "co_occurrence_window_seconds": 120,
                "min_observations": 10,
                "pmi_threshold": 1.0,
                "pairs": {},
                "learned_pairs": [],
                "entity_event_counts": {},
                "total_event_count": 0,
            },
        }
        coord._store.async_load = AsyncMock(return_value=stored_data)

        with patch.object(
            CorrelationDetector, "from_dict", return_value=MagicMock()
        ) as mock_from_dict:
            await coord.async_setup()
            mock_from_dict.assert_called_once_with(stored_data["correlation_state"])

    @pytest.mark.asyncio
    async def test_async_setup_missing_correlation_state_graceful(self) -> None:
        """Missing correlation_state in stored data creates fresh detector."""
        coord, _ = _make_coordinator()
        stored_data = {
            "routine_model": coord._routine_model.to_dict(),
        }
        coord._store.async_load = AsyncMock(return_value=stored_data)

        original_detector = coord._correlation_detector
        await coord.async_setup()

        # Should still have a detector (the original one, not replaced)
        assert coord._correlation_detector is original_detector


# ---------------------------------------------------------------------------
# Test 5: _build_sensor_data populates cross_sensor_patterns
# ---------------------------------------------------------------------------


class TestCorrelationSensorData:
    """_build_sensor_data exposes correlation data in sensor attributes."""

    def test_cross_sensor_patterns_from_detector(self) -> None:
        coord, _ = _make_coordinator()
        coord._correlation_detector = MagicMock()
        coord._correlation_detector.get_correlation_groups.return_value = [
            {
                "entities": ["sensor.a", "sensor.b"],
                "co_occurrence_rate": 0.85,
                "total_observations": 42,
            }
        ]
        coord._correlation_detector.get_correlated_entities.return_value = []

        data = coord._build_sensor_data([], NOW)
        assert data["cross_sensor_patterns"] == [
            {
                "entities": ["sensor.a", "sensor.b"],
                "co_occurrence_rate": 0.85,
                "total_observations": 42,
            }
        ]

    def test_entity_status_includes_correlated_with(self) -> None:
        coord, _ = _make_coordinator(monitored=["sensor.a", "sensor.b"])
        coord._correlation_detector = MagicMock()
        coord._correlation_detector.get_correlation_groups.return_value = []
        coord._correlation_detector.get_correlated_entities.side_effect = (
            lambda eid: ["sensor.b"] if eid == "sensor.a" else []
        )

        # Need last_seen for entity_status to show "active"
        coord._last_seen = {"sensor.a": NOW, "sensor.b": NOW}

        # Mock routine_model to avoid real learning_status calls
        mock_routine_a = MagicMock()
        mock_routine_a.activity_tier = None
        mock_routine_a.daily_activity_rate.return_value = 10
        mock_routine_a.expected_gap_seconds.return_value = 3600
        mock_routine_a.first_observation = None
        mock_routine_b = MagicMock()
        mock_routine_b.activity_tier = None
        mock_routine_b.daily_activity_rate.return_value = 5
        mock_routine_b.expected_gap_seconds.return_value = 7200
        mock_routine_b.first_observation = None
        coord._routine_model = MagicMock()
        coord._routine_model._entities = {
            "sensor.a": mock_routine_a,
            "sensor.b": mock_routine_b,
        }
        coord._routine_model.overall_confidence.return_value = 0.8
        coord._routine_model.learning_status.return_value = "ready"

        data = coord._build_sensor_data([], NOW)
        statuses = data["entity_status"]

        # Find sensor.a entry
        sa = next(s for s in statuses if s["entity_id"] == "sensor.a")
        assert sa["correlated_with"] == ["sensor.b"]

        sb = next(s for s in statuses if s["entity_id"] == "sensor.b")
        assert sb["correlated_with"] == []

    def test_empty_cross_sensor_patterns_when_no_learned(self) -> None:
        coord, _ = _make_coordinator()
        coord._correlation_detector = MagicMock()
        coord._correlation_detector.get_correlation_groups.return_value = []
        coord._correlation_detector.get_correlated_entities.return_value = []

        data = coord._build_sensor_data([], NOW)
        assert data["cross_sensor_patterns"] == []
