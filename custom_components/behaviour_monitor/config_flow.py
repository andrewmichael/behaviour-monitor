"""Config flow for Behaviour Monitor integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_ALERT_REPEAT_INTERVAL,
    CONF_DRIFT_SENSITIVITY,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_HISTORY_WINDOW_DAYS,
    CONF_INACTIVITY_MULTIPLIER,
    CONF_LEARNING_PERIOD,
    CONF_MIN_NOTIFICATION_SEVERITY,
    CONF_MONITORED_ENTITIES,
    CONF_NOTIFICATION_COOLDOWN,
    CONF_NOTIFY_SERVICES,
    CONF_TRACK_ATTRIBUTES,
    DEFAULT_ALERT_REPEAT_INTERVAL,
    DEFAULT_ENABLE_NOTIFICATIONS,
    DEFAULT_HISTORY_WINDOW_DAYS,
    DEFAULT_INACTIVITY_MULTIPLIER,
    DEFAULT_LEARNING_PERIOD_DAYS,
    DEFAULT_MIN_NOTIFICATION_SEVERITY,
    DEFAULT_NOTIFICATION_COOLDOWN,
    DEFAULT_NOTIFY_SERVICES,
    DEFAULT_TRACK_ATTRIBUTES,
    DOMAIN,
    SENSITIVITY_HIGH,
    SENSITIVITY_LOW,
    SENSITIVITY_MEDIUM,
    SEVERITY_CRITICAL,
    SEVERITY_MINOR,
    SEVERITY_MODERATE,
    SEVERITY_SIGNIFICANT,
)

_LOGGER = logging.getLogger(__name__)


def _get_available_entities(hass: HomeAssistant) -> list[str]:
    """Get list of available entities that can be monitored."""
    registry = er.async_get(hass)
    entities = []

    for entity in registry.entities.values():
        if entity.disabled:
            continue
        entities.append(entity.entity_id)

    for state in hass.states.async_all():
        if state.entity_id not in entities:
            entities.append(state.entity_id)

    return sorted(entities)


def _build_data_schema(
    *,
    entities_default: list[str] | None = None,
    history_window_default: int = DEFAULT_HISTORY_WINDOW_DAYS,
    inactivity_multiplier_default: float = DEFAULT_INACTIVITY_MULTIPLIER,
    drift_sensitivity_default: str = SENSITIVITY_MEDIUM,
    enable_notifications_default: bool = DEFAULT_ENABLE_NOTIFICATIONS,
    notification_cooldown_default: int = DEFAULT_NOTIFICATION_COOLDOWN,
    alert_repeat_interval_default: int = DEFAULT_ALERT_REPEAT_INTERVAL,
    min_severity_default: str = DEFAULT_MIN_NOTIFICATION_SEVERITY,
    learning_period_default: int = DEFAULT_LEARNING_PERIOD_DAYS,
    track_attributes_default: bool = DEFAULT_TRACK_ATTRIBUTES,
) -> vol.Schema:
    """Build the shared config/options schema."""
    schema_dict: dict[vol.Marker, Any] = {
        vol.Required(CONF_MONITORED_ENTITIES): EntitySelector(
            EntitySelectorConfig(multiple=True)
        ),
        vol.Required(
            CONF_HISTORY_WINDOW_DAYS, default=history_window_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=7,
                max=90,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="days",
            )
        ),
        vol.Required(
            CONF_LEARNING_PERIOD, default=learning_period_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=1,
                max=30,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="days",
            )
        ),
        vol.Required(
            CONF_TRACK_ATTRIBUTES, default=track_attributes_default
        ): BooleanSelector(),
        vol.Required(
            CONF_INACTIVITY_MULTIPLIER, default=inactivity_multiplier_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=1.5,
                max=10.0,
                step=0.5,
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_DRIFT_SENSITIVITY, default=drift_sensitivity_default
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    {
                        "value": SENSITIVITY_HIGH,
                        "label": "High (sensitive to small shifts)",
                    },
                    {
                        "value": SENSITIVITY_MEDIUM,
                        "label": "Medium (balanced) - recommended",
                    },
                    {
                        "value": SENSITIVITY_LOW,
                        "label": "Low (major shifts only)",
                    },
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_ENABLE_NOTIFICATIONS, default=enable_notifications_default
        ): BooleanSelector(),
        vol.Optional(
            CONF_NOTIFY_SERVICES, default=DEFAULT_NOTIFY_SERVICES
        ): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT, multiple=True)
        ),
        vol.Required(
            CONF_NOTIFICATION_COOLDOWN, default=notification_cooldown_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=5,
                max=240,
                step=5,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="minutes",
            )
        ),
        vol.Required(
            CONF_ALERT_REPEAT_INTERVAL, default=alert_repeat_interval_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=30,
                max=1440,
                step=30,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="minutes",
            )
        ),
        vol.Required(
            CONF_MIN_NOTIFICATION_SEVERITY,
            default=min_severity_default,
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": SEVERITY_MINOR, "label": "Minor"},
                    {"value": SEVERITY_MODERATE, "label": "Moderate"},
                    {
                        "value": SEVERITY_SIGNIFICANT,
                        "label": "Significant - recommended",
                    },
                    {
                        "value": SEVERITY_CRITICAL,
                        "label": "Critical - very quiet",
                    },
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    }

    if entities_default is not None:
        # Replace the required marker with a default for options flow
        schema_dict = {
            (
                vol.Required(CONF_MONITORED_ENTITIES, default=entities_default)
                if k == vol.Required(CONF_MONITORED_ENTITIES)
                else k
            ): v
            for k, v in schema_dict.items()
        }

    return vol.Schema(schema_dict)


class BehaviourMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Behaviour Monitor."""

    VERSION = 6

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_MONITORED_ENTITIES):
                errors["base"] = "no_entities_selected"
            else:
                unique_id = "_".join(sorted(user_input[CONF_MONITORED_ENTITIES]))
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Behaviour Monitor",
                    data=user_input,
                )

        data_schema = _build_data_schema()

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return BehaviourMonitorOptionsFlow(config_entry)


