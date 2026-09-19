"""The Behaviour Monitor integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er, issue_registry as ir
import voluptuous as vol

from .const import (
    CONF_ACTIVITY_TIER_OVERRIDE,
    CONF_ALERT_REPEAT_INTERVAL,
    CONF_BURST_DISCARD_THRESHOLD,
    CONF_CATEGORY_CONTACT,
    CONF_CATEGORY_LIGHT,
    CONF_CATEGORY_MOTION,
    CONF_CATEGORY_PANIC,
    CONF_CATEGORY_PLUG,
    CONF_CORRELATION_WINDOW,
    CONF_DOOR_DEBOUNCE_SECONDS,
    CONF_DOOR_OPEN_EXTENDED_SECONDS,
    CONF_DOOR_OPEN_PROLONGED_SECONDS,
    CONF_DRIFT_SENSITIVITY,
    CONF_EXCURSION_WINDOW_SECONDS,
    CONF_EXTERIOR_DOORS,
    CONF_HISTORY_WINDOW_DAYS,
    CONF_INACTIVITY_MULTIPLIER,
    CONF_LEARNING_PERIOD,
    CONF_MAX_INACTIVITY_MULTIPLIER,
    CONF_MIN_INACTIVITY_MULTIPLIER,
    CONF_MONITORED_ENTITIES,
    CONF_MOTION_DEBOUNCE_SECONDS,
    CONF_PANIC_HEARTBEAT_HOURS,
    CONF_PANIC_RENOTIFY_MINUTES,
    CONF_PANIC_TEST_REMINDER_DAYS,
    CONF_REBOOTSTRAP_MOTION,
    CONF_REBOOTSTRAP_ROLES,
    CONF_RETRIGGER_COLLAPSE_SECONDS,
    CONF_ROLE_OVERRIDES,
    CONF_STARTUP_GRACE_SECONDS,
    CONF_TRACK_ATTRIBUTES,
    CONF_TRACK_ATTRIBUTES_EXCLUDE,
    CONF_TRACK_ATTRIBUTES_INCLUDE,
    CONTACT_DEVICE_CLASSES,
    DEFAULT_ACTIVITY_TIER_OVERRIDE,
    DEFAULT_ALERT_REPEAT_INTERVAL,
    DEFAULT_BURST_DISCARD_THRESHOLD,
    DEFAULT_CATEGORY_PANIC,
    DEFAULT_CORRELATION_WINDOW,
    DEFAULT_DOOR_DEBOUNCE_SECONDS,
    DEFAULT_DOOR_OPEN_EXTENDED_SECONDS,
    DEFAULT_DOOR_OPEN_PROLONGED_SECONDS,
    DEFAULT_EXCURSION_WINDOW_SECONDS,
    DEFAULT_EXTERIOR_DOORS,
    DEFAULT_HISTORY_WINDOW_DAYS,
    DEFAULT_INACTIVITY_MULTIPLIER,
    DEFAULT_LEARNING_PERIOD_DAYS,
    DEFAULT_MAX_INACTIVITY_MULTIPLIER,
    DEFAULT_MIN_INACTIVITY_MULTIPLIER,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
    DEFAULT_PANIC_HEARTBEAT_HOURS,
    DEFAULT_PANIC_RENOTIFY_MINUTES,
    DEFAULT_PANIC_TEST_REMINDER_DAYS,
    DEFAULT_RETRIGGER_COLLAPSE_SECONDS,
    DEFAULT_STARTUP_GRACE_SECONDS,
    DEFAULT_TRACK_ATTRIBUTES,
    DEFAULT_TRACK_ATTRIBUTES_EXCLUDE,
    DEFAULT_TRACK_ATTRIBUTES_INCLUDE,
    DOMAIN,
    SENSITIVITY_MEDIUM,
    SERVICE_ACKNOWLEDGE_PANIC,
    SERVICE_CLEAR_SNOOZE,
    SERVICE_DISABLE_HOLIDAY_MODE,
    SERVICE_ENABLE_HOLIDAY_MODE,
    SERVICE_PANIC_TEST,
    SERVICE_ROUTINE_RESET,
    SERVICE_SNOOZE,
    SNOOZE_DURATIONS,
)
from .coordinator import BehaviourMonitorCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.SELECT, Platform.BUTTON]

# ML config keys removed in v1.1
_ML_KEYS_REMOVED_V3 = (
    "enable_ml",
    "retrain_period",
    "ml_learning_period",
    "cross_sensor_window",
)

# Old sigma/ML keys removed in v1.1 (v3 -> v4)
_OLD_KEYS_REMOVED_V4 = (
    "sensitivity",
    "learning_period",
    "enable_ml",
    "retrain_period",
    "ml_learning_period",
    "cross_sensor_window",
    "track_attributes",
)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate config entry to the current version.

    v2 -> v3: Remove ML config keys, add history_window_days.
    v3 -> v4: Remove remaining old sigma/ML keys, add inactivity_multiplier and
              drift_sensitivity defaults.
    v4 -> v5: Add learning_period (default 7) and track_attributes (default False).
    """
    if config_entry.version < 3:
        new_data = dict(config_entry.data)

        # Remove deprecated ML keys
        for key in _ML_KEYS_REMOVED_V3:
            new_data.pop(key, None)

        # Add new history_window_days with default if not already present
        new_data.setdefault(CONF_HISTORY_WINDOW_DAYS, DEFAULT_HISTORY_WINDOW_DAYS)

        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=3,
        )

        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v3 — ML options removed"
        )

    if config_entry.version < 4:
        new_data = dict(config_entry.data)

        # Remove old sigma/ML keys that are no longer used by v1.1
        for key in _OLD_KEYS_REMOVED_V4:
            new_data.pop(key, None)

        # Ensure new v1.1 config keys have defaults
        new_data.setdefault(CONF_HISTORY_WINDOW_DAYS, DEFAULT_HISTORY_WINDOW_DAYS)
        new_data.setdefault(CONF_INACTIVITY_MULTIPLIER, DEFAULT_INACTIVITY_MULTIPLIER)
        new_data.setdefault(CONF_DRIFT_SENSITIVITY, SENSITIVITY_MEDIUM)

        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=4,
        )

        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v4 — sigma/ML options removed, "
            "inactivity_multiplier and drift_sensitivity added"
        )

    if config_entry.version < 5:
        new_data = dict(config_entry.data)

        # Add new v2.9 config keys with defaults
        new_data.setdefault(CONF_LEARNING_PERIOD, DEFAULT_LEARNING_PERIOD_DAYS)
        new_data.setdefault(CONF_TRACK_ATTRIBUTES, DEFAULT_TRACK_ATTRIBUTES)

        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=5,
        )

        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v5 — learning_period and track_attributes added"
        )

    if config_entry.version < 6:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_ALERT_REPEAT_INTERVAL, DEFAULT_ALERT_REPEAT_INTERVAL)
        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=6,
        )
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v6 — alert_repeat_interval added"
        )

    if config_entry.version < 7:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_MIN_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER)
        new_data.setdefault(CONF_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MAX_INACTIVITY_MULTIPLIER)
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=7)
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v7 — adaptive inactivity bounds added"
        )

    if config_entry.version < 8:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_ACTIVITY_TIER_OVERRIDE, DEFAULT_ACTIVITY_TIER_OVERRIDE)
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=8)
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v8 — activity_tier_override added"
        )

    if config_entry.version < 9:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_CORRELATION_WINDOW, DEFAULT_CORRELATION_WINDOW)
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=9)
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v9 — correlation_window added"
        )

    if config_entry.version < 10:
        new_data = dict(config_entry.data)
        new_data.setdefault(
            CONF_TRACK_ATTRIBUTES_INCLUDE, list(DEFAULT_TRACK_ATTRIBUTES_INCLUDE)
        )
        new_data.setdefault(
            CONF_TRACK_ATTRIBUTES_EXCLUDE, list(DEFAULT_TRACK_ATTRIBUTES_EXCLUDE)
        )
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=10)
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v10 — "
            "per-entity track_attributes overrides added"
        )

    if config_entry.version < 11:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_CATEGORY_MOTION, [])
        new_data.setdefault(CONF_CATEGORY_CONTACT, [])
        new_data.setdefault(CONF_CATEGORY_PLUG, [])
        new_data.setdefault(CONF_CATEGORY_LIGHT, [])
        new_data.setdefault(CONF_MOTION_DEBOUNCE_SECONDS, DEFAULT_MOTION_DEBOUNCE_SECONDS)
        # One-shot: the coordinator rebuilds motion routines with debounce
        # from recorder history on its next setup, then clears this flag.
        new_data[CONF_REBOOTSTRAP_MOTION] = True
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=11)
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v11 — "
            "entity categories and motion debounce added"
        )

    if config_entry.version < 12:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_CATEGORY_PANIC, list(DEFAULT_CATEGORY_PANIC))
        new_data.setdefault(CONF_PANIC_RENOTIFY_MINUTES, DEFAULT_PANIC_RENOTIFY_MINUTES)
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=12)
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v12 — panic button category added"
        )

    if config_entry.version < 13:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_STARTUP_GRACE_SECONDS, DEFAULT_STARTUP_GRACE_SECONDS)
        new_data.setdefault(CONF_BURST_DISCARD_THRESHOLD, DEFAULT_BURST_DISCARD_THRESHOLD)
        new_data.setdefault(CONF_PANIC_HEARTBEAT_HOURS, DEFAULT_PANIC_HEARTBEAT_HOURS)
        new_data.setdefault(CONF_PANIC_TEST_REMINDER_DAYS, DEFAULT_PANIC_TEST_REMINDER_DAYS)
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=13)
        _LOGGER.info("Behaviour Monitor: Config entry migrated to v13 — system integrity settings added")

    if config_entry.version < 14:
        new_data = dict(config_entry.data)
        lines = [ln for ln in (new_data.get(CONF_ROLE_OVERRIDES) or "").splitlines() if ln.strip()]
        overrides: dict[str, str] = {}
        for key, value in (
            (CONF_CATEGORY_MOTION, "motion"),
            (CONF_CATEGORY_CONTACT, "door"),
            (CONF_CATEGORY_PLUG, "appliance"),
            (CONF_CATEGORY_LIGHT, "appliance"),
        ):
            for eid in new_data.pop(key, None) or []:
                overrides.setdefault(eid, value)
        # De-duplicate entity ids across the four old lists, preserving
        # first-seen order (first kind wins), so the migration's own output
        # can never make parse_role_overrides reject the whole map for a
        # repeated entity.
        lines.extend(f"{eid}: {value}" for eid, value in overrides.items())
        new_data[CONF_ROLE_OVERRIDES] = "\n".join(lines)
        new_data.setdefault(CONF_EXTERIOR_DOORS, list(DEFAULT_EXTERIOR_DOORS))
        new_data.setdefault(CONF_DOOR_DEBOUNCE_SECONDS, DEFAULT_DOOR_DEBOUNCE_SECONDS)
        new_data.setdefault(CONF_RETRIGGER_COLLAPSE_SECONDS, DEFAULT_RETRIGGER_COLLAPSE_SECONDS)
        new_data.setdefault(CONF_EXCURSION_WINDOW_SECONDS, DEFAULT_EXCURSION_WINDOW_SECONDS)
        new_data.setdefault(CONF_DOOR_OPEN_EXTENDED_SECONDS, DEFAULT_DOOR_OPEN_EXTENDED_SECONDS)
        new_data.setdefault(CONF_DOOR_OPEN_PROLONGED_SECONDS, DEFAULT_DOOR_OPEN_PROLONGED_SECONDS)
        new_data[CONF_REBOOTSTRAP_ROLES] = True
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=14)
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v14 — roles replace categories; "
            "door/appliance baselines rebuild once"
        )
        if not new_data[CONF_EXTERIOR_DOORS] and _has_contact_entity(hass, new_data.get(CONF_MONITORED_ENTITIES, [])):
            try:
                ir.async_create_issue(
                    hass, DOMAIN, "exterior_doors_unconfirmed",
                    is_fixable=False, is_persistent=True, severity=ir.IssueSeverity.WARNING,
                    translation_key="exterior_doors_unconfirmed",
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not create repair issue exterior_doors_unconfirmed")

    return True


def _has_contact_entity(hass: HomeAssistant, entity_ids: list[str]) -> bool:
    """True when any monitored entity has a contact device class in the entity registry."""
    try:
        registry = er.async_get(hass)
        for eid in entity_ids:
            entry = registry.async_get(eid)
            if entry is None:
                continue
            dc = entry.device_class or entry.original_device_class
            if isinstance(dc, str) and dc in CONTACT_DEVICE_CLASSES:
                return True
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not inspect entity registry during migration", exc_info=True)
    return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Behaviour Monitor from a config entry."""
    coordinator = BehaviourMonitorCoordinator(hass, entry)

    # Set up the coordinator
    await coordinator.async_setup()

    # Perform initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator for platform setup
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward entry setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    async def handle_enable_holiday_mode(call: ServiceCall) -> None:
        """Handle enable holiday mode service call."""
        await coordinator.async_enable_holiday_mode()

    async def handle_disable_holiday_mode(call: ServiceCall) -> None:
        """Handle disable holiday mode service call."""
        await coordinator.async_disable_holiday_mode()

    async def handle_snooze(call: ServiceCall) -> None:
        """Handle snooze service call."""
        duration = call.data.get("duration")
        await coordinator.async_snooze(duration)

    async def handle_clear_snooze(call: ServiceCall) -> None:
        """Handle clear snooze service call."""
        await coordinator.async_clear_snooze()

    async def handle_routine_reset(call: ServiceCall) -> None:
        """Handle routine reset service call."""
        entity_id = call.data["entity_id"]
        await coordinator.async_routine_reset(entity_id)

    async def handle_acknowledge_panic(call: ServiceCall) -> None:
        """Handle acknowledge panic service call."""
        await coordinator.async_acknowledge_panic(call.data.get("entity_id"))

    async def handle_panic_test(call: ServiceCall) -> None:
        """Handle panic test service call."""
        await coordinator.async_panic_test(call.data.get("entity_id"))

    # Register services for this instance
    hass.services.async_register(
        DOMAIN,
        SERVICE_ENABLE_HOLIDAY_MODE,
        handle_enable_holiday_mode,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DISABLE_HOLIDAY_MODE,
        handle_disable_holiday_mode,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SNOOZE,
        handle_snooze,
        schema=vol.Schema({
            vol.Required("duration"): vol.In(list(SNOOZE_DURATIONS.keys())),
        }),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_SNOOZE,
        handle_clear_snooze,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ROUTINE_RESET,
        handle_routine_reset,
        schema=vol.Schema({vol.Required("entity_id"): str}),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ACKNOWLEDGE_PANIC,
        handle_acknowledge_panic,
        schema=vol.Schema({vol.Optional("entity_id"): str}),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_PANIC_TEST,
        handle_panic_test,
        schema=vol.Schema({vol.Optional("entity_id"): str}),
    )

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "Behaviour Monitor set up with %d monitored entities",
        len(coordinator.monitored_entities),
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Shut down coordinator
        coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_shutdown()

        # Unregister services
        hass.services.async_remove(DOMAIN, SERVICE_ENABLE_HOLIDAY_MODE)
        hass.services.async_remove(DOMAIN, SERVICE_DISABLE_HOLIDAY_MODE)
        hass.services.async_remove(DOMAIN, SERVICE_SNOOZE)
        hass.services.async_remove(DOMAIN, SERVICE_CLEAR_SNOOZE)
        hass.services.async_remove(DOMAIN, SERVICE_ROUTINE_RESET)
        hass.services.async_remove(DOMAIN, SERVICE_ACKNOWLEDGE_PANIC)
        hass.services.async_remove(DOMAIN, SERVICE_PANIC_TEST)

        # Remove from hass data
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
