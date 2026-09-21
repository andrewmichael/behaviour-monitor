"""Tests for the acknowledge button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.behaviour_monitor.button import (
    AcknowledgeButton,
    async_setup_entry,
)


@pytest.mark.asyncio
async def test_button_acknowledges(mock_hass, mock_config_entry):
    coordinator = MagicMock()
    coordinator.site_name = "Test House"
    coordinator.async_acknowledge = AsyncMock()
    mock_hass.data = {"behaviour_monitor": {mock_config_entry.entry_id: coordinator}}
    added = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, added)
    button = added.call_args.args[0][0]
    assert isinstance(button, AcknowledgeButton)
    await button.async_press()
    coordinator.async_acknowledge.assert_awaited_once()
