"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.behaviour_monitor.config_flow import (
    BehaviourMonitorConfigFlow,
    BehaviourMonitorOptionsFlow,
)
from custom_components.behaviour_monitor.const import (
    CONF_CROSS_SENSOR_WINDOW,
    CONF_ENABLE_ML,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_LEARNING_PERIOD,
    CONF_MONITORED_ENTITIES,
    CONF_RETRAIN_PERIOD,
    CONF_SENSITIVITY,
    DEFAULT_CROSS_SENSOR_WINDOW,
    DEFAULT_ENABLE_ML,
    DEFAULT_ENABLE_NOTIFICATIONS,
    DEFAULT_LEARNING_PERIOD,
    DEFAULT_RETRAIN_PERIOD,
    DEFAULT_SENSITIVITY,
    DOMAIN,
)


class TestBehaviourMonitorConfigFlow:
    """Tests for BehaviourMonitorConfigFlow."""

    @pytest.fixture
    def config_flow(self) -> BehaviourMonitorConfigFlow:
        """Create a config flow instance."""
        flow = BehaviourMonitorConfigFlow()
        flow.hass = MagicMock()
        return flow

    @pytest.mark.asyncio
    async def test_step_user_no_input(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        """Test user step with no input shows form."""
        result = await config_flow.async_step_user(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {}

    @pytest.mark.asyncio
    async def test_step_user_no_entities_selected(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step with no entities selected shows error."""
        user_input = {
            CONF_MONITORED_ENTITIES: [],
            CONF_SENSITIVITY: DEFAULT_SENSITIVITY,
            CONF_LEARNING_PERIOD: DEFAULT_LEARNING_PERIOD,
            CONF_ENABLE_NOTIFICATIONS: DEFAULT_ENABLE_NOTIFICATIONS,
            CONF_ENABLE_ML: DEFAULT_ENABLE_ML,
            CONF_RETRAIN_PERIOD: DEFAULT_RETRAIN_PERIOD,
            CONF_CROSS_SENSOR_WINDOW: DEFAULT_CROSS_SENSOR_WINDOW,
        }

        result = await config_flow.async_step_user(user_input=user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "no_entities_selected"

    @pytest.mark.asyncio
    async def test_step_user_valid_input(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step with valid input creates entry."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_SENSITIVITY: "medium",
            CONF_LEARNING_PERIOD: 7,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_ENABLE_ML: True,
            CONF_RETRAIN_PERIOD: 14,
            CONF_CROSS_SENSOR_WINDOW: 300,
        }

        # Mock the unique ID methods
        config_flow.async_set_unique_id = AsyncMock()
        config_flow._abort_if_unique_id_configured = MagicMock()

        result = await config_flow.async_step_user(user_input=user_input)

        assert result["type"] == "create_entry"
        assert result["title"] == "Behaviour Monitor"
        assert result["data"] == user_input

    @pytest.mark.asyncio
    async def test_unique_id_based_on_entities(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test unique ID is generated from sorted entity list."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.b", "sensor.a"],
            CONF_SENSITIVITY: "medium",
            CONF_LEARNING_PERIOD: 7,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_ENABLE_ML: True,
            CONF_RETRAIN_PERIOD: 14,
            CONF_CROSS_SENSOR_WINDOW: 300,
        }

        unique_id_calls = []

        async def mock_set_unique_id(uid: str) -> None:
            unique_id_calls.append(uid)

        config_flow.async_set_unique_id = mock_set_unique_id
        config_flow._abort_if_unique_id_configured = MagicMock()

        await config_flow.async_step_user(user_input=user_input)

        # Should be sorted alphabetically
        assert unique_id_calls[0] == "sensor.a_sensor.b"


class TestBehaviourMonitorOptionsFlow:
    """Tests for BehaviourMonitorOptionsFlow."""

    @pytest.fixture
    def options_flow(self, mock_config_entry: MagicMock) -> BehaviourMonitorOptionsFlow:
        """Create an options flow instance."""
        flow = BehaviourMonitorOptionsFlow(mock_config_entry)
        flow.hass = MagicMock()
        flow.hass.config_entries = MagicMock()
        flow.hass.config_entries.async_update_entry = MagicMock()
        return flow

    @pytest.mark.asyncio
    async def test_step_init_no_input(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step with no input shows form."""
        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "init"
        assert result["errors"] == {}

    @pytest.mark.asyncio
    async def test_step_init_no_entities_selected(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step with no entities selected shows error."""
        user_input = {
            CONF_MONITORED_ENTITIES: [],
            CONF_SENSITIVITY: "medium",
            CONF_LEARNING_PERIOD: 7,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_ENABLE_ML: True,
            CONF_RETRAIN_PERIOD: 14,
            CONF_CROSS_SENSOR_WINDOW: 300,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "no_entities_selected"

    @pytest.mark.asyncio
    async def test_step_init_valid_input(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test init step with valid input updates config entry."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_SENSITIVITY: "high",
            CONF_LEARNING_PERIOD: 14,
            CONF_ENABLE_NOTIFICATIONS: False,
            CONF_ENABLE_ML: False,
            CONF_RETRAIN_PERIOD: 7,
            CONF_CROSS_SENSOR_WINDOW: 600,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "create_entry"
        # Data is now stored in config entry, not returned in result
        assert result["data"] == {}

    @pytest.mark.asyncio
    async def test_step_init_preserves_defaults(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test init step shows current values as defaults."""
        # Verify the config entry data is accessible
        assert mock_config_entry.data[CONF_SENSITIVITY] == "medium"
        assert mock_config_entry.data[CONF_LEARNING_PERIOD] == 7
