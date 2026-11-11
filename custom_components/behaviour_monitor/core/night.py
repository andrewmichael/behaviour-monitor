"""Night: when the house has gone to bed, long night trips and night doors.

Night starts when someone goes up (day-room activity, then night-room
activity within a few minutes), the downstairs then stays quiet with no
sitting appliance on, and that going-up lies inside the learned night. It
ends at the first day-room activity at or after the learned night end.

A night trip starts only after a coming-down: night-room activity a few
minutes before its first day-room activity. Day-room activity without one
means someone was still downstairs (a partner reading quietly, say): the
night is cancelled unrecorded and bedtime is looked for again from there.
The cancel waits ``came_down_grace_min`` first: a bedroom sensor's burst
end, sent after its debounce, can arrive after the downstairs motion it
preceded and still be the coming-down.

During the night only motion counts as day-room activity for trips and
for cancelling; an appliance or light switching does not. A night-room
burst end can be the coming-down.

An outside door opening during the night pushes at once, unless the house
was out or a door at that hour is normal for the house. It clears at
night-room activity after it, at the night's end, or after
``unusual_ttl_min``, and it outlives a cancelled night.

All bounds come from ``Whereabouts.night_start()`` and ``night_end()``;
everything else is event sequence. Elapsed times use UTC subtraction so
they stay right across a clock change; times of day use local wall time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent, EventKind
from .slots import iso_day
from .whereabouts import Whereabouts

if TYPE_CHECKING:
    from .unusual import UnusualConfig

_NOON = 720
# During the night only these are evidence of someone downstairs.
_MOTION = (EventKind.PRESENCE, EventKind.BURST_END)
_DAY_MIN = 1440


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _since(later: datetime, earlier: datetime) -> float:
    """Minutes from ``earlier`` to ``later``, correct across a clock change."""
    return (_utc(later) - _utc(earlier)).total_seconds() / 60


def _after(a: datetime, b: datetime) -> bool:
    return _utc(a) > _utc(b)


def _minute(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


def _from_noon(minute: int) -> int:
    return (minute - _NOON) % _DAY_MIN


def _night_key(ts: datetime) -> date:
    """The evening a moment belongs to: before noon is the previous evening."""
    day = ts.date()
    return day - timedelta(days=1) if _minute(ts) < _NOON else day


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("timestamps must be ISO strings")
    return datetime.fromisoformat(value)


def _iso(ts: datetime | None) -> str | None:
    return None if ts is None else ts.isoformat()


@dataclass
class _NightRecord:
    trip: float
    doors: list[int]


class NightWatch:
    """Tracks the night in progress and learns what is normal at night."""

    def __init__(self, config: UnusualConfig) -> None:
        self._cfg = config
        # Going up, outside night.
        self._last_day_at: datetime | None = None
        self._went_up_at: datetime | None = None
        # The latest night-room activity, in or out of night.
        self._last_night_at: datetime | None = None
        # The latest night-room burst end in the night, for coming down only.
        self._night_burst_at: datetime | None = None
        self._night_burst_rise: datetime | None = None
        # The night in progress.
        self.night_since: datetime | None = None
        self._trip_start: datetime | None = None
        self._trip_last_day: datetime | None = None
        self._trip_up_at: datetime | None = None
        self._trip_room: str = ""
        self._door_at: datetime | None = None
        self._door_entity: str | None = None
        # Downstairs motion with no coming-down yet: when it began, its
        # latest time and room, and night-room activity seen after it.
        self._pending_at: datetime | None = None
        self._pending_last: datetime | None = None
        self._pending_room: str = ""
        self._pending_up: datetime | None = None
        self._trip_max: float = 0.0
        self._doors: list[int] = []
        # Finalised nights, keyed by the evening's ISO date.
        self._nights: dict[str, _NightRecord] = {}

    # ------------------------------------------------------------ learning

    def _night_room(self, room: str | None, where: Whereabouts) -> bool:
        return where.is_bedroom(room) or (
            room is not None and room in self._cfg.upstairs
        )

    def _activity_at(self, ev: ActivityEvent, where: Whereabouts) -> datetime | None:
        """When ``ev`` shows someone active, or None if it doesn't.

        A burst end counts at its fall, but no later than the burst's last
        rise plus ``burst_activity_max_min``, as in ``Whereabouts``: a held-on
        motion sensor sends one presence and then only its burst end.
        """
        if ev.kind is EventKind.BURST_END:
            rise = ev.last_rise or ev.timestamp
            cap = _utc(rise) + timedelta(minutes=where.burst_activity_max_min)
            if _utc(ev.timestamp) <= cap:
                return ev.timestamp
            return cap.astimezone(ev.timestamp.tzinfo)
        return ev.timestamp if ev.is_activity else None

    def _went_up(self, night_at: datetime, day_at: datetime | None) -> bool:
        """Night-room activity this soon after day-room activity: going up."""
        return (
            day_at is not None
            and 0 <= _since(night_at, day_at) <= self._cfg.went_up_within_min
        )

    def record(self, ev: ActivityEvent, where: Whereabouts) -> None:
        """Feed one event, before ``where`` records it."""
        ts = self._activity_at(ev, where)
        if ts is None:
            return
        self._advance(ts, where)
        door = ev.kind is EventKind.OPEN and ev.entity_id in where.outside_doors
        night_room = not door and self._night_room(ev.room, where)
        if ev.kind is EventKind.BURST_END and night_room:
            # Not evidence of being downstairs, but a bedroom sensor held on
            # until someone gets up falls as they leave: during the night it
            # can be the coming-down, and nothing else.
            if self.night_since is not None and _after(ts, self.night_since):
                rise = ev.last_rise or ev.timestamp
                if self._night_burst_at is None or _after(ts, self._night_burst_at):
                    self._night_burst_at, self._night_burst_rise = ts, rise
                self._pending_came_down(ts, rise)
            return
        day_room = not door and not night_room
        if night_room and self._door_at is not None and _after(ts, self._door_at):
            self._clear_door()  # someone is back in a night room
        if (
            self.night_since is not None
            and not night_room
            and self._is_morning(ts, where)
        ):
            self._end_night()
        if self.night_since is None:
            if day_room:
                self._day_outside_night(ts)
            elif night_room:
                self._last_night_at = ts
                if self._went_up_at is None and self._went_up(ts, self._last_day_at):
                    self._went_up_at = ts
            return
        if not _after(ts, self.night_since):
            return  # a late burst end from before the night began
        if day_room and ev.kind not in _MOTION:
            # During the night only motion is someone downstairs: a TV's
            # standby wake or an automated light must not start a trip or
            # cancel the night.
            return
        if day_room:
            burst = ev.kind is EventKind.BURST_END
            rise = (ev.last_rise or ev.timestamp) if burst else ts
            self._day_in_night(ts, ev.room, burst, rise)
        elif night_room:
            self._last_night_at = ts
            if self._trip_start is not None and self._went_up(ts, self._trip_last_day):
                self._trip_up_at = ts
            if self._pending_at is not None:
                if _after(ts, self._pending_at):
                    if self._pending_up is None or _after(ts, self._pending_up):
                        self._pending_up = ts
                else:
                    self._pending_came_down(ts, ts)
        elif not where.is_out(ts):
            # Owner's decision (third fix wave): the occupants are elderly and
            # the owner is remote, so a night door pushes straight away; a
            # late return is unlikely and a missed night event costs more.
            self._door_at = ts
            self._door_entity = ev.entity_id
            self._doors.append(ts.hour)

    def _day_outside_night(self, ts: datetime) -> None:
        if self._last_day_at is None or _after(ts, self._last_day_at):
            self._last_day_at = ts
        if self._went_up_at is not None and not _after(self._went_up_at, ts):
            self._went_up_at = None
        # A burst end can arrive after the night-room activity it preceded.
        if (
            self._went_up_at is None
            and self._last_night_at is not None
            and _after(self._last_night_at, ts)
            and self._went_up(self._last_night_at, self._last_day_at)
        ):
            self._went_up_at = self._last_night_at

    def _overlaps(self, rise: datetime, active: datetime, at: datetime) -> bool:
        """Night-room activity from ``rise`` to ``active`` reaches into the
        ``went_up_within_min`` before ``at``: a bedroom sensor still showing
        someone (it usually falls after they're downstairs) counts."""
        return not _after(rise, at) and (
            _since(at, active) <= self._cfg.went_up_within_min
        )

    def _came_down(self, at: datetime) -> bool:
        """Night-room activity this soon before ``at``: someone came down.

        A night-room burst end counts too, over its span from its last rise
        to its activity time.
        """
        last = self._last_night_at
        if last is not None and 0 <= _since(at, last) <= self._cfg.went_up_within_min:
            return True
        burst, rise = self._night_burst_at, self._night_burst_rise
        return burst is not None and self._overlaps(rise or burst, burst, at)

    def _cancel_night(self, ts: datetime) -> None:
        """Someone was still downstairs: no night yet, and none recorded.

        An open night door has already pushed, so it stays open.
        """
        door_at, door_entity = self._door_at, self._door_entity
        self.clear()
        self._door_at, self._door_entity = door_at, door_entity
        self._day_outside_night(ts)

    def _pending_came_down(self, at: datetime, rise: datetime) -> None:
        """Night-room activity from ``rise`` to ``at`` may be the pending
        motion's coming-down, delivered late: if so, the motion starts a
        trip."""
        start = self._pending_at
        if start is None or not self._overlaps(rise, at, start):
            return
        last, room, up = self._pending_last, self._pending_room, self._pending_up
        self._clear_pending()
        self._trip_start = start
        self._trip_last_day = last or start
        self._trip_room = room
        self._trip_up_at = None
        if up is not None and self._went_up(up, self._trip_last_day):
            self._trip_up_at = up

    def _clear_pending(self) -> None:
        self._pending_at = self._pending_last = self._pending_up = None
        self._pending_room = ""

    def _resolve_pending(self, now: datetime) -> None:
        """No coming-down arrived within the grace: cancel the night."""
        start = self._pending_at
        if start is None or _since(now, start) < self._cfg.came_down_grace_min:
            return
        last, up = self._pending_last or start, self._pending_up
        self._cancel_night(last)
        if up is not None and _after(up, last):
            # Night-room activity after the downstairs motion: maybe going up.
            self._last_night_at = up
            if self._went_up(up, self._last_day_at):
                self._went_up_at = up

    def _expire_door(self, now: datetime, where: Whereabouts) -> None:
        t = self._door_at
        if t is None:
            return
        morning = _night_key(t) + timedelta(days=1)
        if _since(now, t) >= self._cfg.unusual_ttl_min or (
            now.date(),
            _minute(now),
        ) >= (morning, where.night_end(morning)):
            self._clear_door()

    def _day_in_night(
        self, ts: datetime, room: str, burst: bool, rise: datetime
    ) -> None:
        last = self._trip_last_day
        if (
            not burst  # a burst end is motion held since its presence
            and self._trip_start is not None
            and last is not None
            and _since(ts, last) >= self._cfg.bedtime_quiet_min
        ):
            # Downstairs was quiet this long: they went back unseen, and
            # this is a new trip.
            self._close_trip()
        if self._trip_start is None:
            if (
                burst
                and self._last_night_at is not None
                and not _after(rise, self._last_night_at)
            ):
                return  # motion held since before the last going up
            if self._pending_at is not None:
                if _after(ts, self._pending_last or ts):
                    self._pending_last, self._pending_room = ts, room
                return
            if not self._came_down(rise):
                # Wait for a late night-room burst end before cancelling.
                self._pending_at = self._pending_last = ts
                self._pending_room = room
                self._pending_up = None
                return
            self._trip_start = ts
            self._trip_up_at = None
        if self._trip_last_day is None or _after(ts, self._trip_last_day):
            self._trip_last_day = ts
            self._trip_room = room
        if self._trip_up_at is not None and not _after(self._trip_up_at, ts):
            self._trip_up_at = None  # downstairs again: the same trip goes on
        if (
            self._trip_up_at is None
            and self._last_night_at is not None
            and _after(self._last_night_at, ts)
            and self._went_up(self._last_night_at, self._trip_last_day)
        ):
            self._trip_up_at = self._last_night_at

    def _clear_door(self) -> None:
        self._door_at = None
        self._door_entity = None

    def _is_morning(self, ts: datetime, where: Whereabouts) -> bool:
        assert self.night_since is not None
        morning = _night_key(self.night_since) + timedelta(days=1)
        end = where.night_end(morning)
        return (ts.date(), _minute(ts)) >= (morning, end)

    def _advance(self, now: datetime, where: Whereabouts) -> None:
        cfg = self._cfg
        self._expire_door(now, where)
        if self.night_since is not None:
            if _since(now, self.night_since) >= cfg.night_max_h * 60:
                self._end_night()
                return
            self._resolve_pending(now)
        if self.night_since is not None:
            if (
                self._trip_start is not None
                and self._trip_last_day is not None
                and self._trip_up_at is not None
                and _since(now, self._trip_last_day) >= cfg.trip_end_quiet_min
            ):
                self._close_trip()
            return
        up = self._went_up_at
        if up is None or _since(now, up) < cfg.bedtime_quiet_min:
            return
        if self._last_day_at is not None and _after(self._last_day_at, up):
            return
        if any(not self._night_room(r, where) for r in where.sitting_rooms()):
            return
        end = where.night_end(_night_key(up) + timedelta(days=1))
        if not (
            _from_noon(where.night_start()) <= _from_noon(_minute(up)) < _from_noon(end)
        ):
            return
        self.night_since = up
        self._went_up_at = None
        self._trip_max = 0.0
        self._doors = []

    def _close_trip(self) -> None:
        if self._trip_start is not None and self._trip_last_day is not None:
            length = _since(self._trip_last_day, self._trip_start)
            self._trip_max = max(self._trip_max, length)
        self._trip_start = self._trip_last_day = self._trip_up_at = None
        self._trip_room = ""

    def _end_night(self) -> None:
        """Finalise the night in progress under its evening's date."""
        assert self.night_since is not None
        self._close_trip()
        key = iso_day(_night_key(self.night_since))
        self._nights[key] = _NightRecord(
            round(self._trip_max, 1), sorted(set(self._doors))
        )
        self.clear()

    def clear(self) -> None:
        """Drop the night in progress; finalised nights are kept."""
        self._last_day_at = self._went_up_at = self.night_since = None
        self._last_night_at = None
        self._night_burst_at = self._night_burst_rise = None
        self._clear_pending()
        self._trip_start = self._trip_last_day = self._trip_up_at = None
        self._trip_room = ""
        self._clear_door()
        self._trip_max = 0.0
        self._doors = []

    def remove(self, entity_id: str) -> None:
        if self._door_entity == entity_id:
            self._clear_door()

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        self._nights = {k: r for k, r in self._nights.items() if k >= cutoff}

    # ---------------------------------------------------------- evaluation

    def _learned(self, now: datetime) -> list[_NightRecord]:
        hi = _night_key(now)
        lo = iso_day(hi - timedelta(days=self._cfg.window_days))
        return [r for k, r in self._nights.items() if lo <= k < iso_day(hi)]

    def evaluate(
        self, now: datetime, where: Whereabouts, names: Callable[[str], str]
    ) -> list[Alert]:
        """The night pushes open at ``now``."""
        cfg = self._cfg
        self._advance(now, where)
        learned = self._learned(now)
        if len(learned) < cfg.min_days:
            return []
        enough = cfg.night_normal_fraction * len(learned)
        out: list[Alert] = []
        start, last = self._trip_start, self._trip_last_day
        span = 0.0 if start is None or last is None else _since(last, start)
        if (
            self.night_since is not None
            and start is not None
            and span >= cfg.night_trip_min
        ):
            long_trips = sum(r.trip >= cfg.night_trip_min for r in learned)
            if long_trips <= enough:
                raised = _utc(start) + timedelta(minutes=cfg.night_trip_min)
                out.append(
                    Alert(
                        cls=AlertClass.WELFARE,
                        source="night",
                        kind="night_downstairs",
                        severity=Severity.MEDIUM,
                        explanation=(
                            "Someone has been downstairs for "
                            f"{int(span)} min during the night "
                            f"(since {start:%H:%M}, in the {self._trip_room})"
                        ),
                        raised_at=raised.astimezone(start.tzinfo),
                        details={"room": self._trip_room, "since": f"{start:%H:%M}"},
                    )
                )
        t = self._door_at
        if t is not None and self._door_entity is not None:
            h = t.hour
            near = sum(
                any((d - h) % 24 in (0, 1, 23) for d in r.doors) for r in learned
            )
            if near <= enough:
                out.append(
                    Alert(
                        cls=AlertClass.WELFARE,
                        source="night",
                        kind="night_door",
                        severity=Severity.MEDIUM,
                        explanation=(
                            f"{names(self._door_entity)} opened during the night "
                            f"at {t:%H:%M}"
                        ),
                        raised_at=t,
                        details={"door": self._door_entity, "at": f"{t:%H:%M}"},
                    )
                )
        return out

    # --------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_day_at": _iso(self._last_day_at),
            "went_up_at": _iso(self._went_up_at),
            "last_night_at": _iso(self._last_night_at),
            "night_burst_at": _iso(self._night_burst_at),
            "night_burst_rise": _iso(self._night_burst_rise),
            "night_since": _iso(self.night_since),
            "trip_start": _iso(self._trip_start),
            "trip_last_day": _iso(self._trip_last_day),
            "trip_up_at": _iso(self._trip_up_at),
            "trip_room": self._trip_room,
            "door_at": _iso(self._door_at),
            "door_entity": self._door_entity,
            "pending_at": _iso(self._pending_at),
            "pending_last": _iso(self._pending_last),
            "pending_room": self._pending_room,
            "pending_up": _iso(self._pending_up),
            "trip_max": self._trip_max,
            "doors": list(self._doors),
            "nights": {
                k: {"trip": r.trip, "doors": list(r.doors)}
                for k, r in sorted(self._nights.items())
            },
        }

    @classmethod
    def from_dict(cls, data: Any, config: UnusualConfig) -> "NightWatch":
        """Restore; raises on bad data so the caller can start fresh."""
        n = cls(config)
        if not isinstance(data, dict):
            raise TypeError("night state must be a mapping")
        n._last_day_at = _dt(data["last_day_at"])
        n._went_up_at = _dt(data["went_up_at"])
        n._last_night_at = _dt(data.get("last_night_at"))
        n._night_burst_at = _dt(data.get("night_burst_at"))
        n._night_burst_rise = _dt(data.get("night_burst_rise"))
        n.night_since = _dt(data["night_since"])
        n._trip_start = _dt(data["trip_start"])
        n._trip_last_day = _dt(data["trip_last_day"])
        n._trip_up_at = _dt(data["trip_up_at"])
        n._trip_room = str(data["trip_room"])
        n._door_at = _dt(data["door_at"])
        door = data["door_entity"]
        n._door_entity = None if door is None else str(door)
        # Stores from the door hold may carry "door_held": a held door is
        # simply an open one now, so the key is ignored.
        n._pending_at = _dt(data.get("pending_at"))
        n._pending_last = _dt(data.get("pending_last"))
        n._pending_room = str(data.get("pending_room") or "")
        n._pending_up = _dt(data.get("pending_up"))
        n._trip_max = float(data["trip_max"])
        n._doors = [int(h) for h in data["doors"]]
        nights: dict[str, _NightRecord] = {}
        for k, r in data["nights"].items():
            date.fromisoformat(k)
            nights[str(k)] = _NightRecord(
                float(r["trip"]), [int(h) for h in r["doors"]]
            )
        n._nights = nights
        return n
