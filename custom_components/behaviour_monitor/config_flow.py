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
    CONF_ACTIVITY_TIER_OVERRIDE,
    CONF_ALERT_REPEAT_INTERVAL,
    CONF_BURST_DISCARD_THRESHOLD,
    CONF_CATEGORY_PANIC,
    CONF_CORRELATION_WINDOW,
    CONF_DOOR_DEBOUNCE_SECONDS,
    CONF_DOOR_OPEN_EXTENDED_SECONDS,
    CONF_DOOR_OPEN_PROLONGED_SECONDS,
    CONF_DRIFT_SENSITIVITY,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_EXCURSION_WINDOW_SECONDS,
    CONF_EXTERIOR_DOORS,
    CONF_HISTORY_WINDOW_DAYS,
    CONF_INACTIVITY_MULTIPLIER,
    CONF_LEARNING_PERIOD,
    CONF_MAX_INACTIVITY_MULTIPLIER,
    CONF_MIN_INACTIVITY_MULTIPLIER,
    CONF_MIN_NOTIFICATION_SEVERITY,
    CONF_MONITORED_ENTITIES,
    CONF_MOTION_DEBOUNCE_SECONDS,
    CONF_NOTIFICATION_COOLDOWN,
    CONF_NOTIFY_SERVICES,
    CONF_PANIC_HEARTBEAT_HOURS,
    CONF_PANIC_RENOTIFY_MINUTES,
    CONF_PANIC_TEST_REMINDER_DAYS,
    CONF_RETRIGGER_COLLAPSE_SECONDS,
    CONF_ROLE_OVERRIDES,
    CONF_STARTUP_GRACE_SECONDS,
    CONF_TRACK_ATTRIBUTES,
    CONF_TRACK_ATTRIBUTES_EXCLUDE,
    CONF_TRACK_ATTRIBUTES_INCLUDE,
    DEFAULT_ACTIVITY_TIER_OVERRIDE,
    DEFAULT_ALERT_REPEAT_INTERVAL,
    DEFAULT_BURST_DISCARD_THRESHOLD,
    DEFAULT_CATEGORY_PANIC,
    DEFAULT_CORRELATION_WINDOW,
    DEFAULT_DOOR_DEBOUNCE_SECONDS,
    DEFAULT_DOOR_OPEN_EXTENDED_SECONDS,
    DEFAULT_DOOR_OPEN_PROLONGED_SECONDS,
    DEFAULT_ENABLE_NOTIFICATIONS,
    DEFAULT_EXCURSION_WINDOW_SECONDS,
    DEFAULT_EXTERIOR_DOORS,
    DEFAULT_HISTORY_WINDOW_DAYS,
    DEFAULT_INACTIVITY_MULTIPLIER,
    DEFAULT_LEARNING_PERIOD_DAYS,
    DEFAULT_MAX_INACTIVITY_MULTIPLIER,
    DEFAULT_MIN_INACTIVITY_MULTIPLIER,
    DEFAULT_MIN_NOTIFICATION_SEVERITY,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
    DEFAULT_NOTIFICATION_COOLDOWN,
    DEFAULT_NOTIFY_SERVICES,
    DEFAULT_PANIC_HEARTBEAT_HOURS,
    DEFAULT_PANIC_RENOTIFY_MINUTES,
    DEFAULT_PANIC_TEST_REMINDER_DAYS,
    DEFAULT_RETRIGGER_COLLAPSE_SECONDS,
    DEFAULT_ROLE_OVERRIDES,
    DEFAULT_STARTUP_GRACE_SECONDS,
    DEFAULT_TRACK_ATTRIBUTES,
    DEFAULT_TRACK_ATTRIBUTES_EXCLUDE,
    DEFAULT_TRACK_ATTRIBUTES_INCLUDE,
    DOMAIN,
    ROLE_KINDS,
    SENSITIVITY_HIGH,
    SENSITIVITY_LOW,
    SENSITIVITY_MEDIUM,
    SEVERITY_CRITICAL,
    SEVERITY_MINOR,
    SEVERITY_MODERATE,
    SEVERITY_SIGNIFICANT,
)
from .entity_role import parse_role_overrides

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


