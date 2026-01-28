"""Sensor platform for Behaviour Monitor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ANOMALY_DETAILS,
    ATTR_CROSS_SENSOR_PATTERNS,
    ATTR_LAST_RETRAIN,
    ATTR_LEARNING_PROGRESS,
    ATTR_ML_STATUS,
    ATTR_MONITORED_ENTITIES,
    DOMAIN,
)
from .coordinator import BehaviourMonitorCoordinator


@dataclass(frozen=True, kw_only=True)
class BehaviourMonitorSensorDescription(SensorEntityDescription):
    """Describes a Behaviour Monitor sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    extra_attrs_fn: Callable[[BehaviourMonitorCoordinator, dict[str, Any]], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[BehaviourMonitorSensorDescription, ...] = (
    BehaviourMonitorSensorDescription(
        key="last_activity",
        name="Last Activity",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: (
            datetime.fromisoformat(data["last_activity"])
            if data.get("last_activity")
            else None
        ),
    ),
    BehaviourMonitorSensorDescription(
        key="activity_score",
        name="Activity Score",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        value_fn=lambda data: round(data.get("activity_score", 0), 1),
    ),
    BehaviourMonitorSensorDescription(
        key="anomaly_detected",
        name="Anomaly Detected",
        icon="mdi:alert-circle",
        value_fn=lambda data: "on" if data.get("anomaly_detected", False) else "off",
        extra_attrs_fn=lambda coord, data: {
            ATTR_ANOMALY_DETAILS: data.get("anomalies", []),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="baseline_confidence",
        name="Baseline Confidence",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:brain",
        value_fn=lambda data: round(data.get("confidence", 0), 1),
        extra_attrs_fn=lambda coord, data: {
            ATTR_LEARNING_PROGRESS: (
                "complete" if coord.analyzer.is_learning_complete() else "learning"
            ),
            ATTR_ML_STATUS: data.get("ml_status", {}),
            ATTR_LAST_RETRAIN: data.get("ml_status", {}).get("last_trained"),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="daily_activity_count",
        name="Daily Activity Count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=lambda data: data.get("daily_count", 0),
        extra_attrs_fn=lambda coord, data: {
            ATTR_MONITORED_ENTITIES: list(coord.monitored_entities),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="cross_sensor_patterns",
        name="Cross-Sensor Patterns",
        icon="mdi:relation-many-to-many",
        value_fn=lambda data: len(data.get("cross_sensor_patterns", [])),
        extra_attrs_fn=lambda coord, data: {
            ATTR_CROSS_SENSOR_PATTERNS: data.get("cross_sensor_patterns", []),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Behaviour Monitor sensors."""
    coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        BehaviourMonitorSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


class BehaviourMonitorSensor(
    CoordinatorEntity[BehaviourMonitorCoordinator], SensorEntity
):
    """Representation of a Behaviour Monitor sensor."""

    entity_description: BehaviourMonitorSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BehaviourMonitorCoordinator,
        entry: ConfigEntry,
        description: BehaviourMonitorSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Behaviour Monitor",
            manufacturer="Custom Integration",
            model="Pattern Analyzer",
            sw_version="2.0.0",
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if self.entity_description.extra_attrs_fn is None:
            return None
        if self.coordinator.data is None:
            return None
        return self.entity_description.extra_attrs_fn(
            self.coordinator, self.coordinator.data
        )
