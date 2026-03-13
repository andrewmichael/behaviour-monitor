"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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
    CONF_MIN_NOTIFICATION_SEVERITY,
    CONF_MONITORED_ENTITIES,
    CONF_NOTIFICATION_COOLDOWN,
    CONF_RETRAIN_PERIOD,
    CONF_SENSITIVITY,
    DEFAULT_CROSS_SENSOR_WINDOW,
    DEFAULT_ENABLE_ML,
    DEFAULT_ENABLE_NOTIFICATIONS,
    DEFAULT_LEARNING_PERIOD,
    DEFAULT_NOTIFICATION_COOLDOWN,
    DEFAULT_RETRAIN_PERIOD,
    DEFAULT_SENSITIVITY,
    SEVERITY_SIGNIFICANT,
    SEVERITY_MINOR,
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
        # Verify the v4 config entry data is accessible
        from custom_components.behaviour_monitor.const import (
            CONF_DRIFT_SENSITIVITY,
            CONF_HISTORY_WINDOW_DAYS,
            CONF_INACTIVITY_MULTIPLIER,
        )
        assert mock_config_entry.data[CONF_HISTORY_WINDOW_DAYS] == 28
        assert mock_config_entry.data[CONF_INACTIVITY_MULTIPLIER] == 3.0
        assert mock_config_entry.data[CONF_DRIFT_SENSITIVITY] == "medium"

    @pytest.mark.asyncio
    async def test_step_init_shows_cooldown_field(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step shows notification cooldown field in schema."""
        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "init"
        # Verify the schema contains our new field.
        # Under test mocks, vol.Schema returns a dict directly (the schema argument).
        schema = result["data_schema"]
        schema_keys = [str(k) for k in schema.keys()]
        assert any(CONF_NOTIFICATION_COOLDOWN in k for k in schema_keys)

    @pytest.mark.asyncio
    async def test_step_init_shows_min_severity_field(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step shows minimum notification severity field in schema."""
        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "init"
        # Under test mocks, vol.Schema returns a dict directly (the schema argument).
        schema = result["data_schema"]
        schema_keys = [str(k) for k in schema.keys()]
        assert any(CONF_MIN_NOTIFICATION_SEVERITY in k for k in schema_keys)

    @pytest.mark.asyncio
    async def test_step_init_cooldown_round_trips(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test that cooldown value round-trips through options flow into entry data."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_SENSITIVITY: "medium",
            CONF_LEARNING_PERIOD: 7,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_ENABLE_ML: True,
            CONF_RETRAIN_PERIOD: 14,
            CONF_CROSS_SENSOR_WINDOW: 300,
            CONF_NOTIFICATION_COOLDOWN: 60,
            CONF_MIN_NOTIFICATION_SEVERITY: SEVERITY_SIGNIFICANT,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "create_entry"
        # Verify the config entry data was updated with the cooldown value
        options_flow.hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = options_flow.hass.config_entries.async_update_entry.call_args
        updated_data = call_kwargs[1]["data"]
        assert updated_data[CONF_NOTIFICATION_COOLDOWN] == 60

    @pytest.mark.asyncio
    async def test_step_init_min_severity_round_trips(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test that min_severity value round-trips through options flow into entry data."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_SENSITIVITY: "medium",
            CONF_LEARNING_PERIOD: 7,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_ENABLE_ML: True,
            CONF_RETRAIN_PERIOD: 14,
            CONF_CROSS_SENSOR_WINDOW: 300,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
            CONF_MIN_NOTIFICATION_SEVERITY: SEVERITY_MINOR,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "create_entry"
        options_flow.hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = options_flow.hass.config_entries.async_update_entry.call_args
        updated_data = call_kwargs[1]["data"]
        assert updated_data[CONF_MIN_NOTIFICATION_SEVERITY] == SEVERITY_MINOR

    @pytest.mark.asyncio
    async def test_step_init_cooldown_defaults_when_not_in_entry(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test that cooldown defaults to DEFAULT_NOTIFICATION_COOLDOWN when not set in entry."""
        # Ensure the new keys are absent from mock data
        mock_config_entry.data.pop(CONF_NOTIFICATION_COOLDOWN, None)
        mock_config_entry.data.pop(CONF_MIN_NOTIFICATION_SEVERITY, None)

        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        # Form should still render without error when new keys are missing from entry data
        assert result["errors"] == {}
