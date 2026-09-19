"""Panic button state machine.

Pure Python stdlib only. Zero Home Assistant imports. The coordinator owns one
instance, feeds it press/release transitions and the current time, and asks it
which entities are active and which are due for re-notification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class _PanicState:
    active_since: datetime
    last_notified: datetime
    acknowledged: bool = False


@dataclass
class _DeviceState:
    available: bool = False
    last_reported: datetime | None = None
    battery: float | None = None
    last_test: datetime | None = None
    test_window_until: datetime | None = None  # not persisted


def _fmt(delta: timedelta) -> str:
    """Short human duration: '3d', '24h', '45m'."""
    secs = int(delta.total_seconds())
    if secs > 86400:
        return f"{secs // 86400}d"
    if secs >= 3600:
        return f"{secs // 3600}h"
    return f"{max(1, secs // 60)}m"


class PanicMonitor:
    """Track pressed panic buttons, acknowledgement, and re-notification timing."""

    def __init__(self) -> None:
        self._states: dict[str, _PanicState] = {}
        self._devices: dict[str, _DeviceState] = {}

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def press(self, entity_id: str, now: datetime) -> bool:
        """Mark the entity active. Returns True only for a new activation."""
        if entity_id in self._states:
            return False
        self._states[entity_id] = _PanicState(active_since=now, last_notified=now)
        return True

    def release(self, entity_id: str) -> None:
        """Clear the entity entirely, including any acknowledgement."""
        self._states.pop(entity_id, None)

    def acknowledge(self, now: datetime, entity_id: str | None = None) -> list[str]:
        """Acknowledge one entity or all active ones. Returns ids newly acknowledged."""
        targets = [entity_id] if entity_id is not None else list(self._states)
        changed: list[str] = []
        for eid in targets:
            state = self._states.get(eid)
            if state is not None and not state.acknowledged:
                state.acknowledged = True
                changed.append(eid)
        return changed

    def due(self, now: datetime, interval: timedelta) -> list[str]:
        """Return unacknowledged entities due for re-notification and stamp them."""
        result: list[str] = []
        for eid, state in self._states.items():
            if state.acknowledged:
                continue
            if now - state.last_notified >= interval:
                state.last_notified = now
                result.append(eid)
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def active(self) -> list[tuple[str, datetime, bool]]:
        """(entity_id, active_since, acknowledged) for every active entity, oldest first."""
        return sorted(
            ((eid, s.active_since, s.acknowledged) for eid, s in self._states.items()),
            key=lambda item: item[1],
        )

    def is_active(self, entity_id: str) -> bool:
        return entity_id in self._states

    def active_since(self, entity_id: str) -> datetime | None:
        state = self._states.get(entity_id)
        return state.active_since if state is not None else None

    def unacknowledged(self) -> list[str]:
        return [eid for eid, _, acked in self.active() if not acked]

    # ------------------------------------------------------------------
    # Device liveness
    # ------------------------------------------------------------------

    def update_device(
        self,
        entity_id: str,
        *,
        available: bool,
        last_reported: datetime | None,
        battery: float | None,
    ) -> None:
        d = self._devices.setdefault(entity_id, _DeviceState())
        d.available = available
        d.last_reported = last_reported
        d.battery = battery

    def known_devices(self) -> list[str]:
        return sorted(self._devices)

    def device_status(self, entity_id: str) -> dict[str, Any]:
        d = self._devices.get(entity_id, _DeviceState())
        return {
            "available": d.available,
            "last_reported": d.last_reported.isoformat() if d.last_reported else None,
            "battery": d.battery,
            "last_test": d.last_test.isoformat() if d.last_test else None,
        }

    def open_test_window(
        self, now: datetime, until: datetime, entity_id: str | None = None
    ) -> list[str]:
        """Open a test-press window for one known device or all. Returns ids opened."""
        targets = [entity_id] if entity_id is not None else list(self._devices)
        opened: list[str] = []
        for eid in targets:
            d = self._devices.get(eid)
            if d is None:
                continue
            d.test_window_until = until
            opened.append(eid)
        return opened

    def in_test_window(self, entity_id: str, now: datetime) -> bool:
        d = self._devices.get(entity_id)
        return (
            d is not None
            and d.test_window_until is not None
            and now < d.test_window_until
        )

    def record_test(self, entity_id: str, now: datetime) -> None:
        d = self._devices.setdefault(entity_id, _DeviceState())
        d.last_test = now
        d.test_window_until = None

    def device_alerts(
        self,
        now: datetime,
        heartbeat: timedelta | None,
        reminder: timedelta | None,
        low_battery: float,
    ) -> list[tuple[str, str, str, str]]:
        """(entity_id, kind, severity, message) for every device-health condition.

        kind ∈ {unavailable, heartbeat, battery, test_reminder}; severity ∈ {low, medium, high}.
        ``heartbeat``/``reminder`` of None disable those checks.
        """
        out: list[tuple[str, str, str, str]] = []
        for eid in sorted(self._devices):
            d = self._devices[eid]
            if not d.available:
                out.append(
                    (eid, "unavailable", "high", f"panic button {eid} is unavailable")
                )
            if heartbeat is not None:
                if d.last_reported is None:
                    out.append(
                        (
                            eid,
                            "heartbeat",
                            "high",
                            f"panic button {eid} has never reported",
                        )
                    )
                elif now - d.last_reported >= heartbeat:
                    out.append(
                        (
                            eid,
                            "heartbeat",
                            "high",
                            f"panic button {eid} has not reported for {_fmt(now - d.last_reported)}",
                        )
                    )
            if d.battery is not None and d.battery <= low_battery:
                out.append(
                    (
                        eid,
                        "battery",
                        "medium",
                        f"panic button {eid} battery at {int(d.battery)}%",
                    )
                )
            if reminder is not None:
                if d.last_test is None:
                    out.append(
                        (
                            eid,
                            "test_reminder",
                            "low",
                            f"panic button {eid} has never been test-pressed",
                        )
                    )
                elif now - d.last_test >= reminder:
                    out.append(
                        (
                            eid,
                            "test_reminder",
                            "low",
                            f"panic button {eid} has not been test-pressed for {_fmt(now - d.last_test)}",
                        )
                    )
        return out

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": {
                eid: {
                    "active_since": s.active_since.isoformat(),
                    "last_notified": s.last_notified.isoformat(),
                    "acknowledged": s.acknowledged,
                }
                for eid, s in self._states.items()
            },
            "devices": {
                eid: {
                    "available": d.available,
                    "last_reported": (
                        d.last_reported.isoformat() if d.last_reported else None
                    ),
                    "battery": d.battery,
                    "last_test": d.last_test.isoformat() if d.last_test else None,
                }
                for eid, d in self._devices.items()
            },
        }

    @staticmethod
    def _parse(value: Any) -> datetime | None:
        try:
            return datetime.fromisoformat(value) if isinstance(value, str) else None
        except ValueError:
            return None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PanicMonitor:
        monitor = cls()
        if not isinstance(data, dict):
            return monitor
        # Legacy (v5.1) flat shape: {eid: {active_since, ...}}
        legacy = "active" not in data and "devices" not in data
        active_raw = data if legacy else data.get("active", {})
        if isinstance(active_raw, dict):
            for eid, raw in active_raw.items():
                if not isinstance(raw, dict):
                    continue
                since = cls._parse(raw.get("active_since"))
                notified = cls._parse(raw.get("last_notified"))
                if since is None or notified is None:
                    continue
                monitor._states[eid] = _PanicState(
                    active_since=since,
                    last_notified=notified,
                    acknowledged=bool(raw.get("acknowledged", False)),
                )
        devices_raw = {} if legacy else data.get("devices", {})
        if isinstance(devices_raw, dict):
            for eid, raw in devices_raw.items():
                if not isinstance(raw, dict):
                    continue
                battery = raw.get("battery")
                monitor._devices[eid] = _DeviceState(
                    available=bool(raw.get("available", False)),
                    last_reported=cls._parse(raw.get("last_reported")),
                    battery=(
                        float(battery) if isinstance(battery, (int, float)) else None
                    ),
                    last_test=cls._parse(raw.get("last_test")),
                )
        return monitor
