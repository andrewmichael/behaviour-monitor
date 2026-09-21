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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Behaviour Monitor acknowledge button."""
    coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AcknowledgeButton(coordinator, entry)])


class AcknowledgeButton(CoordinatorEntity[BehaviourMonitorCoordinator], ButtonEntity):
    """Button to acknowledge the current welfare alert."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:check-decagram"

    def __init__(
        self, coordinator: BehaviourMonitorCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_acknowledge"
        self._attr_name = "Acknowledge"
        self._attr_device_info = device_info(entry, coordinator.site_name)

    async def async_press(self) -> None:
        """Acknowledge the current welfare alert."""
        await self.coordinator.async_acknowledge()
