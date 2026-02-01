"""Tests for the select platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock

import pytest

from custom_components.behaviour_monitor.select import (
    SnoozeDurationSelect,
    async_setup_entry,
)
from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator
from custom_components.behaviour_monitor.const import (
    ATTR_SNOOZE_ACTIVE,
    ATTR_SNOOZE_UNTIL,
    DOMAIN,
    SNOOZE_OFF,
    SNOOZE_1_HOUR,
    SNOOZE_2_HOURS,
    SNOOZE_4_HOURS,
    SNOOZE_1_DAY,
    SNOOZE_LABELS,
    SNOOZE_OPTIONS,
)


class TestSnoozeDurationSelect:
    """Tests for the SnoozeDurationSelect entity."""

    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        """Create a mock coordinator."""
        coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        coordinator.is_snoozed.return_value = False
        coordinator.get_snooze_duration_key.return_value = SNOOZE_OFF
        coordinator.snooze_until = None
        coordinator.async_snooze = AsyncMock()
        coordinator.async_clear_snooze = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_config_entry(self) -> MagicMock:
        """Create a mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        return entry

    def test_select_initialization(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test select entity initialization."""
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)

        assert select._attr_unique_id == "test_entry_123_snooze_duration"
        assert select._attr_name == "Snooze Notifications"
        assert select._attr_icon == "mdi:bell-sleep"
        assert select._attr_has_entity_name is True
        assert select._attr_options == [SNOOZE_LABELS[opt] for opt in SNOOZE_OPTIONS]
        assert len(select._attr_options) == 5  # off, 1h, 2h, 4h, 1d

    def test_device_info(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test device info configuration."""
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)

        device_info = select._attr_device_info
        assert device_info is not None
        assert (DOMAIN, "test_entry_123") in device_info["identifiers"]
        assert device_info["name"] == "Behaviour Monitor"
        assert device_info["manufacturer"] == "Custom Integration"
        assert device_info["model"] == "Pattern Analyzer"

    def test_current_option_when_not_snoozed(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test current_option returns Off when not snoozed."""
        mock_coordinator.get_snooze_duration_key.return_value = SNOOZE_OFF
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)

        assert select.current_option == "Off"

    def test_current_option_when_snoozed_1_hour(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test current_option returns correct label for 1 hour."""
        mock_coordinator.get_snooze_duration_key.return_value = SNOOZE_1_HOUR
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)

        assert select.current_option == "1 Hour"

    def test_current_option_when_snoozed_2_hours(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test current_option returns correct label for 2 hours."""
        mock_coordinator.get_snooze_duration_key.return_value = SNOOZE_2_HOURS
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)

        assert select.current_option == "2 Hours"

    def test_current_option_when_snoozed_4_hours(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test current_option returns correct label for 4 hours."""
        mock_coordinator.get_snooze_duration_key.return_value = SNOOZE_4_HOURS
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)

        assert select.current_option == "4 Hours"

    def test_current_option_when_snoozed_1_day(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test current_option returns correct label for 1 day."""
        mock_coordinator.get_snooze_duration_key.return_value = SNOOZE_1_DAY
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)

        assert select.current_option == "1 Day"

    def test_extra_state_attributes_not_snoozed(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test extra_state_attributes when not snoozed."""
        mock_coordinator.is_snoozed.return_value = False
        mock_coordinator.snooze_until = None
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)

        attrs = select.extra_state_attributes

        assert attrs[ATTR_SNOOZE_ACTIVE] is False
        assert "description" in attrs
        assert ATTR_SNOOZE_UNTIL not in attrs

    def test_extra_state_attributes_snoozed_with_until(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test extra_state_attributes when snoozed with until timestamp."""
        mock_coordinator.is_snoozed.return_value = True
        snooze_time = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_coordinator.snooze_until = snooze_time
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)

        attrs = select.extra_state_attributes

        assert attrs[ATTR_SNOOZE_ACTIVE] is True
        assert ATTR_SNOOZE_UNTIL in attrs
        assert attrs[ATTR_SNOOZE_UNTIL] == snooze_time.isoformat()

    @pytest.mark.asyncio
    async def test_async_select_option_off(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test selecting Off calls async_clear_snooze."""
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)
        select.async_write_ha_state = MagicMock()

        await select.async_select_option("Off")

        mock_coordinator.async_clear_snooze.assert_called_once()
        mock_coordinator.async_snooze.assert_not_called()
        select.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_select_option_1_hour(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test selecting 1 Hour calls async_snooze with correct key."""
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)
        select.async_write_ha_state = MagicMock()

        await select.async_select_option("1 Hour")

        mock_coordinator.async_snooze.assert_called_once_with(SNOOZE_1_HOUR)
        mock_coordinator.async_clear_snooze.assert_not_called()
        select.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_select_option_2_hours(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test selecting 2 Hours calls async_snooze with correct key."""
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)
        select.async_write_ha_state = MagicMock()

        await select.async_select_option("2 Hours")

        mock_coordinator.async_snooze.assert_called_once_with(SNOOZE_2_HOURS)
        select.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_select_option_4_hours(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test selecting 4 Hours calls async_snooze with correct key."""
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)
        select.async_write_ha_state = MagicMock()

        await select.async_select_option("4 Hours")

        mock_coordinator.async_snooze.assert_called_once_with(SNOOZE_4_HOURS)
        select.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_select_option_1_day(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test selecting 1 Day calls async_snooze with correct key."""
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)
        select.async_write_ha_state = MagicMock()

        await select.async_select_option("1 Day")

        mock_coordinator.async_snooze.assert_called_once_with(SNOOZE_1_DAY)
        select.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_select_option_invalid(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test selecting invalid option does nothing."""
        select = SnoozeDurationSelect(mock_coordinator, mock_config_entry)
        select.async_write_ha_state = MagicMock()

        await select.async_select_option("Invalid Option")

        mock_coordinator.async_snooze.assert_not_called()
        mock_coordinator.async_clear_snooze.assert_not_called()
        # Invalid option returns early, doesn't write state
        select.async_write_ha_state.assert_not_called()


class TestAsyncSetupEntry:
    """Tests for the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_creates_snooze_select(self) -> None:
        """Test setup creates snooze duration select entity."""
        # Setup mocks
        mock_hass = MagicMock()
        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry_123"
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Verify select was added
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 1
        assert isinstance(entities[0], SnoozeDurationSelect)

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
