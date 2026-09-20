# Generic Welfare Core Implementation Plan (Part 2 of 2: Home Assistant shell)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the v4 coordinator, config flow, sensors and services with a thin Home Assistant shell around `core.engine.Engine`, with category config, room resolution from areas, class-based delivery, migration and a real-site fixture exporter.

**Architecture:** The coordinator translates Home Assistant into `Engine` calls and `DeliveryAction` values into service calls, repair issues and logbook entries. Rooms come from the entity or device area registry with the site name stripped for display. Sensors read the engine snapshot. Old detector modules and their tests are deleted.

**Tech Stack:** Home Assistant custom integration APIs (config entries, DataUpdateCoordinator, Store, entity/device/area registries, issue_registry, recorder history). Tests use the existing `tests/conftest.py` module mocks, extended in Task 3.

**Spec:** `docs/superpowers/specs/2026-09-20-generic-welfare-core-design.md`

**Prerequisite:** Part 1 (`docs/superpowers/plans/2026-09-20-generic-welfare-core.md`) is complete and committed.

## Global Constraints

- The coordinator is the only file that imports both Home Assistant and `core`. Platforms import the coordinator only.
- Config entry version becomes 11. Store version becomes 11 and a v10 store is discarded.
- Option keys and defaults match the spec's table exactly: `motion_debounce_s` 90, `plug_margin_w` 5, `learning_days` 14, `window_days` 28, `health_grace_s` 900, `push_repeat_s` 1800, `push_min_severity` medium, `house_low_ratio` 3, `chain_window_s` 1800, `timing_promote_days` 7, `drift_sensitivity` medium.
- Category config keys: `motion_entities`, `contact_entities`, `plug_entities`, `panic_entities`, `light_entities`, `other_entities`. Plus `site_name` and `notify_service`.
- Manifest version 5.0.0. Device `sw_version` reads from one constant `VERSION` in `const.py`; no hard-coded version strings in platforms.
- Black 88, ruff clean, conventional commits, run `venv/bin/python -m pytest tests/ -q` before each commit.

## File map

| File | Change |
|---|---|
| `const.py` | rewrite: new keys, defaults, versions, attrs, services |
| `config_flow.py` | rewrite: setup and options steps |
| `coordinator.py` | rewrite around `Engine` |
| `sensor.py` | rewrite to the snapshot shape |
| `button.py` | new: Acknowledge button |
| `switch.py`, `select.py` | device info via `VERSION`; select reads snooze from coordinator |
| `__init__.py` | migration v11, services, platforms |
| `services.yaml`, `translations/en.json` | new services and fields |
| `scripts/export_fixture.py` | new: real-site export |
| delete | `routine_model.py`, `acute_detector.py`, `drift_detector.py`, `correlation_detector.py`, `alert_result.py`, their tests, `tests/test_coordinator_correlation.py` |
| `tests/conftest.py` | more HA mocks |
| `Makefile`, `README.md`, `CLAUDE.md`, `manifest.json` | docs and version |

---

### Task 1: Constants

**Files:**
- Modify: `custom_components/behaviour_monitor/const.py` (full rewrite)
- Create: `tests/test_const.py`

**Interfaces:**
- Produces every name used by later tasks: `DOMAIN`, `VERSION`, `CONFIG_VERSION`, `STORAGE_KEY`, `STORAGE_VERSION`, `UPDATE_INTERVAL`, `CONF_SITE_NAME`, `CONF_NOTIFY_SERVICE`, `CATEGORY_CONF_KEYS` (ordered dict category value to key), `CONF_MOTION_ENTITIES` etc, option keys `CONF_MOTION_DEBOUNCE_S` ... `CONF_DRIFT_SENSITIVITY`, `OPTION_DEFAULTS` dict, `SNOOZE_*` (kept), `SERVICE_ACKNOWLEDGE`, `SERVICE_RESET_LEARNING`, `SERVICE_TEST_PANIC`, `SERVICE_ENABLE_HOLIDAY_MODE`, `SERVICE_DISABLE_HOLIDAY_MODE`, `SERVICE_SNOOZE`, `SERVICE_CLEAR_SNOOZE`, `ISSUE_ASSIGN_CATEGORIES`, `LEGACY_CONF_MONITORED_ENTITIES`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_const.py
from custom_components.behaviour_monitor import const


def test_category_keys_cover_all_six_categories_in_order():
    assert list(const.CATEGORY_CONF_KEYS) == ["motion", "contact", "plug", "panic", "light", "other"]
    assert const.CATEGORY_CONF_KEYS["motion"] == const.CONF_MOTION_ENTITIES == "motion_entities"
    assert const.CATEGORY_CONF_KEYS["other"] == "other_entities"


def test_option_defaults_match_spec():
    assert const.OPTION_DEFAULTS == {
        "motion_debounce_s": 90,
        "plug_margin_w": 5,
        "learning_days": 14,
        "window_days": 28,
        "health_grace_s": 900,
        "push_repeat_s": 1800,
        "push_min_severity": "medium",
        "house_low_ratio": 3,
        "chain_window_s": 1800,
        "timing_promote_days": 7,
        "drift_sensitivity": "medium",
    }


def test_versions_and_services():
    assert const.CONFIG_VERSION == 11 and const.STORAGE_VERSION == 11
    assert const.VERSION == "5.0.0"
    assert const.SERVICE_ACKNOWLEDGE == "acknowledge"
    assert const.SERVICE_RESET_LEARNING == "reset_learning"
    assert const.SERVICE_TEST_PANIC == "test_panic"
    assert const.SNOOZE_DURATIONS["1_hour"] == 3600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_const.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'CATEGORY_CONF_KEYS'`

- [ ] **Step 3: Write the new const.py**

```python
# custom_components/behaviour_monitor/const.py
"""Constants for the Behaviour Monitor integration (v5)."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "behaviour_monitor"
VERSION: Final = "5.0.0"
CONFIG_VERSION: Final = 11
STORAGE_KEY: Final = "behaviour_monitor"
STORAGE_VERSION: Final = 11
UPDATE_INTERVAL: Final = 60  # seconds
SAVE_DEBOUNCE_S: Final = 30

# Setup-step config keys
CONF_SITE_NAME: Final = "site_name"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_MOTION_ENTITIES: Final = "motion_entities"
CONF_CONTACT_ENTITIES: Final = "contact_entities"
CONF_PLUG_ENTITIES: Final = "plug_entities"
CONF_PANIC_ENTITIES: Final = "panic_entities"
CONF_LIGHT_ENTITIES: Final = "light_entities"
CONF_OTHER_ENTITIES: Final = "other_entities"

CATEGORY_CONF_KEYS: Final[dict[str, str]] = {
    "motion": CONF_MOTION_ENTITIES,
    "contact": CONF_CONTACT_ENTITIES,
    "plug": CONF_PLUG_ENTITIES,
    "panic": CONF_PANIC_ENTITIES,
    "light": CONF_LIGHT_ENTITIES,
    "other": CONF_OTHER_ENTITIES,
}

# Options-step keys (names match EngineConfig.from_options)
CONF_MOTION_DEBOUNCE_S: Final = "motion_debounce_s"
CONF_PLUG_MARGIN_W: Final = "plug_margin_w"
CONF_LEARNING_DAYS: Final = "learning_days"
CONF_WINDOW_DAYS: Final = "window_days"
CONF_HEALTH_GRACE_S: Final = "health_grace_s"
CONF_PUSH_REPEAT_S: Final = "push_repeat_s"
CONF_PUSH_MIN_SEVERITY: Final = "push_min_severity"
CONF_HOUSE_LOW_RATIO: Final = "house_low_ratio"
CONF_CHAIN_WINDOW_S: Final = "chain_window_s"
CONF_TIMING_PROMOTE_DAYS: Final = "timing_promote_days"
CONF_DRIFT_SENSITIVITY: Final = "drift_sensitivity"

OPTION_DEFAULTS: Final[dict[str, int | str]] = {
    CONF_MOTION_DEBOUNCE_S: 90,
    CONF_PLUG_MARGIN_W: 5,
    CONF_LEARNING_DAYS: 14,
    CONF_WINDOW_DAYS: 28,
    CONF_HEALTH_GRACE_S: 900,
    CONF_PUSH_REPEAT_S: 1800,
    CONF_PUSH_MIN_SEVERITY: "medium",
    CONF_HOUSE_LOW_RATIO: 3,
    CONF_CHAIN_WINDOW_S: 1800,
    CONF_TIMING_PROMOTE_DAYS: 7,
    CONF_DRIFT_SENSITIVITY: "medium",
}

SEVERITY_OPTIONS: Final = ["low", "medium", "high", "critical"]
SENSITIVITY_OPTIONS: Final = ["low", "medium", "high"]

# Legacy (v10) key kept only for migration
LEGACY_CONF_MONITORED_ENTITIES: Final = "monitored_entities"

# Snooze
SNOOZE_OFF: Final = "off"
SNOOZE_DURATIONS: Final = {
    SNOOZE_OFF: 0,
    "1_hour": 3600,
    "2_hours": 7200,
    "4_hours": 14400,
    "1_day": 86400,
}
SNOOZE_OPTIONS: Final = list(SNOOZE_DURATIONS)
SNOOZE_LABELS: Final = {
    SNOOZE_OFF: "Off",
    "1_hour": "1 Hour",
    "2_hours": "2 Hours",
    "4_hours": "4 Hours",
    "1_day": "1 Day",
}

# Services
SERVICE_ENABLE_HOLIDAY_MODE: Final = "enable_holiday_mode"
SERVICE_DISABLE_HOLIDAY_MODE: Final = "disable_holiday_mode"
SERVICE_SNOOZE: Final = "snooze"
SERVICE_CLEAR_SNOOZE: Final = "clear_snooze"
SERVICE_ACKNOWLEDGE: Final = "acknowledge"
SERVICE_RESET_LEARNING: Final = "reset_learning"
SERVICE_TEST_PANIC: Final = "test_panic"

# Repair issue ids
ISSUE_ASSIGN_CATEGORIES: Final = "assign_categories"
ISSUE_HEALTH_PREFIX: Final = "health_"

# Events
EVENT_LOGBOOK: Final = "logbook_entry"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_const.py -v`
Expected: 3 passed. Other test files now fail to import because old constants are gone; that is expected until Task 8 deletes them.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/const.py tests/test_const.py
git commit -m "feat!: v5 constants with category config keys and spec option defaults"
```

---

### Task 2: Config flow

**Files:**
- Modify: `custom_components/behaviour_monitor/config_flow.py` (full rewrite)
- Modify: `tests/test_config_flow.py` (full rewrite)

**Interfaces:**
- Produces: `BehaviourMonitorConfigFlow` (VERSION 11) with `async_step_user`, `BehaviourMonitorOptionsFlow` with `async_step_init`, helpers `entity_specs_from_data(data) -> list[tuple[str, str]]` returning `(entity_id, category)` pairs in category order, and `validate_categories(data) -> str | None` returning an error key: `no_entities` when every list is empty, `duplicate_entity` when an entity appears in two lists.
- Entry `data` holds site name, notify service and the six lists. Entry `options` holds the tuning keys.

- [ ] **Step 1: Write the failing test**

```python
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
    result = await flow.async_step_user({**GOOD, CONF_CONTACT_ENTITIES: ["binary_sensor.k"]})
    assert result["type"] == "form" and result["errors"]["base"] == "duplicate_entity"
    result = await flow.async_step_user({CONF_SITE_NAME: "x", CONF_NOTIFY_SERVICE: "notify.n"})
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
    result = await flow.async_step_init({**GOOD, CONF_MOTION_ENTITIES: ["binary_sensor.k", "binary_sensor.b"], CONF_LEARNING_DAYS: 21})
    assert result["type"] == "create_entry"
    assert result["data"][CONF_LEARNING_DAYS] == 21
    assert result["data"][CONF_MOTION_DEBOUNCE_S] == OPTION_DEFAULTS["motion_debounce_s"]
    flow.hass.config_entries.async_update_entry.assert_called_once()
    kwargs = flow.hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["data"][CONF_MOTION_ENTITIES] == ["binary_sensor.k", "binary_sensor.b"]
    assert CONF_LEARNING_DAYS not in kwargs["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_config_flow.py -v`
Expected: FAIL with `ImportError: cannot import name 'entity_specs_from_data'`

- [ ] **Step 3: Write the new config flow**

```python
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


def _number(key: str, minimum: float, maximum: float, step: float, unit: str | None = None) -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX, unit_of_measurement=unit))


def _setup_schema(defaults: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_SITE_NAME, default=defaults.get(CONF_SITE_NAME, "")): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
        vol.Required(CONF_NOTIFY_SERVICE, default=defaults.get(CONF_NOTIFY_SERVICE, "")): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
    }
    for category, key in CATEGORY_CONF_KEYS.items():
        domains = _CATEGORY_DOMAINS[category]
        cfg = EntitySelectorConfig(multiple=True, domain=domains) if domains else EntitySelectorConfig(multiple=True)
        fields[vol.Optional(key, default=list(defaults.get(key) or []))] = EntitySelector(cfg)
    return vol.Schema(fields)


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    def d(key: str) -> Any:
        return current.get(key, OPTION_DEFAULTS[key])

    return vol.Schema(
        {
            vol.Required(CONF_MOTION_DEBOUNCE_S, default=d(CONF_MOTION_DEBOUNCE_S)): _number(CONF_MOTION_DEBOUNCE_S, 10, 600, 5, "s"),
            vol.Required(CONF_PLUG_MARGIN_W, default=d(CONF_PLUG_MARGIN_W)): _number(CONF_PLUG_MARGIN_W, 1, 100, 1, "W"),
            vol.Required(CONF_LEARNING_DAYS, default=d(CONF_LEARNING_DAYS)): _number(CONF_LEARNING_DAYS, 3, 60, 1, "d"),
            vol.Required(CONF_WINDOW_DAYS, default=d(CONF_WINDOW_DAYS)): _number(CONF_WINDOW_DAYS, 7, 90, 1, "d"),
            vol.Required(CONF_HEALTH_GRACE_S, default=d(CONF_HEALTH_GRACE_S)): _number(CONF_HEALTH_GRACE_S, 60, 7200, 30, "s"),
            vol.Required(CONF_PUSH_REPEAT_S, default=d(CONF_PUSH_REPEAT_S)): _number(CONF_PUSH_REPEAT_S, 300, 14400, 60, "s"),
            vol.Required(CONF_PUSH_MIN_SEVERITY, default=d(CONF_PUSH_MIN_SEVERITY)): SelectSelector(SelectSelectorConfig(options=SEVERITY_OPTIONS, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_HOUSE_LOW_RATIO, default=d(CONF_HOUSE_LOW_RATIO)): _number(CONF_HOUSE_LOW_RATIO, 1.5, 10, 0.5),
            vol.Required(CONF_CHAIN_WINDOW_S, default=d(CONF_CHAIN_WINDOW_S)): _number(CONF_CHAIN_WINDOW_S, 120, 3600, 30, "s"),
            vol.Required(CONF_TIMING_PROMOTE_DAYS, default=d(CONF_TIMING_PROMOTE_DAYS)): _number(CONF_TIMING_PROMOTE_DAYS, 3, 30, 1, "d"),
            vol.Required(CONF_DRIFT_SENSITIVITY, default=d(CONF_DRIFT_SENSITIVITY)): SelectSelector(SelectSelectorConfig(options=SENSITIVITY_OPTIONS, mode=SelectSelectorMode.DROPDOWN)),
        }
    )


def _split_input(user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (entry data, entry options) from a merged form submission."""
    data = {k: v for k, v in user_input.items() if k not in OPTION_DEFAULTS}
    for key in CATEGORY_CONF_KEYS.values():
        data[key] = list(user_input.get(key) or [])
    options = {k: user_input.get(k, dflt) for k, dflt in OPTION_DEFAULTS.items()}
    return data, options


class BehaviourMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = CONFIG_VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            err = validate_categories(user_input)
            if err:
                errors["base"] = err
            else:
                data, options = _split_input(user_input)
                await self.async_set_unique_id(f"{DOMAIN}_{data[CONF_SITE_NAME].strip().lower()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_SITE_NAME], data=data, options=options)
        return self.async_show_form(step_id="user", data_schema=_setup_schema(user_input or {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> "BehaviourMonitorOptionsFlow":
        return BehaviourMonitorOptionsFlow(config_entry)


class BehaviourMonitorOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: Any) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = {**self._entry.data, **self._entry.options}
        if user_input is not None:
            merged = {**current, **user_input}
            err = validate_categories(merged)
            if err:
                errors["base"] = err
            else:
                data, options = _split_input(merged)
                self.hass.config_entries.async_update_entry(self._entry, data=data)
                return self.async_create_entry(title="", data=options)
        schema = vol.Schema({**_setup_schema(current).schema, **_options_schema(current).schema})
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
```

The conftest mocks `voluptuous.Schema` as identity and `vol.Required` as its key, so `_setup_schema(current).schema` must not be used in tests. Guard it: in `async_step_init`, build `schema` as `_merged_schema(current)` defined as:

```python
def _merged_schema(current: dict[str, Any]) -> Any:
    setup, options = _setup_schema(current), _options_schema(current)
    if hasattr(setup, "schema") and hasattr(options, "schema"):
        return vol.Schema({**setup.schema, **options.schema})
    return {**(setup if isinstance(setup, dict) else {}), **(options if isinstance(options, dict) else {})}
```

and call `_merged_schema(current)` in place of the inline `vol.Schema({...})`.

Also `async_create_entry` in the real `ConfigFlow` accepts `options=`; the conftest mock does not. Extend the mock in Task 3 Step 1 (see below) before running this test; until then the test passes with the `options` keyword dropped by the mock's `**kwargs`. Add `**kwargs` to the mock's `async_create_entry` signatures in `tests/conftest.py` now:

```python
        def async_create_entry(self, title, data, description=None, description_placeholders=None, **kwargs):
            return {"type": "create_entry", "title": title, "data": data, "description": description,
                    "description_placeholders": description_placeholders, "options": kwargs.get("options", {})}
```

and for `MockOptionsFlow`:

```python
        def async_create_entry(self, title="", data=None, **kwargs):
            return {"type": "create_entry", "title": title, "data": data or {}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_config_flow.py tests/test_const.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/config_flow.py tests/test_config_flow.py tests/conftest.py
git commit -m "feat!: config flow with site name, notify service and six category lists"
```

---

### Task 3: Coordinator around the Engine

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py` (full rewrite)
- Modify: `tests/conftest.py` (add registry, issue, button and recorder mocks; new `mock_config_entry`)
- Modify: `tests/test_coordinator.py` (full rewrite)

**Interfaces:**
- Produces `BehaviourMonitorCoordinator(hass, entry)` with:
  - `async_setup()`, `async_shutdown()`
  - `site_name`, `display_room(room) -> str`, `entity_specs -> list[EntitySpec]`, `holiday_mode`, `snooze_until`, `is_snoozed()`, `get_snooze_duration_key()`
  - `async_enable_holiday_mode()`, `async_disable_holiday_mode()`, `async_snooze(key)`, `async_clear_snooze()`, `async_acknowledge()`, `async_reset_learning(entity_id=None)`, `async_test_panic()`
  - `data` is `engine.snapshot(now)` plus `"site": site_name`, `"last_notification": {"timestamp", "kind"}`.
- Delivery: `push` calls the configured notify service with `title=f"{site} welfare"` and `message=explanation`, plus `persistent_notification.create` with `notification_id=f"{DOMAIN}_{entry_id}_welfare"`; `push_clear` calls the notify service with "Cleared: ..." and dismisses the persistent notification; `repair_create` and `repair_delete` use `issue_registry.async_create_issue` / `async_delete_issue` with issue id `f"{ISSUE_HEALTH_PREFIX}{entry_id}_{alert.key}"`; `log` fires `logbook_entry` on the bus with `name=site`, `message=explanation`, `domain=DOMAIN`; `log_clear` does nothing.
- Room resolution: entity registry entry `area_id`, else its device's `area_id`, else the entity's friendly name from `hass.states`, else the entity id. Area names come from `area_registry`. Display name strips a leading site name.

- [ ] **Step 1: Extend conftest mocks**

Add inside `_setup_ha_mocks()` after the storage mock:

```python
    # Registries: entity, device, area
    class _Reg:
        def __init__(self):
            self.entities = {}
            self.devices = {}
            self.areas = {}

        def async_get(self, key):
            return self.entities.get(key) or self.devices.get(key) or self.areas.get(key)

        def async_get_area(self, area_id):
            return self.areas.get(area_id)

    _registry = _Reg()
    for mod_name in ("entity_registry", "device_registry", "area_registry"):
        mod = MagicMock()
        mod.async_get = lambda hass, _r=_registry: _r
        setattr(mock_ha_helpers, mod_name, mod)
        sys.modules[f"homeassistant.helpers.{mod_name}"] = mod
    mock_ha_helpers.entity_registry.EVENT_ENTITY_REGISTRY_UPDATED = "entity_registry_updated"
    mock_ha_helpers.area_registry.EVENT_AREA_REGISTRY_UPDATED = "area_registry_updated"

    # Issue registry
    mock_issue = MagicMock()
    mock_issue.async_create_issue = MagicMock()
    mock_issue.async_delete_issue = MagicMock()
    mock_issue.IssueSeverity = MagicMock(WARNING="warning", ERROR="error")
    mock_ha_helpers.issue_registry = mock_issue
    sys.modules["homeassistant.helpers.issue_registry"] = mock_issue

    # Button platform
    mock_button = MagicMock()

    class MockButtonEntity:
        def __init__(self):
            self._attr_unique_id = None
            self._attr_name = None
            self._attr_device_info = None

        async def async_press(self):
            pass

    mock_button.ButtonEntity = MockButtonEntity
    mock_components.button = mock_button
    sys.modules["homeassistant.components.button"] = mock_button
    MockPlatform.BUTTON = "button"

    # Recorder (bootstrap is patched in tests; module must import)
    mock_recorder = MagicMock()
    mock_recorder.get_instance = lambda hass: None
    mock_recorder_history = MagicMock()
    mock_components.recorder = mock_recorder
    sys.modules["homeassistant.components.recorder"] = mock_recorder
    sys.modules["homeassistant.components.recorder.history"] = mock_recorder_history

    # Debouncer
    class MockDebouncer:
        def __init__(self, hass, logger, cooldown, immediate, function):
            self._function = function

        async def async_call(self):
            await self._function()

        def async_shutdown(self):
            pass

    mock_debounce = MagicMock()
    mock_debounce.Debouncer = MockDebouncer
    mock_ha_helpers.debounce = mock_debounce
    sys.modules["homeassistant.helpers.debounce"] = mock_debounce
```

`mock_components` is defined further down in the existing function; move the `mock_components = MagicMock()` line above this block. Also make `mock_dt_util.now` return an aware datetime: `mock_dt_util.now = lambda: datetime.now(timezone.utc)` and add `mock_dt_util.as_local = lambda dt: dt`; import `timezone` at the top of conftest.

Replace the `mock_config_entry` fixture body's data:

```python
            self.entry_id = "test_entry_id"
            self.version = 11
            self.data = {
                "site_name": "Test House",
                "notify_service": "notify.mobile_app_phone",
                "motion_entities": ["binary_sensor.kitchen_motion", "binary_sensor.bed_motion"],
                "contact_entities": ["binary_sensor.front_door"],
                "plug_entities": ["sensor.kettle_power"],
                "panic_entities": ["binary_sensor.panic"],
                "light_entities": [],
                "other_entities": [],
            }
            self.options = {}
```

- [ ] **Step 2: Write the failing coordinator test**

```python
# tests/test_coordinator.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator
from custom_components.behaviour_monitor.core.alert_router import DeliveryAction
from custom_components.behaviour_monitor.core.alerts import Alert, AlertClass, Severity
from custom_components.behaviour_monitor.core.events import Category

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)


def _state(entity_id: str, state: str, name: str | None = None):
    return SimpleNamespace(entity_id=entity_id, state=state, attributes={"friendly_name": name} if name else {})


@pytest.fixture
def coordinator(mock_hass, mock_config_entry):
    from homeassistant.helpers import entity_registry as er
    reg = er.async_get(mock_hass)
    reg.entities.clear(); reg.devices.clear(); reg.areas.clear()
    reg.entities["binary_sensor.kitchen_motion"] = SimpleNamespace(area_id="a_kitchen", device_id=None)
    reg.entities["binary_sensor.bed_motion"] = SimpleNamespace(area_id=None, device_id="dev_bed")
    reg.devices["dev_bed"] = SimpleNamespace(area_id="a_bed")
    reg.areas["a_kitchen"] = SimpleNamespace(name="Test House Kitchen")
    reg.areas["a_bed"] = SimpleNamespace(name="Bedroom")
    mock_hass.states.get = lambda eid: _state(eid, "off", "Front door Door") if eid == "binary_sensor.front_door" else None
    return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)


def test_specs_resolve_rooms_from_entity_then_device_then_name(coordinator):
    rooms = {s.entity_id: s.room for s in coordinator.entity_specs}
    assert rooms["binary_sensor.kitchen_motion"] == "Test House Kitchen"
    assert rooms["binary_sensor.bed_motion"] == "Bedroom"
    assert rooms["binary_sensor.front_door"] == "Front door Door"
    assert rooms["sensor.kettle_power"] == "sensor.kettle_power"
    cats = {s.entity_id: s.category for s in coordinator.entity_specs}
    assert cats["binary_sensor.panic"] is Category.PANIC


def test_display_room_strips_site_prefix(coordinator):
    assert coordinator.display_room("Test House Kitchen") == "Kitchen"
    assert coordinator.display_room("test house Bedroom") == "Bedroom"
    assert coordinator.display_room("Bedroom") == "Bedroom"
    assert coordinator.display_room("Test Houseboat") == "Test Houseboat"


@pytest.mark.asyncio
async def test_setup_bootstraps_from_recorder_and_subscribes(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()) as boot:
        await coordinator.async_setup()
    boot.assert_awaited_once()
    assert set(boot.await_args.args[0]) == {s.entity_id for s in coordinator.entity_specs}
    mock_hass.bus.async_listen.assert_any_call("state_changed", coordinator._handle_state_changed)


@pytest.mark.asyncio
async def test_state_change_feeds_engine_and_panic_pushes(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch("custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW):
        event = SimpleNamespace(data={"entity_id": "binary_sensor.panic", "old_state": _state("binary_sensor.panic", "off"), "new_state": _state("binary_sensor.panic", "on")})
        coordinator._handle_state_changed(event)
        await coordinator._flush_actions()
    calls = [c.args[:2] for c in mock_hass.services.async_call.await_args_list]
    assert ("notify", "mobile_app_phone") in calls
    assert ("persistent_notification", "create") in calls
    assert coordinator.data is None or coordinator.data["welfare"]["status"] in ("learning", "critical")


@pytest.mark.asyncio
async def test_delivery_actions_map_to_services_issues_and_logbook(coordinator, mock_hass):
    from homeassistant.helpers import issue_registry as ir
    ir.async_create_issue.reset_mock(); ir.async_delete_issue.reset_mock()
    welfare = Alert(AlertClass.WELFARE, "house", "inactivity", Severity.HIGH, "No activity", NOW)
    health = Alert(AlertClass.HEALTH, "binary_sensor.kitchen_motion", "unavailable", Severity.MEDIUM, "down", NOW)
    stat = Alert(AlertClass.STATISTICAL, "sensor.kettle_power", "routine_missed", Severity.LOW, "missed", NOW)
    await coordinator._perform([DeliveryAction("push", welfare), DeliveryAction("repair_create", health), DeliveryAction("log", stat)], NOW)
    notify = [c for c in mock_hass.services.async_call.await_args_list if c.args[:2] == ("notify", "mobile_app_phone")]
    assert notify and notify[0].args[2]["title"] == "Test House welfare" and notify[0].args[2]["message"] == "No activity"
    ir.async_create_issue.assert_called_once()
    assert ir.async_create_issue.call_args.args[2] == "health_test_entry_id_health:binary_sensor.kitchen_motion:unavailable"
    mock_hass.bus.async_fire.assert_any_call("logbook_entry", {"name": "Test House", "message": "missed", "domain": "behaviour_monitor"})
    assert coordinator.last_notification == {"timestamp": NOW.isoformat(), "kind": "inactivity"}
    await coordinator._perform([DeliveryAction("push_clear", welfare), DeliveryAction("repair_delete", health)], NOW)
    ir.async_delete_issue.assert_called_once()
    assert ("persistent_notification", "dismiss") in [c.args[:2] for c in mock_hass.services.async_call.await_args_list]


@pytest.mark.asyncio
async def test_update_data_returns_snapshot_with_site(coordinator):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    with patch("custom_components.behaviour_monitor.coordinator.dt_util.now", return_value=NOW):
        data = await coordinator._async_update_data()
    assert data["site"] == "Test House"
    assert data["welfare"]["status"] == "learning"
    assert set(data["entities"]) == {s.entity_id for s in coordinator.entity_specs}


@pytest.mark.asyncio
async def test_holiday_snooze_ack_reset_roundtrip(coordinator):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    await coordinator.async_enable_holiday_mode()
    assert coordinator.holiday_mode is True
    await coordinator.async_disable_holiday_mode()
    assert coordinator.holiday_mode is False
    await coordinator.async_snooze("2_hours")
    assert coordinator.is_snoozed() and coordinator.get_snooze_duration_key() == "2_hours"
    await coordinator.async_clear_snooze()
    assert not coordinator.is_snoozed()
    await coordinator.async_reset_learning("binary_sensor.kitchen_motion")
    await coordinator.async_reset_learning()
    await coordinator.async_acknowledge()
    saved = coordinator._store._data
    assert saved["engine"]["schema"] == 1 and saved["site"] == "Test House"


@pytest.mark.asyncio
async def test_test_panic_pushes_without_learning(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    before = coordinator._engine.to_dict()["house"]
    await coordinator.async_test_panic()
    assert ("notify", "mobile_app_phone") in [c.args[:2] for c in mock_hass.services.async_call.await_args_list]
    assert coordinator._engine.to_dict()["house"] == before


@pytest.mark.asyncio
async def test_registry_update_reresolves_rooms(coordinator, mock_hass):
    with patch.object(coordinator, "_bootstrap_entities", new=AsyncMock()):
        await coordinator.async_setup()
    from homeassistant.helpers import entity_registry as er
    er.async_get(mock_hass).areas["a_bed"] = SimpleNamespace(name="Back Bedroom")
    await coordinator._async_registry_updated(SimpleNamespace(data={}))
    assert {s.room for s in coordinator.entity_specs} >= {"Back Bedroom"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_coordinator.py -v`
Expected: FAIL with `ImportError` or `AttributeError` on `entity_specs`

- [ ] **Step 4: Write the new coordinator**

```python
# custom_components/behaviour_monitor/coordinator.py
"""Thin Home Assistant shell around core.engine.Engine."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .config_flow import entity_specs_from_data
from .const import (
    CONF_NOTIFY_SERVICE,
    CONF_SITE_NAME,
    DOMAIN,
    EVENT_LOGBOOK,
    ISSUE_HEALTH_PREFIX,
    OPTION_DEFAULTS,
    SAVE_DEBOUNCE_S,
    SNOOZE_DURATIONS,
    SNOOZE_OFF,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .core.alert_router import DeliveryAction
from .core.engine import Engine, EngineConfig, EntitySpec
from .core.events import ActivityEvent, Category, EventKind

try:
    from homeassistant.components.recorder import get_instance as recorder_get_instance
    from homeassistant.components.recorder.history import (
        state_changes_during_period as recorder_state_changes_during_period,
    )
except ImportError:  # pragma: no cover
    recorder_get_instance = None  # type: ignore[assignment]
    recorder_state_changes_during_period = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)


class BehaviourMonitorCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=UPDATE_INTERVAL))
        self._entry = entry
        self._site: str = str(entry.data.get(CONF_SITE_NAME, "Behaviour Monitor"))
        self._notify: str = str(entry.data.get(CONF_NOTIFY_SERVICE, ""))
        options = {**OPTION_DEFAULTS, **entry.options}
        self._config = EngineConfig.from_options(options)
        self._specs: list[EntitySpec] = self._resolve_specs()
        self._engine = Engine(self._config, self._specs)
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self._pending: list[tuple[DeliveryAction, datetime]] = []
        self._unsubs: list[Any] = []
        self._last_notification: dict[str, Any] = {"timestamp": None, "kind": None}
        self._saver = Debouncer(hass, _LOGGER, cooldown=SAVE_DEBOUNCE_S, immediate=False, function=self._save)

    # ----------------------------------------------------------- properties

    @property
    def site_name(self) -> str:
        return self._site

    @property
    def entity_specs(self) -> list[EntitySpec]:
        return list(self._specs)

    @property
    def holiday_mode(self) -> bool:
        return self._engine.holiday

    @property
    def snooze_until(self) -> datetime | None:
        return self._engine.snooze_until

    @property
    def last_notification(self) -> dict[str, Any]:
        return dict(self._last_notification)

    def is_snoozed(self) -> bool:
        return self._engine.is_snoozed(dt_util.now())

    def get_snooze_duration_key(self) -> str:
        if not self.is_snoozed():
            return SNOOZE_OFF
        rem = (self._engine.snooze_until - dt_util.now()).total_seconds()  # type: ignore[operator]
        return min((k for k in SNOOZE_DURATIONS if k != SNOOZE_OFF), key=lambda k: abs(rem - SNOOZE_DURATIONS[k]))

    def display_room(self, room: str) -> str:
        prefix = self._site.strip().lower()
        low = room.lower()
        if prefix and low.startswith(prefix) and len(room) > len(prefix) and room[len(prefix)].isspace():
            return room[len(prefix):].strip()
        return room

    # ---------------------------------------------------------------- rooms

    def _resolve_specs(self) -> list[EntitySpec]:
        ent_reg, dev_reg, area_reg = er.async_get(self.hass), dr.async_get(self.hass), ar.async_get(self.hass)
        specs: list[EntitySpec] = []
        for entity_id, category in entity_specs_from_data(self._entry.data):
            specs.append(EntitySpec(entity_id, Category(category), self._room_for(entity_id, ent_reg, dev_reg, area_reg)))
        return specs

    def _room_for(self, entity_id: str, ent_reg: Any, dev_reg: Any, area_reg: Any) -> str:
        entry = ent_reg.async_get(entity_id)
        area_id = getattr(entry, "area_id", None)
        if not area_id and getattr(entry, "device_id", None):
            device = dev_reg.async_get(entry.device_id)
            area_id = getattr(device, "area_id", None)
        if area_id:
            area = area_reg.async_get_area(area_id)
            if area is not None and getattr(area, "name", None):
                return str(area.name)
        state = self.hass.states.get(entity_id)
        if state is not None and state.attributes.get("friendly_name"):
            return str(state.attributes["friendly_name"])
        return entity_id

    async def _async_registry_updated(self, event: Any) -> None:
        new_specs = self._resolve_specs()
        old = {s.entity_id: s.room for s in self._specs}
        for s in new_specs:
            if s.entity_id in old and old[s.entity_id] != s.room:
                self._engine.rename_room(old[s.entity_id], s.room)
        self._specs = new_specs
        self._engine.set_entities(self._specs)
        await self._saver.async_call()

    # ------------------------------------------------------------- lifecycle

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored and isinstance(stored, dict) and "engine" in stored:
            self._engine = Engine.from_dict(stored["engine"], self._config, self._specs)
            self._last_notification = stored.get("last_notification", self._last_notification)
            known = set(stored.get("entity_ids", []))
            new_ids = [s.entity_id for s in self._specs if s.entity_id not in known]
        else:
            new_ids = [s.entity_id for s in self._specs]
        if new_ids:
            await self._bootstrap_entities(new_ids)
            await self._save()
        self._unsubs.append(self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed))
        self._unsubs.append(self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._async_registry_updated))
        self._unsubs.append(self.hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, self._async_registry_updated))

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save({
            "site": self._site,
            "entity_ids": [s.entity_id for s in self._specs],
            "engine": self._engine.to_dict(),
            "last_notification": self._last_notification,
        })

    async def _bootstrap_entities(self, entity_ids: list[str]) -> None:
        if recorder_get_instance is None or recorder_state_changes_during_period is None:
            _LOGGER.warning("Recorder unavailable; skipping bootstrap")
            return
        instance = recorder_get_instance(self.hass)
        if instance is None:
            return
        end = dt_util.now()
        start = end - timedelta(days=self._config.window_days)
        for eid in entity_ids:
            try:
                rows = await instance.async_add_executor_job(recorder_state_changes_during_period, self.hass, start, end, [eid], False)
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Could not load recorder history for %s", eid)
                continue
            prev: str | None = None
            for s in rows.get(eid, []):
                ts = dt_util.as_local(s.last_changed)
                self._engine.handle_state(eid, prev, s.state, ts, learn_only=True)
                prev = s.state
        self._engine.poll(end)

    # ----------------------------------------------------------------- events

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        eid = event.data.get("entity_id", "")
        if eid not in {s.entity_id for s in self._specs}:
            return
        new = event.data.get("new_state")
        if new is None:
            return
        old = event.data.get("old_state")
        now = dt_util.now()
        actions = self._engine.handle_state(eid, old.state if old else None, str(new.state), now)
        if actions:
            self._pending.extend((a, now) for a in actions)
            self.hass.async_create_task(self._flush_actions())
        self.hass.async_create_task(self._saver.async_call())

    async def _flush_actions(self) -> None:
        pending, self._pending = self._pending, []
        for action, when in pending:
            await self._perform([action], when)
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()
        try:
            actions = self._engine.poll(now)
            await self._perform(actions, now)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Engine poll failed")
        snap = self._engine.snapshot(now)
        snap["site"] = self._site
        snap["last_notification"] = dict(self._last_notification)
        snap["display_rooms"] = {s.room: self.display_room(s.room) for s in self._specs}
        return snap

    # --------------------------------------------------------------- delivery

    async def _perform(self, actions: list[DeliveryAction], now: datetime) -> None:
        for act in actions:
            alert = act.alert
            text = self._render(alert.explanation)
            if act.action == "push":
                await self._notify(f"{self._site} welfare", text)
                await self.hass.services.async_call("persistent_notification", "create", {
                    "title": f"{self._site} welfare", "message": text,
                    "notification_id": f"{DOMAIN}_{self._entry.entry_id}_welfare"})
                self._last_notification = {"timestamp": now.isoformat(), "kind": alert.kind}
            elif act.action == "push_clear":
                await self._notify(f"{self._site} welfare", f"Cleared: {text}")
                await self.hass.services.async_call("persistent_notification", "dismiss", {
                    "notification_id": f"{DOMAIN}_{self._entry.entry_id}_welfare"})
            elif act.action == "repair_create":
                ir.async_create_issue(self.hass, DOMAIN, self._issue_id(alert.key), is_fixable=False,
                                      severity=ir.IssueSeverity.WARNING, translation_key="device_health",
                                      translation_placeholders={"site": self._site, "message": text})
            elif act.action == "repair_delete":
                ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(alert.key))
            elif act.action == "log":
                self.hass.bus.async_fire(EVENT_LOGBOOK, {"name": self._site, "message": text, "domain": DOMAIN})

    def _issue_id(self, key: str) -> str:
        return f"{ISSUE_HEALTH_PREFIX}{self._entry.entry_id}_{key}"

    def _render(self, text: str) -> str:
        for s in sorted(self._specs, key=lambda s: -len(s.room)):
            disp = self.display_room(s.room)
            if disp != s.room:
                text = text.replace(s.room, disp)
        return text

    async def _notify(self, title: str, message: str) -> None:
        if "." not in self._notify:
            return
        domain, service = self._notify.split(".", 1)
        await self.hass.services.async_call(domain, service, {"title": title, "message": message})

    # --------------------------------------------------------------- controls

    async def _after_control(self) -> None:
        await self._save()
        await self.async_request_refresh()

    async def async_enable_holiday_mode(self) -> None:
        self._engine.holiday = True
        await self._after_control()

    async def async_disable_holiday_mode(self) -> None:
        self._engine.holiday = False
        await self._after_control()

    async def async_snooze(self, duration_key: str) -> None:
        secs = SNOOZE_DURATIONS.get(duration_key, 0)
        self._engine.snooze_until = dt_util.now() + timedelta(seconds=secs) if secs > 0 else None
        await self._after_control()

    async def async_clear_snooze(self) -> None:
        self._engine.snooze_until = None
        await self._after_control()

    async def async_acknowledge(self) -> None:
        now = dt_util.now()
        self._engine.acknowledge(now)
        await self._perform(self._engine.poll(now), now)
        await self._after_control()

    async def async_reset_learning(self, entity_id: str | None = None) -> None:
        self._engine.reset(entity_id)
        ids = [entity_id] if entity_id else [s.entity_id for s in self._specs]
        await self._bootstrap_entities(ids)
        await self._after_control()

    async def async_test_panic(self) -> None:
        now = dt_util.now()
        spec = next((s for s in self._specs if s.category is Category.PANIC), None)
        room = spec.room if spec else "test"
        eid = spec.entity_id if spec else "test"
        ev = ActivityEvent(eid, Category.PANIC, EventKind.PANIC, room, now, bypass=True)
        await self._perform(self._engine._router.submit_panic(ev, now), now)
        self._engine.acknowledge(now)
        await self._after_control()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_coordinator.py tests/test_config_flow.py tests/test_const.py -v`
Expected: 17 passed. `test_test_panic_pushes_without_learning` reaches into `_engine._router`; keep that private access confined to `async_test_panic` and the test.

- [ ] **Step 6: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py tests/conftest.py tests/test_coordinator.py
git commit -m "feat!: coordinator drives core Engine, resolves rooms from areas, routes delivery actions"
```

---

### Task 4: Sensors, button, switch and select on the snapshot

**Files:**
- Modify: `custom_components/behaviour_monitor/sensor.py` (full rewrite)
- Create: `custom_components/behaviour_monitor/button.py`
- Modify: `custom_components/behaviour_monitor/switch.py` (device info)
- Modify: `custom_components/behaviour_monitor/select.py` (device info)
- Modify: `tests/test_sensor.py` (full rewrite), `tests/test_switch.py`, `tests/test_select.py` (device info assertions)
- Create: `tests/test_button.py`

**Interfaces:**
- Produces `SENSOR_DESCRIPTIONS` with keys `welfare_status`, `house_activity`, `anomaly`, `device_health`, `learning`, `entity_status`, `last_activity`, `daily_activity_count`, `last_notification`; `device_info(entry, site) -> DeviceInfo` in `sensor.py` reused by the other platforms; `AcknowledgeButton`.

- [ ] **Step 1: Write the failing sensor and button tests**

```python
# tests/test_sensor.py
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.behaviour_monitor.sensor import SENSOR_DESCRIPTIONS, BehaviourMonitorSensor, async_setup_entry, device_info

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
SNAP = {
    "site": "Test House",
    "welfare": {"status": "medium", "reasons": ["No activity in Test House Kitchen"], "open_alerts": [{"key": "welfare:house:inactivity"}]},
    "house": {"last_activity": NOW.isoformat(), "last_room": "Test House Kitchen", "gap_s": 7200.0, "expected_s": 600.0, "rooms_today": ["Test House Kitchen"], "daily_count": 12},
    "anomalies": [{"key": "statistical:sensor.kettle_power:routine_missed"}],
    "health": {"states": {"binary_sensor.k": "ok", "binary_sensor.p": "unavailable"}, "dropouts_today": 1, "alerts": [{"key": "health:binary_sensor.p:unavailable"}]},
    "learning": {"confidence": 100.0, "days_seen": 14, "days_remaining": 0, "first_observation": None, "models": {"house": 1.0}},
    "entities": {"binary_sensor.k": {"category": "motion", "room": "Test House Kitchen", "last_seen": None, "expected_hours": [8], "health": "ok"}},
    "chains": [{"name": "A → B", "rooms": ["A", "B"], "hop_median_s": [240.0]}],
    "last_notification": {"timestamp": NOW.isoformat(), "kind": "inactivity"},
    "display_rooms": {"Test House Kitchen": "Kitchen"},
}


def _desc(key):
    return next(d for d in SENSOR_DESCRIPTIONS if d.key == key)


def test_sensor_keys():
    assert [d.key for d in SENSOR_DESCRIPTIONS] == [
        "welfare_status", "house_activity", "anomaly", "device_health", "learning",
        "entity_status", "last_activity", "daily_activity_count", "last_notification",
    ]


def test_welfare_and_house_values_and_display_rooms():
    assert _desc("welfare_status").value_fn(SNAP) == "medium"
    attrs = _desc("welfare_status").extra_attrs_fn(MagicMock(), SNAP)
    assert attrs["reasons"] == ["No activity in Kitchen"]
    assert _desc("house_activity").value_fn(SNAP) == 7200
    h = _desc("house_activity").extra_attrs_fn(MagicMock(), SNAP)
    assert h["last_room"] == "Kitchen" and h["rooms_today"] == ["Kitchen"] and h["expected_gap_s"] == 600.0


def test_anomaly_health_learning_entity_status():
    assert _desc("anomaly").value_fn(SNAP) == 1
    assert _desc("device_health").value_fn(SNAP) == "unavailable"
    assert _desc("device_health").extra_attrs_fn(MagicMock(), SNAP)["dropouts_today"] == 1
    assert _desc("learning").value_fn(SNAP) == 100.0
    assert _desc("entity_status").value_fn(SNAP) == "1 monitored, 0 down"
    es = _desc("entity_status").extra_attrs_fn(MagicMock(), SNAP)["entities"]
    assert es["binary_sensor.k"]["room"] == "Kitchen"


def test_timestamps_and_count():
    assert _desc("last_activity").value_fn(SNAP) == NOW
    assert _desc("last_activity").value_fn({"house": {}}) is None
    assert _desc("daily_activity_count").value_fn(SNAP) == 12
    assert _desc("last_notification").value_fn(SNAP) == NOW
    assert _desc("last_notification").value_fn({}) is None


def test_device_info_uses_version_constant(mock_config_entry):
    from custom_components.behaviour_monitor.const import VERSION
    info = device_info(mock_config_entry, "Test House")
    assert info["sw_version"] == VERSION and info["name"] == "Test House"


@pytest.mark.asyncio
async def test_setup_entry_adds_nine_sensors(mock_hass, mock_config_entry):
    coordinator = MagicMock(); coordinator.data = SNAP; coordinator.site_name = "Test House"
    mock_hass.data = {"behaviour_monitor": {mock_config_entry.entry_id: coordinator}}
    added = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, added)
    entities = added.call_args.args[0]
    assert len(entities) == 9 and all(isinstance(e, BehaviourMonitorSensor) for e in entities)
    assert entities[0].native_value == "medium"
```

```python
# tests/test_button.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.behaviour_monitor.button import AcknowledgeButton, async_setup_entry


@pytest.mark.asyncio
async def test_button_acknowledges(mock_hass, mock_config_entry):
    coordinator = MagicMock(); coordinator.site_name = "Test House"; coordinator.async_acknowledge = AsyncMock()
    mock_hass.data = {"behaviour_monitor": {mock_config_entry.entry_id: coordinator}}
    added = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, added)
    button = added.call_args.args[0][0]
    assert isinstance(button, AcknowledgeButton)
    await button.async_press()
    coordinator.async_acknowledge.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_sensor.py tests/test_button.py -v`
Expected: FAIL with `ImportError: cannot import name 'device_info'` and `ModuleNotFoundError: ... button`

- [ ] **Step 3: Write sensor.py and button.py, adjust switch.py and select.py**

```python
# custom_components/behaviour_monitor/sensor.py
"""Sensor platform reading the Engine snapshot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import BehaviourMonitorCoordinator


def device_info(entry: ConfigEntry, site: str) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=site, manufacturer="Behaviour Monitor", model="Welfare core", sw_version=VERSION)


def _disp(data: dict[str, Any], room: str | None) -> str | None:
    return data.get("display_rooms", {}).get(room, room) if room else room


def _render(data: dict[str, Any], text: str) -> str:
    for full, short in sorted(data.get("display_rooms", {}).items(), key=lambda kv: -len(kv[0])):
        text = text.replace(full, short)
    return text


def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class BehaviourMonitorSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any] = None  # type: ignore[assignment]
    extra_attrs_fn: Callable[[Any, dict[str, Any]], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[BehaviourMonitorSensorDescription, ...] = (
    BehaviourMonitorSensorDescription(
        key="welfare_status", name="Welfare Status", icon="mdi:heart-pulse",
        value_fn=lambda d: d.get("welfare", {}).get("status", "unknown"),
        extra_attrs_fn=lambda c, d: {
            "reasons": [_render(d, r) for r in d.get("welfare", {}).get("reasons", [])],
            "open_alerts": d.get("welfare", {}).get("open_alerts", []),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="house_activity", name="House Activity", icon="mdi:home-clock", native_unit_of_measurement="s",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (int(g) if (g := d.get("house", {}).get("gap_s")) is not None else None),
        extra_attrs_fn=lambda c, d: {
            "last_room": _disp(d, d.get("house", {}).get("last_room")),
            "expected_gap_s": d.get("house", {}).get("expected_s"),
            "rooms_today": [_disp(d, r) for r in d.get("house", {}).get("rooms_today", [])],
        },
    ),
    BehaviourMonitorSensorDescription(
        key="anomaly", name="Anomaly", icon="mdi:chart-bell-curve",
        value_fn=lambda d: len(d.get("anomalies", [])),
        extra_attrs_fn=lambda c, d: {"anomalies": d.get("anomalies", [])},
    ),
    BehaviourMonitorSensorDescription(
        key="device_health", name="Device Health", icon="mdi:stethoscope",
        value_fn=lambda d: (
            "unavailable" if "unavailable" in (s := d.get("health", {}).get("states", {})).values()
            else "silent" if "silent" in s.values() else "ok"
        ),
        extra_attrs_fn=lambda c, d: {
            "states": d.get("health", {}).get("states", {}),
            "dropouts_today": d.get("health", {}).get("dropouts_today", 0),
            "alerts": d.get("health", {}).get("alerts", []),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="learning", name="Learning", icon="mdi:brain", native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("learning", {}).get("confidence", 0.0),
        extra_attrs_fn=lambda c, d: {k: v for k, v in d.get("learning", {}).items() if k != "confidence"},
    ),
    BehaviourMonitorSensorDescription(
        key="entity_status", name="Entity Status", icon="mdi:format-list-checks",
        value_fn=lambda d: (
            f"{len(e := d.get('entities', {}))} monitored, "
            f"{sum(1 for v in e.values() if v.get('health') != 'ok')} down"
        ),
        extra_attrs_fn=lambda c, d: {
            "entities": {eid: {**v, "room": _disp(d, v.get("room"))} for eid, v in d.get("entities", {}).items()},
            "chains": d.get("chains", []),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="last_activity", name="Last Activity", device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _ts(d.get("house", {}).get("last_activity")),
    ),
    BehaviourMonitorSensorDescription(
        key="daily_activity_count", name="Daily Activity Count", icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.get("house", {}).get("daily_count", 0),
    ),
    BehaviourMonitorSensorDescription(
        key="last_notification", name="Last Notification", device_class=SensorDeviceClass.TIMESTAMP, icon="mdi:bell-ring",
        value_fn=lambda d: _ts(d.get("last_notification", {}).get("timestamp")),
        extra_attrs_fn=lambda c, d: {"kind": d.get("last_notification", {}).get("kind")},
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BehaviourMonitorSensor(coordinator, entry, d) for d in SENSOR_DESCRIPTIONS])


class BehaviourMonitorSensor(CoordinatorEntity[BehaviourMonitorCoordinator], SensorEntity):
    entity_description: BehaviourMonitorSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator: BehaviourMonitorCoordinator, entry: ConfigEntry, description: BehaviourMonitorSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = device_info(entry, coordinator.site_name)

    @property
    def native_value(self) -> Any:
        return None if self.coordinator.data is None else self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.extra_attrs_fn is None or self.coordinator.data is None:
            return None
        return self.entity_description.extra_attrs_fn(self.coordinator, self.coordinator.data)
```

```python
# custom_components/behaviour_monitor/button.py
"""Acknowledge button: stops welfare repeats until the alert clears."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BehaviourMonitorCoordinator
from .sensor import device_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AcknowledgeButton(coordinator, entry)])


