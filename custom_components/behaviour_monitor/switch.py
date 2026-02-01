"""Switch platform for Behaviour Monitor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_HOLIDAY_MODE, DOMAIN
from .coordinator import BehaviourMonitorCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Behaviour Monitor switches."""
    coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [HolidayModeSwitch(coordinator, entry)]

    async_add_entities(entities)


class HolidayModeSwitch(CoordinatorEntity[BehaviourMonitorCoordinator], SwitchEntity):
    """Switch to enable/disable Holiday Mode."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:beach"

    def __init__(
        self,
        coordinator: BehaviourMonitorCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_holiday_mode"
        self._attr_name = "Holiday Mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Behaviour Monitor",
            manufacturer="Custom Integration",
            model="Pattern Analyzer",
            sw_version="2.6.0",
        )

    @property
    def is_on(self) -> bool:
        """Return true if holiday mode is on."""
        return self.coordinator.holiday_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "description": (
                "When enabled, all tracking and learning is paused. "
                "No state changes are recorded, no patterns updated, "
                "and no notifications sent."
            ),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on holiday mode."""
        await self.coordinator.async_enable_holiday_mode()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off holiday mode."""
        await self.coordinator.async_disable_holiday_mode()
        self.async_write_ha_state()
