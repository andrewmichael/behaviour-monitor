"""The Behaviour Monitor integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
import voluptuous as vol

from .const import (
    CONF_HISTORY_WINDOW_DAYS,
    DEFAULT_HISTORY_WINDOW_DAYS,
    DOMAIN,
    SERVICE_CLEAR_SNOOZE,
    SERVICE_DISABLE_HOLIDAY_MODE,
    SERVICE_ENABLE_HOLIDAY_MODE,
    SERVICE_SNOOZE,
    SNOOZE_DURATIONS,
)
from .coordinator import BehaviourMonitorCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.SELECT]

# ML config keys removed in v1.1
_ML_KEYS_REMOVED_V3 = (
    "enable_ml",
    "retrain_period",
    "ml_learning_period",
    "cross_sensor_window",
)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate config entry to the current version.

    v2 -> v3: Remove ML config keys, add history_window_days.
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

    return True


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

        # Remove from hass data
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
