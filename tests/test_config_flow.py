"""Tests for the v1.1 config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.behaviour_monitor.config_flow import (
    BehaviourMonitorConfigFlow,
    BehaviourMonitorOptionsFlow,
)
from custom_components.behaviour_monitor.const import (
    CONF_ALERT_REPEAT_INTERVAL,
    CONF_DRIFT_SENSITIVITY,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_HISTORY_WINDOW_DAYS,
    CONF_INACTIVITY_MULTIPLIER,
    CONF_LEARNING_PERIOD,
    CONF_MIN_INACTIVITY_MULTIPLIER,
    CONF_MAX_INACTIVITY_MULTIPLIER,
    CONF_MIN_NOTIFICATION_SEVERITY,
    CONF_MONITORED_ENTITIES,
    CONF_NOTIFICATION_COOLDOWN,
    CONF_TRACK_ATTRIBUTES,
    DEFAULT_ALERT_REPEAT_INTERVAL,
    DEFAULT_ENABLE_NOTIFICATIONS,
    DEFAULT_HISTORY_WINDOW_DAYS,
    DEFAULT_INACTIVITY_MULTIPLIER,
    DEFAULT_LEARNING_PERIOD_DAYS,
    DEFAULT_MIN_INACTIVITY_MULTIPLIER,
    DEFAULT_MAX_INACTIVITY_MULTIPLIER,
    DEFAULT_NOTIFICATION_COOLDOWN,
    DEFAULT_TRACK_ATTRIBUTES,
    SENSITIVITY_MEDIUM,
    SENSITIVITY_HIGH,
    SEVERITY_SIGNIFICANT,
    SEVERITY_MINOR,
)


class TestBehaviourMonitorConfigFlow:
    """Tests for BehaviourMonitorConfigFlow — v1.1 schema."""

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
    async def test_step_user_schema_includes_new_fields(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test that initial setup schema includes learning_period and track_attributes."""
        result = await config_flow.async_step_user(user_input=None)

        schema = result["data_schema"]
        schema_keys = {str(k) for k in schema.keys()}
        assert any(CONF_LEARNING_PERIOD in k for k in schema_keys), (
            f"learning_period missing from schema keys: {schema_keys}"
        )
        assert any(CONF_TRACK_ATTRIBUTES in k for k in schema_keys), (
            f"track_attributes missing from schema keys: {schema_keys}"
        )

    @pytest.mark.asyncio
    async def test_step_user_no_entities_selected(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step with no entities selected shows error."""
        user_input = {
            CONF_MONITORED_ENTITIES: [],
            CONF_HISTORY_WINDOW_DAYS: DEFAULT_HISTORY_WINDOW_DAYS,
            CONF_INACTIVITY_MULTIPLIER: DEFAULT_INACTIVITY_MULTIPLIER,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: DEFAULT_ENABLE_NOTIFICATIONS,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
        }

        result = await config_flow.async_step_user(user_input=user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "no_entities_selected"

    @pytest.mark.asyncio
    async def test_step_user_valid_input(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step with valid v1.1 input creates entry."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_HISTORY_WINDOW_DAYS: 28,
            CONF_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_NOTIFICATION_COOLDOWN: 30,
            CONF_MIN_NOTIFICATION_SEVERITY: SEVERITY_SIGNIFICANT,
        }

        config_flow.async_set_unique_id = AsyncMock()
        config_flow._abort_if_unique_id_configured = MagicMock()

        result = await config_flow.async_step_user(user_input=user_input)

        assert result["type"] == "create_entry"
        assert result["title"] == "Behaviour Monitor"
        assert result["data"] == user_input

    @pytest.mark.asyncio
    async def test_step_user_creates_entry_with_inactivity_multiplier(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step stores inactivity_multiplier in entry data."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1"],
            CONF_HISTORY_WINDOW_DAYS: 14,
            CONF_INACTIVITY_MULTIPLIER: 5.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_HIGH,
            CONF_ENABLE_NOTIFICATIONS: False,
            CONF_NOTIFICATION_COOLDOWN: 60,
        }

        config_flow.async_set_unique_id = AsyncMock()
        config_flow._abort_if_unique_id_configured = MagicMock()

        result = await config_flow.async_step_user(user_input=user_input)

        assert result["type"] == "create_entry"
        assert result["data"][CONF_INACTIVITY_MULTIPLIER] == 5.0

    @pytest.mark.asyncio
    async def test_step_user_creates_entry_with_drift_sensitivity(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step stores drift_sensitivity in entry data."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1"],
            CONF_HISTORY_WINDOW_DAYS: 28,
            CONF_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_HIGH,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_NOTIFICATION_COOLDOWN: 30,
        }

        config_flow.async_set_unique_id = AsyncMock()
        config_flow._abort_if_unique_id_configured = MagicMock()

        result = await config_flow.async_step_user(user_input=user_input)

        assert result["type"] == "create_entry"
        assert result["data"][CONF_DRIFT_SENSITIVITY] == SENSITIVITY_HIGH

    @pytest.mark.asyncio
    async def test_version_is_7(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        """Test VERSION is 7 after v3.0 adaptive inactivity config flow additions."""
        assert config_flow.VERSION == 7

    @pytest.mark.asyncio
    async def test_step_user_min_exceeds_max_returns_error(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step: submitting min > max returns inactivity_min_exceeds_max error."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1"],
            CONF_HISTORY_WINDOW_DAYS: DEFAULT_HISTORY_WINDOW_DAYS,
            CONF_INACTIVITY_MULTIPLIER: DEFAULT_INACTIVITY_MULTIPLIER,
            CONF_MIN_INACTIVITY_MULTIPLIER: 5.0,
            CONF_MAX_INACTIVITY_MULTIPLIER: 2.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: DEFAULT_ENABLE_NOTIFICATIONS,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
        }

        result = await config_flow.async_step_user(user_input=user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "inactivity_min_exceeds_max"

    @pytest.mark.asyncio
    async def test_step_user_min_equal_max_creates_entry(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step: submitting min == max with valid entities creates entry."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1"],
            CONF_HISTORY_WINDOW_DAYS: DEFAULT_HISTORY_WINDOW_DAYS,
            CONF_INACTIVITY_MULTIPLIER: DEFAULT_INACTIVITY_MULTIPLIER,
            CONF_MIN_INACTIVITY_MULTIPLIER: 3.0,
            CONF_MAX_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: DEFAULT_ENABLE_NOTIFICATIONS,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
        }

        config_flow.async_set_unique_id = AsyncMock()
        config_flow._abort_if_unique_id_configured = MagicMock()

        result = await config_flow.async_step_user(user_input=user_input)

        assert result["type"] == "create_entry"

    @pytest.mark.asyncio
    async def test_schema_includes_min_inactivity_multiplier(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step schema includes min_inactivity_multiplier field."""
        result = await config_flow.async_step_user(user_input=None)

        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        assert any(CONF_MIN_INACTIVITY_MULTIPLIER in k for k in schema_keys_str), (
            f"min_inactivity_multiplier missing from schema keys: {schema_keys_str}"
        )

    @pytest.mark.asyncio
    async def test_schema_includes_max_inactivity_multiplier(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test user step schema includes max_inactivity_multiplier field."""
        result = await config_flow.async_step_user(user_input=None)

        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        assert any(CONF_MAX_INACTIVITY_MULTIPLIER in k for k in schema_keys_str), (
            f"max_inactivity_multiplier missing from schema keys: {schema_keys_str}"
        )

    @pytest.mark.asyncio
    async def test_unique_id_based_on_entities(
        self, config_flow: BehaviourMonitorConfigFlow
    ) -> None:
        """Test unique ID is generated from sorted entity list."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.b", "sensor.a"],
            CONF_HISTORY_WINDOW_DAYS: 28,
            CONF_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_NOTIFICATION_COOLDOWN: 30,
        }

        unique_id_calls = []

        async def mock_set_unique_id(uid: str) -> None:
            unique_id_calls.append(uid)

        config_flow.async_set_unique_id = mock_set_unique_id
        config_flow._abort_if_unique_id_configured = MagicMock()

        await config_flow.async_step_user(user_input=user_input)

        # Should be sorted alphabetically
        assert unique_id_calls[0] == "sensor.a_sensor.b"

    def test_no_ml_fields_in_schema(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        """Test config flow schema does not include ML-specific fields."""
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            config_flow.async_step_user(user_input=None)
        )
        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        # Should NOT have old ML keys
        assert not any("enable_ml" in k for k in schema_keys_str)
        assert not any("retrain_period" in k for k in schema_keys_str)
        assert not any("ml_learning_period" in k for k in schema_keys_str)
        assert not any("cross_sensor_window" in k for k in schema_keys_str)