class BehaviourMonitorOptionsFlow(OptionsFlow):
    """Handle options flow for Behaviour Monitor."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_MONITORED_ENTITIES):
                errors["base"] = "no_entities_selected"
            else:
                # Merge user input with existing data to preserve all fields
                updated_data = dict(self._config_entry.data)
                updated_data.update(user_input)

                # Explicitly handle optional fields that might be missing or empty
                # When notify_services field is cleared, it may be missing from
                # user_input entirely - set it to empty list
                if CONF_NOTIFY_SERVICES not in user_input:
                    updated_data[CONF_NOTIFY_SERVICES] = []
                elif not user_input.get(CONF_NOTIFY_SERVICES):
                    updated_data[CONF_NOTIFY_SERVICES] = []

                # Update the config entry data (not just options)
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=updated_data,
                )
                return self.async_create_entry(title="", data={})

        current_entities = self._config_entry.data.get(CONF_MONITORED_ENTITIES, [])
        current_history_window = self._config_entry.data.get(
            CONF_HISTORY_WINDOW_DAYS, DEFAULT_HISTORY_WINDOW_DAYS
        )
        current_inactivity_multiplier = self._config_entry.data.get(
            CONF_INACTIVITY_MULTIPLIER, DEFAULT_INACTIVITY_MULTIPLIER
        )
        current_drift_sensitivity = self._config_entry.data.get(
            CONF_DRIFT_SENSITIVITY, SENSITIVITY_MEDIUM
        )
        current_notifications = self._config_entry.data.get(
            CONF_ENABLE_NOTIFICATIONS, DEFAULT_ENABLE_NOTIFICATIONS
        )
        current_notify_services = self._config_entry.data.get(
            CONF_NOTIFY_SERVICES, DEFAULT_NOTIFY_SERVICES
        )
        current_cooldown = self._config_entry.data.get(
            CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN
        )
        current_alert_repeat_interval = self._config_entry.data.get(
            CONF_ALERT_REPEAT_INTERVAL, DEFAULT_ALERT_REPEAT_INTERVAL
        )
        current_min_severity = self._config_entry.data.get(
            CONF_MIN_NOTIFICATION_SEVERITY, DEFAULT_MIN_NOTIFICATION_SEVERITY
        )
        current_learning_period = self._config_entry.data.get(
            CONF_LEARNING_PERIOD, DEFAULT_LEARNING_PERIOD_DAYS
        )
        current_track_attributes = self._config_entry.data.get(
            CONF_TRACK_ATTRIBUTES, DEFAULT_TRACK_ATTRIBUTES
        )

        data_schema = _build_data_schema(
            entities_default=current_entities,
            history_window_default=current_history_window,
            inactivity_multiplier_default=current_inactivity_multiplier,
            drift_sensitivity_default=current_drift_sensitivity,
            enable_notifications_default=current_notifications,
            notification_cooldown_default=current_cooldown,
            alert_repeat_interval_default=current_alert_repeat_interval,
            min_severity_default=current_min_severity,
            learning_period_default=current_learning_period,
            track_attributes_default=current_track_attributes,
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                data_schema,
                {CONF_NOTIFY_SERVICES: current_notify_services},
            ),
            errors=errors,
        )
