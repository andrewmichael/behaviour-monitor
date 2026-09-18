"""Button platform for Behaviour Monitor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BehaviourMonitorCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Behaviour Monitor buttons."""
    coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AcknowledgePanicButton(coordinator, entry)])


class AcknowledgePanicButton(
    CoordinatorEntity[BehaviourMonitorCoordinator], ButtonEntity
):
    """Button that acknowledges every active panic alert."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:alarm-light-off"

    def __init__(
        self, coordinator: BehaviourMonitorCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_acknowledge_panic"
        self._attr_name = "Acknowledge Panic"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Behaviour Monitor",
            manufacturer="Custom Integration",
            model="Pattern Analyzer",
            sw_version="2.6.0",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose which panics are active and how many await acknowledgement."""
        return {
            "active_panics": list(self.coordinator.panic_active),
            "unacknowledged": len(self.coordinator.panic_unacknowledged),
            "devices": dict(self.coordinator.panic_devices),
        }

    async def async_press(self) -> None:
        """Acknowledge all active panic alerts."""
        await self.coordinator.async_acknowledge_panic()
