"""Tests for the data update coordinator."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator
from custom_components.behaviour_monitor.const import DOMAIN
from custom_components.behaviour_monitor.ml_analyzer import ML_AVAILABLE


class TestBehaviourMonitorCoordinator:
    """Tests for BehaviourMonitorCoordinator."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator instance."""
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    def test_initialization(
        self, coordinator: BehaviourMonitorCoordinator, mock_config_entry: MagicMock
    ) -> None:
        """Test coordinator initialization."""
        assert coordinator.analyzer is not None
        assert coordinator.ml_analyzer is not None
        assert coordinator.monitored_entities == {"sensor.test1", "sensor.test2"}
        # ML is only enabled if both config requests it AND River is installed
        assert coordinator.ml_enabled == ML_AVAILABLE

    def test_monitored_entities(self, coordinator: BehaviourMonitorCoordinator) -> None:
        """Test monitored entities property."""
        entities = coordinator.monitored_entities
        assert "sensor.test1" in entities
        assert "sensor.test2" in entities

    def test_recent_anomalies_initially_empty(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test recent anomalies is empty initially."""
        assert len(coordinator.recent_anomalies) == 0

    def test_recent_ml_anomalies_initially_empty(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test recent ML anomalies is empty initially."""
        assert len(coordinator.recent_ml_anomalies) == 0

    @pytest.mark.asyncio
    async def test_async_setup_subscribes_to_events(
        self, coordinator: BehaviourMonitorCoordinator, mock_hass: MagicMock
    ) -> None:
        """Test setup subscribes to state changed events."""
        with patch.object(coordinator._store, "async_load", return_value=None):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()

        mock_hass.bus.async_listen.assert_called()

    @pytest.mark.asyncio
    async def test_async_shutdown_saves_data(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test shutdown saves data."""
        # Setup first
        with patch.object(coordinator._store, "async_load", return_value=None):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()

        # Mock the save methods
        with patch.object(coordinator._store, "async_save", new_callable=AsyncMock) as mock_save:
            with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                await coordinator.async_shutdown()

        mock_save.assert_called_once()

    def test_handle_state_changed_ignores_unmonitored(
        self, coordinator: BehaviourMonitorCoordinator, mock_hass: MagicMock
    ) -> None:
        """Test state changed handler ignores unmonitored entities."""
        event = MagicMock()
        event.data = {
            "entity_id": "sensor.unmonitored",
            "old_state": MagicMock(state="off"),
            "new_state": MagicMock(state="on"),
        }

        initial_patterns = len(coordinator.analyzer.patterns)
        coordinator._handle_state_changed(event)

        # Should not have added any patterns
        assert len(coordinator.analyzer.patterns) == initial_patterns

    def test_handle_state_changed_records_monitored(
        self, coordinator: BehaviourMonitorCoordinator, mock_hass: MagicMock
    ) -> None:
        """Test state changed handler records monitored entities."""
        old_state = MagicMock()
        old_state.state = "off"

        new_state = MagicMock()
        new_state.state = "on"

        event = MagicMock()
        event.data = {
            "entity_id": "sensor.test1",
            "old_state": old_state,
            "new_state": new_state,
        }

        coordinator._handle_state_changed(event)

        # Should have recorded the state change
        assert "sensor.test1" in coordinator.analyzer.patterns

    def test_handle_state_changed_ignores_attribute_only_changes(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test state changed handler ignores attribute-only changes when track_attributes is off."""
        # Disable attribute tracking for this test
        coordinator._track_attributes = False

        old_state = MagicMock()
        old_state.state = "on"

        new_state = MagicMock()
        new_state.state = "on"  # Same state

        event = MagicMock()
        event.data = {
            "entity_id": "sensor.test1",
            "old_state": old_state,
            "new_state": new_state,
        }

        initial_count = coordinator.analyzer.get_total_daily_count()
        coordinator._handle_state_changed(event)

        # Count should not change when track_attributes is off
        assert coordinator.analyzer.get_total_daily_count() == initial_count

    def test_handle_state_changed_tracks_attribute_changes_when_enabled(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test state changed handler tracks attribute changes when track_attributes is on."""
        # Enable attribute tracking (should be on by default)
        coordinator._track_attributes = True

        old_state = MagicMock()
        old_state.state = "on"
        old_state.attributes = {"brightness": 100}

        new_state = MagicMock()
        new_state.state = "on"  # Same state
        new_state.attributes = {"brightness": 50}  # Different attributes

        event = MagicMock()
        event.data = {
            "entity_id": "sensor.test1",
            "old_state": old_state,
            "new_state": new_state,
        }

        initial_count = coordinator.analyzer.get_total_daily_count()
        coordinator._handle_state_changed(event)

        # Count should increase when track_attributes is on and attributes changed
        assert coordinator.analyzer.get_total_daily_count() == initial_count + 1

    def test_handle_state_changed_ignores_none_states(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test state changed handler ignores None states."""
        event = MagicMock()
        event.data = {
            "entity_id": "sensor.test1",
            "old_state": None,
            "new_state": MagicMock(state="on"),
        }

        initial_count = coordinator.analyzer.get_total_daily_count()
        coordinator._handle_state_changed(event)

        # Count should not change
        assert coordinator.analyzer.get_total_daily_count() == initial_count

    @pytest.mark.asyncio
    async def test_async_update_data_returns_dict(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test update data returns expected dictionary."""
        with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
            with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                data = await coordinator._async_update_data()

        assert "last_activity" in data
        assert "activity_score" in data
        assert "anomaly_detected" in data
        assert "confidence" in data
        assert "daily_count" in data
        assert "anomalies" in data
        assert "ml_status" in data
        assert "cross_sensor_patterns" in data

    @pytest.mark.asyncio
    async def test_async_update_data_ml_status(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test update data includes ML status."""
        with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
            with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                data = await coordinator._async_update_data()

        ml_status = data["ml_status"]
        assert "enabled" in ml_status
        assert "trained" in ml_status
        assert "sample_count" in ml_status
        # ML is only enabled if River is installed
        assert ml_status["enabled"] == ML_AVAILABLE

    @pytest.mark.asyncio
    async def test_send_notification(
        self, coordinator: BehaviourMonitorCoordinator, mock_hass: MagicMock
    ) -> None:
        """Test sending notification."""
        from custom_components.behaviour_monitor.analyzer import AnomalyResult

        anomaly = AnomalyResult(
            is_anomaly=True,
            entity_id="sensor.test1",
            anomaly_type="unusual_activity",
            z_score=3.5,
            expected_mean=2.0,
            expected_std=0.5,
            actual_value=5.0,
            timestamp=datetime.now(),
            time_slot="monday 09:00",
            description="Test anomaly",
        )

        await coordinator._send_notification([anomaly])

        mock_hass.services.async_call.assert_called_once()
        call_args = mock_hass.services.async_call.call_args
        assert call_args[0][0] == "persistent_notification"
        assert call_args[0][1] == "create"

    @pytest.mark.asyncio
    async def test_send_ml_notification(
        self, coordinator: BehaviourMonitorCoordinator, mock_hass: MagicMock
    ) -> None:
        """Test sending ML notification."""
        from custom_components.behaviour_monitor.ml_analyzer import MLAnomalyResult

        anomaly = MLAnomalyResult(
            is_anomaly=True,
            entity_id="sensor.test1",
            anomaly_score=-0.5,
            anomaly_type="isolation_forest",
            description="Test ML anomaly",
            timestamp=datetime.now(),
            related_entities=[],
        )

        await coordinator._send_ml_notification([anomaly])

        mock_hass.services.async_call.assert_called_once()
        call_args = mock_hass.services.async_call.call_args
        assert call_args[0][0] == "persistent_notification"
        assert call_args[0][1] == "create"


class TestCoordinatorMLIntegration:
    """Tests for coordinator ML integration."""

    @pytest.fixture
    def coordinator_with_ml(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator with ML enabled."""
        mock_config_entry.data["enable_ml"] = True
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    @pytest.fixture
    def coordinator_without_ml(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator with ML disabled."""
        mock_config_entry.data["enable_ml"] = False
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    def test_ml_enabled_property(
        self, coordinator_with_ml: BehaviourMonitorCoordinator
    ) -> None:
        """Test ML enabled property when ML is configured on."""
        # ML is only truly enabled if both config requests it AND River is installed
        assert coordinator_with_ml.ml_enabled == ML_AVAILABLE

    def test_ml_disabled_property(
        self, coordinator_without_ml: BehaviourMonitorCoordinator
    ) -> None:
        """Test ML enabled property when ML is off."""
        assert coordinator_without_ml.ml_enabled is False

    def test_ml_analyzer_exists_when_enabled(
        self, coordinator_with_ml: BehaviourMonitorCoordinator
    ) -> None:
        """Test ML analyzer exists when ML is enabled."""
        assert coordinator_with_ml.ml_analyzer is not None

    @pytest.mark.asyncio
    async def test_check_retrain_not_called_when_ml_disabled(
        self, coordinator_without_ml: BehaviourMonitorCoordinator
    ) -> None:
        """Test retrain check is skipped when ML is disabled."""
        # Should not raise any errors
        await coordinator_without_ml._check_retrain()

    @pytest.mark.asyncio
    async def test_save_data_skips_ml_when_disabled(
        self, coordinator_without_ml: BehaviourMonitorCoordinator
    ) -> None:
        """Test ML data is not saved when ML is disabled."""
        with patch.object(
            coordinator_without_ml._store, "async_save", new_callable=AsyncMock
        ) as mock_stat_save:
            with patch.object(
                coordinator_without_ml._ml_store, "async_save", new_callable=AsyncMock
            ) as mock_ml_save:
                await coordinator_without_ml._save_data()

        mock_stat_save.assert_called_once()
        mock_ml_save.assert_not_called()
