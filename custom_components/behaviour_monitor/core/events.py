"""Typed events produced by the normaliser and consumed by every model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Category(str, Enum):
    """User-assigned entity category."""

    MOTION = "motion"
    CONTACT = "contact"
    PLUG = "plug"
    PANIC = "panic"
    LIGHT = "light"
    OTHER = "other"


class EventKind(str, Enum):
    """What a state change meant, per category rules."""

    PRESENCE = "presence"
    BURST_END = "burst_end"
    OPEN = "open"
    CLOSE = "close"
    APPLIANCE_ON = "appliance_on"
    APPLIANCE_OFF = "appliance_off"
    PANIC = "panic"
    PANIC_RELEASE = "panic_release"
    LIGHT_ON = "light_on"
    LIGHT_OFF = "light_off"
    GENERIC = "generic"


ACTIVITY_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.PRESENCE,
        EventKind.OPEN,
        EventKind.APPLIANCE_ON,
        EventKind.LIGHT_ON,
        EventKind.GENERIC,
    }
)
"""Kinds that count as the person doing something."""

UNAVAILABLE_STATES: frozenset[str] = frozenset({"unavailable", "unknown"})


@dataclass(frozen=True)
class ActivityEvent:
    """A category-aware event derived from one state change."""

    entity_id: str
    category: Category
    kind: EventKind
    room: str
    timestamp: datetime
    duration_s: float | None = None
    bypass: bool = False

    @property
    def is_activity(self) -> bool:
        """True when this event is evidence of the occupant acting."""
        return self.kind in ACTIVITY_KINDS


@dataclass(frozen=True)
class HealthEvent:
    """An availability transition for a monitored entity."""

    entity_id: str
    category: Category
    room: str
    timestamp: datetime
    available: bool
