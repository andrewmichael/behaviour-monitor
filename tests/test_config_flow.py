# tests/test_config_flow.py
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.behaviour_monitor.config_flow import (
    BehaviourMonitorConfigFlow,
    BehaviourMonitorOptionsFlow,
    entity_specs_from_data,
    validate_categories,
)
from custom_components.behaviour_monitor.const import (
    CONF_CONTACT_ENTITIES,
    CONF_LEARNING_DAYS,
    CONF_MOTION_DEBOUNCE_S,
    CONF_MOTION_ENTITIES,
    CONF_NOTIFY_SERVICE,
    CONF_PANIC_ENTITIES,
    CONF_SITE_NAME,
    OPTION_DEFAULTS,
)

GOOD = {
    CONF_SITE_NAME: "Biddulph Road",
    CONF_NOTIFY_SERVICE: "notify.mobile_app_phone",
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


@pytest.mark.asyncio
async def test_user_step_shows_form_then_creates_entry():
    flow = BehaviourMonitorConfigFlow()
    flow.hass = MagicMock()
    result = await flow.async_step_user(None)
    assert result["type"] == "form" and result["step_id"] == "user"
    result = await flow.async_step_user({**GOOD})
    assert result["type"] == "create_entry"
    assert result["title"] == "Biddulph Road"
    assert result["data"][CONF_MOTION_ENTITIES] == ["binary_sensor.k"]
    assert flow.VERSION == 11


@pytest.mark.asyncio
async def test_user_step_rejects_duplicates_and_empty():
    flow = BehaviourMonitorConfigFlow()
    flow.hass = MagicMock()
    result = await flow.async_step_user(
        {**GOOD, CONF_CONTACT_ENTITIES: ["binary_sensor.k"]}
    )
    assert result["type"] == "form" and result["errors"]["base"] == "duplicate_entity"
    result = await flow.async_step_user(
        {CONF_SITE_NAME: "x", CONF_NOTIFY_SERVICE: "notify.n"}
    )
    assert result["errors"]["base"] == "no_entities"


@pytest.mark.asyncio
async def test_options_flow_updates_data_and_options():
    entry = MagicMock()
    entry.data = dict(GOOD)
    entry.options = {}
    flow = BehaviourMonitorOptionsFlow(entry)
    flow.hass = MagicMock()
    result = await flow.async_step_init(None)
    assert result["type"] == "form" and result["step_id"] == "init"
    result = await flow.async_step_init(
        {
            **GOOD,
            CONF_MOTION_ENTITIES: ["binary_sensor.k", "binary_sensor.b"],
            CONF_LEARNING_DAYS: 21,
        }
    )
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


@pytest.mark.asyncio
async def test_options_flow_clearing_a_category_persists_empty_list():
    entry = MagicMock()
    entry.data = dict(GOOD)
    entry.options = {}
    flow = BehaviourMonitorOptionsFlow(entry)
    flow.hass = MagicMock()
    submitted = {
        CONF_SITE_NAME: GOOD[CONF_SITE_NAME],
        CONF_NOTIFY_SERVICE: GOOD[CONF_NOTIFY_SERVICE],
        CONF_MOTION_ENTITIES: GOOD[CONF_MOTION_ENTITIES],
    }
    result = await flow.async_step_init(submitted)
    assert result["type"] == "create_entry"
    kwargs = flow.hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"][CONF_CONTACT_ENTITIES] == []
    assert kwargs["data"][CONF_MOTION_ENTITIES] == GOOD[CONF_MOTION_ENTITIES]
