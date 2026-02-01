"""Tests for the switch platform."""

from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock

import pytest

from custom_components.behaviour_monitor.switch import (
    HolidayModeSwitch,
    async_setup_entry,
)
from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator
from custom_components.behaviour_monitor.const import DOMAIN


class TestHolidayModeSwitch:
    """Tests for the HolidayModeSwitch entity."""

    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        """Create a mock coordinator."""
        coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        coordinator.holiday_mode = False
        coordinator.async_enable_holiday_mode = AsyncMock()
        coordinator.async_disable_holiday_mode = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_config_entry(self) -> MagicMock:
        """Create a mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        return entry

    def test_switch_initialization(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test switch entity initialization."""
        switch = HolidayModeSwitch(mock_coordinator, mock_config_entry)

        assert switch._attr_unique_id == "test_entry_123_holiday_mode"
        assert switch._attr_name == "Holiday Mode"
        assert switch._attr_icon == "mdi:beach"
        assert switch._attr_has_entity_name is True

    def test_device_info(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test device info configuration."""
        switch = HolidayModeSwitch(mock_coordinator, mock_config_entry)

        device_info = switch._attr_device_info
        assert device_info is not None
        assert (DOMAIN, "test_entry_123") in device_info["identifiers"]
        assert device_info["name"] == "Behaviour Monitor"
        assert device_info["manufacturer"] == "Custom Integration"
        assert device_info["model"] == "Pattern Analyzer"

    def test_is_on_returns_false_when_disabled(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test is_on returns False when holiday mode is disabled."""
        mock_coordinator.holiday_mode = False
        switch = HolidayModeSwitch(mock_coordinator, mock_config_entry)

        assert switch.is_on is False

    def test_is_on_returns_true_when_enabled(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test is_on returns True when holiday mode is enabled."""
        mock_coordinator.holiday_mode = True
        switch = HolidayModeSwitch(mock_coordinator, mock_config_entry)

        assert switch.is_on is True

    def test_extra_state_attributes(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test extra_state_attributes contains description."""
        switch = HolidayModeSwitch(mock_coordinator, mock_config_entry)

        attrs = switch.extra_state_attributes

        assert "description" in attrs
        assert "tracking and learning is paused" in attrs["description"].lower()

    @pytest.mark.asyncio
    async def test_async_turn_on(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test async_turn_on calls coordinator enable method."""
        switch = HolidayModeSwitch(mock_coordinator, mock_config_entry)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()

        mock_coordinator.async_enable_holiday_mode.assert_called_once()
        switch.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_turn_off(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test async_turn_off calls coordinator disable method."""
        switch = HolidayModeSwitch(mock_coordinator, mock_config_entry)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()

        mock_coordinator.async_disable_holiday_mode.assert_called_once()
        switch.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_turn_on_with_kwargs(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test async_turn_on accepts kwargs (HA compatibility)."""
        switch = HolidayModeSwitch(mock_coordinator, mock_config_entry)
        switch.async_write_ha_state = MagicMock()

        # Should not raise even with unexpected kwargs
        await switch.async_turn_on(some_key="some_value")

        mock_coordinator.async_enable_holiday_mode.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_turn_off_with_kwargs(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test async_turn_off accepts kwargs (HA compatibility)."""
        switch = HolidayModeSwitch(mock_coordinator, mock_config_entry)
        switch.async_write_ha_state = MagicMock()

        # Should not raise even with unexpected kwargs
        await switch.async_turn_off(some_key="some_value")

        mock_coordinator.async_disable_holiday_mode.assert_called_once()


class TestAsyncSetupEntry:
    """Tests for the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_creates_holiday_switch(self) -> None:
        """Test setup creates holiday mode switch entity."""
        # Setup mocks
        mock_hass = MagicMock()
        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry_123"
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Verify switch was added
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 1
        assert isinstance(entities[0], HolidayModeSwitch)

    @pytest.mark.asyncio
    async def test_async_setup_entry_uses_coordinator_from_hass_data(self) -> None:
        """Test setup uses coordinator from hass.data."""
        mock_hass = MagicMock()
        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry_456"
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        entities = async_add_entities.call_args[0][0]
        assert entities[0].coordinator == mock_coordinator
