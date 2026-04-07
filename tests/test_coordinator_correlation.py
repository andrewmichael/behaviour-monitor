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


# ---------------------------------------------------------------------------
# Test 6: Break detection wiring in coordinator
# ---------------------------------------------------------------------------


class TestCorrelationBreakDetection:
    """check_breaks is called in _run_detection; welfare excludes CORRELATION_BREAK."""

    def test_run_detection_calls_check_breaks(self) -> None:
        """_run_detection calls check_breaks for each monitored entity with a routine."""
        from custom_components.behaviour_monitor.alert_result import (
            AlertResult,
            AlertSeverity,
            AlertType,
        )

        coord, _ = _make_coordinator(monitored=["sensor.a", "sensor.b"])

        # Give sensor.a a routine entry so it enters the acute/drift loop
        mock_routine = MagicMock()
        mock_routine.activity_tier = None
        coord._routine_model._entities = {"sensor.a": mock_routine}

        break_alert = AlertResult(
            entity_id="sensor.a",
            alert_type=AlertType.CORRELATION_BREAK,
            severity=AlertSeverity.LOW,
            confidence=0.8,
            explanation="correlation break",
            timestamp=NOW.isoformat(),
        )

        coord._correlation_detector = MagicMock()
        coord._correlation_detector.check_breaks.return_value = [break_alert]

        # Mock acute/drift to return nothing
        coord._acute_detector = MagicMock()
        coord._acute_detector.check_inactivity.return_value = None
        coord._acute_detector.check_unusual_time.return_value = None
        coord._drift_detector = MagicMock()
        coord._drift_detector.check.return_value = None

        alerts = coord._run_detection(NOW)

        # check_breaks called for BOTH monitored entities (not just ones with routines)
        assert coord._correlation_detector.check_breaks.call_count == 2
        # The break alert should be in the output
        assert break_alert in alerts

    def test_run_detection_check_breaks_passes_last_seen(self) -> None:
        """check_breaks receives self._last_seen as the last_seen_map argument."""
        coord, _ = _make_coordinator(monitored=["sensor.a"])

        coord._routine_model._entities = {}
        coord._last_seen = {"sensor.a": NOW}

        coord._correlation_detector = MagicMock()
        coord._correlation_detector.check_breaks.return_value = []
        coord._acute_detector = MagicMock()
        coord._drift_detector = MagicMock()

        coord._run_detection(NOW)

        coord._correlation_detector.check_breaks.assert_called_once_with(
            "sensor.a", NOW, coord._last_seen
        )

    def test_derive_welfare_excludes_correlation_breaks(self) -> None:
        """Welfare with only CORRELATION_BREAK alerts returns status 'ok'."""
        from custom_components.behaviour_monitor.alert_result import (
            AlertResult,
            AlertSeverity,
            AlertType,
        )

        coord, _ = _make_coordinator()

        break_alert = AlertResult(
            entity_id="sensor.a",
            alert_type=AlertType.CORRELATION_BREAK,
            severity=AlertSeverity.LOW,
            confidence=0.8,
            explanation="correlation break",
            timestamp=NOW.isoformat(),
        )

        result = coord._derive_welfare([break_alert])
        assert result["status"] == "ok"

    def test_derive_welfare_escalates_with_non_correlation_alerts(self) -> None:
        """MEDIUM inactivity alert drives welfare to 'concern' even with correlation break."""
        from custom_components.behaviour_monitor.alert_result import (
            AlertResult,
            AlertSeverity,
            AlertType,
        )

        coord, _ = _make_coordinator()

        break_alert = AlertResult(
            entity_id="sensor.a",
            alert_type=AlertType.CORRELATION_BREAK,
            severity=AlertSeverity.LOW,
            confidence=0.8,
            explanation="correlation break",
            timestamp=NOW.isoformat(),
        )
        inactivity_alert = AlertResult(
            entity_id="sensor.b",
            alert_type=AlertType.INACTIVITY,
            severity=AlertSeverity.MEDIUM,
            confidence=0.9,
            explanation="inactivity alert",
            timestamp=NOW.isoformat(),
        )

        result = coord._derive_welfare([break_alert, inactivity_alert])
        assert result["status"] == "concern"

    @pytest.mark.asyncio
    async def test_correlation_break_suppression_key(self) -> None:
        """_handle_alerts records suppression key '{entity_id}|correlation_break'."""
        from custom_components.behaviour_monitor.alert_result import (
            AlertResult,
            AlertSeverity,
            AlertType,
        )

        coord, _ = _make_coordinator()
        # Enable notifications so _handle_alerts processes alerts
        coord._enable_notifications = True
        # Lower severity gate so LOW alerts pass through
        coord._min_notification_severity = "minor"

        break_alert = AlertResult(
            entity_id="sensor.a",
            alert_type=AlertType.CORRELATION_BREAK,
            severity=AlertSeverity.LOW,
            confidence=0.8,
            explanation="correlation break",
            timestamp=NOW.isoformat(),
        )

        await coord._handle_alerts([break_alert], NOW)

        assert "sensor.a|correlation_break" in coord._alert_suppression


