# tests/test_init.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.behaviour_monitor import (
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
    PLATFORMS,
)
from custom_components.behaviour_monitor.const import (
    CONF_MOTION_ENTITIES,
    CONF_SITE_NAME,
    DOMAIN,
    ISSUE_ASSIGN_CATEGORIES,
    OPTION_DEFAULTS,
    SERVICE_ACKNOWLEDGE,
    SERVICE_RESET_LEARNING,
    SERVICE_TEST_PANIC,
)


def _legacy_entry():
    e = MagicMock()
    e.entry_id = "old"
    e.version = 10
    e.title = "Behaviour Monitor"
    e.data = {
        "monitored_entities": ["binary_sensor.a", "sensor.b"],
        "history_window_days": 28,
    }
    e.options = {}
    return e


@pytest.mark.asyncio
async def test_migrate_v10_moves_entities_aside_and_raises_issue(mock_hass):
    from homeassistant.helpers import issue_registry as ir

    ir.async_create_issue.reset_mock()
    entry = _legacy_entry()
    assert await async_migrate_entry(mock_hass, entry) is True
    kwargs = mock_hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["version"] == 11
    assert kwargs["data"]["legacy_unassigned"] == ["binary_sensor.a", "sensor.b"]
    assert kwargs["data"][CONF_SITE_NAME] == "Behaviour Monitor"
    assert kwargs["data"][CONF_MOTION_ENTITIES] == []
    assert "monitored_entities" not in kwargs["data"]
    assert kwargs["options"] == OPTION_DEFAULTS
    ir.async_create_issue.assert_called_once()
    assert ir.async_create_issue.call_args.args[2] == f"{ISSUE_ASSIGN_CATEGORIES}_old"


@pytest.mark.asyncio
async def test_migrate_v11_is_noop(mock_hass, mock_config_entry):
    assert await async_migrate_entry(mock_hass, mock_config_entry) is True
    mock_hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_setup_unconfigured_entry_only_raises_issue(mock_hass, mock_config_entry):
    from homeassistant.helpers import issue_registry as ir

    ir.async_create_issue.reset_mock()
    mock_config_entry.data = {CONF_SITE_NAME: "X", "notify_service": "notify.n"}
    assert await async_setup_entry(mock_hass, mock_config_entry) is True
    ir.async_create_issue.assert_called_once()
    mock_hass.config_entries.async_forward_entry_setups.assert_not_awaited()


@pytest.mark.asyncio
async def test_setup_registers_platforms_and_services(mock_hass, mock_config_entry):
    with patch(
        "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
    ) as cls:
        coord = MagicMock()
        coord.async_setup = AsyncMock()
        coord.async_config_entry_first_refresh = AsyncMock()
        coord.async_acknowledge = AsyncMock()
        coord.async_reset_learning = AsyncMock()
        coord.async_test_panic = AsyncMock()
        cls.return_value = coord
        assert await async_setup_entry(mock_hass, mock_config_entry) is True
    mock_hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
        mock_config_entry, PLATFORMS
    )
    assert "button" in PLATFORMS
    registered = {
        c.args[1]: c.args[2] for c in mock_hass.services.async_register.call_args_list
    }
    assert {
        SERVICE_ACKNOWLEDGE,
        SERVICE_RESET_LEARNING,
        SERVICE_TEST_PANIC,
        "snooze",
        "clear_snooze",
        "enable_holiday_mode",
        "disable_holiday_mode",
    } <= set(registered)
    await registered[SERVICE_RESET_LEARNING](
        MagicMock(data={"entity_id": "binary_sensor.kitchen_motion"})
    )
    coord.async_reset_learning.assert_awaited_once_with("binary_sensor.kitchen_motion")
    await registered[SERVICE_TEST_PANIC](MagicMock(data={}))
    coord.async_test_panic.assert_awaited_once()


@pytest.mark.asyncio
async def test_unload_shuts_down_and_removes(mock_hass, mock_config_entry):
    coord = MagicMock()
    coord.async_shutdown = AsyncMock()
    mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: coord}}
    assert await async_unload_entry(mock_hass, mock_config_entry) is True
    coord.async_shutdown.assert_awaited_once()
    assert mock_config_entry.entry_id not in mock_hass.data[DOMAIN]
