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


class PanicMonitor:
    """Track pressed panic buttons, acknowledgement, and re-notification timing."""

    def __init__(self) -> None:
        self._states: dict[str, _PanicState] = {}

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
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            eid: {
                "active_since": s.active_since.isoformat(),
                "last_notified": s.last_notified.isoformat(),
                "acknowledged": s.acknowledged,
            }
            for eid, s in self._states.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PanicMonitor:
        monitor = cls()
        if not isinstance(data, dict):
            return monitor
        for eid, raw in data.items():
            if not isinstance(raw, dict):
                continue
            try:
                since = datetime.fromisoformat(raw["active_since"])
                notified = datetime.fromisoformat(raw["last_notified"])
            except (KeyError, TypeError, ValueError):
                continue
            monitor._states[eid] = _PanicState(
                active_since=since,
                last_notified=notified,
                acknowledged=bool(raw.get("acknowledged", False)),
            )
        return monitor
