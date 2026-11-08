"""Buttons: clear open panics; open a test alert."""

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
    """Set up the Behaviour Monitor buttons."""
    coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ClearPanicButton(coordinator, entry),
            TestAlertButton(coordinator, entry),
        ]
    )


class ClearPanicButton(CoordinatorEntity[BehaviourMonitorCoordinator], ButtonEntity):
    """Button to clear every open panic alert."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:alarm-light-off"

    def __init__(
        self, coordinator: BehaviourMonitorCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_acknowledge"
        self._attr_name = "Clear panic"
        self._attr_device_info = device_info(entry, coordinator.site_name)

    async def async_press(self) -> None:
        """Clear every open panic alert."""
        await self.coordinator.async_clear_alert(None)


class TestAlertButton(CoordinatorEntity[BehaviourMonitorCoordinator], ButtonEntity):
    """Button that opens a test alert through the real event path.

    Same as the test_panic service: the alert events carry test: true.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:bell-ring"

    def __init__(
        self, coordinator: BehaviourMonitorCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_test_notification"
        self._attr_name = "Test alert"
        self._attr_device_info = device_info(entry, coordinator.site_name)

    async def async_press(self) -> None:
        """Open a test alert."""
        await self.coordinator.async_test_panic()
