"""Tests for the integration setup and lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.behaviour_monitor import (
    async_setup_entry,
    async_unload_entry,
    async_reload_entry,
    async_migrate_entry,
)
from custom_components.behaviour_monitor.const import (
    DOMAIN,
    STORAGE_VERSION,
    SERVICE_ROUTINE_RESET,
    SERVICE_ENABLE_HOLIDAY_MODE,
    SERVICE_DISABLE_HOLIDAY_MODE,
    SERVICE_SNOOZE,
    SERVICE_CLEAR_SNOOZE,
)
from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator
from custom_components.behaviour_monitor.const import (
    CONF_ALERT_REPEAT_INTERVAL,
    CONF_LEARNING_PERIOD,
    CONF_MAX_INACTIVITY_MULTIPLIER,
    CONF_MIN_INACTIVITY_MULTIPLIER,
    CONF_TRACK_ATTRIBUTES,
    DEFAULT_ALERT_REPEAT_INTERVAL,
    DEFAULT_LEARNING_PERIOD_DAYS,
    DEFAULT_MAX_INACTIVITY_MULTIPLIER,
    DEFAULT_MIN_INACTIVITY_MULTIPLIER,
    DEFAULT_TRACK_ATTRIBUTES,
)


class TestAsyncSetupEntry:
    """Tests for async_setup_entry."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_success(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test successful integration setup."""
        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.monitored_entities = {"sensor.test1", "sensor.test2"}
            mock_coordinator_class.return_value = mock_coordinator

            result = await async_setup_entry(mock_hass, mock_config_entry)

            assert result is True
            mock_coordinator.async_setup.assert_called_once()
            mock_coordinator.async_config_entry_first_refresh.assert_called_once()
            mock_hass.config_entries.async_forward_entry_setups.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_stores_coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test that setup stores coordinator in hass.data."""
        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.monitored_entities = {"sensor.test1", "sensor.test2"}
            mock_coordinator_class.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            assert DOMAIN in mock_hass.data
            assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]
            assert mock_hass.data[DOMAIN][mock_config_entry.entry_id] == mock_coordinator

    @pytest.mark.asyncio
    async def test_async_setup_entry_forwards_to_platforms(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test that setup forwards to sensor platform."""
        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.monitored_entities = {"sensor.test1", "sensor.test2"}
            mock_coordinator_class.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            mock_hass.config_entries.async_forward_entry_setups.assert_called_once()
            call_args = mock_hass.config_entries.async_forward_entry_setups.call_args
            assert call_args[0][0] == mock_config_entry
            # Verify sensor platform is in the list
            assert "sensor" in [str(p) for p in call_args[0][1]]

    @pytest.mark.asyncio
    async def test_async_setup_entry_registers_update_listener(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test that setup registers update listener."""
        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.monitored_entities = {"sensor.test1", "sensor.test2"}
            mock_coordinator_class.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            # Verify update listener was registered
            mock_config_entry.add_update_listener.assert_called_once()
            mock_config_entry.async_on_unload.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_handles_coordinator_setup_failure(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test setup handles coordinator setup failure."""
        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock(side_effect=Exception("Setup failed"))
            mock_coordinator_class.return_value = mock_coordinator

            with pytest.raises(Exception, match="Setup failed"):
                await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_async_setup_entry_registers_routine_reset_service(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test that setup registers the routine_reset service."""
        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.monitored_entities = {"sensor.test1"}
            mock_coordinator_class.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            # Verify services were registered
            service_calls = [call[0] for call in mock_hass.services.async_register.call_args_list]
            registered_services = [(c[0], c[1]) for c in service_calls]
            assert (DOMAIN, SERVICE_ROUTINE_RESET) in registered_services

    @pytest.mark.asyncio
    async def test_async_setup_entry_registers_all_services(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test that setup registers all expected services."""
        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.monitored_entities = {"sensor.test1"}
            mock_coordinator_class.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            service_calls = [call[0] for call in mock_hass.services.async_register.call_args_list]
            registered_services = [(c[0], c[1]) for c in service_calls]
            expected_services = [
                (DOMAIN, SERVICE_ENABLE_HOLIDAY_MODE),
                (DOMAIN, SERVICE_DISABLE_HOLIDAY_MODE),
                (DOMAIN, SERVICE_SNOOZE),
                (DOMAIN, SERVICE_CLEAR_SNOOZE),
                (DOMAIN, SERVICE_ROUTINE_RESET),
            ]
            for svc in expected_services:
                assert svc in registered_services, f"Service {svc} not registered"


class TestAsyncUnloadEntry:
    """Tests for async_unload_entry."""

    @pytest.mark.asyncio
    async def test_async_unload_entry_success(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test successful integration unload."""
        # Setup coordinator in hass.data
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_coordinator.async_shutdown = AsyncMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        mock_hass.config_entries.async_unload_platforms.assert_called_once()
        mock_coordinator.async_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_unload_entry_removes_coordinator_from_data(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test that unload removes coordinator from hass.data."""
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_coordinator.async_shutdown = AsyncMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}

        await async_unload_entry(mock_hass, mock_config_entry)

        assert mock_config_entry.entry_id not in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_async_unload_entry_unloads_platforms(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test that unload unloads sensor platform."""
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_coordinator.async_shutdown = AsyncMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}

        await async_unload_entry(mock_hass, mock_config_entry)

        mock_hass.config_entries.async_unload_platforms.assert_called_once()
        call_args = mock_hass.config_entries.async_unload_platforms.call_args
        assert call_args[0][0] == mock_config_entry
        assert "sensor" in [str(p) for p in call_args[0][1]]

    @pytest.mark.asyncio
    async def test_async_unload_entry_handles_platform_unload_failure(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test unload handles platform unload failure."""
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_coordinator.async_shutdown = AsyncMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(mock_hass, mock_config_entry)

        # Should return False and not shut down coordinator
        assert result is False
        mock_coordinator.async_shutdown.assert_not_called()
        # Coordinator should still be in hass.data
        assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_async_unload_entry_calls_coordinator_shutdown(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test that unload calls coordinator shutdown."""
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_coordinator.async_shutdown = AsyncMock()
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}

        await async_unload_entry(mock_hass, mock_config_entry)

        mock_coordinator.async_shutdown.assert_called_once()


class TestAsyncReloadEntry:
    """Tests for async_reload_entry."""

    @pytest.mark.asyncio
    async def test_async_reload_entry_calls_reload(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test that reload calls config_entries.async_reload."""
        await async_reload_entry(mock_hass, mock_config_entry)

        mock_hass.config_entries.async_reload.assert_called_once_with(
            mock_config_entry.entry_id
        )

    @pytest.mark.asyncio
    async def test_async_reload_entry_with_correct_entry_id(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test reload uses correct entry_id."""
        mock_config_entry.entry_id = "specific_test_id"

        await async_reload_entry(mock_hass, mock_config_entry)

        mock_hass.config_entries.async_reload.assert_called_once_with("specific_test_id")


class TestIntegrationLifecycle:
    """Integration tests for full setup/unload lifecycle."""

    @pytest.mark.asyncio
    async def test_setup_then_unload_lifecycle(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test complete setup and unload lifecycle."""
        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.async_shutdown = AsyncMock()
            mock_coordinator.monitored_entities = {"sensor.test1", "sensor.test2"}
            mock_coordinator_class.return_value = mock_coordinator

            # Setup
            setup_result = await async_setup_entry(mock_hass, mock_config_entry)
            assert setup_result is True
            assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]

            # Unload
            unload_result = await async_unload_entry(mock_hass, mock_config_entry)
            assert unload_result is True
            assert mock_config_entry.entry_id not in mock_hass.data[DOMAIN]
            mock_coordinator.async_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_entries_independent(self, mock_hass: MagicMock) -> None:
        """Test multiple config entries are independent."""
        # Create two separate config entries
        entry1 = MagicMock()
        entry1.entry_id = "entry_1"
        entry1.data = {
            "monitored_entities": ["sensor.test1"],
            "sensitivity": "medium",
            "learning_period": 7,
            "enable_notifications": True,
            "enable_ml": True,
            "retrain_period": 14,
            "cross_sensor_window": 300,
        }
        entry1.add_update_listener = MagicMock(return_value=MagicMock())
        entry1.async_on_unload = MagicMock()

        entry2 = MagicMock()
        entry2.entry_id = "entry_2"
        entry2.data = {
            "monitored_entities": ["sensor.test2"],
            "sensitivity": "high",
            "learning_period": 14,
            "enable_notifications": False,
            "enable_ml": False,
            "retrain_period": 7,
            "cross_sensor_window": 600,
        }
        entry2.add_update_listener = MagicMock(return_value=MagicMock())
        entry2.async_on_unload = MagicMock()

        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coord1 = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coord1.async_setup = AsyncMock()
            mock_coord1.async_config_entry_first_refresh = AsyncMock()
            mock_coord1.async_shutdown = AsyncMock()
            mock_coord1.monitored_entities = {"sensor.test1"}

            mock_coord2 = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coord2.async_setup = AsyncMock()
            mock_coord2.async_config_entry_first_refresh = AsyncMock()
            mock_coord2.async_shutdown = AsyncMock()
            mock_coord2.monitored_entities = {"sensor.test2"}

            # Return different coordinators for each entry
            mock_coordinator_class.side_effect = [mock_coord1, mock_coord2]

            # Setup both entries
            await async_setup_entry(mock_hass, entry1)
            await async_setup_entry(mock_hass, entry2)

            # Verify both are in hass.data
            assert entry1.entry_id in mock_hass.data[DOMAIN]
            assert entry2.entry_id in mock_hass.data[DOMAIN]
            assert mock_hass.data[DOMAIN][entry1.entry_id] == mock_coord1
            assert mock_hass.data[DOMAIN][entry2.entry_id] == mock_coord2

            # Unload first entry
            await async_unload_entry(mock_hass, entry1)

            # First entry should be gone, second should remain
            assert entry1.entry_id not in mock_hass.data[DOMAIN]
            assert entry2.entry_id in mock_hass.data[DOMAIN]
            mock_coord1.async_shutdown.assert_called_once()
            mock_coord2.async_shutdown.assert_not_called()


class TestStorageVersion:
    """Tests for STORAGE_VERSION constant."""

    def test_storage_version_is_7(self) -> None:
        """Test that STORAGE_VERSION equals 7 after adaptive inactivity bump."""
        assert STORAGE_VERSION == 7


class TestMigrateEntry:
    """Tests for async_migrate_entry."""

    def _make_config_entry(self, version: int, data: dict) -> MagicMock:
        """Create a mock config entry with given version and data."""
        entry = MagicMock()
        entry.version = version
        entry.data = data
        return entry

    @pytest.mark.asyncio
    async def test_migrate_v2_removes_enable_ml(self) -> None:
        """Migration from v2 removes enable_ml key (verified at v3->v4 step)."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=2,
            data={
                "monitored_entities": ["sensor.test1"],
                "sensitivity": "medium",
                "enable_ml": True,
                "retrain_period": 14,
                "ml_learning_period": 7,
                "cross_sensor_window": 300,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v2 produces 3 calls: v2->v3, v3->v4, v4->v5. Check v3->v4 call (index 1).
        call_args = hass.config_entries.async_update_entry.call_args_list[1]
        new_data = call_args[1]["data"]
        assert "enable_ml" not in new_data

    @pytest.mark.asyncio
    async def test_migrate_v2_removes_retrain_period(self) -> None:
        """Migration from v2 removes retrain_period key (verified at v3->v4 step)."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=2,
            data={
                "monitored_entities": ["sensor.test1"],
                "sensitivity": "medium",
                "enable_ml": True,
                "retrain_period": 14,
                "ml_learning_period": 7,
                "cross_sensor_window": 300,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v2 produces 3 calls: v2->v3, v3->v4, v4->v5. Check v3->v4 call (index 1).
        call_args = hass.config_entries.async_update_entry.call_args_list[1]
        new_data = call_args[1]["data"]
        assert "retrain_period" not in new_data

    @pytest.mark.asyncio
    async def test_migrate_v2_removes_ml_learning_period(self) -> None:
        """Migration from v2 removes ml_learning_period key (verified at v3->v4 step)."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=2,
            data={
                "monitored_entities": ["sensor.test1"],
                "sensitivity": "medium",
                "enable_ml": True,
                "retrain_period": 14,
                "ml_learning_period": 7,
                "cross_sensor_window": 300,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v2 produces 3 calls: v2->v3, v3->v4, v4->v5. Check v3->v4 call (index 1).
        call_args = hass.config_entries.async_update_entry.call_args_list[1]
        new_data = call_args[1]["data"]
        assert "ml_learning_period" not in new_data

    @pytest.mark.asyncio
    async def test_migrate_v2_removes_cross_sensor_window(self) -> None:
        """Migration from v2 removes cross_sensor_window key (verified at v3->v4 step)."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=2,
            data={
                "monitored_entities": ["sensor.test1"],
                "sensitivity": "medium",
                "enable_ml": True,
                "retrain_period": 14,
                "ml_learning_period": 7,
                "cross_sensor_window": 300,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v2 produces 3 calls: v2->v3, v3->v4, v4->v5. Check v3->v4 call (index 1).
        call_args = hass.config_entries.async_update_entry.call_args_list[1]
        new_data = call_args[1]["data"]
        assert "cross_sensor_window" not in new_data

    @pytest.mark.asyncio
    async def test_migrate_v2_adds_history_window_days(self) -> None:
        """Migration from v2 adds history_window_days=28 (verified at v2->v3 step)."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=2,
            data={
                "monitored_entities": ["sensor.test1"],
                "sensitivity": "medium",
                "enable_ml": True,
                "retrain_period": 14,
                "ml_learning_period": 7,
                "cross_sensor_window": 300,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v2 produces 3 calls: v2->v3, v3->v4, v4->v5. Check v2->v3 call (index 0).
        call_args = hass.config_entries.async_update_entry.call_args_list[0]
        new_data = call_args[1]["data"]
        assert new_data["history_window_days"] == 28

    @pytest.mark.asyncio
    async def test_migrate_v2_preserves_existing_keys(self) -> None:
        """Migration from v2 preserves monitored_entities and notification keys."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=2,
            data={
                "monitored_entities": ["sensor.test1", "sensor.test2"],
                "sensitivity": "high",
                "learning_period": 14,
                "enable_notifications": False,
                "enable_ml": True,
                "retrain_period": 14,
                "ml_learning_period": 7,
                "cross_sensor_window": 300,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v2 produces 3 calls: v2->v3, v3->v4, v4->v5. Check v3->v4 call (index 1)
        # for sigma/ML key removal verification.
        call_args = hass.config_entries.async_update_entry.call_args_list[1]
        new_data = call_args[1]["data"]
        assert new_data["monitored_entities"] == ["sensor.test1", "sensor.test2"]
        assert new_data["enable_notifications"] is False
        # Old sigma/ML keys are removed by v4 migration
        assert "sensitivity" not in new_data
        assert "learning_period" not in new_data
        assert "enable_ml" not in new_data

    @pytest.mark.asyncio
    async def test_migrate_v2_updates_version_to_7(self) -> None:
        """Migration from v2 ends at version=7 (v2->v3->v4->v5->v6->v7 in one call)."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=2,
            data={
                "monitored_entities": ["sensor.test1"],
                "enable_ml": True,
                "retrain_period": 14,
                "ml_learning_period": 7,
                "cross_sensor_window": 300,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # Five calls: one for v3, one for v4, one for v5, one for v6, one for v7
        assert hass.config_entries.async_update_entry.call_count == 5
        last_call = hass.config_entries.async_update_entry.call_args
        assert last_call[1]["version"] == 7

    @pytest.mark.asyncio
    async def test_migrate_v3_upgrades_to_v7(self) -> None:
        """Migration from v3 migrates through v4, v5, v6, to v7."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=3,
            data={
                "monitored_entities": ["sensor.test1"],
                "sensitivity": "medium",
                "history_window_days": 28,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # Four calls: v3->v4, v4->v5, v5->v6, v6->v7
        assert hass.config_entries.async_update_entry.call_count == 4
        # Check v3->v4 call (index 0) for v4-specific changes
        v4_call = hass.config_entries.async_update_entry.call_args_list[0]
        assert v4_call[1]["version"] == 4
        v4_data = v4_call[1]["data"]
        assert "sensitivity" not in v4_data
        assert v4_data["inactivity_multiplier"] == 3.0
        assert v4_data["drift_sensitivity"] == "medium"
        # Final call should be v7
        last_call = hass.config_entries.async_update_entry.call_args
        assert last_call[1]["version"] == 7

    @pytest.mark.asyncio
    async def test_migrate_v4_upgrades_to_v7(self) -> None:
        """Migration from v4 upgrades through v5, v6 to v7."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=4,
            data={
                "monitored_entities": ["sensor.test1"],
                "history_window_days": 28,
                "inactivity_multiplier": 3.0,
                "drift_sensitivity": "medium",
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # Three calls: v4->v5, v5->v6, v6->v7
        assert hass.config_entries.async_update_entry.call_count == 3
        last_call = hass.config_entries.async_update_entry.call_args
        assert last_call.kwargs.get("version") == 7 or last_call[1].get("version") == 7

    @pytest.mark.asyncio
    async def test_migrate_v4_adds_learning_period(self) -> None:
        """Migration from v4 adds learning_period with default value (v4->v5 step)."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=4,
            data={"monitored_entities": ["sensor.test"]},
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v4->v5 call is index 0; v5->v6 call is index 1
        call_args = hass.config_entries.async_update_entry.call_args_list[0]
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_LEARNING_PERIOD] == DEFAULT_LEARNING_PERIOD_DAYS

    @pytest.mark.asyncio
    async def test_migrate_v4_adds_track_attributes(self) -> None:
        """Migration from v4 adds track_attributes with default value (v4->v5 step)."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=4,
            data={"monitored_entities": ["sensor.test"]},
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v4->v5 call is index 0; v5->v6 call is index 1
        call_args = hass.config_entries.async_update_entry.call_args_list[0]
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_TRACK_ATTRIBUTES] == DEFAULT_TRACK_ATTRIBUTES

    @pytest.mark.asyncio
    async def test_migrate_v4_updates_version_to_7(self) -> None:
        """Migration from v4 ends at version=7 (v4->v5->v6->v7)."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=4,
            data={"monitored_entities": ["sensor.test"]},
        )

        await async_migrate_entry(hass, entry)

        last_call = hass.config_entries.async_update_entry.call_args
        assert last_call.kwargs.get("version") == 7 or last_call[1].get("version") == 7

    @pytest.mark.asyncio
    async def test_migrate_v4_preserves_existing_learning_period(self) -> None:
        """Migration does not overwrite an existing learning_period value."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=4,
            data={"monitored_entities": ["sensor.test"], CONF_LEARNING_PERIOD: 14},
        )

        await async_migrate_entry(hass, entry)

        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_LEARNING_PERIOD] == 14

    @pytest.mark.asyncio
    async def test_migrate_always_returns_true(self) -> None:
        """async_migrate_entry always returns True regardless of version."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        for version in [2, 3]:
            entry = self._make_config_entry(
                version=version,
                data={"monitored_entities": []},
            )
            result = await async_migrate_entry(hass, entry)
            assert result is True

    @pytest.mark.asyncio
    async def test_migrate_v2_history_window_days_not_overwritten_if_present(self) -> None:
        """If history_window_days already exists in v2 data, it is preserved (v2->v3 step)."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=2,
            data={
                "monitored_entities": ["sensor.test1"],
                "enable_ml": False,
                "retrain_period": 7,
                "ml_learning_period": 3,
                "cross_sensor_window": 120,
                "history_window_days": 14,  # already present
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v2->v3 call (index 0) is where history_window_days is set
        call_args = hass.config_entries.async_update_entry.call_args_list[0]
        new_data = call_args[1]["data"]
        # setdefault should NOT overwrite the existing value
        assert new_data["history_window_days"] == 14


class TestMigrateEntryV5ToV6:
    """Tests for v5->v6 migration (alert_repeat_interval)."""

    def _make_config_entry(self, version: int, data: dict) -> MagicMock:
        """Create a mock config entry with given version and data."""
        entry = MagicMock()
        entry.version = version
        entry.data = data
        return entry

    @pytest.mark.asyncio
    async def test_migrate_v5_to_v7(self) -> None:
        """Migration from v5 cascades through v6 (alert_repeat_interval) and v7 (min/max bounds)."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=5,
            data={
                "monitored_entities": ["sensor.test"],
                "history_window_days": 28,
                "inactivity_multiplier": 3.0,
                "drift_sensitivity": "medium",
                "learning_period": 7,
                "track_attributes": True,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # Two calls: v5->v6 and v6->v7
        assert hass.config_entries.async_update_entry.call_count == 2
        # v5->v6 call (index 0) adds alert_repeat_interval
        v6_call = hass.config_entries.async_update_entry.call_args_list[0]
        v6_data = v6_call.kwargs.get("data") or v6_call[1].get("data")
        assert v6_data[CONF_ALERT_REPEAT_INTERVAL] == DEFAULT_ALERT_REPEAT_INTERVAL
        assert (v6_call.kwargs.get("version") or v6_call[1].get("version")) == 6
        # v6->v7 call (index 1) adds min/max bounds
        last_call = hass.config_entries.async_update_entry.call_args
        version = last_call.kwargs.get("version") or last_call[1].get("version")
        assert version == 7

    @pytest.mark.asyncio
    async def test_migrate_v5_to_v6_preserves_existing(self) -> None:
        """Migration from v5 preserves an existing alert_repeat_interval value."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=5,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_ALERT_REPEAT_INTERVAL: 120,  # already set to custom value
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_ALERT_REPEAT_INTERVAL] == 120

    def test_config_flow_version_is_7(self) -> None:
        """BehaviourMonitorConfigFlow.VERSION should be 7 after adaptive inactivity bump."""
        from custom_components.behaviour_monitor.config_flow import BehaviourMonitorConfigFlow
        assert BehaviourMonitorConfigFlow.VERSION == 7


class TestMigrateEntryV6ToV7:
    """Tests for v6->v7 migration (adaptive inactivity bounds)."""

    def _make_config_entry(self, version: int, data: dict) -> MagicMock:
        """Create a mock config entry with given version and data."""
        entry = MagicMock()
        entry.version = version
        entry.data = data
        return entry

    @pytest.mark.asyncio
    async def test_migrate_v6_to_v7_adds_min_inactivity_multiplier(self) -> None:
        """Migration from v6 adds min_inactivity_multiplier=1.5 and bumps to version=7."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=6,
            data={
                "monitored_entities": ["sensor.test"],
                "history_window_days": 28,
                "inactivity_multiplier": 3.0,
                "drift_sensitivity": "medium",
                "learning_period": 7,
                "track_attributes": True,
                "alert_repeat_interval": 240,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_MIN_INACTIVITY_MULTIPLIER] == DEFAULT_MIN_INACTIVITY_MULTIPLIER

    @pytest.mark.asyncio
    async def test_migrate_v6_to_v7_adds_max_inactivity_multiplier(self) -> None:
        """Migration from v6 adds max_inactivity_multiplier=10.0."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=6,
            data={
                "monitored_entities": ["sensor.test"],
                "alert_repeat_interval": 240,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_MAX_INACTIVITY_MULTIPLIER] == DEFAULT_MAX_INACTIVITY_MULTIPLIER

    @pytest.mark.asyncio
    async def test_migrate_v6_to_v7_bumps_version(self) -> None:
        """Migration from v6 bumps config entry version to 7."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=6,
            data={"monitored_entities": ["sensor.test"]},
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        version = call_args.kwargs.get("version") or call_args[1].get("version")
        assert version == 7

    @pytest.mark.asyncio
    async def test_migrate_v7_is_noop(self) -> None:
        """A v7 config entry is not re-migrated — async_update_entry is not called."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=7,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_MIN_INACTIVITY_MULTIPLIER: 2.0,
                CONF_MAX_INACTIVITY_MULTIPLIER: 8.0,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_migrate_v6_preserves_existing_min_inactivity_multiplier(self) -> None:
        """Migration does not overwrite an existing min_inactivity_multiplier value."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=6,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_MIN_INACTIVITY_MULTIPLIER: 2.5,  # already set to custom value
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_MIN_INACTIVITY_MULTIPLIER] == 2.5

    @pytest.mark.asyncio
    async def test_migrate_v2_ends_at_v7(self) -> None:
        """Migration from v2 cascades all the way to v7."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_config_entry(
            version=2,
            data={
                "monitored_entities": ["sensor.test1"],
                "enable_ml": True,
                "retrain_period": 14,
                "ml_learning_period": 7,
                "cross_sensor_window": 300,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # Five migration steps: v2->v3, v3->v4, v4->v5, v5->v6, v6->v7
        assert hass.config_entries.async_update_entry.call_count == 5
        last_call = hass.config_entries.async_update_entry.call_args
        assert last_call[1]["version"] == 7
