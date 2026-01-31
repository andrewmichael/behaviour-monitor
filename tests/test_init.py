"""Tests for the integration setup and lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.behaviour_monitor import (
    async_setup_entry,
    async_unload_entry,
    async_reload_entry,
)
from custom_components.behaviour_monitor.const import DOMAIN
from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator


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
