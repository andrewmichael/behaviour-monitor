"""Select platform for Behaviour Monitor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SNOOZE_LABELS,
    SNOOZE_OFF,
    SNOOZE_OPTIONS,
)
from .coordinator import BehaviourMonitorCoordinator
from .sensor import device_info

ATTR_SNOOZE_ACTIVE = "snooze_active"
ATTR_SNOOZE_UNTIL = "snooze_until"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Behaviour Monitor selects."""
    coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [SnoozeDurationSelect(coordinator, entry)]

    async_add_entities(entities)


class SnoozeDurationSelect(
    CoordinatorEntity[BehaviourMonitorCoordinator], SelectEntity
):
    """Select entity for snooze duration."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bell-sleep"

    def __init__(
        self,
        coordinator: BehaviourMonitorCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_snooze_duration"
        self._attr_name = "Snooze Notifications"
        self._attr_options = [SNOOZE_LABELS[opt] for opt in SNOOZE_OPTIONS]
        self._attr_device_info = device_info(entry, coordinator.site_name)

    @property
    def current_option(self) -> str:
        """Return the current selected option."""
        # Get the current snooze duration key
        current_key = self.coordinator.get_snooze_duration_key()
        return SNOOZE_LABELS[current_key]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            ATTR_SNOOZE_ACTIVE: self.coordinator.is_snoozed(),
            "description": (
                "Temporarily pause anomaly detection and notifications. "
                "State tracking continues but patterns are not updated."
            ),
        }

        snooze_until = self.coordinator.snooze_until
        if snooze_until:
            attrs[ATTR_SNOOZE_UNTIL] = snooze_until.isoformat()

        return attrs

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Convert label back to key
        duration_key = None
        for key, label in SNOOZE_LABELS.items():
            if label == option:
                duration_key = key
                break

        if duration_key is None:
            return

        if duration_key == SNOOZE_OFF:
            await self.coordinator.async_clear_snooze()
        else:
            await self.coordinator.async_snooze(duration_key)

        self.async_write_ha_state()
