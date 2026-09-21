"""Sensor platform reading the Engine snapshot."""

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

from .const import DOMAIN, VERSION
from .coordinator import BehaviourMonitorCoordinator


def device_info(entry: ConfigEntry, site: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=site,
        manufacturer="Behaviour Monitor",
        model="Welfare core",
        sw_version=VERSION,
    )


def _disp(data: dict[str, Any], room: str | None) -> str | None:
    return data.get("display_rooms", {}).get(room, room) if room else room


def _render(data: dict[str, Any], text: str) -> str:
    for full, short in sorted(
        data.get("display_rooms", {}).items(), key=lambda kv: -len(kv[0])
    ):
        text = text.replace(full, short)
    return text


def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class BehaviourMonitorSensorDescription(SensorEntityDescription):
    """Describes a Behaviour Monitor sensor."""

    value_fn: Callable[[dict[str, Any]], Any] = None  # type: ignore[assignment]
    extra_attrs_fn: Callable[[Any, dict[str, Any]], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[BehaviourMonitorSensorDescription, ...] = (
    BehaviourMonitorSensorDescription(
        key="welfare_status",
        name="Welfare Status",
        icon="mdi:heart-pulse",
        value_fn=lambda d: d.get("welfare", {}).get("status", "unknown"),
        extra_attrs_fn=lambda c, d: {
            "reasons": [_render(d, r) for r in d.get("welfare", {}).get("reasons", [])],
            "open_alerts": d.get("welfare", {}).get("open_alerts", []),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="house_activity",
        name="House Activity",
        icon="mdi:home-clock",
        native_unit_of_measurement="s",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (
            int(g) if (g := d.get("house", {}).get("gap_s")) is not None else None
        ),
        extra_attrs_fn=lambda c, d: {
            "last_room": _disp(d, d.get("house", {}).get("last_room")),
            "expected_gap_s": d.get("house", {}).get("expected_s"),
            "rooms_today": [
                _disp(d, r) for r in d.get("house", {}).get("rooms_today", [])
            ],
        },
    ),
    BehaviourMonitorSensorDescription(
        key="anomaly",
        name="Anomaly",
        icon="mdi:chart-bell-curve",
        value_fn=lambda d: len(d.get("anomalies", [])),
        extra_attrs_fn=lambda c, d: {"anomalies": d.get("anomalies", [])},
    ),
    BehaviourMonitorSensorDescription(
        key="device_health",
        name="Device Health",
        icon="mdi:stethoscope",
        value_fn=lambda d: (
            "unavailable"
            if "unavailable" in (s := d.get("health", {}).get("states", {})).values()
            else "silent" if "silent" in s.values() else "ok"
        ),
        extra_attrs_fn=lambda c, d: {
            "states": d.get("health", {}).get("states", {}),
            "dropouts_today": d.get("health", {}).get("dropouts_today", 0),
            "alerts": d.get("health", {}).get("alerts", []),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="learning",
        name="Learning",
        icon="mdi:brain",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("learning", {}).get("confidence", 0.0),
        extra_attrs_fn=lambda c, d: {
            k: v for k, v in d.get("learning", {}).items() if k != "confidence"
        },
    ),
    BehaviourMonitorSensorDescription(
        key="entity_status",
        name="Entity Status",
        icon="mdi:format-list-checks",
        value_fn=lambda d: (
            f"{len(e := d.get('entities', {}))} monitored, "
            f"{sum(1 for v in e.values() if v.get('health') != 'ok')} down"
        ),
        extra_attrs_fn=lambda c, d: {
            "entities": {
                eid: {**v, "room": _disp(d, v.get("room"))}
                for eid, v in d.get("entities", {}).items()
            },
            "chains": d.get("chains", []),
        },
    ),
    BehaviourMonitorSensorDescription(
        key="last_activity",
        name="Last Activity",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _ts(d.get("house", {}).get("last_activity")),
    ),
    BehaviourMonitorSensorDescription(
        key="daily_activity_count",
        name="Daily Activity Count",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.get("house", {}).get("daily_count", 0),
    ),
    BehaviourMonitorSensorDescription(
        key="last_notification",
        name="Last Notification",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:bell-ring",
        value_fn=lambda d: _ts(d.get("last_notification", {}).get("timestamp")),
        extra_attrs_fn=lambda c, d: {
            "kind": d.get("last_notification", {}).get("kind")
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
    async_add_entities(
        [BehaviourMonitorSensor(coordinator, entry, d) for d in SENSOR_DESCRIPTIONS]
    )


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
        self._attr_device_info = device_info(entry, coordinator.site_name)

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return (
            None
            if self.coordinator.data is None
            else self.entity_description.value_fn(self.coordinator.data)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if (
            self.entity_description.extra_attrs_fn is None
            or self.coordinator.data is None
        ):
            return None
        return self.entity_description.extra_attrs_fn(
            self.coordinator, self.coordinator.data
        )
