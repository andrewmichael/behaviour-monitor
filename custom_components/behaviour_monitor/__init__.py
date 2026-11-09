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
    BLUEPRINT_URL,
    CATEGORY_CONF_KEYS,
    CONF_ATTENTION_MIN_SEVERITY,
    CONF_OUTSIDE_DOORS,
    CONF_SITE_NAME,
    CONF_SITTING_APPLIANCES,
    CONFIG_VERSION,
    DOMAIN,
    ISSUE_ASSIGN_CATEGORIES,
    ISSUE_NOTIFICATIONS_MOVED,
    LEGACY_CONF_HOUSE_LOW_RATIO,
    LEGACY_CONF_MONITORED_ENTITIES,
    LEGACY_CONF_NOTIFY_SERVICE,
    LEGACY_CONF_PUSH_MIN_SEVERITY,
    LEGACY_CONF_PUSH_REPEAT_S,
    OPTION_DEFAULTS,
    SERVICE_CLEAR_ALERT,
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
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BUTTON,
]
LEGACY_UNASSIGNED = "legacy_unassigned"


def _raise_assign_issue(
    hass: HomeAssistant, entry: ConfigEntry, unassigned: list[str]
) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_ASSIGN_CATEGORIES}_{entry.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="assign_categories",
        translation_placeholders={
            "site": str(entry.data.get(CONF_SITE_NAME, entry.title)),
            "entities": ", ".join(unassigned) or "none",
        },
    )


def _raise_notifications_moved_issue(
    hass: HomeAssistant, entry: ConfigEntry, site: str, service: str
) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_NOTIFICATIONS_MOVED}_{entry.entry_id}",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_NOTIFICATIONS_MOVED,
        learn_more_url=BLUEPRINT_URL,
        translation_placeholders={"site": site, "service": service},
    )


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version >= CONFIG_VERSION:
        return True
    data = dict(entry.data)
    options = dict(entry.options)
    old_service = str(data.pop(LEGACY_CONF_NOTIFY_SERVICE, "") or "")
    from_legacy = entry.version < 11
    if from_legacy:
        legacy = list(data.pop(LEGACY_CONF_MONITORED_ENTITIES, []))
        for key in list(data):
            if key not in (CONF_SITE_NAME, *CATEGORY_CONF_KEYS.values()):
                data.pop(key)
        data.setdefault(CONF_SITE_NAME, entry.title)
        for key in CATEGORY_CONF_KEYS.values():
            data.setdefault(key, [])
        data[LEGACY_UNASSIGNED] = legacy
        options = dict(OPTION_DEFAULTS)
    else:
        legacy = []
        if entry.version < 12:
            options[CONF_ATTENTION_MIN_SEVERITY] = options.pop(
                LEGACY_CONF_PUSH_MIN_SEVERITY,
                OPTION_DEFAULTS[CONF_ATTENTION_MIN_SEVERITY],
            )
            options.pop(LEGACY_CONF_PUSH_REPEAT_S, None)
    # v13: the whereabouts lists start empty and bedrooms stays unset, so the
    # engine picks the rooms named "bedroom". The house silence ratio is gone.
    options.setdefault(CONF_OUTSIDE_DOORS, [])
    options.setdefault(CONF_SITTING_APPLIANCES, [])
    options.pop(LEGACY_CONF_HOUSE_LOW_RATIO, None)
    hass.config_entries.async_update_entry(
        entry, data=data, options=options, version=CONFIG_VERSION
    )
    if from_legacy and not entity_specs_from_data(data):
        _raise_assign_issue(hass, entry, legacy)
    if old_service:
        _raise_notifications_moved_issue(
            hass, entry, str(data.get(CONF_SITE_NAME, entry.title)), old_service
        )
    _LOGGER.info(
        "Behaviour Monitor: migrated %s to v%d", entry.entry_id, CONFIG_VERSION
    )
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

    async def clear_alert(call: ServiceCall) -> None:
        alert_id = call.data.get("alert_id")
        cleared = False
        for c in _coordinators(hass):
            cleared = await c.async_clear_alert(alert_id) or cleared
        if alert_id and not cleared:
            _LOGGER.warning("No open panic with id %s", alert_id)

    async def reset_learning(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_reset_learning(call.data.get("entity_id"))

    async def test_panic(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_test_panic()

    hass.services.async_register(DOMAIN, SERVICE_ENABLE_HOLIDAY_MODE, enable_holiday)
    hass.services.async_register(DOMAIN, SERVICE_DISABLE_HOLIDAY_MODE, disable_holiday)
    hass.services.async_register(
        DOMAIN,
        SERVICE_SNOOZE,
        snooze,
        schema=vol.Schema({vol.Required("duration"): vol.In(list(SNOOZE_DURATIONS))}),
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_SNOOZE, clear_snooze)
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_ALERT,
        clear_alert,
        schema=vol.Schema({vol.Optional("alert_id"): str}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_LEARNING,
        reset_learning,
        schema=vol.Schema({vol.Optional("entity_id"): str}),
    )
    hass.services.async_register(DOMAIN, SERVICE_TEST_PANIC, test_panic)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.entry_id not in hass.data.get(DOMAIN, {}):
        return True
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        if not hass.data[DOMAIN]:
            for name in (
                SERVICE_ENABLE_HOLIDAY_MODE,
                SERVICE_DISABLE_HOLIDAY_MODE,
                SERVICE_SNOOZE,
                SERVICE_CLEAR_SNOOZE,
                SERVICE_CLEAR_ALERT,
                SERVICE_RESET_LEARNING,
                SERVICE_TEST_PANIC,
            ):
                hass.services.async_remove(DOMAIN, name)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
