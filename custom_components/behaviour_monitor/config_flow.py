# custom_components/behaviour_monitor/config_flow.py
"""Config flow: site name, six category lists, whereabouts lists; tuning options."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
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
    CATEGORY_CONF_KEYS,
    CONF_BEDROOMS,
    CONF_CHAIN_WINDOW_S,
    CONF_CONTACT_ENTITIES,
    CONF_DRIFT_SENSITIVITY,
    CONF_HEALTH_GRACE_S,
    CONF_LOW_BATTERY_PCT,
    CONF_LEARNING_DAYS,
    CONF_ATTENTION_MIN_SEVERITY,
    CONF_MOTION_DEBOUNCE_S,
    CONF_OUTSIDE_DOORS,
    CONF_PLUG_ENTITIES,
    CONF_PLUG_MARGIN_W,
    CONF_SITE_NAME,
    CONF_SITTING_APPLIANCES,
    CONF_TIMING_PROMOTE_DAYS,
    CONF_WINDOW_DAYS,
    CONFIG_VERSION,
    DOMAIN,
    OPTION_DEFAULTS,
    SENSITIVITY_OPTIONS,
    SEVERITY_OPTIONS,
)
from .rooms import bedroom_suggestions, display_room, resolve_room

WHEREABOUTS_KEYS = (CONF_OUTSIDE_DOORS, CONF_BEDROOMS, CONF_SITTING_APPLIANCES)

_CATEGORY_DOMAINS: dict[str, list[str] | None] = {
    "motion": ["binary_sensor"],
    "contact": ["binary_sensor"],
    "plug": ["sensor", "switch"],
    "panic": ["binary_sensor"],
    "light": ["light", "switch"],
    "other": None,
}


def entity_specs_from_data(data: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for category, key in CATEGORY_CONF_KEYS.items():
        for eid in data.get(key) or []:
            out.append((eid, category))
    return out


def validate_categories(data: dict[str, Any]) -> str | None:
    specs = entity_specs_from_data(data)
    if not specs:
        return "no_entities"
    ids = [e for e, _ in specs]
    if len(ids) != len(set(ids)):
        return "duplicate_entity"
    return None


def _number_config(
    minimum: float, maximum: float, step: float, unit: str | None
) -> dict[str, Any]:
    """NumberSelector config. The unit key is omitted when there is no unit:
    Home Assistant validates it as a string, so None fails the whole form."""
    cfg: dict[str, Any] = {
        "min": minimum,
        "max": maximum,
        "step": step,
        "mode": NumberSelectorMode.BOX,
    }
    if unit is not None:
        cfg["unit_of_measurement"] = unit
    return cfg


def _number(
    key: str, minimum: float, maximum: float, step: float, unit: str | None = None
) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(**_number_config(minimum, maximum, step, unit))
    )


def _setup_schema(defaults: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_SITE_NAME, default=defaults.get(CONF_SITE_NAME, "")
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
    }
    for category, key in CATEGORY_CONF_KEYS.items():
        domains = _CATEGORY_DOMAINS[category]
        cfg = (
            EntitySelectorConfig(multiple=True, domain=domains)
            if domains
            else EntitySelectorConfig(multiple=True)
        )
        fields[vol.Optional(key, default=list(defaults.get(key) or []))] = (
            EntitySelector(cfg)
        )
    return vol.Schema(fields)


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    def d(key: str) -> Any:
        return current.get(key, OPTION_DEFAULTS[key])

    return vol.Schema(
        {
            vol.Required(
                CONF_MOTION_DEBOUNCE_S, default=d(CONF_MOTION_DEBOUNCE_S)
            ): _number(CONF_MOTION_DEBOUNCE_S, 10, 600, 5, "s"),
            vol.Required(CONF_PLUG_MARGIN_W, default=d(CONF_PLUG_MARGIN_W)): _number(
                CONF_PLUG_MARGIN_W, 1, 100, 1, "W"
            ),
            vol.Required(CONF_LEARNING_DAYS, default=d(CONF_LEARNING_DAYS)): _number(
                CONF_LEARNING_DAYS, 3, 60, 1, "d"
            ),
            vol.Required(CONF_WINDOW_DAYS, default=d(CONF_WINDOW_DAYS)): _number(
                CONF_WINDOW_DAYS, 7, 90, 1, "d"
            ),
            vol.Required(CONF_HEALTH_GRACE_S, default=d(CONF_HEALTH_GRACE_S)): _number(
                CONF_HEALTH_GRACE_S, 60, 7200, 30, "s"
            ),
            vol.Required(
                CONF_LOW_BATTERY_PCT, default=d(CONF_LOW_BATTERY_PCT)
            ): _number(CONF_LOW_BATTERY_PCT, 5, 50, 1, "%"),
            vol.Required(
                CONF_ATTENTION_MIN_SEVERITY, default=d(CONF_ATTENTION_MIN_SEVERITY)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=SEVERITY_OPTIONS, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(CONF_CHAIN_WINDOW_S, default=d(CONF_CHAIN_WINDOW_S)): _number(
                CONF_CHAIN_WINDOW_S, 120, 3600, 30, "s"
            ),
            vol.Required(
                CONF_TIMING_PROMOTE_DAYS, default=d(CONF_TIMING_PROMOTE_DAYS)
            ): _number(CONF_TIMING_PROMOTE_DAYS, 3, 30, 1, "d"),
            vol.Required(
                CONF_DRIFT_SENSITIVITY, default=d(CONF_DRIFT_SENSITIVITY)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=SENSITIVITY_OPTIONS, mode=SelectSelectorMode.DROPDOWN
                )
            ),
        }
    )


def _entity_label(hass: Any, entity_id: str, site: str) -> str:
    """Friendly name without a leading site name, or the entity id."""
    state = hass.states.get(entity_id) if hass is not None else None
    name = state.attributes.get("friendly_name") if state is not None else None
    return display_room(site, str(name)) if name else entity_id


def _tick_list(options: list[dict[str, str]]) -> SelectSelector:
    """All three whereabouts lists are tick boxes of the same style."""
    return SelectSelector(
        SelectSelectorConfig(
            options=sorted(options, key=lambda o: (o["label"].lower(), o["value"])),
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


def _whereabouts_schema(
    hass: Any, data: dict[str, Any], current: dict[str, Any]
) -> vol.Schema:
    """Tick lists: outside doors from the site's contacts, bedrooms from the
    rooms its sensors are in, and sitting appliances from its plugs.

    Current values are suggested rather than defaults: a default would refill
    a list the user cleared, and a cleared list must save as []. A saved
    value that is no longer offered (its sensor left the category) is dropped
    from the suggestion so the form can still be submitted.
    """
    site = str(data.get(CONF_SITE_NAME, ""))
    rooms = {resolve_room(hass, eid)[0] for eid, _ in entity_specs_from_data(data)}
    contacts = list(data.get(CONF_CONTACT_ENTITIES) or [])
    plugs = list(data.get(CONF_PLUG_ENTITIES) or [])
    saved = current.get(CONF_BEDROOMS)
    bedrooms = (
        bedroom_suggestions(rooms)
        if saved is None
        else [room for room in saved if room in rooms]
    )
    doors = [e for e in current.get(CONF_OUTSIDE_DOORS) or [] if e in contacts]
    sitting = [e for e in current.get(CONF_SITTING_APPLIANCES) or [] if e in plugs]
    return vol.Schema(
        {
            vol.Optional(
                CONF_OUTSIDE_DOORS, description={"suggested_value": doors}
            ): _tick_list(
                [{"value": e, "label": _entity_label(hass, e, site)} for e in contacts]
            ),
            vol.Optional(
                CONF_BEDROOMS, description={"suggested_value": bedrooms}
            ): _tick_list(
                [{"value": r, "label": display_room(site, r)} for r in rooms]
            ),
            vol.Optional(
                CONF_SITTING_APPLIANCES, description={"suggested_value": sitting}
            ): _tick_list(
                [{"value": e, "label": _entity_label(hass, e, site)} for e in plugs]
            ),
        }
    )


def validate_whereabouts(
    data: dict[str, Any], user_input: dict[str, Any]
) -> dict[str, str]:
    """Errors for a door that is not a contact or an appliance that is not a
    plug, which a list left over from before the categories changed can hold."""
    errors: dict[str, str] = {}
    contacts = set(data.get(CONF_CONTACT_ENTITIES) or [])
    plugs = set(data.get(CONF_PLUG_ENTITIES) or [])
    if not set(user_input.get(CONF_OUTSIDE_DOORS) or []) <= contacts:
        errors[CONF_OUTSIDE_DOORS] = "door_not_contact"
    if not set(user_input.get(CONF_SITTING_APPLIANCES) or []) <= plugs:
        errors[CONF_SITTING_APPLIANCES] = "appliance_not_plug"
    return errors


def _whereabouts_options(user_input: dict[str, Any]) -> dict[str, Any]:
    return {key: list(user_input.get(key) or []) for key in WHEREABOUTS_KEYS}


def _merged_schema(current: dict[str, Any]) -> Any:
    setup, options = _setup_schema(current), _options_schema(current)
    if hasattr(setup, "schema") and hasattr(options, "schema"):
        return vol.Schema({**setup.schema, **options.schema})
    return {
        **(setup if isinstance(setup, dict) else {}),
        **(options if isinstance(options, dict) else {}),
    }


def _split_input(user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (entry data, entry options) from a merged form submission."""
    data = {
        k: v
        for k, v in user_input.items()
        if k not in OPTION_DEFAULTS and k not in WHEREABOUTS_KEYS
    }
    for key in CATEGORY_CONF_KEYS.values():
        data[key] = list(user_input.get(key) or [])
    options = {k: user_input.get(k, dflt) for k, dflt in OPTION_DEFAULTS.items()}
    return data, options


class BehaviourMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = CONFIG_VERSION

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            err = validate_categories(user_input)
            if err:
                errors["base"] = err
            else:
                self._data, self._options = _split_input(user_input)
                await self.async_set_unique_id(
                    f"{DOMAIN}_{self._data[CONF_SITE_NAME].strip().lower()}"
                )
                self._abort_if_unique_id_configured()
                return await self.async_step_whereabouts()
        return self.async_show_form(
            step_id="user", data_schema=_setup_schema(user_input or {}), errors=errors
        )

    async def async_step_whereabouts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_whereabouts(self._data, user_input)
            if not errors:
                return self.async_create_entry(
                    title=self._data[CONF_SITE_NAME],
                    data=self._data,
                    options={**self._options, **_whereabouts_options(user_input)},
                )
        return self.async_show_form(
            step_id="whereabouts",
            data_schema=_whereabouts_schema(
                self.hass, self._data, {**self._options, **(user_input or {})}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> "BehaviourMonitorOptionsFlow":
        return BehaviourMonitorOptionsFlow(config_entry)


class BehaviourMonitorOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: Any) -> None:
        self._entry = config_entry
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = {**self._entry.data, **self._entry.options}
        if user_input is not None:
            merged = {**current, **user_input}
            for key in CATEGORY_CONF_KEYS.values():
                merged[key] = list(user_input.get(key) or [])
            err = validate_categories(merged)
            if err:
                errors["base"] = err
            else:
                self._data, self._options = _split_input(merged)
                return await self.async_step_whereabouts()
        schema = _merged_schema(current)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def async_step_whereabouts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Shown after init. The entry data is written only here, so leaving
        the flow at this step changes nothing."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_whereabouts(self._data, user_input)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    self._entry, data=self._data
                )
                return self.async_create_entry(
                    title="",
                    data={**self._options, **_whereabouts_options(user_input)},
                )
        current = {**self._entry.options, **(user_input or {})}
        return self.async_show_form(
            step_id="whereabouts",
            data_schema=_whereabouts_schema(self.hass, self._data, current),
            errors=errors,
        )