def _validate_track_attribute_overrides(user_input: dict[str, Any]) -> str | None:
    """Return an error key if the per-entity override lists conflict, else None."""
    include = set(user_input.get(CONF_TRACK_ATTRIBUTES_INCLUDE) or [])
    exclude = set(user_input.get(CONF_TRACK_ATTRIBUTES_EXCLUDE) or [])
    if include & exclude:
        return "track_attributes_overlap"
    return None


def _validate_roles(user_input: dict[str, Any]) -> str | None:
    """Return an error key when the role inputs conflict, else None."""
    try:
        overrides = parse_role_overrides(user_input.get(CONF_ROLE_OVERRIDES) or "")
    except ValueError:
        return "role_overrides_invalid"
    panic = set(user_input.get(CONF_CATEGORY_PANIC) or [])
    exterior = set(user_input.get(CONF_EXTERIOR_DOORS) or [])
    full_role = {eid for eid, value in overrides.items() if value not in ROLE_KINDS}
    if panic & exterior or full_role & (panic | exterior):
        return "role_overlap"
    extended = int(user_input.get(CONF_DOOR_OPEN_EXTENDED_SECONDS, DEFAULT_DOOR_OPEN_EXTENDED_SECONDS))
    prolonged = int(user_input.get(CONF_DOOR_OPEN_PROLONGED_SECONDS, DEFAULT_DOOR_OPEN_PROLONGED_SECONDS))
    if extended >= prolonged:
        return "door_open_thresholds"
    return None


