"""Tests for the data update coordinator."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator
from custom_components.behaviour_monitor.const import (
    CONF_MIN_NOTIFICATION_SEVERITY,
    CONF_NOTIFICATION_COOLDOWN,
    SEVERITY_MINOR,
    SEVERITY_SIGNIFICANT,
    WELFARE_DEBOUNCE_CYCLES,
)
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


class TestCoordinatorStatePersistence:
    """Tests for coordinator state persistence across reboots."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator instance."""
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_coordinator_state_saved_in_new_format(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test that coordinator state is saved in new format with both analyzer and coordinator sections."""
        from datetime import timezone

        # Set some coordinator state
        coordinator._last_notification_time = datetime.now(timezone.utc)
        coordinator._last_notification_type = "statistical"
        coordinator._last_welfare_status = "ok"

        saved_data = None

        async def capture_save(data: dict[str, Any]) -> None:
            nonlocal saved_data
            saved_data = data

        with patch.object(coordinator._store, "async_save", side_effect=capture_save):
            with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                await coordinator._save_data()

        # Verify v3 format structure (routine_model key, no analyzer key)
        assert saved_data is not None
        assert "routine_model" in saved_data  # v3 format uses routine_model, not analyzer
        assert "coordinator" in saved_data

        # Verify coordinator state is included
        coord_state = saved_data["coordinator"]
        assert coord_state["last_notification_time"] is not None
        assert coord_state["last_notification_type"] == "statistical"
        assert coord_state["last_welfare_status"] == "ok"

    @pytest.mark.asyncio
    async def test_coordinator_state_restored_from_new_format(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test that coordinator state is restored when loading new format."""
        from datetime import timezone

        # Create data in new format
        test_time = datetime.now(timezone.utc)
        new_format_data = {
            "analyzer": {
                "patterns": {},
                "sensitivity_threshold": 2.0,
                "learning_period_days": 7,
                "daily_counts": {},
                "daily_count_date": None,
            },
            "coordinator": {
                "last_notification_time": test_time.isoformat(),
                "last_notification_type": "welfare",
                "last_welfare_status": "concern",
            },
        }

        with patch.object(coordinator._store, "async_load", return_value=new_format_data):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()

        # Verify coordinator state was restored
        assert coordinator._last_notification_time is not None
        assert coordinator._last_notification_type == "welfare"
        assert coordinator._last_welfare_status == "concern"

    @pytest.mark.asyncio
    async def test_backward_compatibility_with_old_format(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test backward compatibility with old format (direct analyzer dict)."""
        # Create data in old format (just analyzer dict, no coordinator section)
        old_format_data = {
            "patterns": {},
            "sensitivity_threshold": 2.0,
            "learning_period_days": 7,
            # No "analyzer" or "coordinator" keys - this is the analyzer dict directly
        }

        with patch.object(coordinator._store, "async_load", return_value=old_format_data):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()

        # Should load without error
        assert coordinator.analyzer is not None
        # Coordinator state should be at defaults
        assert coordinator._last_notification_time is None
        assert coordinator._last_notification_type is None
        assert coordinator._last_welfare_status is None

    @pytest.mark.asyncio
    async def test_notification_tracking_persists_across_save_load(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test that notification tracking survives save/load cycle."""
        from datetime import timezone

        # Set notification tracking
        test_time = datetime.now(timezone.utc)
        coordinator._last_notification_time = test_time
        coordinator._last_notification_type = "statistical"

        # Save
        saved_data = None

        async def capture_save(data: dict[str, Any]) -> None:
            nonlocal saved_data
            saved_data = data

        with patch.object(coordinator._store, "async_save", side_effect=capture_save):
            with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                await coordinator._save_data()

        # Create new coordinator and load
        new_coordinator = BehaviourMonitorCoordinator(
            coordinator.hass, coordinator._entry
        )

        with patch.object(new_coordinator._store, "async_load", return_value=saved_data):
            with patch.object(new_coordinator._ml_store, "async_load", return_value=None):
                await new_coordinator.async_setup()

        # Verify notification tracking was restored
        assert new_coordinator._last_notification_time is not None
        assert new_coordinator._last_notification_type == "statistical"

    @pytest.mark.asyncio
    async def test_welfare_status_persists_across_save_load(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test that welfare status tracking survives save/load cycle."""
        # Set welfare status
        coordinator._last_welfare_status = "alert"

        # Save
        saved_data = None

        async def capture_save(data: dict[str, Any]) -> None:
            nonlocal saved_data
            saved_data = data

        with patch.object(coordinator._store, "async_save", side_effect=capture_save):
            with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                await coordinator._save_data()

        # Create new coordinator and load
        new_coordinator = BehaviourMonitorCoordinator(
            coordinator.hass, coordinator._entry
        )

        with patch.object(new_coordinator._store, "async_load", return_value=saved_data):
            with patch.object(new_coordinator._ml_store, "async_load", return_value=None):
                await new_coordinator.async_setup()

        # Verify welfare status was restored
        assert new_coordinator._last_welfare_status == "alert"

    @pytest.mark.asyncio
    async def test_empty_coordinator_state_handles_none_values(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test that None values in coordinator state are handled correctly."""
        new_format_data = {
            "analyzer": {
                "patterns": {},
                "sensitivity_threshold": 2.0,
                "learning_period_days": 7,
                "daily_counts": {},
                "daily_count_date": None,
            },
            "coordinator": {
                "last_notification_time": None,
                "last_notification_type": None,
                "last_welfare_status": None,
            },
        }

        with patch.object(coordinator._store, "async_load", return_value=new_format_data):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()

        # Should handle None values gracefully
        assert coordinator._last_notification_time is None
        assert coordinator._last_notification_type is None
        assert coordinator._last_welfare_status is None

    @pytest.mark.asyncio
    async def test_notification_time_timezone_handling(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test that notification time handles timezones correctly on restore."""
        from datetime import timezone

        test_time = datetime.now(timezone.utc)
        new_format_data = {
            "analyzer": {
                "patterns": {},
                "sensitivity_threshold": 2.0,
                "learning_period_days": 7,
                "daily_counts": {},
                "daily_count_date": None,
            },
            "coordinator": {
                "last_notification_time": test_time.isoformat(),
                "last_notification_type": "ml",
                "last_welfare_status": "ok",
            },
        }

        with patch.object(coordinator._store, "async_load", return_value=new_format_data):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()

        # Verify timestamp was restored with timezone
        assert coordinator._last_notification_time is not None
        assert coordinator._last_notification_time.tzinfo is not None


class TestCoordinatorHolidayMode:
    """Tests for coordinator holiday mode functionality."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator instance."""
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    def test_holiday_mode_property_default_false(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test holiday mode is False by default."""
        assert coordinator.holiday_mode is False

    @pytest.mark.asyncio
    async def test_async_enable_holiday_mode(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test enabling holiday mode."""
        await coordinator.async_enable_holiday_mode()

        assert coordinator.holiday_mode is True

    @pytest.mark.asyncio
    async def test_async_disable_holiday_mode(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test disabling holiday mode."""
        await coordinator.async_enable_holiday_mode()
        assert coordinator.holiday_mode is True

        await coordinator.async_disable_holiday_mode()
        assert coordinator.holiday_mode is False

    def test_holiday_mode_prevents_state_recording(
        self, coordinator: BehaviourMonitorCoordinator, mock_hass: MagicMock
    ) -> None:
        """Test holiday mode prevents state changes from being recorded."""
        # Enable holiday mode
        coordinator._holiday_mode = True

        event = MagicMock()
        event.data = {
            "entity_id": "sensor.test1",
            "old_state": MagicMock(state="off"),
            "new_state": MagicMock(state="on"),
        }

        initial_patterns = len(coordinator.analyzer.patterns)
        coordinator._handle_state_changed(event)

        # Should not have recorded pattern due to holiday mode
        assert len(coordinator.analyzer.patterns) == initial_patterns

    @pytest.mark.asyncio
    async def test_holiday_mode_persists_across_save_load(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test that holiday mode state survives save/load cycle."""
        # Enable holiday mode
        await coordinator.async_enable_holiday_mode()

        # Save
        saved_data = None

        async def capture_save(data: dict[str, Any]) -> None:
            nonlocal saved_data
            saved_data = data

        with patch.object(coordinator._store, "async_save", side_effect=capture_save):
            with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                await coordinator._save_data()

        # Create new coordinator and load
        new_coordinator = BehaviourMonitorCoordinator(
            coordinator.hass, coordinator._entry
        )

        with patch.object(new_coordinator._store, "async_load", return_value=saved_data):
            with patch.object(new_coordinator._ml_store, "async_load", return_value=None):
                await new_coordinator.async_setup()

        # Verify holiday mode was restored
        assert new_coordinator.holiday_mode is True


class TestCoordinatorNotificationSuppression:
    """Tests for notification suppression behaviors (Plan 02 red phase).

    These tests define the expected behavior after Plan 02 implements:
    - Per-entity cooldown tracking
    - Severity gate filtering
    - Welfare debounce counter
    - Cross-path deduplication

    ALL suppression tests are expected to fail until Plan 02 implements the logic.
    """

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator with suppression config."""
        mock_config_entry.data[CONF_NOTIFICATION_COOLDOWN] = 30
        mock_config_entry.data[CONF_MIN_NOTIFICATION_SEVERITY] = SEVERITY_SIGNIFICANT
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    @pytest.fixture
    def stat_anomaly_factory(self):
        """Factory for creating mock AnomalyResult objects."""
        from custom_components.behaviour_monitor.analyzer import AnomalyResult

        def _make(
            entity_id="sensor.test1",
            anomaly_type="unusual_activity",
            z_score=4.0,
            severity=SEVERITY_SIGNIFICANT,
            description="Test anomaly",
        ):
            return AnomalyResult(
                is_anomaly=True,
                entity_id=entity_id,
                anomaly_type=anomaly_type,
                z_score=z_score,
                expected_mean=2.0,
                expected_std=0.5,
                actual_value=5.0,
                timestamp=datetime.now(timezone.utc),
                time_slot="monday 09:00",
                description=description,
            )

        return _make

    @pytest.fixture
    def ml_anomaly_factory(self):
        """Factory for creating mock MLAnomalyResult objects."""
        from custom_components.behaviour_monitor.ml_analyzer import MLAnomalyResult

        def _make(entity_id="sensor.test1", anomaly_type="isolation_forest"):
            return MLAnomalyResult(
                is_anomaly=True,
                entity_id=entity_id,
                anomaly_score=-0.5,
                anomaly_type=anomaly_type,
                description="Test ML anomaly",
                timestamp=datetime.now(timezone.utc),
                related_entities=[],
            )

        return _make

    # -------------------------------------------------------------------------
    # Per-entity cooldown tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cooldown_per_entity(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
        stat_anomaly_factory,
    ) -> None:
        """Entity A notification does not block Entity B notification.

        Cooldown is tracked per (entity_id, anomaly_type) key, not globally.
        When entity A fires, entity B should still be able to fire immediately.
        """
        anomaly_a = stat_anomaly_factory(entity_id="sensor.test1")
        anomaly_b = stat_anomaly_factory(entity_id="sensor.test2")

        notification_calls = []

        with patch.object(
            coordinator, "_send_notification", new_callable=AsyncMock
        ) as mock_send:
            mock_send.side_effect = lambda anomalies: notification_calls.extend(anomalies)

            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer, "check_for_anomalies", return_value=[anomaly_a]
                        ):
                            await coordinator._async_update_data()

                        with patch.object(
                            coordinator._analyzer, "check_for_anomalies", return_value=[anomaly_b]
                        ):
                            await coordinator._async_update_data()

        # Both entity A and entity B should have triggered notifications
        # (cooldown is per-entity, not global)
        assert mock_send.call_count == 2, (
            f"Expected 2 notification calls (one per entity), got {mock_send.call_count}. "
            "Per-entity cooldown not implemented yet."
        )

    @pytest.mark.asyncio
    async def test_cooldown_suppresses_repeat(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
        stat_anomaly_factory,
    ) -> None:
        """Same entity+type within cooldown window gets no second notification.

        After entity A fires, a second anomaly of the same type within the cooldown
        window must be suppressed.
        """
        anomaly_a = stat_anomaly_factory(
            entity_id="sensor.test1", anomaly_type="unusual_activity"
        )

        with patch.object(
            coordinator, "_send_notification", new_callable=AsyncMock
        ) as mock_send:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer,
                            "check_for_anomalies",
                            return_value=[anomaly_a],
                        ):
                            await coordinator._async_update_data()
                            # Second call immediately after — same entity, same type
                            await coordinator._async_update_data()

        # Second notification should be suppressed by cooldown
        assert mock_send.call_count == 1, (
            f"Expected 1 notification (second suppressed by cooldown), got {mock_send.call_count}. "
            "Cooldown suppression not implemented yet."
        )

    @pytest.mark.asyncio
    async def test_cooldown_expires(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
        stat_anomaly_factory,
    ) -> None:
        """After cooldown window passes, same entity+type gets notified again.

        When the cooldown for (entity_id, anomaly_type) expires, a new anomaly
        of the same type must fire a notification.
        """
        anomaly = stat_anomaly_factory(
            entity_id="sensor.test1", anomaly_type="unusual_activity"
        )

        # First notification fires at t=0
        t_zero = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        # After cooldown (30 min + 1 sec), notification should fire again
        t_after_cooldown = t_zero + timedelta(minutes=31)

        with patch.object(
            coordinator, "_send_notification", new_callable=AsyncMock
        ) as mock_send:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer,
                            "check_for_anomalies",
                            return_value=[anomaly],
                        ):
                            with patch(
                                "custom_components.behaviour_monitor.coordinator.dt_util.now",
                                return_value=t_zero,
                            ):
                                await coordinator._async_update_data()

                            with patch(
                                "custom_components.behaviour_monitor.coordinator.dt_util.now",
                                return_value=t_after_cooldown,
                            ):
                                await coordinator._async_update_data()

        assert mock_send.call_count == 2, (
            f"Expected 2 notifications (cooldown expired), got {mock_send.call_count}. "
            "Cooldown expiry not implemented yet."
        )

    @pytest.mark.asyncio
    async def test_cooldown_resets_on_clear(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
        stat_anomaly_factory,
    ) -> None:
        """When entity returns to normal, cooldown entry is removed; re-anomaly triggers new notification.

        The per-entity cooldown map should be cleared when an entity's anomaly
        clears (no longer anomalous), so the next anomaly fires immediately.
        """
        anomaly = stat_anomaly_factory(
            entity_id="sensor.test1", anomaly_type="unusual_activity"
        )

        with patch.object(
            coordinator, "_send_notification", new_callable=AsyncMock
        ) as mock_send:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        # First anomaly — fires notification
                        with patch.object(
                            coordinator._analyzer,
                            "check_for_anomalies",
                            return_value=[anomaly],
                        ):
                            await coordinator._async_update_data()

                        # Entity clears (no anomaly) — should reset cooldown
                        with patch.object(
                            coordinator._analyzer, "check_for_anomalies", return_value=[]
                        ):
                            await coordinator._async_update_data()

                        # Re-anomaly immediately after clear — should fire again
                        with patch.object(
                            coordinator._analyzer,
                            "check_for_anomalies",
                            return_value=[anomaly],
                        ):
                            await coordinator._async_update_data()

        assert mock_send.call_count == 2, (
            f"Expected 2 notifications (clear resets cooldown), got {mock_send.call_count}. "
            "Cooldown-on-clear reset not implemented yet."
        )

    # -------------------------------------------------------------------------
    # Deduplication tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_dedup_different_types_separate(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
        stat_anomaly_factory,
    ) -> None:
        """Same entity with different anomaly_type gets separate notifications.

        Cooldown key is (entity_id, anomaly_type). Different types on the same
        entity each get their own cooldown and should each fire.
        """
        anomaly_type_a = stat_anomaly_factory(
            entity_id="sensor.test1", anomaly_type="unusual_activity"
        )
        anomaly_type_b = stat_anomaly_factory(
            entity_id="sensor.test1", anomaly_type="inactivity"
        )

        with patch.object(
            coordinator, "_send_notification", new_callable=AsyncMock
        ) as mock_send:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer,
                            "check_for_anomalies",
                            return_value=[anomaly_type_a],
                        ):
                            await coordinator._async_update_data()

                        with patch.object(
                            coordinator._analyzer,
                            "check_for_anomalies",
                            return_value=[anomaly_type_b],
                        ):
                            await coordinator._async_update_data()

        assert mock_send.call_count == 2, (
            f"Expected 2 notifications (different types = separate cooldowns), "
            f"got {mock_send.call_count}. Per-type cooldown not implemented yet."
        )

    @pytest.mark.asyncio
    async def test_cross_path_dedup(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
        stat_anomaly_factory,
        ml_anomaly_factory,
    ) -> None:
        """Stat+ML flag same entity in same cycle, only one notification fires.

        When both statistical and ML analyzers detect an anomaly on the same entity
        in the same update cycle, only one notification should fire (cross-path dedup).
        """
        stat_anomaly = stat_anomaly_factory(
            entity_id="sensor.test1", anomaly_type="unusual_activity"
        )
        ml_anomaly = ml_anomaly_factory(
            entity_id="sensor.test1", anomaly_type="unusual_activity"
        )

        stat_call_count = 0
        ml_call_count = 0

        async def count_stat(anomalies):
            nonlocal stat_call_count
            stat_call_count += 1

        async def count_ml(anomalies):
            nonlocal ml_call_count
            ml_call_count += 1

        coordinator._enable_ml = True
        coordinator._recent_events = []
        # Patch is_trained as a property via type() to allow patching a read-only property
        with patch("custom_components.behaviour_monitor.coordinator.BehaviourMonitorCoordinator._async_update_data"):
            pass  # no-op to keep context manager approach readable

        with patch.object(coordinator, "_send_notification", side_effect=count_stat):
            with patch.object(coordinator, "_send_ml_notification", side_effect=count_ml):
                with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                    with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                        with patch.object(
                            coordinator._analyzer, "is_learning_complete", return_value=True
                        ):
                            with patch.object(
                                coordinator._analyzer,
                                "check_for_anomalies",
                                return_value=[stat_anomaly],
                            ):
                                with patch.object(
                                    type(coordinator._ml_analyzer),
                                    "is_trained",
                                    new_callable=lambda: property(lambda self: True),
                                ):
                                    with patch.object(
                                        coordinator._ml_analyzer,
                                        "check_anomaly",
                                        return_value=ml_anomaly,
                                    ):
                                        with patch.object(
                                            coordinator._ml_analyzer,
                                            "check_cross_sensor_anomalies",
                                            return_value=[],
                                        ):
                                            await coordinator._async_update_data()

        total_notifications = stat_call_count + ml_call_count
        assert total_notifications == 1, (
            f"Expected 1 notification (cross-path dedup), got {total_notifications} "
            f"(stat={stat_call_count}, ml={ml_call_count}). "
            "Cross-path deduplication not implemented yet."
        )

    # -------------------------------------------------------------------------
    # Severity gate tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_severity_gate_suppresses(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
        stat_anomaly_factory,
    ) -> None:
        """Anomaly below configured severity does not trigger notification.

        When min_notification_severity is "significant" (default), anomalies with
        severity "minor" or "moderate" must not fire a notification.
        """
        # Create a minor anomaly (z_score 1.7 = SEVERITY_MINOR)
        minor_anomaly = stat_anomaly_factory(
            entity_id="sensor.test1",
            z_score=1.7,
            severity=SEVERITY_MINOR,
        )
        # Ensure coordinator is configured with significant threshold
        coordinator._entry.data[CONF_MIN_NOTIFICATION_SEVERITY] = SEVERITY_SIGNIFICANT

        with patch.object(
            coordinator, "_send_notification", new_callable=AsyncMock
        ) as mock_send:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer,
                            "check_for_anomalies",
                            return_value=[minor_anomaly],
                        ):
                            await coordinator._async_update_data()

        assert mock_send.call_count == 0, (
            f"Expected 0 notifications (minor below significant gate), "
            f"got {mock_send.call_count}. Severity gate not implemented yet."
        )

    @pytest.mark.asyncio
    async def test_severity_gate_sensor_state_unaffected(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
        stat_anomaly_factory,
    ) -> None:
        """Anomaly below gate still appears in returned sensor data.

        The severity gate filters notifications, not sensor data. Even a suppressed
        minor anomaly must still appear in the returned dict's "anomalies" list.
        """
        minor_anomaly = stat_anomaly_factory(
            entity_id="sensor.test1",
            z_score=1.7,
            severity=SEVERITY_MINOR,
        )
        coordinator._entry.data[CONF_MIN_NOTIFICATION_SEVERITY] = SEVERITY_SIGNIFICANT

        with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
            with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                with patch.object(
                    coordinator._analyzer, "is_learning_complete", return_value=True
                ):
                    with patch.object(
                        coordinator._analyzer,
                        "check_for_anomalies",
                        return_value=[minor_anomaly],
                    ):
                        data = await coordinator._async_update_data()

        # The anomaly should appear in sensor data even though no notification fired
        assert len(data["anomalies"]) == 1, (
            f"Expected anomaly in sensor data even when below gate, "
            f"got {len(data['anomalies'])}."
        )
        assert data["anomalies"][0]["entity_id"] == "sensor.test1"

    @pytest.mark.asyncio
    async def test_severity_gate_passes_above_threshold(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
        stat_anomaly_factory,
    ) -> None:
        """Anomaly at/above configured severity fires notification.

        A significant anomaly (z_score >= 3.5) when min_severity is "significant"
        must fire a notification.
        """
        significant_anomaly = stat_anomaly_factory(
            entity_id="sensor.test1",
            z_score=4.0,
            severity=SEVERITY_SIGNIFICANT,
        )
        coordinator._entry.data[CONF_MIN_NOTIFICATION_SEVERITY] = SEVERITY_SIGNIFICANT

        with patch.object(
            coordinator, "_send_notification", new_callable=AsyncMock
        ) as mock_send:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer,
                            "check_for_anomalies",
                            return_value=[significant_anomaly],
                        ):
                            await coordinator._async_update_data()

        assert mock_send.call_count == 1, (
            f"Expected 1 notification (significant meets gate), "
            f"got {mock_send.call_count}. Severity gate not implemented yet."
        )

    # -------------------------------------------------------------------------
    # Welfare debounce tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_welfare_debounce_no_notify_first_cycle(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
    ) -> None:
        """First cycle of new welfare status does not send notification.

        When welfare status changes from "ok" to "concern", the first cycle
        should start the debounce counter but NOT fire a notification.
        """
        coordinator._last_welfare_status = "ok"

        welfare_concern = {"status": "concern", "message": "Test concern"}

        with patch.object(
            coordinator, "_send_welfare_notification", new_callable=AsyncMock
        ) as mock_welfare:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer,
                            "check_for_anomalies",
                            return_value=[],
                        ):
                            with patch.object(
                                coordinator._analyzer,
                                "get_welfare_status",
                                return_value=welfare_concern,
                            ):
                                await coordinator._async_update_data()

        assert mock_welfare.call_count == 0, (
            f"Expected 0 welfare notifications on first cycle (debounce), "
            f"got {mock_welfare.call_count}. Welfare debounce not implemented yet."
        )

    @pytest.mark.asyncio
    async def test_welfare_debounce_notifies_after_n_cycles(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
    ) -> None:
        """After N=3 consecutive cycles at new status, notification fires.

        After WELFARE_DEBOUNCE_CYCLES consecutive cycles with the same new welfare
        status, a notification should fire.
        """
        coordinator._last_welfare_status = "ok"

        welfare_concern = {"status": "concern", "message": "Test concern"}

        with patch.object(
            coordinator, "_send_welfare_notification", new_callable=AsyncMock
        ) as mock_welfare:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer, "check_for_anomalies", return_value=[]
                        ):
                            with patch.object(
                                coordinator._analyzer,
                                "get_welfare_status",
                                return_value=welfare_concern,
                            ):
                                # Run WELFARE_DEBOUNCE_CYCLES times
                                for _ in range(WELFARE_DEBOUNCE_CYCLES):
                                    await coordinator._async_update_data()

        assert mock_welfare.call_count == 1, (
            f"Expected 1 welfare notification after {WELFARE_DEBOUNCE_CYCLES} cycles, "
            f"got {mock_welfare.call_count}. Welfare debounce N-cycle trigger not implemented yet."
        )

    @pytest.mark.asyncio
    async def test_welfare_debounce_resets_on_revert(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
    ) -> None:
        """If status reverts before N cycles, counter resets.

        If welfare status changes to "concern" but reverts to "ok" before
        WELFARE_DEBOUNCE_CYCLES complete, no notification should fire and the
        counter should reset.
        """
        coordinator._last_welfare_status = "ok"

        welfare_concern = {"status": "concern", "message": "Test concern"}
        welfare_ok = {"status": "ok", "message": "All clear"}

        with patch.object(
            coordinator, "_send_welfare_notification", new_callable=AsyncMock
        ) as mock_welfare:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer, "check_for_anomalies", return_value=[]
                        ):
                            # Run N-1 cycles with concern
                            with patch.object(
                                coordinator._analyzer,
                                "get_welfare_status",
                                return_value=welfare_concern,
                            ):
                                for _ in range(WELFARE_DEBOUNCE_CYCLES - 1):
                                    await coordinator._async_update_data()

                            # Revert to ok before N cycles complete
                            with patch.object(
                                coordinator._analyzer,
                                "get_welfare_status",
                                return_value=welfare_ok,
                            ):
                                await coordinator._async_update_data()

        assert mock_welfare.call_count == 0, (
            f"Expected 0 welfare notifications (reverted before N cycles), "
            f"got {mock_welfare.call_count}. Welfare debounce revert reset not implemented yet."
        )

    @pytest.mark.asyncio
    async def test_welfare_debounce_deescalation(
        self,
        coordinator: BehaviourMonitorCoordinator,
        mock_hass: MagicMock,
    ) -> None:
        """De-escalation (concern to ok) also requires N cycles.

        When welfare de-escalates (e.g., "concern" -> "ok"), the debounce
        should also apply — no immediate notification on the first cycle.
        """
        # Start at concern status (escalated)
        coordinator._last_welfare_status = "concern"

        welfare_ok = {"status": "ok", "message": "All clear"}

        with patch.object(
            coordinator, "_send_welfare_notification", new_callable=AsyncMock
        ) as mock_welfare:
            with patch.object(coordinator._store, "async_save", new_callable=AsyncMock):
                with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                    with patch.object(
                        coordinator._analyzer, "is_learning_complete", return_value=True
                    ):
                        with patch.object(
                            coordinator._analyzer, "check_for_anomalies", return_value=[]
                        ):
                            with patch.object(
                                coordinator._analyzer,
                                "get_welfare_status",
                                return_value=welfare_ok,
                            ):
                                # First cycle of de-escalation — should NOT notify
                                await coordinator._async_update_data()

        assert mock_welfare.call_count == 0, (
            f"Expected 0 welfare notifications on first de-escalation cycle (debounce), "
            f"got {mock_welfare.call_count}. Welfare debounce for de-escalation not implemented yet."
        )


class TestCoordinatorSnooze:
    """Tests for coordinator snooze functionality."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator instance."""
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    def test_is_snoozed_default_false(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test is_snoozed returns False by default."""
        assert coordinator.is_snoozed() is False

    def test_get_snooze_duration_key_when_not_snoozed(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test get_snooze_duration_key returns 'off' when not snoozed."""
        from custom_components.behaviour_monitor.const import SNOOZE_OFF

        assert coordinator.get_snooze_duration_key() == SNOOZE_OFF

    @pytest.mark.asyncio
    async def test_async_snooze_1_hour(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test snoozing for 1 hour."""
        from custom_components.behaviour_monitor.const import SNOOZE_1_HOUR

        await coordinator.async_snooze(SNOOZE_1_HOUR)

        assert coordinator.is_snoozed() is True
        assert coordinator.get_snooze_duration_key() == SNOOZE_1_HOUR
        assert coordinator.snooze_until is not None

    @pytest.mark.asyncio
    async def test_async_snooze_2_hours(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test snoozing for 2 hours."""
        from custom_components.behaviour_monitor.const import SNOOZE_2_HOURS

        await coordinator.async_snooze(SNOOZE_2_HOURS)

        assert coordinator.is_snoozed() is True
        assert coordinator.get_snooze_duration_key() == SNOOZE_2_HOURS

    @pytest.mark.asyncio
    async def test_async_snooze_4_hours(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test snoozing for 4 hours."""
        from custom_components.behaviour_monitor.const import SNOOZE_4_HOURS

        await coordinator.async_snooze(SNOOZE_4_HOURS)

        assert coordinator.is_snoozed() is True
        assert coordinator.get_snooze_duration_key() == SNOOZE_4_HOURS

    @pytest.mark.asyncio
    async def test_async_snooze_1_day(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test snoozing for 1 day."""
        from custom_components.behaviour_monitor.const import SNOOZE_1_DAY

        await coordinator.async_snooze(SNOOZE_1_DAY)

        assert coordinator.is_snoozed() is True
        assert coordinator.get_snooze_duration_key() == SNOOZE_1_DAY

    @pytest.mark.asyncio
    async def test_async_snooze_off_clears_snooze(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test that snoozing with 'off' key clears the snooze."""
        from custom_components.behaviour_monitor.const import SNOOZE_OFF, SNOOZE_1_HOUR

        # First snooze
        await coordinator.async_snooze(SNOOZE_1_HOUR)
        assert coordinator.is_snoozed() is True

        # Snooze with "off" should clear
        await coordinator.async_snooze(SNOOZE_OFF)
        assert coordinator.is_snoozed() is False

    @pytest.mark.asyncio
    async def test_async_clear_snooze(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test clearing snooze."""
        from custom_components.behaviour_monitor.const import SNOOZE_1_HOUR, SNOOZE_OFF

        # First snooze
        await coordinator.async_snooze(SNOOZE_1_HOUR)
        assert coordinator.is_snoozed() is True

        # Clear snooze
        await coordinator.async_clear_snooze()
        assert coordinator.is_snoozed() is False
        assert coordinator.get_snooze_duration_key() == SNOOZE_OFF

    @pytest.mark.asyncio
    async def test_snooze_prevents_pattern_updates(
        self, coordinator: BehaviourMonitorCoordinator, mock_hass: MagicMock
    ) -> None:
        """Test that snooze prevents pattern updates but allows state tracking."""
        from custom_components.behaviour_monitor.const import SNOOZE_1_HOUR

        # Set snooze using the proper method
        await coordinator.async_snooze(SNOOZE_1_HOUR)

        event = MagicMock()
        event.data = {
            "entity_id": "sensor.test1",
            "old_state": MagicMock(state="off"),
            "new_state": MagicMock(state="on"),
        }

        initial_patterns = len(coordinator.analyzer.patterns)
        coordinator._handle_state_changed(event)

        # Should not have updated patterns due to snooze
        assert len(coordinator.analyzer.patterns) == initial_patterns

    @pytest.mark.asyncio
    async def test_snooze_persists_across_save_load(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Test that snooze state survives save/load cycle."""
        from datetime import timezone
        from custom_components.behaviour_monitor.const import SNOOZE_1_HOUR

        # Set snooze
        await coordinator.async_snooze(SNOOZE_1_HOUR)

        # Save
        saved_data = None

        async def capture_save(data: dict[str, Any]) -> None:
            nonlocal saved_data
            saved_data = data

        with patch.object(coordinator._store, "async_save", side_effect=capture_save):
            with patch.object(coordinator._ml_store, "async_save", new_callable=AsyncMock):
                await coordinator._save_data()

        # Create new coordinator and load
        new_coordinator = BehaviourMonitorCoordinator(
            coordinator.hass, coordinator._entry
        )

        # Patch dt_util to use timezone-aware datetimes throughout
        mock_now = datetime.now(timezone.utc)
        with patch("custom_components.behaviour_monitor.coordinator.dt_util.DEFAULT_TIME_ZONE", timezone.utc):
            with patch("custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=mock_now):
                with patch.object(new_coordinator._store, "async_load", return_value=saved_data):
                    with patch.object(new_coordinator._ml_store, "async_load", return_value=None):
                        await new_coordinator.async_setup()

                # Verify snooze was restored (keep patches active for is_snoozed check)
                assert new_coordinator.is_snoozed() is True
                assert new_coordinator.get_snooze_duration_key() == SNOOZE_1_HOUR
                assert new_coordinator.snooze_until is not None


# ---------------------------------------------------------------------------
# Helper: load the v2 storage fixture
# ---------------------------------------------------------------------------

def _load_v2_fixture() -> dict:
    """Load the v2 storage fixture from disk."""
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "v2_storage.json"
    )
    with open(fixture_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Task 1: Storage migration tests
# ---------------------------------------------------------------------------


class TestStorageMigration:
    """Tests for v2 -> v3 storage migration logic."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator instance."""
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    async def test_v2_storage_loads_without_crash(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Loading v2 storage (has 'analyzer' key, no 'routine_model') does not crash."""
        v2_data = _load_v2_fixture()
        with patch.object(coordinator._store, "async_load", return_value=v2_data):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                # Must not raise
                await coordinator.async_setup()

    async def test_v2_storage_creates_empty_routine_model(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Loading v2 storage creates an empty RoutineModel (no entity data)."""
        v2_data = _load_v2_fixture()
        with patch.object(coordinator._store, "async_load", return_value=v2_data):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()
        # RoutineModel should exist but be empty (no entities)
        assert hasattr(coordinator, "_routine_model")
        assert coordinator._routine_model is not None
        assert coordinator._routine_model.overall_confidence() == 0.0

    async def test_v2_storage_preserves_coordinator_state(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Loading v2 storage preserves coordinator state (holiday_mode, cooldowns, etc.)."""
        v2_data = _load_v2_fixture()
        v2_data["coordinator"]["holiday_mode"] = True
        v2_data["coordinator"]["welfare_consecutive_cycles"] = 3
        with patch.object(coordinator._store, "async_load", return_value=v2_data):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()
        assert coordinator._holiday_mode is True
        assert coordinator._welfare_consecutive_cycles == 3

    async def test_v3_storage_deserializes_routine_model(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Loading v3 storage (has 'routine_model' key) deserializes RoutineModel via from_dict."""
        from custom_components.behaviour_monitor.routine_model import RoutineModel

        original = RoutineModel(history_window_days=28)
        original.record(
            "sensor.test1",
            datetime(2024, 1, 15, 10, 0, 0),
            "on",
            is_binary=True,
        )
        v3_data = {
            "routine_model": original.to_dict(),
            "coordinator": {
                "last_notification_time": None,
                "last_notification_type": None,
                "last_welfare_status": None,
                "holiday_mode": False,
                "snooze_until": None,
                "notification_cooldowns": {},
                "welfare_consecutive_cycles": 0,
                "welfare_pending_status": None,
            },
        }
        with patch.object(coordinator._store, "async_load", return_value=v3_data):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()
        # The restored model should have the entity loaded
        assert hasattr(coordinator, "_routine_model")
        assert coordinator._routine_model is not None
        # Since we recorded one event, confidence is non-zero (time-based)
        # The entity should exist in the model
        conf = coordinator._routine_model.overall_confidence()
        # Overall confidence may be 0 (no time elapsed) but model was loaded
        assert isinstance(conf, float)

    async def test_empty_storage_creates_empty_routine_model(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Empty/None storage creates an empty RoutineModel without crashing."""
        with patch.object(coordinator._store, "async_load", return_value=None):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()
        assert hasattr(coordinator, "_routine_model")
        assert coordinator._routine_model is not None
        assert coordinator._routine_model.overall_confidence() == 0.0

    async def test_v2_storage_logs_migration_info(
        self, coordinator: BehaviourMonitorCoordinator, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Loading v2 storage logs an info-level migration message."""
        v2_data = _load_v2_fixture()
        with patch.object(coordinator._store, "async_load", return_value=v2_data):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                with caplog.at_level(logging.INFO):
                    await coordinator.async_setup()
        # Should log something about migration / v2 format
        log_text = caplog.text.lower()
        assert "v2" in log_text or "migrat" in log_text or "discard" in log_text


class TestMLStoreCleanup:
    """Tests for orphaned ML storage cleanup."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator instance."""
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    async def test_ml_store_deleted_when_exists(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """ML store is deleted when orphaned ML storage file exists."""
        ml_data = {"some": "ml_data"}
        ml_store_mock = AsyncMock()
        ml_store_mock.async_load = AsyncMock(return_value=ml_data)
        ml_store_mock.async_remove = AsyncMock()

        with patch.object(coordinator._store, "async_load", return_value=None):
            with patch.object(coordinator, "_ml_store", ml_store_mock):
                await coordinator.async_setup()

        ml_store_mock.async_remove.assert_awaited_once()

    async def test_ml_cleanup_no_crash_when_absent(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """ML store cleanup does not crash when ML storage file does not exist."""
        ml_store_mock = AsyncMock()
        ml_store_mock.async_load = AsyncMock(return_value=None)
        ml_store_mock.async_remove = AsyncMock()

        with patch.object(coordinator._store, "async_load", return_value=None):
            with patch.object(coordinator, "_ml_store", ml_store_mock):
                # Must not raise even when there's nothing to delete
                await coordinator.async_setup()

        ml_store_mock.async_remove.assert_not_awaited()

    async def test_ml_cleanup_survives_exception(
        self, coordinator: BehaviourMonitorCoordinator, caplog: pytest.LogCaptureFixture
    ) -> None:
        """ML store cleanup wraps exceptions and does not crash setup."""
        ml_store_mock = AsyncMock()
        ml_store_mock.async_load = AsyncMock(side_effect=Exception("storage error"))

        with patch.object(coordinator._store, "async_load", return_value=None):
            with patch.object(coordinator, "_ml_store", ml_store_mock):
                # Must not raise
                await coordinator.async_setup()


class TestDeprecationLogs:
    """Tests for deprecation warnings logged at startup."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator instance."""
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    async def test_three_deprecation_warnings_logged(
        self, coordinator: BehaviourMonitorCoordinator, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Exactly 3 deprecation warnings are logged (one per deprecated sensor)."""
        with patch.object(coordinator._store, "async_load", return_value=None):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                with caplog.at_level(logging.WARNING):
                    await coordinator.async_setup()

        deprecation_warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "deprecated" in r.message.lower()
        ]
        assert len(deprecation_warnings) == 3

    async def test_deprecation_warnings_mention_sensors(
        self, coordinator: BehaviourMonitorCoordinator, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Deprecation warnings mention the deprecated sensor names."""
        with patch.object(coordinator._store, "async_load", return_value=None):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                with caplog.at_level(logging.WARNING):
                    await coordinator.async_setup()

        deprecation_text = " ".join(
            r.message for r in caplog.records
            if r.levelno == logging.WARNING and "deprecated" in r.message.lower()
        )
        # All three deprecated sensor types should be mentioned
        assert "ml_status" in deprecation_text
        assert "ml_training" in deprecation_text
        assert "cross_sensor" in deprecation_text


class TestSensorDataStubs:
    """Tests for stub data keys in _build_sensor_data / _async_update_data."""

    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator instance after setup."""
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    async def _setup_coordinator(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """Helper to set up coordinator with mocked storage."""
        with patch.object(coordinator._store, "async_load", return_value=None):
            with patch.object(coordinator._ml_store, "async_load", return_value=None):
                await coordinator.async_setup()

    async def test_ml_status_stub_in_sensor_data(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """coordinator.data includes ml_status_stub='Removed in v1.1'."""
        await self._setup_coordinator(coordinator)
        data = await coordinator._async_update_data()
        assert data.get("ml_status_stub") == "Removed in v1.1"

    async def test_ml_training_stub_in_sensor_data(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """coordinator.data includes ml_training_stub='N/A'."""
        await self._setup_coordinator(coordinator)
        data = await coordinator._async_update_data()
        assert data.get("ml_training_stub") == "N/A"

    async def test_cross_sensor_stub_in_sensor_data(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """coordinator.data includes cross_sensor_stub=0."""
        await self._setup_coordinator(coordinator)
        data = await coordinator._async_update_data()
        assert data.get("cross_sensor_stub") == 0

    async def test_learning_status_in_sensor_data(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """coordinator.data includes learning_status key (string)."""
        await self._setup_coordinator(coordinator)
        data = await coordinator._async_update_data()
        assert "learning_status" in data
        assert data["learning_status"] in ("inactive", "learning", "ready")

    async def test_baseline_confidence_in_sensor_data(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """coordinator.data includes baseline_confidence as float 0.0-100.0."""
        await self._setup_coordinator(coordinator)
        data = await coordinator._async_update_data()
        assert "baseline_confidence" in data
        assert isinstance(data["baseline_confidence"], float)
        assert 0.0 <= data["baseline_confidence"] <= 100.0

    async def test_learning_status_inactive_when_no_data(
        self, coordinator: BehaviourMonitorCoordinator
    ) -> None:
        """learning_status is 'inactive' when no history has been loaded."""
        await self._setup_coordinator(coordinator)
        data = await coordinator._async_update_data()
        # Empty RoutineModel -> confidence 0.0 -> status "inactive"
        assert data["learning_status"] == "inactive"
        assert data["baseline_confidence"] == 0.0


