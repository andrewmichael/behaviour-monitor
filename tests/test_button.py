"""Tests for the button platform: clear panic and test alert."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.behaviour_monitor.button import (
    ClearPanicButton,
    TestAlertButton,
    async_setup_entry,
)


@pytest.mark.asyncio
async def test_clear_panic_button_clears_all_panics(mock_hass, mock_config_entry):
    coordinator = MagicMock()
    coordinator.site_name = "Test House"
    coordinator.async_clear_alert = AsyncMock()
    mock_hass.data = {"behaviour_monitor": {mock_config_entry.entry_id: coordinator}}
    added = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, added)
    button = added.call_args.args[0][0]
    assert isinstance(button, ClearPanicButton)
    await button.async_press()
    coordinator.async_clear_alert.assert_awaited_once_with(None)
    assert button.unique_id == f"{mock_config_entry.entry_id}_acknowledge"
    assert button.name == "Clear panic"


@pytest.mark.asyncio
async def test_test_alert_button_opens_test_panic(mock_hass, mock_config_entry):
    coordinator = MagicMock()
    coordinator.site_name = "Test House"
    coordinator.async_test_panic = AsyncMock()
    mock_hass.data = {"behaviour_monitor": {mock_config_entry.entry_id: coordinator}}
    added = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, added)
    buttons = added.call_args.args[0]
    button = next(b for b in buttons if isinstance(b, TestAlertButton))
    assert button.unique_id == f"{mock_config_entry.entry_id}_test_notification"
    assert button.name == "Test alert"
    await button.async_press()
    coordinator.async_test_panic.assert_awaited_once()