def _build_data_schema(
    *,
    entities_default: list[str] | None = None,
    history_window_default: int = DEFAULT_HISTORY_WINDOW_DAYS,
    inactivity_multiplier_default: float = DEFAULT_INACTIVITY_MULTIPLIER,
    min_inactivity_multiplier_default: float = DEFAULT_MIN_INACTIVITY_MULTIPLIER,
    max_inactivity_multiplier_default: float = DEFAULT_MAX_INACTIVITY_MULTIPLIER,
    drift_sensitivity_default: str = SENSITIVITY_MEDIUM,
    activity_tier_override_default: str = DEFAULT_ACTIVITY_TIER_OVERRIDE,
    correlation_window_default: int = DEFAULT_CORRELATION_WINDOW,
    enable_notifications_default: bool = DEFAULT_ENABLE_NOTIFICATIONS,
    notification_cooldown_default: int = DEFAULT_NOTIFICATION_COOLDOWN,
    alert_repeat_interval_default: int = DEFAULT_ALERT_REPEAT_INTERVAL,
    min_severity_default: str = DEFAULT_MIN_NOTIFICATION_SEVERITY,
    learning_period_default: int = DEFAULT_LEARNING_PERIOD_DAYS,
    track_attributes_default: bool = DEFAULT_TRACK_ATTRIBUTES,
    track_attributes_include_default: list[str] | None = None,
    track_attributes_exclude_default: list[str] | None = None,
    exterior_doors_default: list[str] | None = None,
    role_overrides_default: str = DEFAULT_ROLE_OVERRIDES,
    motion_debounce_seconds_default: int = DEFAULT_MOTION_DEBOUNCE_SECONDS,
    door_debounce_seconds_default: int = DEFAULT_DOOR_DEBOUNCE_SECONDS,
    retrigger_collapse_seconds_default: int = DEFAULT_RETRIGGER_COLLAPSE_SECONDS,
    excursion_window_seconds_default: int = DEFAULT_EXCURSION_WINDOW_SECONDS,
    door_open_extended_seconds_default: int = DEFAULT_DOOR_OPEN_EXTENDED_SECONDS,
    door_open_prolonged_seconds_default: int = DEFAULT_DOOR_OPEN_PROLONGED_SECONDS,
    category_panic_default: list[str] | None = None,
    panic_renotify_minutes_default: int = DEFAULT_PANIC_RENOTIFY_MINUTES,
    startup_grace_seconds_default: int = DEFAULT_STARTUP_GRACE_SECONDS,
    burst_discard_threshold_default: int = DEFAULT_BURST_DISCARD_THRESHOLD,
    panic_heartbeat_hours_default: int = DEFAULT_PANIC_HEARTBEAT_HOURS,
    panic_test_reminder_days_default: int = DEFAULT_PANIC_TEST_REMINDER_DAYS,
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
        vol.Optional(
            CONF_TRACK_ATTRIBUTES_INCLUDE,
            default=list(track_attributes_include_default or DEFAULT_TRACK_ATTRIBUTES_INCLUDE),
        ): EntitySelector(EntitySelectorConfig(multiple=True)),
        vol.Optional(
            CONF_TRACK_ATTRIBUTES_EXCLUDE,
            default=list(track_attributes_exclude_default or DEFAULT_TRACK_ATTRIBUTES_EXCLUDE),
        ): EntitySelector(EntitySelectorConfig(multiple=True)),
        vol.Optional(
            CONF_EXTERIOR_DOORS,
            default=list(exterior_doors_default or DEFAULT_EXTERIOR_DOORS),
        ): EntitySelector(EntitySelectorConfig(multiple=True, domain="binary_sensor")),
        vol.Optional(
            CONF_ROLE_OVERRIDES, default=role_overrides_default
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)),
        vol.Required(
            CONF_MOTION_DEBOUNCE_SECONDS, default=motion_debounce_seconds_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=600,
                step=10,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="seconds",
            )
        ),
        vol.Required(CONF_DOOR_DEBOUNCE_SECONDS, default=door_debounce_seconds_default): NumberSelector(
            NumberSelectorConfig(min=0, max=600, step=10, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
        vol.Required(CONF_RETRIGGER_COLLAPSE_SECONDS, default=retrigger_collapse_seconds_default): NumberSelector(
            NumberSelectorConfig(min=0, max=30, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
        vol.Required(CONF_EXCURSION_WINDOW_SECONDS, default=excursion_window_seconds_default): NumberSelector(
            NumberSelectorConfig(min=0, max=600, step=10, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
        vol.Required(CONF_DOOR_OPEN_EXTENDED_SECONDS, default=door_open_extended_seconds_default): NumberSelector(
            NumberSelectorConfig(min=1, max=3600, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
        vol.Required(CONF_DOOR_OPEN_PROLONGED_SECONDS, default=door_open_prolonged_seconds_default): NumberSelector(
            NumberSelectorConfig(min=1, max=86400, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
        vol.Optional(
            CONF_CATEGORY_PANIC,
            default=list(category_panic_default or DEFAULT_CATEGORY_PANIC),
        ): EntitySelector(EntitySelectorConfig(multiple=True, domain="binary_sensor")),
        vol.Required(
            CONF_PANIC_RENOTIFY_MINUTES, default=panic_renotify_minutes_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=1,
                max=60,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="minutes",
            )
        ),
        vol.Required(
            CONF_STARTUP_GRACE_SECONDS, default=startup_grace_seconds_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=300,
                step=10,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="seconds",
            )
        ),
        vol.Required(
            CONF_BURST_DISCARD_THRESHOLD, default=burst_discard_threshold_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=10,
                step=1,
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_PANIC_HEARTBEAT_HOURS, default=panic_heartbeat_hours_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=168,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="hours",
            )
        ),
        vol.Required(
            CONF_PANIC_TEST_REMINDER_DAYS, default=panic_test_reminder_days_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=365,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="days",
            )
        ),
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
            CONF_MIN_INACTIVITY_MULTIPLIER,
            default=min_inactivity_multiplier_default,
        ): NumberSelector(
            NumberSelectorConfig(
                min=0.5,
                max=5.0,
                step=0.5,
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_MAX_INACTIVITY_MULTIPLIER,
            default=max_inactivity_multiplier_default,
        ): NumberSelector(
            NumberSelectorConfig(
                min=2.0,
                max=20.0,
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
            CONF_ACTIVITY_TIER_OVERRIDE, default=activity_tier_override_default
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": "auto", "label": "Auto (recommended)"},
                    {"value": "high", "label": "High frequency"},
                    {"value": "medium", "label": "Medium frequency"},
                    {"value": "low", "label": "Low frequency"},
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_CORRELATION_WINDOW, default=correlation_window_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=30,
                max=600,
                step=10,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="seconds",
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

    VERSION = 14

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            min_val = float(
                user_input.get(
                    CONF_MIN_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER
                )
            )
            max_val = float(
                user_input.get(
                    CONF_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MAX_INACTIVITY_MULTIPLIER
                )
            )
            if min_val > max_val:
                errors["base"] = "inactivity_min_exceeds_max"
            elif not user_input.get(CONF_MONITORED_ENTITIES):
                errors["base"] = "no_entities_selected"
            elif (override_error := _validate_track_attribute_overrides(user_input)):
                errors["base"] = override_error
            elif (role_error := _validate_roles(user_input)):
                errors["base"] = role_error
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
            min_val = float(
                user_input.get(
                    CONF_MIN_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER
                )
            )
            max_val = float(
                user_input.get(
                    CONF_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MAX_INACTIVITY_MULTIPLIER
                )
            )
            if min_val > max_val:
                errors["base"] = "inactivity_min_exceeds_max"
            elif not user_input.get(CONF_MONITORED_ENTITIES):
                errors["base"] = "no_entities_selected"
            elif (override_error := _validate_track_attribute_overrides(user_input)):
                errors["base"] = override_error
            elif (role_error := _validate_roles(user_input)):
                errors["base"] = role_error
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

                # Same treatment for the per-entity override lists: a cleared
                # entity selector may be absent from user_input entirely
                for key in (
                    CONF_TRACK_ATTRIBUTES_INCLUDE,
                    CONF_TRACK_ATTRIBUTES_EXCLUDE,
                    CONF_CATEGORY_PANIC,
                    CONF_EXTERIOR_DOORS,
                ):
                    if not user_input.get(key):
                        updated_data[key] = []

                if not user_input.get(CONF_ROLE_OVERRIDES):
                    updated_data[CONF_ROLE_OVERRIDES] = ""

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
        current_track_attributes_include = self._config_entry.data.get(
            CONF_TRACK_ATTRIBUTES_INCLUDE, DEFAULT_TRACK_ATTRIBUTES_INCLUDE
        )
        current_track_attributes_exclude = self._config_entry.data.get(
            CONF_TRACK_ATTRIBUTES_EXCLUDE, DEFAULT_TRACK_ATTRIBUTES_EXCLUDE
        )
        current_min_inactivity_multiplier = self._config_entry.data.get(
            CONF_MIN_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER
        )
        current_max_inactivity_multiplier = self._config_entry.data.get(
            CONF_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MAX_INACTIVITY_MULTIPLIER
        )
        current_activity_tier_override = self._config_entry.data.get(
            CONF_ACTIVITY_TIER_OVERRIDE, DEFAULT_ACTIVITY_TIER_OVERRIDE
        )
        current_correlation_window = self._config_entry.data.get(
            CONF_CORRELATION_WINDOW, DEFAULT_CORRELATION_WINDOW
        )
        current_exterior_doors = self._config_entry.data.get(
            CONF_EXTERIOR_DOORS, DEFAULT_EXTERIOR_DOORS
        )
        current_role_overrides = self._config_entry.data.get(
            CONF_ROLE_OVERRIDES, DEFAULT_ROLE_OVERRIDES
        )
        current_motion_debounce_seconds = self._config_entry.data.get(
            CONF_MOTION_DEBOUNCE_SECONDS, DEFAULT_MOTION_DEBOUNCE_SECONDS
        )
        current_door_debounce_seconds = self._config_entry.data.get(
            CONF_DOOR_DEBOUNCE_SECONDS, DEFAULT_DOOR_DEBOUNCE_SECONDS
        )
        current_retrigger_collapse_seconds = self._config_entry.data.get(
            CONF_RETRIGGER_COLLAPSE_SECONDS, DEFAULT_RETRIGGER_COLLAPSE_SECONDS
        )
        current_excursion_window_seconds = self._config_entry.data.get(
            CONF_EXCURSION_WINDOW_SECONDS, DEFAULT_EXCURSION_WINDOW_SECONDS
        )
        current_door_open_extended_seconds = self._config_entry.data.get(
            CONF_DOOR_OPEN_EXTENDED_SECONDS, DEFAULT_DOOR_OPEN_EXTENDED_SECONDS
        )
        current_door_open_prolonged_seconds = self._config_entry.data.get(
            CONF_DOOR_OPEN_PROLONGED_SECONDS, DEFAULT_DOOR_OPEN_PROLONGED_SECONDS
        )
        current_category_panic = self._config_entry.data.get(
            CONF_CATEGORY_PANIC, DEFAULT_CATEGORY_PANIC
        )
        current_panic_renotify_minutes = self._config_entry.data.get(
            CONF_PANIC_RENOTIFY_MINUTES, DEFAULT_PANIC_RENOTIFY_MINUTES
        )
        current_startup_grace_seconds = self._config_entry.data.get(
            CONF_STARTUP_GRACE_SECONDS, DEFAULT_STARTUP_GRACE_SECONDS
        )
        current_burst_discard_threshold = self._config_entry.data.get(
            CONF_BURST_DISCARD_THRESHOLD, DEFAULT_BURST_DISCARD_THRESHOLD
        )
        current_panic_heartbeat_hours = self._config_entry.data.get(
            CONF_PANIC_HEARTBEAT_HOURS, DEFAULT_PANIC_HEARTBEAT_HOURS
        )
        current_panic_test_reminder_days = self._config_entry.data.get(
            CONF_PANIC_TEST_REMINDER_DAYS, DEFAULT_PANIC_TEST_REMINDER_DAYS
        )

        data_schema = _build_data_schema(
            entities_default=current_entities,
            history_window_default=current_history_window,
            inactivity_multiplier_default=current_inactivity_multiplier,
            min_inactivity_multiplier_default=current_min_inactivity_multiplier,
            max_inactivity_multiplier_default=current_max_inactivity_multiplier,
            drift_sensitivity_default=current_drift_sensitivity,
            activity_tier_override_default=current_activity_tier_override,
            correlation_window_default=current_correlation_window,
            enable_notifications_default=current_notifications,
            notification_cooldown_default=current_cooldown,
            alert_repeat_interval_default=current_alert_repeat_interval,
            min_severity_default=current_min_severity,
            learning_period_default=current_learning_period,
            track_attributes_default=current_track_attributes,
            track_attributes_include_default=current_track_attributes_include,
            track_attributes_exclude_default=current_track_attributes_exclude,
            exterior_doors_default=current_exterior_doors,
            role_overrides_default=current_role_overrides,
            motion_debounce_seconds_default=current_motion_debounce_seconds,
            door_debounce_seconds_default=current_door_debounce_seconds,
            retrigger_collapse_seconds_default=current_retrigger_collapse_seconds,
            excursion_window_seconds_default=current_excursion_window_seconds,
            door_open_extended_seconds_default=current_door_open_extended_seconds,
            door_open_prolonged_seconds_default=current_door_open_prolonged_seconds,
            category_panic_default=current_category_panic,
            panic_renotify_minutes_default=current_panic_renotify_minutes,
            startup_grace_seconds_default=current_startup_grace_seconds,
            burst_discard_threshold_default=current_burst_discard_threshold,
            panic_heartbeat_hours_default=current_panic_heartbeat_hours,
            panic_test_reminder_days_default=current_panic_test_reminder_days,
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                data_schema,
                {CONF_NOTIFY_SERVICES: current_notify_services},
            ),
            errors=errors,
        )
