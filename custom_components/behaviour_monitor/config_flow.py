# custom_components/behaviour_monitor/config_flow.py
"""Config flow: site name, notify service, six category lists; options for tuning."""

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
    CONF_CHAIN_WINDOW_S,
    CONF_DRIFT_SENSITIVITY,
    CONF_HEALTH_GRACE_S,
    CONF_HOUSE_LOW_RATIO,
    CONF_LEARNING_DAYS,
    CONF_MOTION_DEBOUNCE_S,
    CONF_NOTIFY_SERVICE,
    CONF_PLUG_MARGIN_W,
    CONF_PUSH_MIN_SEVERITY,
    CONF_PUSH_REPEAT_S,
    CONF_SITE_NAME,
    CONF_TIMING_PROMOTE_DAYS,
    CONF_WINDOW_DAYS,
    CONFIG_VERSION,
    DOMAIN,
    OPTION_DEFAULTS,
    SENSITIVITY_OPTIONS,
    SEVERITY_OPTIONS,
)

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
        vol.Required(
            CONF_NOTIFY_SERVICE, default=defaults.get(CONF_NOTIFY_SERVICE, "")
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
            vol.Required(CONF_PUSH_REPEAT_S, default=d(CONF_PUSH_REPEAT_S)): _number(
                CONF_PUSH_REPEAT_S, 300, 14400, 60, "s"
            ),
            vol.Required(
                CONF_PUSH_MIN_SEVERITY, default=d(CONF_PUSH_MIN_SEVERITY)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=SEVERITY_OPTIONS, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(
                CONF_HOUSE_LOW_RATIO, default=d(CONF_HOUSE_LOW_RATIO)
            ): _number(CONF_HOUSE_LOW_RATIO, 1.5, 10, 0.5),
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
    data = {k: v for k, v in user_input.items() if k not in OPTION_DEFAULTS}
    for key in CATEGORY_CONF_KEYS.values():
        data[key] = list(user_input.get(key) or [])
    options = {k: user_input.get(k, dflt) for k, dflt in OPTION_DEFAULTS.items()}
    return data, options


class BehaviourMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = CONFIG_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            err = validate_categories(user_input)
            if err:
                errors["base"] = err
            else:
                data, options = _split_input(user_input)
                await self.async_set_unique_id(
                    f"{DOMAIN}_{data[CONF_SITE_NAME].strip().lower()}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=data[CONF_SITE_NAME], data=data, options=options
                )
        return self.async_show_form(
            step_id="user", data_schema=_setup_schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> "BehaviourMonitorOptionsFlow":
        return BehaviourMonitorOptionsFlow(config_entry)


class BehaviourMonitorOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: Any) -> None:
        self._entry = config_entry

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
                data, options = _split_input(merged)
                self.hass.config_entries.async_update_entry(self._entry, data=data)
                return self.async_create_entry(title="", data=options)
        schema = _merged_schema(current)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