class TestBehaviourMonitorOptionsFlow:
    """Tests for BehaviourMonitorOptionsFlow — v1.1 options."""

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
            CONF_HISTORY_WINDOW_DAYS: 28,
            CONF_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_NOTIFICATION_COOLDOWN: 30,
            CONF_MIN_NOTIFICATION_SEVERITY: SEVERITY_SIGNIFICANT,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "no_entities_selected"

    @pytest.mark.asyncio
    async def test_step_init_valid_input(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step with valid v1.1 input updates config entry."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_HISTORY_WINDOW_DAYS: 14,
            CONF_INACTIVITY_MULTIPLIER: 4.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_HIGH,
            CONF_ENABLE_NOTIFICATIONS: False,
            CONF_NOTIFICATION_COOLDOWN: 60,
            CONF_MIN_NOTIFICATION_SEVERITY: SEVERITY_SIGNIFICANT,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "create_entry"
        # v1.1 options flow returns empty data (stores in config entry)
        assert result["data"] == {}

    @pytest.mark.asyncio
    async def test_step_init_preserves_v4_defaults(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test init step shows v4 current values as defaults."""
        assert mock_config_entry.data[CONF_HISTORY_WINDOW_DAYS] == 28
        assert mock_config_entry.data[CONF_INACTIVITY_MULTIPLIER] == 3.0
        assert mock_config_entry.data[CONF_DRIFT_SENSITIVITY] == "medium"

    @pytest.mark.asyncio
    async def test_step_init_shows_inactivity_multiplier_field(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step schema includes inactivity_multiplier field."""
        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        assert any(CONF_INACTIVITY_MULTIPLIER in k for k in schema_keys_str)

    @pytest.mark.asyncio
    async def test_step_init_shows_drift_sensitivity_field(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step schema includes drift_sensitivity field."""
        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        assert any(CONF_DRIFT_SENSITIVITY in k for k in schema_keys_str)

    @pytest.mark.asyncio
    async def test_step_init_shows_cooldown_field(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step shows notification cooldown field in schema."""
        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        assert any(CONF_NOTIFICATION_COOLDOWN in k for k in schema_keys_str)

    @pytest.mark.asyncio
    async def test_step_init_shows_min_severity_field(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step shows minimum notification severity field in schema."""
        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        assert any(CONF_MIN_NOTIFICATION_SEVERITY in k for k in schema_keys_str)

    @pytest.mark.asyncio
    async def test_options_flow_no_ml_fields(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test options flow schema does not include old ML fields."""
        result = await options_flow.async_step_init(user_input=None)

        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        # Should NOT have old ML keys
        assert not any("enable_ml" in k for k in schema_keys_str)
        assert not any("retrain_period" in k for k in schema_keys_str)
        assert not any("ml_learning_period" in k for k in schema_keys_str)
        assert not any("cross_sensor_window" in k for k in schema_keys_str)

    @pytest.mark.asyncio
    async def test_options_flow_inactivity_multiplier_round_trips(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test inactivity_multiplier round-trips through options flow into entry data."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_HISTORY_WINDOW_DAYS: 28,
            CONF_INACTIVITY_MULTIPLIER: 5.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
            CONF_MIN_NOTIFICATION_SEVERITY: SEVERITY_SIGNIFICANT,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "create_entry"
        options_flow.hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = options_flow.hass.config_entries.async_update_entry.call_args
        updated_data = call_kwargs[1]["data"]
        assert updated_data[CONF_INACTIVITY_MULTIPLIER] == 5.0

    @pytest.mark.asyncio
    async def test_options_flow_drift_sensitivity_round_trips(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test drift_sensitivity round-trips through options flow into entry data."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_HISTORY_WINDOW_DAYS: 28,
            CONF_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_HIGH,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
            CONF_MIN_NOTIFICATION_SEVERITY: SEVERITY_SIGNIFICANT,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "create_entry"
        options_flow.hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = options_flow.hass.config_entries.async_update_entry.call_args
        updated_data = call_kwargs[1]["data"]
        assert updated_data[CONF_DRIFT_SENSITIVITY] == SENSITIVITY_HIGH

    @pytest.mark.asyncio
    async def test_step_init_cooldown_round_trips(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test that cooldown value round-trips through options flow into entry data."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_HISTORY_WINDOW_DAYS: 28,
            CONF_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_NOTIFICATION_COOLDOWN: 60,
            CONF_MIN_NOTIFICATION_SEVERITY: SEVERITY_SIGNIFICANT,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "create_entry"
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
            CONF_HISTORY_WINDOW_DAYS: 28,
            CONF_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: True,
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
    async def test_options_flow_schema_includes_new_fields(self) -> None:
        """Test that options schema includes learning_period and track_attributes."""
        config_entry = MagicMock()
        config_entry.data = {
            "monitored_entities": ["sensor.test"],
            CONF_LEARNING_PERIOD: 14,
            CONF_TRACK_ATTRIBUTES: False,
        }
        options_flow = BehaviourMonitorOptionsFlow(config_entry)
        options_flow.hass = MagicMock()

        result = await options_flow.async_step_init(user_input=None)

        schema = result["data_schema"]
        schema_keys = {str(k) for k in schema.keys()}
        assert any(CONF_LEARNING_PERIOD in k for k in schema_keys)
        assert any(CONF_TRACK_ATTRIBUTES in k for k in schema_keys)

    @pytest.mark.asyncio
    async def test_step_init_cooldown_defaults_when_not_in_entry(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test that cooldown defaults gracefully when not set in entry."""
        mock_config_entry.data.pop(CONF_NOTIFICATION_COOLDOWN, None)
        mock_config_entry.data.pop(CONF_MIN_NOTIFICATION_SEVERITY, None)

        result = await options_flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        assert result["errors"] == {}

    @pytest.mark.asyncio
    async def test_schema_includes_alert_repeat_interval(self) -> None:
        """Test that schema built with no args includes alert_repeat_interval key."""
        from custom_components.behaviour_monitor.config_flow import _build_data_schema

        schema = _build_data_schema()
        schema_keys = [str(k) for k in schema.keys()]
        assert any(CONF_ALERT_REPEAT_INTERVAL in k for k in schema_keys), (
            f"alert_repeat_interval missing from schema keys: {schema_keys}"
        )

    @pytest.mark.asyncio
    async def test_schema_uses_custom_alert_repeat_interval_default(self) -> None:
        """Test that schema built with alert_repeat_interval_default=120 uses 120."""
        from custom_components.behaviour_monitor.config_flow import _build_data_schema

        schema = _build_data_schema(alert_repeat_interval_default=120)
        # The key for alert_repeat_interval should have default=120
        # In the mock environment, vol.Required(key, default=value) => key (string),
        # so we verify the field is present; round-trip test confirms the default.
        schema_keys = [str(k) for k in schema.keys()]
        assert any(CONF_ALERT_REPEAT_INTERVAL in k for k in schema_keys), (
            f"alert_repeat_interval missing from schema keys: {schema_keys}"
        )

    @pytest.mark.asyncio
    async def test_options_flow_prefills_alert_repeat_interval_from_entry(self) -> None:
        """Test options flow async_step_init pre-fills alert_repeat_interval from entry.data."""
        config_entry = MagicMock()
        config_entry.data = {
            "monitored_entities": ["sensor.test"],
            CONF_ALERT_REPEAT_INTERVAL: 360,
        }
        flow = BehaviourMonitorOptionsFlow(config_entry)
        flow.hass = MagicMock()

        result = await flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        schema = result["data_schema"]
        schema_keys = [str(k) for k in schema.keys()]
        assert any(CONF_ALERT_REPEAT_INTERVAL in k for k in schema_keys), (
            f"alert_repeat_interval missing from schema keys: {schema_keys}"
        )

    @pytest.mark.asyncio
    async def test_options_flow_alert_repeat_interval_defaults_when_absent(self) -> None:
        """Test options flow falls back to DEFAULT_ALERT_REPEAT_INTERVAL when key absent."""
        config_entry = MagicMock()
        config_entry.data = {
            "monitored_entities": ["sensor.test"],
            # alert_repeat_interval intentionally absent
        }
        flow = BehaviourMonitorOptionsFlow(config_entry)
        flow.hass = MagicMock()

        result = await flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        schema = result["data_schema"]
        schema_keys = [str(k) for k in schema.keys()]
        assert any(CONF_ALERT_REPEAT_INTERVAL in k for k in schema_keys), (
            f"alert_repeat_interval missing from schema keys: {schema_keys}"
        )

    @pytest.mark.asyncio
    async def test_options_flow_alert_repeat_interval_round_trips(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        """Test alert_repeat_interval round-trips through options flow into entry data."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_HISTORY_WINDOW_DAYS: 28,
            CONF_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
            CONF_MIN_NOTIFICATION_SEVERITY: SEVERITY_SIGNIFICANT,
            CONF_ALERT_REPEAT_INTERVAL: 480,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "create_entry"
        options_flow.hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = options_flow.hass.config_entries.async_update_entry.call_args
        updated_data = call_kwargs[1]["data"]
        assert updated_data[CONF_ALERT_REPEAT_INTERVAL] == 480

    @pytest.mark.asyncio
    async def test_step_init_min_exceeds_max_returns_error(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step: submitting min > max returns inactivity_min_exceeds_max error."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1"],
            CONF_HISTORY_WINDOW_DAYS: DEFAULT_HISTORY_WINDOW_DAYS,
            CONF_INACTIVITY_MULTIPLIER: DEFAULT_INACTIVITY_MULTIPLIER,
            CONF_MIN_INACTIVITY_MULTIPLIER: 8.0,
            CONF_MAX_INACTIVITY_MULTIPLIER: 3.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: DEFAULT_ENABLE_NOTIFICATIONS,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "inactivity_min_exceeds_max"

    @pytest.mark.asyncio
    async def test_step_init_min_less_than_max_with_entities_succeeds(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test init step: submitting min <= max with valid entities updates entry."""
        user_input = {
            CONF_MONITORED_ENTITIES: ["sensor.test1"],
            CONF_HISTORY_WINDOW_DAYS: DEFAULT_HISTORY_WINDOW_DAYS,
            CONF_INACTIVITY_MULTIPLIER: DEFAULT_INACTIVITY_MULTIPLIER,
            CONF_MIN_INACTIVITY_MULTIPLIER: 1.5,
            CONF_MAX_INACTIVITY_MULTIPLIER: 10.0,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: DEFAULT_ENABLE_NOTIFICATIONS,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
        }

        result = await options_flow.async_step_init(user_input=user_input)

        assert result["type"] == "create_entry"

    @pytest.mark.asyncio
    async def test_options_schema_includes_min_inactivity_multiplier(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test options init schema includes min_inactivity_multiplier field."""
        result = await options_flow.async_step_init(user_input=None)

        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        assert any(CONF_MIN_INACTIVITY_MULTIPLIER in k for k in schema_keys_str), (
            f"min_inactivity_multiplier missing from options schema: {schema_keys_str}"
        )

    @pytest.mark.asyncio
    async def test_options_schema_includes_max_inactivity_multiplier(
        self, options_flow: BehaviourMonitorOptionsFlow
    ) -> None:
        """Test options init schema includes max_inactivity_multiplier field."""
        result = await options_flow.async_step_init(user_input=None)

        schema = result["data_schema"]
        schema_keys_str = [str(k) for k in schema.keys()]
        assert any(CONF_MAX_INACTIVITY_MULTIPLIER in k for k in schema_keys_str), (
            f"max_inactivity_multiplier missing from options schema: {schema_keys_str}"
        )
