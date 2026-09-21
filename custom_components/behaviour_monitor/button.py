"""Buttons: acknowledge the open welfare alert; send a test notification."""

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
            AcknowledgeButton(coordinator, entry),
            TestNotificationButton(coordinator, entry),
        ]
    )


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


class TestNotificationButton(
    CoordinatorEntity[BehaviourMonitorCoordinator], ButtonEntity
):
    """Button that sends a test push through the real delivery path.

    Same as the test_panic service: a panic alert is delivered to the notify
    service and the persistent notification, then acknowledged at once, so
    nothing is left open and learned state is untouched.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:bell-ring"

    def __init__(
        self, coordinator: BehaviourMonitorCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_test_notification"
        self._attr_name = "Test notification"
        self._attr_device_info = device_info(entry, coordinator.site_name)

    async def async_press(self) -> None:
        """Send a test notification."""
        await self.coordinator.async_test_panic()