class AcknowledgeButton(CoordinatorEntity[BehaviourMonitorCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:check-decagram"

    def __init__(self, coordinator: BehaviourMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_acknowledge"
        self._attr_name = "Acknowledge"
        self._attr_device_info = device_info(entry, coordinator.site_name)

    async def async_press(self) -> None:
        await self.coordinator.async_acknowledge()
```

In `switch.py` and `select.py`, replace the inline `DeviceInfo(...)` blocks with `device_info(entry, coordinator.site_name)` imported from `.sensor`, and delete the `DeviceInfo` import. In `select.py`, the `extra_state_attributes` keep `snooze_active` and `snooze_until` from `coordinator.is_snoozed()` and `coordinator.snooze_until`.

Update `tests/test_switch.py` and `tests/test_select.py`: wherever they construct a coordinator mock, add `coordinator.site_name = "Test House"`; wherever they assert `sw_version == "2.6.0"`, assert against `VERSION` from `const`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_sensor.py tests/test_button.py tests/test_switch.py tests/test_select.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/sensor.py custom_components/behaviour_monitor/button.py custom_components/behaviour_monitor/switch.py custom_components/behaviour_monitor/select.py tests/test_sensor.py tests/test_button.py tests/test_switch.py tests/test_select.py
git commit -m "feat!: sensors on the engine snapshot, acknowledge button, shared device info"
```

---

### Task 5: Integration setup, migration and services

**Files:**
- Modify: `custom_components/behaviour_monitor/__init__.py` (full rewrite)
- Modify: `tests/test_init.py` (full rewrite)

**Interfaces:**
- `PLATFORMS = [SENSOR, SWITCH, SELECT, BUTTON]`.
- `async_migrate_entry`: any version below 11 becomes 11. `monitored_entities` is removed from data and stored under `legacy_unassigned`; `site_name` defaults to the entry title; every category list defaults to empty; options default to `OPTION_DEFAULTS`. If no category list is populated, a repair issue `ISSUE_ASSIGN_CATEGORIES` is created with the unassigned entity ids in placeholders.
- `async_setup_entry`: if no categories are populated, create the repair issue, register nothing else and return `True` so the entry shows as loaded but unconfigured (welfare sensor is not created). Otherwise create coordinator, first refresh, forward platforms, register services `enable_holiday_mode`, `disable_holiday_mode`, `snooze`, `clear_snooze`, `acknowledge`, `reset_learning` (optional `entity_id`), `test_panic`.
- Services are registered once per domain, targeting every loaded entry; a service call runs against every coordinator in `hass.data[DOMAIN]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_init.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.behaviour_monitor import async_migrate_entry, async_setup_entry, async_unload_entry, PLATFORMS
from custom_components.behaviour_monitor.const import (
    CONF_MOTION_ENTITIES, CONF_SITE_NAME, DOMAIN, ISSUE_ASSIGN_CATEGORIES, OPTION_DEFAULTS,
    SERVICE_ACKNOWLEDGE, SERVICE_RESET_LEARNING, SERVICE_TEST_PANIC,
)


def _legacy_entry():
    e = MagicMock()
    e.entry_id = "old"; e.version = 10; e.title = "Behaviour Monitor"
    e.data = {"monitored_entities": ["binary_sensor.a", "sensor.b"], "history_window_days": 28}
    e.options = {}
    return e


@pytest.mark.asyncio
async def test_migrate_v10_moves_entities_aside_and_raises_issue(mock_hass):
    from homeassistant.helpers import issue_registry as ir
    ir.async_create_issue.reset_mock()
    entry = _legacy_entry()
    assert await async_migrate_entry(mock_hass, entry) is True
    kwargs = mock_hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["version"] == 11
    assert kwargs["data"]["legacy_unassigned"] == ["binary_sensor.a", "sensor.b"]
    assert kwargs["data"][CONF_SITE_NAME] == "Behaviour Monitor"
    assert kwargs["data"][CONF_MOTION_ENTITIES] == []
    assert "monitored_entities" not in kwargs["data"]
    assert kwargs["options"] == OPTION_DEFAULTS
    ir.async_create_issue.assert_called_once()
    assert ir.async_create_issue.call_args.args[2] == f"{ISSUE_ASSIGN_CATEGORIES}_old"


@pytest.mark.asyncio
async def test_migrate_v11_is_noop(mock_hass, mock_config_entry):
    assert await async_migrate_entry(mock_hass, mock_config_entry) is True
    mock_hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_setup_unconfigured_entry_only_raises_issue(mock_hass, mock_config_entry):
    from homeassistant.helpers import issue_registry as ir
    ir.async_create_issue.reset_mock()
    mock_config_entry.data = {CONF_SITE_NAME: "X", "notify_service": "notify.n"}
    assert await async_setup_entry(mock_hass, mock_config_entry) is True
    ir.async_create_issue.assert_called_once()
    mock_hass.config_entries.async_forward_entry_setups.assert_not_awaited()


@pytest.mark.asyncio
async def test_setup_registers_platforms_and_services(mock_hass, mock_config_entry):
    with patch("custom_components.behaviour_monitor.BehaviourMonitorCoordinator") as cls:
        coord = MagicMock(); coord.async_setup = AsyncMock(); coord.async_config_entry_first_refresh = AsyncMock()
        coord.async_acknowledge = AsyncMock(); coord.async_reset_learning = AsyncMock(); coord.async_test_panic = AsyncMock()
        cls.return_value = coord
        assert await async_setup_entry(mock_hass, mock_config_entry) is True
    mock_hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(mock_config_entry, PLATFORMS)
    assert "button" in PLATFORMS
    registered = {c.args[1]: c.args[2] for c in mock_hass.services.async_register.call_args_list}
    assert {SERVICE_ACKNOWLEDGE, SERVICE_RESET_LEARNING, SERVICE_TEST_PANIC, "snooze", "clear_snooze", "enable_holiday_mode", "disable_holiday_mode"} <= set(registered)
    await registered[SERVICE_RESET_LEARNING](MagicMock(data={"entity_id": "binary_sensor.kitchen_motion"}))
    coord.async_reset_learning.assert_awaited_once_with("binary_sensor.kitchen_motion")
    await registered[SERVICE_TEST_PANIC](MagicMock(data={}))
    coord.async_test_panic.assert_awaited_once()


@pytest.mark.asyncio
async def test_unload_shuts_down_and_removes(mock_hass, mock_config_entry):
    coord = MagicMock(); coord.async_shutdown = AsyncMock()
    mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: coord}}
    assert await async_unload_entry(mock_hass, mock_config_entry) is True
    coord.async_shutdown.assert_awaited_once()
    assert mock_config_entry.entry_id not in mock_hass.data[DOMAIN]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_init.py -v`
Expected: FAIL with `ImportError` on `PLATFORMS` contents or missing service names

- [ ] **Step 3: Write the new `__init__.py`**

```python
# custom_components/behaviour_monitor/__init__.py
"""The Behaviour Monitor integration (v5)."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import issue_registry as ir

from .config_flow import entity_specs_from_data
from .const import (
    CATEGORY_CONF_KEYS,
    CONF_NOTIFY_SERVICE,
    CONF_SITE_NAME,
    CONFIG_VERSION,
    DOMAIN,
    ISSUE_ASSIGN_CATEGORIES,
    LEGACY_CONF_MONITORED_ENTITIES,
    OPTION_DEFAULTS,
    SERVICE_ACKNOWLEDGE,
    SERVICE_CLEAR_SNOOZE,
    SERVICE_DISABLE_HOLIDAY_MODE,
    SERVICE_ENABLE_HOLIDAY_MODE,
    SERVICE_RESET_LEARNING,
    SERVICE_SNOOZE,
    SERVICE_TEST_PANIC,
    SNOOZE_DURATIONS,
)
from .coordinator import BehaviourMonitorCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.SELECT, Platform.BUTTON]
LEGACY_UNASSIGNED = "legacy_unassigned"


def _raise_assign_issue(hass: HomeAssistant, entry: ConfigEntry, unassigned: list[str]) -> None:
    ir.async_create_issue(
        hass, DOMAIN, f"{ISSUE_ASSIGN_CATEGORIES}_{entry.entry_id}", is_fixable=False,
        severity=ir.IssueSeverity.WARNING, translation_key="assign_categories",
        translation_placeholders={"site": str(entry.data.get(CONF_SITE_NAME, entry.title)), "entities": ", ".join(unassigned) or "none"},
    )


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version >= CONFIG_VERSION:
        return True
    data = dict(entry.data)
    legacy = list(data.pop(LEGACY_CONF_MONITORED_ENTITIES, []))
    for key in list(data):
        if key not in (CONF_SITE_NAME, CONF_NOTIFY_SERVICE, *CATEGORY_CONF_KEYS.values()):
            data.pop(key)
    data.setdefault(CONF_SITE_NAME, entry.title)
    data.setdefault(CONF_NOTIFY_SERVICE, "")
    for key in CATEGORY_CONF_KEYS.values():
        data.setdefault(key, [])
    data[LEGACY_UNASSIGNED] = legacy
    hass.config_entries.async_update_entry(entry, data=data, options=dict(OPTION_DEFAULTS), version=CONFIG_VERSION)
    if not entity_specs_from_data(data):
        _raise_assign_issue(hass, entry, legacy)
    _LOGGER.info("Behaviour Monitor: migrated %s to v%d; categories need assigning", entry.entry_id, CONFIG_VERSION)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not entity_specs_from_data(entry.data):
        _raise_assign_issue(hass, entry, list(entry.data.get(LEGACY_UNASSIGNED, [])))
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))
        return True
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_ASSIGN_CATEGORIES}_{entry.entry_id}")

    coordinator = BehaviourMonitorCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


def _coordinators(hass: HomeAssistant) -> list[BehaviourMonitorCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


def _register_services(hass: HomeAssistant) -> None:
    async def enable_holiday(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_enable_holiday_mode()

    async def disable_holiday(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_disable_holiday_mode()

    async def snooze(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_snooze(call.data["duration"])

    async def clear_snooze(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_clear_snooze()

    async def acknowledge(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_acknowledge()

    async def reset_learning(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_reset_learning(call.data.get("entity_id"))

    async def test_panic(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_test_panic()

    hass.services.async_register(DOMAIN, SERVICE_ENABLE_HOLIDAY_MODE, enable_holiday)
    hass.services.async_register(DOMAIN, SERVICE_DISABLE_HOLIDAY_MODE, disable_holiday)
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE, snooze, schema=vol.Schema({vol.Required("duration"): vol.In(list(SNOOZE_DURATIONS))}))
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_SNOOZE, clear_snooze)
    hass.services.async_register(DOMAIN, SERVICE_ACKNOWLEDGE, acknowledge)
    hass.services.async_register(DOMAIN, SERVICE_RESET_LEARNING, reset_learning, schema=vol.Schema({vol.Optional("entity_id"): str}))
    hass.services.async_register(DOMAIN, SERVICE_TEST_PANIC, test_panic)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.entry_id not in hass.data.get(DOMAIN, {}):
        return True
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        if not hass.data[DOMAIN]:
            for name in (SERVICE_ENABLE_HOLIDAY_MODE, SERVICE_DISABLE_HOLIDAY_MODE, SERVICE_SNOOZE, SERVICE_CLEAR_SNOOZE, SERVICE_ACKNOWLEDGE, SERVICE_RESET_LEARNING, SERVICE_TEST_PANIC):
                hass.services.async_remove(DOMAIN, name)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_init.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/__init__.py tests/test_init.py
git commit -m "feat!: v11 migration with assign-categories repair, new services, button platform"
```

---

### Task 6: services.yaml and translations

**Files:**
- Modify: `custom_components/behaviour_monitor/services.yaml` (full rewrite)
- Modify: `custom_components/behaviour_monitor/translations/en.json` (full rewrite)
- Create: `tests/test_translations.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_translations.py
import json
from pathlib import Path

import yaml  # PyYAML ships with Home Assistant; add to requirements-test.txt if missing

from custom_components.behaviour_monitor.const import CATEGORY_CONF_KEYS, OPTION_DEFAULTS

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "behaviour_monitor"


def test_translations_cover_every_config_and_option_field():
    t = json.loads((ROOT / "translations" / "en.json").read_text())
    user = t["config"]["step"]["user"]["data"]
    init = t["options"]["step"]["init"]["data"]
    for key in ("site_name", "notify_service", *CATEGORY_CONF_KEYS.values()):
        assert key in user and key in init
    for key in OPTION_DEFAULTS:
        assert key in init
    assert set(t["config"]["error"]) >= {"no_entities", "duplicate_entity"}
    assert set(t["issues"]) >= {"assign_categories", "device_health"}


def test_services_yaml_lists_every_service():
    s = yaml.safe_load((ROOT / "services.yaml").read_text())
    assert set(s) == {"enable_holiday_mode", "disable_holiday_mode", "snooze", "clear_snooze", "acknowledge", "reset_learning", "test_panic"}
    assert "entity_id" in s["reset_learning"]["fields"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_translations.py -v`
Expected: FAIL on missing keys

- [ ] **Step 3: Write services.yaml**

```yaml
# custom_components/behaviour_monitor/services.yaml
enable_holiday_mode:
  name: Enable holiday mode
  description: Pause learning and welfare alerts while the occupant is away. Panic and device health still alert.

disable_holiday_mode:
  name: Disable holiday mode
  description: Resume learning and welfare alerts.

snooze:
  name: Snooze
  description: Suppress welfare and statistical delivery for a while. Panic and device health still alert.
  fields:
    duration:
      name: Duration
      required: true
      example: "2_hours"
      selector:
        select:
          options:
            - label: "1 Hour"
              value: "1_hour"
            - label: "2 Hours"
              value: "2_hours"
            - label: "4 Hours"
              value: "4_hours"
            - label: "1 Day"
              value: "1_day"

clear_snooze:
  name: Clear snooze
  description: Resume delivery immediately.

acknowledge:
  name: Acknowledge
  description: Stop repeat pushes for the open welfare alerts. The alert stays open until the house recovers.

reset_learning:
  name: Reset learning
  description: Wipe learned patterns for one entity, or for the whole site when no entity is given, then relearn from the recorder.
  fields:
    entity_id:
      name: Entity
      required: false
      example: "binary_sensor.kitchen_motion"
      selector:
        entity: {}

test_panic:
  name: Test panic
  description: Send a panic push through the real delivery path without touching learned state.
```

- [ ] **Step 4: Write translations/en.json**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Behaviour Monitor site",
        "description": "Name the site, choose where welfare pushes go, and place each sensor in a category. Rooms come from the Home Assistant area of each entity or its device.",
        "data": {
          "site_name": "Site name",
          "notify_service": "Notify service (for example notify.mobile_app_phone)",
          "motion_entities": "Motion sensors",
          "contact_entities": "Door and window contacts",
          "plug_entities": "Power plugs (power sensors or switches)",
          "panic_entities": "Panic buttons",
          "light_entities": "Lights",
          "other_entities": "Other activity entities"
        }
      }
    },
    "error": {
      "no_entities": "Add at least one entity to a category.",
      "duplicate_entity": "An entity appears in more than one category."
    },
    "abort": {
      "already_configured": "A site with this name is already configured."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Behaviour Monitor options",
        "data": {
          "site_name": "Site name",
          "notify_service": "Notify service",
          "motion_entities": "Motion sensors",
          "contact_entities": "Door and window contacts",
          "plug_entities": "Power plugs",
          "panic_entities": "Panic buttons",
          "light_entities": "Lights",
          "other_entities": "Other activity entities",
          "motion_debounce_s": "Motion debounce (seconds)",
          "plug_margin_w": "Plug on-threshold above idle (watts)",
          "learning_days": "Days before alerts start",
          "window_days": "Days of history kept",
          "health_grace_s": "Unavailable grace period (seconds)",
          "push_repeat_s": "Welfare push repeat interval (seconds)",
          "push_min_severity": "Minimum severity to push",
          "house_low_ratio": "House silence ratio for a low welfare alert",
          "chain_window_s": "Chain step window (seconds)",
          "timing_promote_days": "Days of slower routine before a welfare alert",
          "drift_sensitivity": "Drift sensitivity"
        }
      }
    },
    "error": {
      "no_entities": "Add at least one entity to a category.",
      "duplicate_entity": "An entity appears in more than one category."
    }
  },
  "issues": {
    "assign_categories": {
      "title": "Assign categories for {site}",
      "description": "Behaviour Monitor v5 needs each monitored entity placed in a category. Open the integration options and assign: {entities}"
    },
    "device_health": {
      "title": "{site}: sensor problem",
      "description": "{message}"
    }
  },
  "entity": {
    "sensor": {
      "welfare_status": {"name": "Welfare Status"},
      "house_activity": {"name": "House Activity"},
      "anomaly": {"name": "Anomaly"},
      "device_health": {"name": "Device Health"},
      "learning": {"name": "Learning"},
      "entity_status": {"name": "Entity Status"},
      "last_activity": {"name": "Last Activity"},
      "daily_activity_count": {"name": "Daily Activity Count"},
      "last_notification": {"name": "Last Notification"}
    },
    "switch": {"holiday_mode": {"name": "Holiday Mode"}},
    "select": {"snooze": {"name": "Snooze Notifications"}},
    "button": {"acknowledge": {"name": "Acknowledge"}}
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_translations.py -v`
Expected: 2 passed. If `yaml` is missing, add `pyyaml>=6.0` to `requirements-test.txt` and install it.

- [ ] **Step 6: Commit**

```bash
git add custom_components/behaviour_monitor/services.yaml custom_components/behaviour_monitor/translations/en.json tests/test_translations.py requirements-test.txt
git commit -m "feat: v5 services and translations with category fields and repair texts"
```

---

### Task 7: Real-site fixture exporter

**Files:**
- Create: `scripts/export_fixture.py`
- Create: `tests/test_export_fixture.py`

**Interfaces:**
- `python scripts/export_fixture.py --url http://ha:8123 --token $HA_TOKEN --entities ids.json --days 10 --out tests/fixtures/site_real_10d.jsonl` where `ids.json` is a list of `{"entity_id", "category", "room"}`. Uses the REST endpoint `/api/history/period/<start>?filter_entity_id=...&minimal_response&no_attributes`. Entity ids are replaced with `<category>_<n>` and rooms with `Room <n>`; the mapping is printed, not stored.
- Importable pieces: `anonymise(specs) -> tuple[list[dict], dict[str, str], dict[str, str]]`, `rows_to_events(rows_by_entity, id_map) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_fixture.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_fixture import anonymise, rows_to_events  # noqa: E402


def test_anonymise_replaces_ids_and_rooms_consistently():
    specs = [
        {"entity_id": "binary_sensor.kitchen_motion_2", "category": "motion", "room": "Biddulph Road Kitchen"},
        {"entity_id": "sensor.kettle_power", "category": "plug", "room": "Biddulph Road Kitchen"},
        {"entity_id": "binary_sensor.hall_panic", "category": "panic", "room": "Biddulph Road Hall"},
    ]
    out, id_map, room_map = anonymise(specs)
    assert out[0]["entity_id"] == "binary_sensor.motion_1" and out[1]["entity_id"] == "sensor.plug_1"
    assert out[0]["room"] == out[1]["room"] == "Room 1" and out[2]["room"] == "Room 2"
    assert id_map["sensor.kettle_power"] == "sensor.plug_1" and room_map["Biddulph Road Hall"] == "Room 2"


def test_rows_to_events_sorted_and_mapped():
    rows = [
        [{"entity_id": "a", "state": "on", "last_changed": "2026-09-10T08:00:00+01:00"},
         {"entity_id": "a", "state": "off", "last_changed": "2026-09-10T08:01:00+01:00"}],
        [{"entity_id": "b", "state": "12.5", "last_changed": "2026-09-10T07:59:00+01:00"}],
    ]
    ev = rows_to_events(rows, {"a": "binary_sensor.motion_1", "b": "sensor.plug_1"})
    assert [e["e"] for e in ev] == ["sensor.plug_1", "binary_sensor.motion_1", "binary_sensor.motion_1"]
    assert ev[0]["s"] == "12.5" and ev[1]["t"] == "2026-09-10T08:00:00+01:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_export_fixture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'export_fixture'`

- [ ] **Step 3: Write the exporter**

```python
# scripts/export_fixture.py
"""Export recorder history for a site into the fixture format, anonymised.

Usage:
  python scripts/export_fixture.py --url http://homeassistant.local:8123 \
      --token "$HA_TOKEN" --entities site_entities.json --days 10 \
      --out tests/fixtures/site_real_10d.jsonl --site "Real site"

site_entities.json: [{"entity_id": "...", "category": "motion", "room": "Kitchen"}, ...]
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


def anonymise(specs: list[dict]) -> tuple[list[dict], dict[str, str], dict[str, str]]:
    id_map: dict[str, str] = {}
    room_map: dict[str, str] = {}
    counters: dict[str, int] = {}
    out: list[dict] = []
    for s in specs:
        cat = s["category"]
        counters[cat] = counters.get(cat, 0) + 1
        domain = s["entity_id"].split(".", 1)[0]
        new_id = f"{domain}.{cat}_{counters[cat]}"
        id_map[s["entity_id"]] = new_id
        room = s.get("room") or s["entity_id"]
        if room not in room_map:
            room_map[room] = f"Room {len(room_map) + 1}"
        out.append({"entity_id": new_id, "category": cat, "room": room_map[room]})
    return out, id_map, room_map


def rows_to_events(rows_by_entity: list[list[dict]], id_map: dict[str, str]) -> list[dict]:
    events: list[dict] = []
    for rows in rows_by_entity:
        for r in rows:
            eid = id_map.get(r["entity_id"])
            if eid is None:
                continue
            events.append({"t": r["last_changed"], "e": eid, "s": str(r["state"])})
    events.sort(key=lambda e: e["t"])
    return events


def fetch_history(url: str, token: str, entity_ids: list[str], days: int) -> list[list[dict]]:
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = urllib.parse.urlencode({"filter_entity_id": ",".join(entity_ids), "minimal_response": "", "no_attributes": ""})
    req = urllib.request.Request(f"{url.rstrip('/')}/api/history/period/{start}?{q}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        rows = json.load(resp)
    # minimal_response omits entity_id on all but the first row per entity; restore it
    for series in rows:
        if series:
            eid = series[0]["entity_id"]
            for r in series:
                r.setdefault("entity_id", eid)
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--entities", required=True, type=Path)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--site", default="Real site")
    args = p.parse_args(argv)
    specs = json.loads(args.entities.read_text())
    anon, id_map, room_map = anonymise(specs)
    rows = fetch_history(args.url, args.token, list(id_map), args.days)
    events = rows_to_events(rows, id_map)
    args.out.write_text("".join(json.dumps(e) + "\n" for e in events))
    sidecar = args.out.with_suffix("").with_suffix(".sidecar.json")
    sidecar.write_text(json.dumps({"site": args.site, "entities": anon, "options": {"learning_days": 14}}, indent=2))
    print(f"wrote {len(events)} events to {args.out}")
    print("entity map (not stored):", json.dumps(id_map, indent=2))
    print("room map (not stored):", json.dumps(room_map, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_export_fixture.py -v`
Expected: 2 passed

- [ ] **Step 5: Export the real fixture and add a replay test**

This step needs the site's URL and a long-lived token in the environment. If they are not available, skip the export and leave the test marked `skipif` on the fixture's absence.

```bash
cat > /tmp/site_entities.json <<'JSON'
[{"entity_id":"binary_sensor.kitchen_motion_2","category":"motion","room":"Kitchen"},
 {"entity_id":"binary_sensor.back_room_motion","category":"motion","room":"Backroom"},
 {"entity_id":"binary_sensor.front_room_motion","category":"motion","room":"Frontroom"},
 {"entity_id":"binary_sensor.bathroom_motion","category":"motion","room":"Bathroom"},
 {"entity_id":"binary_sensor.back_bedroom_motion","category":"motion","room":"Back Bedroom"},
 {"entity_id":"binary_sensor.front_bedroom_motion","category":"motion","room":"Front Bedroom"},
 {"entity_id":"binary_sensor.front_door_door","category":"contact","room":"Hall"},
 {"entity_id":"binary_sensor.back_door_door","category":"contact","room":"Utilityroom"},
 {"entity_id":"binary_sensor.side_door_door","category":"contact","room":"Utilityroom"},
 {"entity_id":"sensor.kettle_power","category":"plug","room":"Kitchen"},
 {"entity_id":"sensor.teas_maid_power","category":"plug","room":"Boxroom"},
 {"entity_id":"sensor.smart_plug_power","category":"plug","room":"Backroom"},
 {"entity_id":"sensor.front_bedroom_tv_power","category":"plug","room":"Front Bedroom"},
 {"entity_id":"binary_sensor.panic_button_hall_safety","category":"panic","room":"Hall"},
 {"entity_id":"binary_sensor.panic_button_landing_safety","category":"panic","room":"Landing"}]
JSON
venv/bin/python scripts/export_fixture.py --url "$HA_URL" --token "$HA_TOKEN" --entities /tmp/site_entities.json --days 10 --out tests/fixtures/site_real_10d.jsonl
venv/bin/python scripts/replay.py tests/fixtures/site_real_10d.jsonl | grep -c push
```

Append to `tests/core/test_replay_scenarios.py`:

```python
REAL = Path(__file__).resolve().parents[1] / "fixtures" / "site_real_10d.jsonl"


@pytest.mark.skipif(not REAL.exists(), reason="real fixture not exported")
def test_real_site_ten_days_raises_no_welfare_push_above_low():
    tl = run_fixture(REAL, poll_minutes=5)
    welfare = [a.alert for _, a in tl if a.action == "push" and a.alert.cls.value == "welfare"]
    assert all(a.severity.value == "low" for a in welfare), [a.explanation for a in welfare]
    dropouts = [a.alert for _, a in tl if a.action == "repair_create" and a.alert.kind == "dropout"]
    assert len(dropouts) <= 25
```

With only 10 days and `learning_days` 14 the engine never leaves learning in this fixture, so the welfare assertion is trivially true today. The fixture's value is the health and statistical timeline, and it becomes a real welfare check once a longer export replaces it.

- [ ] **Step 6: Commit**

```bash
git add scripts/export_fixture.py tests/test_export_fixture.py tests/core/test_replay_scenarios.py tests/fixtures
git commit -m "feat: real-site fixture exporter with anonymised ids and rooms"
```

---

### Task 8: Remove v4 modules, update docs and version

**Files:**
- Delete: `custom_components/behaviour_monitor/routine_model.py`, `acute_detector.py`, `drift_detector.py`, `correlation_detector.py`, `alert_result.py`
- Delete: `tests/test_routine_model.py`, `tests/test_acute_detector.py`, `tests/test_drift_detector.py`, `tests/test_correlation_detector.py`, `tests/test_alert_result.py`, `tests/test_coordinator_correlation.py`, `scripts/v2_storage.json`
- Modify: `custom_components/behaviour_monitor/manifest.json` (version 5.0.0)
- Modify: `Makefile` (drop `test-analyzer`, `test-ml`; keep `test-core`)
- Modify: `CLAUDE.md`, `custom_components/behaviour_monitor/CLAUDE.md`, `README.md`

- [ ] **Step 1: Delete the old modules and tests**

```bash
git rm custom_components/behaviour_monitor/routine_model.py custom_components/behaviour_monitor/acute_detector.py \
  custom_components/behaviour_monitor/drift_detector.py custom_components/behaviour_monitor/correlation_detector.py \
  custom_components/behaviour_monitor/alert_result.py \
  tests/test_routine_model.py tests/test_acute_detector.py tests/test_drift_detector.py \
  tests/test_correlation_detector.py tests/test_alert_result.py tests/test_coordinator_correlation.py scripts/v2_storage.json
```

- [ ] **Step 2: Verify nothing imports them**

Run: `grep -rn "routine_model\|acute_detector\|correlation_detector\|alert_result\|from .drift_detector" custom_components tests scripts`
Expected: no output.

- [ ] **Step 3: Bump the manifest and fix the Makefile**

In `manifest.json` set `"version": "5.0.0"`. In `Makefile` delete the `test-analyzer` and `test-ml` targets.

- [ ] **Step 4: Update documentation**

Replace the "Architecture Decisions" and "File Structure" sections of the root `CLAUDE.md` with:

```markdown
## Architecture

- `core/` is a pure Python package (stdlib only): `normaliser`, `house_model`,
  `entity_routine`, `chain_model`, `drift_detector`, `health_tracker`,
  `alert_router`, wired by `engine.Engine`. Spec:
  `docs/superpowers/specs/2026-09-20-generic-welfare-core-design.md`.
- `coordinator.py` is the only module that imports both Home Assistant and
  `core`. It resolves rooms from areas, feeds state changes to the engine,
  polls it once a minute and performs the delivery actions it returns.
- Three alert classes: welfare (push, repeated until acknowledged), device
  health (repair issues), statistical (sensor attribute and logbook).
- Learned state persists in `.storage/behaviour_monitor.{entry_id}.json`
  (store version 11) as `Engine.to_dict()`.

## File structure

    custom_components/behaviour_monitor/
    ├── __init__.py        # setup, v11 migration, services
    ├── config_flow.py     # site name, notify service, six category lists, options
    ├── coordinator.py     # Engine shell
    ├── sensor.py          # nine sensors on the engine snapshot
    ├── button.py / switch.py / select.py
    ├── const.py
    └── core/              # pure learning and alerting core
    scripts/replay.py           # replay a fixture, print the alert timeline
    scripts/export_fixture.py   # export a real site to the fixture format
    tests/core/                 # core tests and synthetic scenarios
    tests/fixtures/             # jsonl fixtures with sidecars
```

Update `README.md`: replace the configuration section with the six category lists, the site name and notify service, the options table copied from the spec, and a short "Alert classes" section from spec section 7. Add a "Upgrading from v4" paragraph: learned data is discarded, and a repair issue asks you to assign categories in options.

- [ ] **Step 5: Run the whole suite, lint and format**

Run: `venv/bin/python -m black custom_components tests scripts && venv/bin/python -m ruff check custom_components tests scripts && venv/bin/python -m pytest tests/ -q`
Expected: ruff clean; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat!: remove v4 detectors, bump to 5.0.0, document the v5 architecture

BREAKING CHANGE: config entry v11 requires categories to be assigned in options; v4 learned state is discarded."
```

---

## Self-review against the spec

| Spec section | Task |
|---|---|
| 5.1 rooms from areas, display-name stripping, re-resolve on registry change | 3 |
| 7 delivery table: push and repeat, repair issue, logbook; panic bypass | 3 (`_perform`), 5 (services) |
| 9 store per entry, bootstrap from recorder with local timestamps, entity list changes, reset service | 3 |
| 10 config flow setup and options, defaults table, entities list, services, repair on upgrade | 1, 2, 4, 5, 6 |
| 11 real export fixture | 7 |
| 12 migration | 5 |
| 13 decisions: no extra room config key | 3 (`display_room` uses site name) |

Placeholder scan: none. Type consistency: `EntitySpec`, `Category`, `DeliveryAction` and `Alert` come from Part 1 unchanged; `device_info(entry, site)` is defined once in `sensor.py` and imported by `button.py`, `switch.py`, `select.py`; `coordinator.site_name` is the property every platform reads.

Known deviation from the spec: the spec names sensors `sensor.<site>_welfare_status`; Home Assistant derives the entity id from the device name plus the entity name when `_attr_has_entity_name` is set, so naming the device after the site produces that id without any code.
