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
    CONF_CROSS_SENSOR_WINDOW,
    CONF_ENABLE_ML,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_LEARNING_PERIOD,
    CONF_ML_LEARNING_PERIOD,
    CONF_MONITORED_ENTITIES,
    CONF_NOTIFY_SERVICES,
    CONF_RETRAIN_PERIOD,
    CONF_SENSITIVITY,
    CONF_TRACK_ATTRIBUTES,
    DEFAULT_CROSS_SENSOR_WINDOW,
    DEFAULT_ENABLE_ML,
    DEFAULT_ENABLE_NOTIFICATIONS,
    DEFAULT_LEARNING_PERIOD,
    DEFAULT_ML_LEARNING_PERIOD,
    DEFAULT_NOTIFY_SERVICES,
    DEFAULT_RETRAIN_PERIOD,
    DEFAULT_SENSITIVITY,
    DEFAULT_TRACK_ATTRIBUTES,
    DOMAIN,
    SENSITIVITY_HIGH,
    SENSITIVITY_LOW,
    SENSITIVITY_MEDIUM,
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


class BehaviourMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Behaviour Monitor."""

    VERSION = 2

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

        data_schema = vol.Schema(
            {
                vol.Required(CONF_MONITORED_ENTITIES): EntitySelector(
                    EntitySelectorConfig(multiple=True)
                ),
                vol.Required(
                    CONF_SENSITIVITY, default=DEFAULT_SENSITIVITY
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": SENSITIVITY_LOW, "label": "Low (3σ)"},
                            {"value": SENSITIVITY_MEDIUM, "label": "Medium (2σ)"},
                            {"value": SENSITIVITY_HIGH, "label": "High (1σ)"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_LEARNING_PERIOD, default=DEFAULT_LEARNING_PERIOD
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
                    CONF_ENABLE_NOTIFICATIONS, default=DEFAULT_ENABLE_NOTIFICATIONS
                ): BooleanSelector(),
                vol.Required(
                    CONF_ENABLE_ML, default=DEFAULT_ENABLE_ML
                ): BooleanSelector(),
                vol.Required(
                    CONF_ML_LEARNING_PERIOD, default=DEFAULT_ML_LEARNING_PERIOD
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
                    CONF_RETRAIN_PERIOD, default=DEFAULT_RETRAIN_PERIOD
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
                    CONF_CROSS_SENSOR_WINDOW, default=DEFAULT_CROSS_SENSOR_WINDOW
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=30,
                        max=900,
                        step=30,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
                vol.Required(
                    CONF_TRACK_ATTRIBUTES, default=DEFAULT_TRACK_ATTRIBUTES
                ): BooleanSelector(),
                vol.Optional(
                    CONF_NOTIFY_SERVICES, default=DEFAULT_NOTIFY_SERVICES
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT, multiple=True)
                ),
            }
        )

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
                    # Field is present but empty/None - explicitly set to empty list
                    updated_data[CONF_NOTIFY_SERVICES] = []

                # Update the config entry data (not just options)
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=updated_data,
                )
                return self.async_create_entry(title="", data={})

        current_entities = self._config_entry.data.get(CONF_MONITORED_ENTITIES, [])
        current_sensitivity = self._config_entry.data.get(
            CONF_SENSITIVITY, DEFAULT_SENSITIVITY
        )
        current_learning = self._config_entry.data.get(
            CONF_LEARNING_PERIOD, DEFAULT_LEARNING_PERIOD
        )
        current_notifications = self._config_entry.data.get(
            CONF_ENABLE_NOTIFICATIONS, DEFAULT_ENABLE_NOTIFICATIONS
        )
        current_enable_ml = self._config_entry.data.get(
            CONF_ENABLE_ML, DEFAULT_ENABLE_ML
        )
        current_ml_learning = self._config_entry.data.get(
            CONF_ML_LEARNING_PERIOD, DEFAULT_ML_LEARNING_PERIOD
        )
        current_retrain = self._config_entry.data.get(
            CONF_RETRAIN_PERIOD, DEFAULT_RETRAIN_PERIOD
        )
        current_cross_window = self._config_entry.data.get(
            CONF_CROSS_SENSOR_WINDOW, DEFAULT_CROSS_SENSOR_WINDOW
        )
        current_track_attributes = self._config_entry.data.get(
            CONF_TRACK_ATTRIBUTES, DEFAULT_TRACK_ATTRIBUTES
        )
        current_notify_services = self._config_entry.data.get(
            CONF_NOTIFY_SERVICES, DEFAULT_NOTIFY_SERVICES
        )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_MONITORED_ENTITIES, default=current_entities
                ): EntitySelector(EntitySelectorConfig(multiple=True)),
                vol.Required(
                    CONF_SENSITIVITY, default=current_sensitivity
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": SENSITIVITY_LOW, "label": "Low (3σ)"},
                            {"value": SENSITIVITY_MEDIUM, "label": "Medium (2σ)"},
                            {"value": SENSITIVITY_HIGH, "label": "High (1σ)"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_LEARNING_PERIOD, default=current_learning
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
                    CONF_ENABLE_NOTIFICATIONS, default=current_notifications
                ): BooleanSelector(),
                vol.Required(
                    CONF_ENABLE_ML, default=current_enable_ml
                ): BooleanSelector(),
                vol.Required(
                    CONF_ML_LEARNING_PERIOD, default=current_ml_learning
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
                    CONF_RETRAIN_PERIOD, default=current_retrain
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
                    CONF_CROSS_SENSOR_WINDOW, default=current_cross_window
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=30,
                        max=900,
                        step=30,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
                vol.Required(
                    CONF_TRACK_ATTRIBUTES, default=current_track_attributes
                ): BooleanSelector(),
                vol.Optional(CONF_NOTIFY_SERVICES): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.TEXT,
                        multiple=True,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                data_schema,
                {CONF_NOTIFY_SERVICES: current_notify_services},
            ),
            errors=errors,
        )
