"""Tests for the button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.behaviour_monitor.button import (
    AcknowledgePanicButton,
    async_setup_entry,
)
from custom_components.behaviour_monitor.const import DOMAIN
from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator


class TestAcknowledgePanicButton:
    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        coordinator.panic_active = ["binary_sensor.sos"]
        coordinator.panic_unacknowledged = ["binary_sensor.sos"]
        coordinator.panic_devices = {"binary_sensor.sos": {"available": True, "battery": 50, "last_reported": None, "last_test": None}}
        coordinator.async_acknowledge_panic = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_config_entry(self) -> MagicMock:
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        return entry

    def test_initialization(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        button = AcknowledgePanicButton(mock_coordinator, mock_config_entry)
        assert button._attr_unique_id == "test_entry_123_acknowledge_panic"
        assert button._attr_name == "Acknowledge Panic"
        assert button._attr_icon == "mdi:alarm-light-off"
        assert button._attr_has_entity_name is True
        assert (DOMAIN, "test_entry_123") in button._attr_device_info["identifiers"]

    def test_extra_state_attributes(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        button = AcknowledgePanicButton(mock_coordinator, mock_config_entry)
        attrs = button.extra_state_attributes
        assert attrs["active_panics"] == ["binary_sensor.sos"]
        assert attrs["unacknowledged"] == 1
        assert attrs["devices"] == mock_coordinator.panic_devices

    @pytest.mark.asyncio
    async def test_press_acknowledges_all(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        button = AcknowledgePanicButton(mock_coordinator, mock_config_entry)
        await button.async_press()
        mock_coordinator.async_acknowledge_panic.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_setup_entry_adds_button(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        hass = MagicMock()
        hass.data = {DOMAIN: {"test_entry_123": mock_coordinator}}
        add = MagicMock()
        await async_setup_entry(hass, mock_config_entry, add)
        entities = add.call_args[0][0]
        assert len(entities) == 1
        assert isinstance(entities[0], AcknowledgePanicButton)
