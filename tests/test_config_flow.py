# tests/test_config_flow.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.behaviour_monitor.config_flow import (
    BehaviourMonitorConfigFlow,
    BehaviourMonitorOptionsFlow,
    _number_config,
    entity_specs_from_data,
    validate_categories,
)
from custom_components.behaviour_monitor.const import (
    CONF_BEDROOMS,
    CONF_CONTACT_ENTITIES,
    CONF_LEARNING_DAYS,
    CONF_MOTION_DEBOUNCE_S,
    CONF_MOTION_ENTITIES,
    CONF_OUTSIDE_DOORS,
    CONF_PANIC_ENTITIES,
    CONF_PLUG_ENTITIES,
    CONF_SITE_NAME,
    CONF_SITTING_APPLIANCES,
    OPTION_DEFAULTS,
)

GOOD = {
    CONF_SITE_NAME: "Biddulph Road",
    CONF_MOTION_ENTITIES: ["binary_sensor.k"],
    CONF_CONTACT_ENTITIES: ["binary_sensor.d"],
    CONF_PANIC_ENTITIES: ["binary_sensor.p"],
}


def test_validate_categories():
    assert validate_categories(GOOD) is None
    assert validate_categories({CONF_SITE_NAME: "x"}) == "no_entities"
    bad = {**GOOD, CONF_CONTACT_ENTITIES: ["binary_sensor.k"]}
    assert validate_categories(bad) == "duplicate_entity"


def test_entity_specs_from_data_in_category_order():
    assert entity_specs_from_data(GOOD) == [
        ("binary_sensor.k", "motion"),
        ("binary_sensor.d", "contact"),
        ("binary_sensor.p", "panic"),
    ]


NO_LISTS = {CONF_OUTSIDE_DOORS: [], CONF_BEDROOMS: [], CONF_SITTING_APPLIANCES: []}


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.states.get = lambda eid: None
    return hass


def _rooms(areas: dict[str, str]) -> None:
    """Put each entity in an area of the given name in the shared mock registry."""
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(None)
    reg.entities.clear()
    reg.devices.clear()
    reg.areas.clear()
    for eid, name in areas.items():
        reg.entities[eid] = SimpleNamespace(area_id=f"a_{eid}", device_id=None)
        reg.areas[f"a_{eid}"] = SimpleNamespace(name=name)


class _Key(str):
    """A schema key that remembers the default and description it was given."""

    default = None
    description = None


def _keyed(key, default=None, description=None, **kwargs):
    k = _Key(key)
    k.default = default
    k.description = description
    return k


def _defaults(schema) -> dict:
    return {str(k): k.default for k in schema if isinstance(k, _Key)}


def _suggested(schema) -> dict:
    return {
        str(k): (k.description or {}).get("suggested_value")
        for k in schema
        if isinstance(k, _Key)
    }


