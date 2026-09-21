"""Tests for the button platform: acknowledge and test notification."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.behaviour_monitor.button import (
    AcknowledgeButton,
    TestNotificationButton,
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


@pytest.mark.asyncio
async def test_button_sends_test_notification(mock_hass, mock_config_entry):
    coordinator = MagicMock()
    coordinator.site_name = "Test House"
    coordinator.async_test_panic = AsyncMock()
    mock_hass.data = {"behaviour_monitor": {mock_config_entry.entry_id: coordinator}}
    added = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, added)
    buttons = added.call_args.args[0]
    button = next(b for b in buttons if isinstance(b, TestNotificationButton))
    assert button.unique_id == f"{mock_config_entry.entry_id}_test_notification"
    await button.async_press()
    coordinator.async_test_panic.assert_awaited_once()
