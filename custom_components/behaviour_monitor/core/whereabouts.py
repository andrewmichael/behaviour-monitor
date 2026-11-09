"""Where she probably is, from the activity stream.

Each activity (presence, a door opening, an appliance turning on) starts a new
interval that lasts until the next one. The state, room and TV flag are fixed
when the interval starts, so a TV switched off later neither resets stillness
nor shortens the allowance. Lights and generic events are left out on purpose:
automations switch lights and would keep resetting the clock, hiding a fall.

An outside door is the one exception to "fixed at the start": whether she went
out depends on what happens in the next ten minutes, so that interval reads as
``HOME`` until it has been quiet that long and ``OUT`` afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from .events import ActivityEvent, EventKind


class Where(str, Enum):
    """Where she is taken to be."""

    HOME = "home"
    HOME_TV = "home_tv"
    ASLEEP = "asleep"
    LYING_IN = "lying_in"
    OUT = "out"


@dataclass(frozen=True)
class WhereaboutsConfig:
    """Fixed values (minutes, or minutes after midnight for times of day)."""

    # Door then movement: quiet this long after an outside door means she left.
    out_after_min: float = 10.0
    # Presence in the door's own room this soon is her walking out.
    door_room_ignore_min: float = 2.0
    # Stillness allowances.
    home_floor_min: float = 45.0
    home_cap_min: float = 60.0
    tv_allowance_min: float = 90.0
    lie_in_allowance_min: float = 90.0
    not_up_offset_min: float = 60.0
    outing_factor: float = 1.25
    # Night used until learning completes.
    night_start_min: int = 20 * 60
    night_end_min: int = 5 * 60
    lie_in_end_min: int = 11 * 60
    # Chosen entities and rooms.
    outside_doors: frozenset[str] = frozenset()
    sitting_appliances: frozenset[str] = frozenset()
    # None: rooms whose name contains "bedroom". Empty: none chosen, so the
    # night rules apply to every room.
    bedrooms: frozenset[str] | None = None


@dataclass(frozen=True)
class Interval:
    """A stretch of stillness that began with one activity."""

    start: datetime
    where: Where
    room: str | None
    tv: bool
    door: str | None = None


def _in_window(minute: int, begin: int, end: int) -> bool:
    """True when ``minute`` is in [begin, end), wrapping midnight."""
    if begin <= end:
        return begin <= minute < end
    return minute >= begin or minute < end


class Whereabouts:
    """State machine over the activity stream."""

    def __init__(self, config: WhereaboutsConfig) -> None:
        self._cfg = config
        self._interval: Interval | None = None
        self._door_room: str | None = None
        self._last_room: str | None = None
        self._tvs_on: dict[str, str] = {}

    # Task 2 swaps these for learned values.
    def night_start(self) -> int:
        """Minutes after midnight when the night begins."""
        return self._cfg.night_start_min

    def night_end(self) -> int:
        """Minutes after midnight when the night ends."""
        return self._cfg.night_end_min

    def lie_in_end(self) -> int:
        """Minutes after midnight when the lie-in ends."""
        return self._cfg.lie_in_end_min

    def is_bedroom(self, room: str | None) -> bool:
        """Whether the night rules apply to ``room``."""
        beds = self._cfg.bedrooms
        if beds is not None and not beds:
            return True
        if room is None:
            return False
        if beds is None:
            return "bedroom" in room.lower()
        return room in beds

    def record(self, ev: ActivityEvent) -> None:
        """Feed one event; only presence, open and appliance events start intervals."""
        if self._interval is not None and ev.timestamp < self._interval.start:
            return
        sitting = ev.entity_id in self._cfg.sitting_appliances
        if ev.kind is EventKind.APPLIANCE_OFF:
            if sitting:
                self._tvs_on.pop(ev.entity_id, None)
            return
        if ev.kind not in (
            EventKind.PRESENCE,
            EventKind.OPEN,
            EventKind.APPLIANCE_ON,
        ):
            return
        iv = self._interval
        if (
            ev.kind is EventKind.PRESENCE
            and iv is not None
            and iv.door is not None
            and ev.room == self._door_room
            and ev.timestamp - iv.start
            < timedelta(minutes=self._cfg.door_room_ignore_min)
        ):
            return
        if ev.kind is EventKind.APPLIANCE_ON and sitting:
            self._tvs_on[ev.entity_id] = ev.room
        if ev.kind is not EventKind.OPEN:
            self._last_room = ev.room
        if ev.kind is EventKind.OPEN and ev.entity_id in self._cfg.outside_doors:
            self._door_room = ev.room
            self._interval = Interval(
                ev.timestamp,
                Where.HOME,
                self._last_room,
                self._tv_on_in(self._last_room),
                ev.entity_id,
            )
            return
        self._door_room = None
        tv = self._tv_on_in(self._last_room)
        self._interval = Interval(
            ev.timestamp,
            self._classify(ev.timestamp, self._last_room, tv),
            self._last_room,
            tv,
        )

    def current(self, now: datetime) -> Interval | None:
        """The interval in force at ``now``, or None before any activity."""
        iv = self._interval
        if iv is None:
            return None
        if iv.door is not None and now - iv.start >= timedelta(
            minutes=self._cfg.out_after_min
        ):
            return replace(iv, where=Where.OUT)
        return iv

    def _tv_on_in(self, room: str | None) -> bool:
        return room is not None and room in self._tvs_on.values()

    def _classify(self, start: datetime, room: str | None, tv: bool) -> Where:
        if self.is_bedroom(room):
            minute = start.hour * 60 + start.minute
            if _in_window(minute, self.night_start(), self.night_end()):
                return Where.ASLEEP
            if _in_window(minute, self.night_end(), self.lie_in_end()):
                return Where.LYING_IN
        return Where.HOME_TV if tv else Where.HOME