@pytest.mark.asyncio
async def test_user_step_then_whereabouts_step_creates_entry_with_lists():
    flow = BehaviourMonitorConfigFlow()
    flow.hass = _hass()
    result = await flow.async_step_user(None)
    assert result["type"] == "form" and result["step_id"] == "user"
    result = await flow.async_step_user({**GOOD})
    assert result["type"] == "form" and result["step_id"] == "whereabouts"
    result = await flow.async_step_whereabouts(
        {
            CONF_OUTSIDE_DOORS: ["binary_sensor.d"],
            CONF_BEDROOMS: ["Back Bedroom"],
            CONF_SITTING_APPLIANCES: [],
        }
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Biddulph Road"
    assert result["data"][CONF_MOTION_ENTITIES] == ["binary_sensor.k"]
    assert CONF_OUTSIDE_DOORS not in result["data"]
    options = result["options"]
    assert options[CONF_OUTSIDE_DOORS] == ["binary_sensor.d"]
    assert options[CONF_BEDROOMS] == ["Back Bedroom"]
    assert options[CONF_SITTING_APPLIANCES] == []
    assert options[CONF_LEARNING_DAYS] == OPTION_DEFAULTS[CONF_LEARNING_DAYS]
    assert flow.VERSION == 13


@pytest.mark.asyncio
async def test_bedrooms_default_to_rooms_named_bedroom(monkeypatch):
    from custom_components.behaviour_monitor import config_flow

    _rooms(
        {
            "binary_sensor.k": "Kitchen",
            "binary_sensor.d": "Biddulph Road Hall",
            "binary_sensor.p": "Back Bedroom",
        }
    )
    selects: list[dict] = []
    monkeypatch.setattr(config_flow.vol, "Optional", _keyed)
    monkeypatch.setattr(
        config_flow, "SelectSelectorConfig", lambda **kw: selects.append(kw) or kw
    )
    flow = BehaviourMonitorConfigFlow()
    flow.hass = _hass()
    result = await flow.async_step_user({**GOOD})
    # Suggested, not defaults: a default would refill a list the user cleared.
    suggested = _suggested(result["data_schema"])
    assert suggested[CONF_BEDROOMS] == ["Back Bedroom"]
    assert suggested[CONF_OUTSIDE_DOORS] == []
    assert suggested[CONF_SITTING_APPLIANCES] == []
    assert _defaults(result["data_schema"]) == {
        CONF_BEDROOMS: None,
        CONF_OUTSIDE_DOORS: None,
        CONF_SITTING_APPLIANCES: None,
    }
    # All three lists are tick boxes of the same style: doors, bedrooms, plugs.
    doors, beds, plugs = selects[-3:]
    list_mode = config_flow.SelectSelectorMode.LIST
    assert all(s["mode"] == list_mode and s["multiple"] for s in selects[-3:])
    # Values are the raw room names; labels drop the site-name prefix.
    assert beds["options"] == [
        {"value": "Back Bedroom", "label": "Back Bedroom"},
        {"value": "Biddulph Road Hall", "label": "Hall"},
        {"value": "Kitchen", "label": "Kitchen"},
    ]
    # Doors offer only the site's contacts; with no friendly name, the id.
    assert doors["options"] == [
        {"value": "binary_sensor.d", "label": "binary_sensor.d"}
    ]
    assert plugs["options"] == []


@pytest.mark.asyncio
async def test_door_and_plug_ticks_use_friendly_names_without_the_site(monkeypatch):
    from custom_components.behaviour_monitor import config_flow

    _rooms({"binary_sensor.d": "Hall", "sensor.tv": "Back room"})
    selects: list[dict] = []
    monkeypatch.setattr(config_flow.vol, "Optional", _keyed)
    monkeypatch.setattr(
        config_flow, "SelectSelectorConfig", lambda **kw: selects.append(kw) or kw
    )
    names = {
        "binary_sensor.d": "Biddulph Road Front door",
        "sensor.tv": "Back room TV plug",
    }
    flow = BehaviourMonitorConfigFlow()
    flow.hass = _hass()
    flow.hass.states.get = lambda eid: (
        SimpleNamespace(attributes={"friendly_name": names[eid]})
        if eid in names
        else None
    )
    await flow.async_step_user({**GOOD, CONF_PLUG_ENTITIES: ["sensor.tv"]})
    doors, _, plugs = selects[-3:]
    assert doors["options"] == [{"value": "binary_sensor.d", "label": "Front door"}]
    assert plugs["options"] == [{"value": "sensor.tv", "label": "Back room TV plug"}]


@pytest.mark.asyncio
async def test_options_flow_whereabouts_step_rejects_door_not_contact():
    entry = MagicMock()
    entry.data = {**GOOD, CONF_PLUG_ENTITIES: ["sensor.tv_power"]}
    entry.options = {}
    flow = BehaviourMonitorOptionsFlow(entry)
    flow.hass = _hass()
    result = await flow.async_step_init(dict(entry.data))
    assert result["type"] == "form" and result["step_id"] == "whereabouts"
    result = await flow.async_step_whereabouts(
        {**NO_LISTS, CONF_OUTSIDE_DOORS: ["binary_sensor.k"]}
    )
    assert result["type"] == "form" and result["step_id"] == "whereabouts"
    assert result["errors"] == {CONF_OUTSIDE_DOORS: "door_not_contact"}
    result = await flow.async_step_whereabouts(
        {**NO_LISTS, CONF_SITTING_APPLIANCES: ["binary_sensor.d"]}
    )
    assert result["errors"] == {CONF_SITTING_APPLIANCES: "appliance_not_plug"}
    flow.hass.config_entries.async_update_entry.assert_not_called()
    result = await flow.async_step_whereabouts(
        {
            CONF_OUTSIDE_DOORS: ["binary_sensor.d"],
            CONF_BEDROOMS: [],
            CONF_SITTING_APPLIANCES: ["sensor.tv_power"],
        }
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_OUTSIDE_DOORS] == ["binary_sensor.d"]
    assert result["data"][CONF_SITTING_APPLIANCES] == ["sensor.tv_power"]
    assert result["data"][CONF_BEDROOMS] == []


@pytest.mark.asyncio
async def test_options_flow_clearing_whereabouts_lists_saves_empty_lists(
    monkeypatch,
):
    """A cleared list is left out of the submission and must save as []."""
    from custom_components.behaviour_monitor import config_flow

    monkeypatch.setattr(config_flow.vol, "Optional", _keyed)
    entry = MagicMock()
    entry.data = {**GOOD, CONF_PLUG_ENTITIES: ["sensor.tv_power"]}
    entry.options = {
        CONF_OUTSIDE_DOORS: ["binary_sensor.d"],
        CONF_BEDROOMS: ["Kitchen"],
        CONF_SITTING_APPLIANCES: ["sensor.tv_power"],
    }
    flow = BehaviourMonitorOptionsFlow(entry)
    flow.hass = _hass()
    result = await flow.async_step_init(dict(entry.data))
    assert _suggested(result["data_schema"])[CONF_OUTSIDE_DOORS] == ["binary_sensor.d"]
    assert _defaults(result["data_schema"])[CONF_OUTSIDE_DOORS] is None
    result = await flow.async_step_whereabouts({})
    assert result["type"] == "create_entry"
    assert result["data"][CONF_OUTSIDE_DOORS] == []
    assert result["data"][CONF_BEDROOMS] == []
    assert result["data"][CONF_SITTING_APPLIANCES] == []


@pytest.mark.asyncio
async def test_user_step_rejects_duplicates_and_empty():
    flow = BehaviourMonitorConfigFlow()
    flow.hass = MagicMock()
    result = await flow.async_step_user(
        {**GOOD, CONF_CONTACT_ENTITIES: ["binary_sensor.k"]}
    )
    assert result["type"] == "form" and result["errors"]["base"] == "duplicate_entity"
    result = await flow.async_step_user({CONF_SITE_NAME: "x"})
    assert result["errors"]["base"] == "no_entities"


@pytest.mark.asyncio
async def test_options_flow_updates_data_and_options():
    entry = MagicMock()
    entry.data = dict(GOOD)
    entry.options = {}
    flow = BehaviourMonitorOptionsFlow(entry)
    flow.hass = _hass()
    result = await flow.async_step_init(None)
    assert result["type"] == "form" and result["step_id"] == "init"
    result = await flow.async_step_init(
        {
            **GOOD,
            CONF_MOTION_ENTITIES: ["binary_sensor.k", "binary_sensor.b"],
            CONF_LEARNING_DAYS: 21,
        }
    )
    assert result["step_id"] == "whereabouts"
    result = await flow.async_step_whereabouts(dict(NO_LISTS))
    assert result["type"] == "create_entry"
    assert result["data"][CONF_LEARNING_DAYS] == 21
    assert (
        result["data"][CONF_MOTION_DEBOUNCE_S] == OPTION_DEFAULTS["motion_debounce_s"]
    )
    flow.hass.config_entries.async_update_entry.assert_called_once()
    kwargs = flow.hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"][CONF_MOTION_ENTITIES] == [
        "binary_sensor.k",
        "binary_sensor.b",
    ]
    assert CONF_LEARNING_DAYS not in kwargs["data"]
    assert CONF_OUTSIDE_DOORS not in kwargs["data"]