# ---------------------------------------------------------------------------
# Test 7: Entity removal cleanup during async_setup
# ---------------------------------------------------------------------------


class TestCorrelationEntityRemoval:
    """async_setup purges stale entity correlation state on startup."""

    @pytest.mark.asyncio
    async def test_removes_stale_entities_on_setup(self) -> None:
        """Entities in restored detector state but NOT in _monitored_entities are removed."""
        from custom_components.behaviour_monitor.correlation_detector import (
            CorrelationDetector,
        )

        # Coordinator monitors only sensor.a — sensor.removed is gone from config
        coord, _ = _make_coordinator(monitored=["sensor.a"])

        # Build stored state that includes sensor.removed
        detector = CorrelationDetector(co_occurrence_window_seconds=180)
        detector._entity_event_counts = {"sensor.a": 50, "sensor.removed": 30}
        detector._total_event_count = 80
        detector._pairs[("sensor.a", "sensor.removed")] = MagicMock()
        detector._learned_pairs = {("sensor.a", "sensor.removed")}
        detector._break_cycles = {"sensor.removed": 2}

        stored_data = {
            "correlation_state": detector.to_dict(),
        }
        coord._store.async_load = AsyncMock(return_value=stored_data)

        await coord.async_setup()

        # sensor.removed should be purged from the restored detector
        assert "sensor.removed" not in coord._correlation_detector._entity_event_counts
        assert not any(
            "sensor.removed" in key for key in coord._correlation_detector._pairs
        )
        assert not any(
            "sensor.removed" in key
            for key in coord._correlation_detector._learned_pairs
        )
        assert "sensor.removed" not in coord._correlation_detector._break_cycles

    @pytest.mark.asyncio
    async def test_does_not_remove_monitored_entities(self) -> None:
        """Entities still in _monitored_entities are NOT removed."""
        coord, _ = _make_coordinator(monitored=["sensor.a", "sensor.b"])

        stored_data = {
            "correlation_state": {
                "co_occurrence_window_seconds": 180,
                "min_observations": 10,
                "pmi_threshold": 1.0,
                "pairs": {},
                "learned_pairs": [],
                "entity_event_counts": {"sensor.a": 50, "sensor.b": 30},
                "total_event_count": 80,
                "break_cycles": {},
            },
        }
        coord._store.async_load = AsyncMock(return_value=stored_data)

        await coord.async_setup()

        # Both entities should still be present
        assert "sensor.a" in coord._correlation_detector._entity_event_counts
        assert "sensor.b" in coord._correlation_detector._entity_event_counts

    @pytest.mark.asyncio
    async def test_no_stored_correlation_state_no_removal(self) -> None:
        """No correlation_state in stored data means no remove_entity calls."""
        from custom_components.behaviour_monitor.correlation_detector import (
            CorrelationDetector,
        )

        coord, _ = _make_coordinator(monitored=["sensor.a"])
        original_detector = coord._correlation_detector

        stored_data = {
            "routine_model": coord._routine_model.to_dict(),
        }
        coord._store.async_load = AsyncMock(return_value=stored_data)

        with patch.object(
            CorrelationDetector, "remove_entity"
        ) as mock_remove:
            await coord.async_setup()
            mock_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_event_counts_no_removal(self) -> None:
        """Empty _entity_event_counts means no stale entities to remove."""
        from custom_components.behaviour_monitor.correlation_detector import (
            CorrelationDetector,
        )

        coord, _ = _make_coordinator(monitored=["sensor.a"])

        stored_data = {
            "correlation_state": {
                "co_occurrence_window_seconds": 180,
                "min_observations": 10,
                "pmi_threshold": 1.0,
                "pairs": {},
                "learned_pairs": [],
                "entity_event_counts": {},
                "total_event_count": 0,
                "break_cycles": {},
            },
        }
        coord._store.async_load = AsyncMock(return_value=stored_data)

        with patch.object(
            CorrelationDetector, "remove_entity"
        ) as mock_remove:
            await coord.async_setup()
            mock_remove.assert_not_called()
