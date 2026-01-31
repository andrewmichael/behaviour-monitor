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
    ATTR_ENTITY_STATUS,
    ATTR_EXPECTED_BY_NOW,
    ATTR_LAST_RETRAIN,
    ATTR_LEARNING_PROGRESS,
    ATTR_ML_STATUS,
    ATTR_MONITORED_ENTITIES,
    ATTR_TIME_SINCE_ACTIVITY,
    ATTR_TYPICAL_INTERVAL,
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
    BehaviourMonitorSensorDescription(
        key="ml_status",
        name="ML Status",
        icon="mdi:brain",
        value_fn=lambda data: (
            # Check if fully ready (both samples AND learning period complete)
            "Ready" if data.get("ml_training", {}).get("complete", False)
            # Model has samples but learning period not elapsed
            else "Trained (learning)" if data.get("ml_status", {}).get("trained", False)
            # Still collecting samples
            else "Learning" if data.get("ml_status", {}).get("enabled", False)
            else "Disabled"
        ),
        extra_attrs_fn=lambda coord, data: {
            "enabled": data.get("ml_status", {}).get("enabled", False),
            "trained": data.get("ml_status", {}).get("trained", False),
            "ready": data.get("ml_training", {}).get("complete", False),
            "sample_count": data.get("ml_status", {}).get("sample_count", 0),
            "samples_needed": max(0, 100 - data.get("ml_status", {}).get("sample_count", 0)),
            "learning_period_complete": data.get("ml_training", {}).get("days_remaining", 1) == 0,
            "last_trained": data.get("ml_status", {}).get("last_trained"),
            "next_retrain": data.get("ml_status", {}).get("next_retrain"),
            "ml_available": coord.ml_analyzer.ml_available if coord else False,
        },
    ),
    # Elder Care Sensors
    BehaviourMonitorSensorDescription(
        key="welfare_status",
        name="Welfare Status",
        icon="mdi:heart-pulse",
        value_fn=lambda data: data.get("welfare", {}).get("status", "unknown"),
        extra_attrs_fn=lambda coord, data: {
            "reasons": data.get("welfare", {}).get("reasons", []),
            "summary": data.get("welfare", {}).get("summary", ""),
            "recommendation": data.get("welfare", {}).get("recommendation", ""),
            "entity_count_by_status": data.get("welfare", {}).get("entity_count_by_status", {}),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="routine_progress",
        name="Routine Progress",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:progress-check",
        value_fn=lambda data: data.get("routine", {}).get("progress_percent", 0),
        extra_attrs_fn=lambda coord, data: {
            ATTR_EXPECTED_BY_NOW: data.get("routine", {}).get("expected_by_now", 0),
            "actual_today": data.get("routine", {}).get("actual_today", 0),
            "expected_full_day": data.get("routine", {}).get("expected_full_day", 0),
            "status": data.get("routine", {}).get("status", "unknown"),
            "summary": data.get("routine", {}).get("summary", ""),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="time_since_activity",
        name="Time Since Activity",
        icon="mdi:clock-alert-outline",
        value_fn=lambda data: data.get("activity_context", {}).get("time_since_formatted", "Unknown"),
        extra_attrs_fn=lambda coord, data: {
            ATTR_TIME_SINCE_ACTIVITY: data.get("activity_context", {}).get("time_since_seconds"),
            ATTR_TYPICAL_INTERVAL: data.get("activity_context", {}).get("typical_interval_seconds"),
            "typical_interval_formatted": data.get("activity_context", {}).get("typical_interval_formatted", ""),
            "concern_level": data.get("activity_context", {}).get("concern_level", 0),
            "status": data.get("activity_context", {}).get("status", "unknown"),
            "context": data.get("activity_context", {}).get("context", ""),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="entity_status_summary",
        name="Entity Status Summary",
        icon="mdi:format-list-checks",
        value_fn=lambda data: (
            f"{data.get('welfare', {}).get('entity_count_by_status', {}).get('normal', 0)} OK, "
            f"{data.get('welfare', {}).get('entity_count_by_status', {}).get('attention', 0) + data.get('welfare', {}).get('entity_count_by_status', {}).get('concern', 0) + data.get('welfare', {}).get('entity_count_by_status', {}).get('alert', 0)} Need Attention"
        ),
        extra_attrs_fn=lambda coord, data: {
            ATTR_ENTITY_STATUS: data.get("entity_status", []),
        },
    ),
    # Training Time Remaining Sensors
    BehaviourMonitorSensorDescription(
        key="statistical_training_remaining",
        name="Statistical Training Remaining",
        icon="mdi:timer-sand",
        value_fn=lambda data: data.get("stat_training", {}).get("formatted", "Unknown"),
        extra_attrs_fn=lambda coord, data: {
            "complete": data.get("stat_training", {}).get("complete", False),
            "days_remaining": data.get("stat_training", {}).get("days_remaining"),
            "days_elapsed": data.get("stat_training", {}).get("days_elapsed"),
            "total_days": data.get("stat_training", {}).get("total_days"),
            "first_observation": data.get("stat_training", {}).get("first_observation"),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="ml_training_remaining",
        name="ML Training Remaining",
        icon="mdi:timer-sand",
        value_fn=lambda data: data.get("ml_training", {}).get("formatted", "Unknown"),
        extra_attrs_fn=lambda coord, data: {
            "complete": data.get("ml_training", {}).get("complete", False),
            "status": data.get("ml_training", {}).get("status"),
            "days_remaining": data.get("ml_training", {}).get("days_remaining"),
            "days_elapsed": data.get("ml_training", {}).get("days_elapsed"),
            "total_days": data.get("ml_training", {}).get("total_days"),
            "samples_remaining": data.get("ml_training", {}).get("samples_remaining"),
            "samples_processed": data.get("ml_training", {}).get("samples_processed"),
            "samples_needed": data.get("ml_training", {}).get("samples_needed"),
            "first_event": data.get("ml_training", {}).get("first_event"),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="last_notification",
        name="Last Notification",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:bell-ring",
        value_fn=lambda data: (
            datetime.fromisoformat(data["last_notification"]["timestamp"])
            if data.get("last_notification", {}).get("timestamp")
            else None
        ),
        extra_attrs_fn=lambda coord, data: {
            "type": data.get("last_notification", {}).get("type"),
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
            sw_version="2.6.0",
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