@pytest.mark.asyncio
async def test_options_flow_clearing_a_category_persists_empty_list():
    entry = MagicMock()
    entry.data = dict(GOOD)
    entry.options = {}
    flow = BehaviourMonitorOptionsFlow(entry)
    flow.hass = _hass()
    submitted = {
        CONF_SITE_NAME: GOOD[CONF_SITE_NAME],
        CONF_MOTION_ENTITIES: GOOD[CONF_MOTION_ENTITIES],
    }
    await flow.async_step_init(submitted)
    result = await flow.async_step_whereabouts(dict(NO_LISTS))
    assert result["type"] == "create_entry"
    kwargs = flow.hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"][CONF_CONTACT_ENTITIES] == []
    assert kwargs["data"][CONF_MOTION_ENTITIES] == GOOD[CONF_MOTION_ENTITIES]


def test_number_config_omits_unit_when_none():
    """Home Assistant's NumberSelector requires a string unit when the key is
    present, so a unitless option must leave the key out entirely rather than
    pass None. Passing None makes every options form fail to build (400)."""
    assert "unit_of_measurement" not in _number_config(1.5, 10, 0.5, None)
    assert _number_config(10, 600, 5, "s")["unit_of_measurement"] == "s"


def _field_names(schema) -> set[str]:
    fields = schema.schema if hasattr(schema, "schema") else schema
    return {str(k) for k in fields}


def test_setup_form_has_no_notify_service():
    from custom_components.behaviour_monitor.config_flow import _setup_schema

    assert "notify_service" not in _field_names(_setup_schema({}))


def test_options_form_has_attention_severity_and_no_push_options():
    from custom_components.behaviour_monitor.config_flow import _options_schema

    names = _field_names(_options_schema({}))
    assert "attention_min_severity" in names
    assert not {"push_repeat_s", "push_min_severity", "notify_service"} & names
    assert "house_low_ratio" not in names


def test_options_form_has_low_battery_level_defaulting_to_20():
    from custom_components.behaviour_monitor import config_flow

    defaults: dict = {}

    def required(key, default=None):
        defaults[key] = default
        return key

    with patch.object(config_flow.vol, "Required", side_effect=required), patch.object(
        config_flow, "_number", wraps=config_flow._number
    ) as number:
        config_flow._options_schema({})
        assert defaults["low_battery_pct"] == 20
        number.assert_any_call("low_battery_pct", 5, 50, 1, "%")
        config_flow._options_schema({"low_battery_pct": 35})
        assert defaults["low_battery_pct"] == 35
