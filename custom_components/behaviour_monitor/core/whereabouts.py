"""Where she probably is, from the activity stream.

Each activity (presence, a door opening, an appliance turning on) starts a new
interval that lasts until the next one. The state, room and TV flag are fixed
when the interval starts, so a TV switched off later neither resets stillness
nor shortens the allowance. Lights and generic events are left out on purpose:
automations switch lights and would keep resetting the clock, hiding a fall.

An outside door is the one exception to "fixed at the start": whether she went
out depends on what happens in the next ten minutes, so that interval reads as
``HOME`` until it has been quiet that long and ``OUT`` afterwards. An outside
door during a door interval, pending or out, is her return: an ordinary
interval in the door's room.

A motion burst's end is activity too: a sensor re-triggered inside its
debounce emits no new presence, so the room still moving after another room's
presence would otherwise be lost. A burst end newer than the interval starts a
new one at its time. The room follows the latest motion, not the latest
sensor to clear: it moves to the burst's room only when the burst's last rise
is later than the rise that set the current room, so a landing that clears a
second after the bedroom on the way back to bed leaves her in the bedroom.
During a door interval a burst end is ignored: sensors hold "on" for a minute
or more, so a burst ending after the door opened is not evidence anyone is
home.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Callable

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent, EventKind
from .slots import iso_day


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
    # A burst is evidence of activity until its fall, but no later than this
    # long after its last rise: a sensor stuck "on" must not hide stillness.
    burst_activity_max_min: float = 10.0
    # Stillness allowances.
    home_floor_min: float = 45.0
    home_cap_min: float = 60.0
    tv_allowance_min: float = 90.0
    lie_in_allowance_min: float = 90.0
    not_up_offset_min: float = 60.0
    outing_factor: float = 1.25
    # Learning: samples from this many distinct days before a value is trusted.
    min_days: int = 3
    home_quantile: float = 0.995
    waking_high_quantile: float = 0.95
    waking_low_quantile: float = 0.05
    night_start_quantile: float = 0.05
    # Fallbacks for waking times until learning completes.
    usual_waking_fallback_min: int = 9 * 60
    earliest_waking_fallback_min: int = 6 * 60
    outing_fallback_min: float = 240.0
    # Offsets and clamps (minutes; times of day are minutes after midnight).
    night_start_offset_min: int = 60
    night_start_clamp: tuple[int, int] = (18 * 60, 25 * 60)
    night_end_offset_min: int = 60
    night_end_clamp: tuple[int, int] = (3 * 60, 9 * 60)
    lie_in_offset_min: int = 120
    lie_in_latest_min: int = 13 * 60
    # The main sleep starts between these times (wrapping midnight).
    sleep_window: tuple[int, int] = (18 * 60, 4 * 60)
    # A bedroom interval this long is sleep: it can start the night, and
    # one before noon cancels the waking seen before it.
    sleep_min_min: float = 60.0
    # Waking is the first activity at or after this time.
    waking_after_min: int = 4 * 60
    # An outing this long or longer is a trip away, not an outing.
    max_outing_min: float = 24 * 60.0
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
    # No alerts while fewer than this fraction of sensors are live.
    min_live_fraction: float = 0.5
    # Severity turns HIGH at this multiple of the limit (stillness states).
    high_factor: float = 1.5
    # Severity turns HIGH this long after the deadline (not_up, not_back).
    high_after_min: float = 60.0


@dataclass(frozen=True)
class Interval:
    """A stretch of stillness that began with one activity."""

    start: datetime
    where: Where
    room: str | None
    tv: bool
    door: str | None = None
    # Set when the interval began at a burst end in the room it was already
    # in: the start of that run, so bedtime and "back to bed" lengths count
    # from the presence, not from the end of the burst.
    run_start: datetime | None = None


def _quantile(xs: list[float], p: float) -> float:
    """``sorted(xs)[min(len-1, int(p*len))]``; ``xs`` must not be empty."""
    ys = sorted(xs)
    return ys[min(len(ys) - 1, int(p * len(ys)))]


def _in_window(minute: int, begin: int, end: int) -> bool:
    """True when ``minute`` is in [begin, end), wrapping midnight."""
    if begin <= end:
        return begin <= minute < end
    return minute >= begin or minute < end


@dataclass(frozen=True)
class WhereAssessment:
    """Where she is taken to be at one moment, and the alert if any."""

    where: Where | None
    since: datetime | None
    room: str | None
    limit_min: float | None
    deadline: datetime | None
    alert: Alert | None
    degraded: bool


def _dur(minutes: float) -> str:
    m = int(minutes)
    return f"{m // 60}h {m % 60}m" if m >= 60 else f"{m} min"


class Whereabouts:
    """State machine over the activity stream."""

    def __init__(self, config: WhereaboutsConfig) -> None:
        self._cfg = config
        self._interval: Interval | None = None
        self._door_room: str | None = None
        self._last_room: str | None = None
        # When the motion (or other activity) that set ``_last_room`` rose.
        self._room_rise: datetime | None = None
        self._tvs_on: dict[str, str] = {}
        # Learned, all keyed by ISO day.
        self._home: dict[str, dict[int, list[float]]] = {}
        self._outs: dict[str, list[float]] = {}
        # Day -> (start minute, end minute) of each closed outing that began
        # that day, minutes after local midnight, end clipped to 1440.
        self._out_spans: dict[str, list[tuple[int, int]]] = {}
        # Night key (the evening's date) -> (onset, minutes to the end of
        # the night's last sleep interval).
        self._sleeps: dict[str, tuple[datetime, float]] = {}
        # Day -> minutes after midnight of the first non-bedroom activity.
        self._wakes: dict[str, int] = {}

    # ------------------------------------------------------------- learned

    def home_limit_min(self, hour: int) -> float:
        """Longest ordinary stillness at ``hour`` before it is worth an alert."""
        cfg = self._cfg
        days = [d[hour] for d in self._home.values() if d.get(hour)]
        if len(days) < cfg.min_days:
            return cfg.home_cap_min
        samples = [m for lengths in days for m in lengths]
        q = _quantile(samples, cfg.home_quantile)
        return max(cfg.home_floor_min, min(cfg.home_cap_min, q))

    def _wakings(self, today: date | None) -> dict[str, int]:
        wakes = dict(self._wakes)
        if self._cfg.bedrooms == frozenset():
            # No bedrooms chosen: she is up when the main sleep ends.
            for start, length in self._sleeps.values():
                end = start + timedelta(minutes=length)
                minute = end.hour * 60 + end.minute
                if minute >= self._cfg.waking_after_min:
                    wakes.setdefault(iso_day(end.date()), minute)
        # A day's waking can still change until the day is over, so the
        # caller's day in progress does not count yet.
        if today is not None:
            wakes.pop(iso_day(today), None)
        return wakes

    # The learned waking values below take ``today``, the caller's day in
    # progress, which is left out. None counts every day.

    def usual_waking_min(self, today: date | None = None) -> int:
        """Minutes after midnight she is usually up by (95th percentile)."""
        wakes = list(self._wakings(today).values())
        if len(wakes) < self._cfg.min_days:
            return self._cfg.usual_waking_fallback_min
        return int(_quantile(wakes, self._cfg.waking_high_quantile))

    def earliest_waking_min(self, today: date | None = None) -> int:
        """Minutes after midnight of her earliest waking (5th percentile)."""
        wakes = list(self._wakings(today).values())
        if len(wakes) < self._cfg.min_days:
            return self._cfg.earliest_waking_fallback_min
        return int(_quantile(wakes, self._cfg.waking_low_quantile))

    def longest_out_min(self) -> float | None:
        """Her longest outing, or None until outings on enough days."""
        days = [lengths for lengths in self._outs.values() if lengths]
        if len(days) < self._cfg.min_days:
            return None
        return max(m for lengths in days for m in lengths)

    def night_start(self) -> int:
        """Minutes after midnight when the night begins."""
        cfg = self._cfg
        if len(self._sleeps) < cfg.min_days:
            return cfg.night_start_min
        # Measured from noon so that 23:30 and 00:30 sort the right way round.
        from_noon = [
            (s.hour * 60 + s.minute - 12 * 60) % 1440 for s, _ in self._sleeps.values()
        ]
        low, high = cfg.night_start_clamp
        value = _quantile(from_noon, cfg.night_start_quantile)
        value -= cfg.night_start_offset_min
        value = max(low - 12 * 60, min(high - 12 * 60, value))
        return int((value + 12 * 60) % 1440)

    def night_end(self, today: date | None = None) -> int:
        """Minutes after midnight when the night ends."""
        cfg = self._cfg
        if len(self._wakings(today)) < cfg.min_days:
            return cfg.night_end_min
        low, high = cfg.night_end_clamp
        value = self.earliest_waking_min(today) - cfg.night_end_offset_min
        return max(low, min(high, value))

    def lie_in_end(self, today: date | None = None) -> int:
        """Minutes after midnight when the lie-in ends."""
        cfg = self._cfg
        if len(self._wakings(today)) < cfg.min_days:
            return cfg.lie_in_end_min
        value = self.usual_waking_min(today) + cfg.lie_in_offset_min
        return max(
            self.night_end(today) + cfg.lie_in_offset_min,
            min(cfg.lie_in_latest_min, value),
        )

    def _close(self, iv: Interval, end: datetime) -> None:
        """Learn from ``iv``, whose length is known now that ``end`` came."""
        cfg = self._cfg
        length = (end - iv.start).total_seconds() / 60
        out = iv.where is Where.OUT or (
            iv.door is not None and length >= cfg.out_after_min
        )
        day = iso_day(iv.start.date())
        begun = iv.run_start or iv.start
        if out:
            if length < cfg.max_outing_min:
                self._outs.setdefault(day, []).append(length)
                start_min = iv.start.hour * 60 + iv.start.minute
                if end.date() == iv.start.date():
                    end_min = end.hour * 60 + end.minute
                else:
                    end_min = 1440
                self._out_spans.setdefault(day, []).append((start_min, end_min))
            return
        if iv.where is Where.HOME:
            hours = self._home.setdefault(day, {})
            hours.setdefault(iv.start.hour, []).append(length)
        minute = begun.hour * 60 + begun.minute
        if (
            self.is_bedroom(iv.room)
            and _in_window(minute, *cfg.sleep_window)
            and (end - begun).total_seconds() / 60 >= cfg.sleep_min_min
        ):
            # A night split by a bathroom trip keeps its first onset and
            # stretches to the end of its last sleep interval.
            night = begun.date()
            if begun.hour < 12:
                night -= timedelta(days=1)
            key = iso_day(night)
            known = self._sleeps.get(key)
            onset = begun if known is None else min(known[0], begun)
            ends = (
                [end]
                if known is None
                else [end, known[0] + timedelta(minutes=known[1])]
            )
            self._sleeps[key] = (onset, (max(ends) - onset).total_seconds() / 60)

    def _begin(self, iv: Interval) -> None:
        if self._interval is not None:
            self._close(self._interval, iv.start)
        self._interval = iv

    def restart_clock(self, now: datetime, keep_anchored: bool = False) -> None:
        """Keep the state and count stillness from ``now``.

        An outing already under way stays ``OUT``: the moved start would
        otherwise put it back inside the door-then-movement window.

        ``keep_anchored`` is for a gap in polling: ``ASLEEP`` and ``OUT``
        keep their start, since their deadline is the next morning or the
        time she left, not a stretch of stillness. The end of a holiday
        restarts every state.
        """
        iv = self.current(now)
        if iv is None:
            return
        if keep_anchored and iv.where in (Where.ASLEEP, Where.OUT):
            self._interval = iv
            return
        self._interval = replace(iv, start=now, run_start=None)

    def rename_room(self, old: str, new: str) -> None:
        """Follow a renamed room in the remembered rooms and interval."""

        def ren(room: str | None) -> str | None:
            return new if room == old else room

        self._last_room = ren(self._last_room)
        self._door_room = ren(self._door_room)
        self._tvs_on = {e: new if r == old else r for e, r in self._tvs_on.items()}
        if self._interval is not None:
            self._interval = replace(self._interval, room=ren(self._interval.room))

    def prune(self, before: date) -> None:
        """Forget days before ``before``."""
        cutoff = iso_day(before)
        self._home = {d: v for d, v in self._home.items() if d >= cutoff}
        self._outs = {d: v for d, v in self._outs.items() if d >= cutoff}
        self._out_spans = {d: v for d, v in self._out_spans.items() if d >= cutoff}
        self._sleeps = {d: v for d, v in self._sleeps.items() if d >= cutoff}
        self._wakes = {d: v for d, v in self._wakes.items() if d >= cutoff}

    # --------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        iv = self._interval
        return {
            "home": {
                d: {str(h): list(v) for h, v in hours.items()}
                for d, hours in self._home.items()
            },
            "outs": {d: list(v) for d, v in self._outs.items()},
            "out_spans": {
                d: [[a, b] for a, b in v] for d, v in self._out_spans.items()
            },
            "sleeps": {
                d: [s.isoformat(), length] for d, (s, length) in self._sleeps.items()
            },
            "wakes": dict(self._wakes),
            "interval": (
                {
                    "start": iv.start.isoformat(),
                    "where": iv.where.value,
                    "room": iv.room,
                    "tv": iv.tv,
                    "door": iv.door,
                    "run_start": iv.run_start.isoformat() if iv.run_start else None,
                }
                if iv
                else None
            ),
            "door_room": self._door_room,
            "last_room": self._last_room,
            "room_rise": self._room_rise.isoformat() if self._room_rise else None,
            "tvs_on": dict(self._tvs_on),
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], config: WhereaboutsConfig
    ) -> "Whereabouts":
        w = cls(config)
        try:
            w._home = {
                d: {int(h): [float(x) for x in v] for h, v in hours.items()}
                for d, hours in data["home"].items()
            }
            w._outs = {d: [float(x) for x in v] for d, v in data["outs"].items()}
            w._sleeps = {
                d: (datetime.fromisoformat(s), float(length))
                for d, (s, length) in data["sleeps"].items()
            }
            w._wakes = {d: int(m) for d, m in data["wakes"].items()}
            raw = data.get("interval")
            if raw:
                w._interval = Interval(
                    datetime.fromisoformat(raw["start"]),
                    Where(raw["where"]),
                    raw["room"],
                    bool(raw["tv"]),
                    raw["door"],
                    (
                        datetime.fromisoformat(raw["run_start"])
                        if raw.get("run_start")
                        else None
                    ),
                )
            w._door_room = data.get("door_room")
            w._last_room = data.get("last_room")
            rise = data.get("room_rise")
            w._room_rise = datetime.fromisoformat(rise) if rise else None
            if w._room_rise is None and w._last_room and w._interval:
                # A store from before rises were kept: the interval's start
                # is the best evidence of when the room was set.
                w._room_rise = w._interval.start
            w._tvs_on = dict(data.get("tvs_on", {}))
            w._out_spans = {
                d: [(int(a), int(b)) for a, b in v]
                for d, v in data.get("out_spans", {}).items()
            }
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return w

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
        """Feed one event.

        Presence, open and appliance-on events start intervals, and so does a
        burst end that brings newer activity (see ``_burst_end``).
        """
        if self._interval is not None and ev.timestamp < self._interval.start:
            return
        if ev.kind is EventKind.BURST_END:
            self._burst_end(ev)
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
        self._cancel_waking(ev.timestamp)
        self._note_waking(ev)
        if ev.kind is EventKind.APPLIANCE_ON and sitting:
            self._tvs_on[ev.entity_id] = ev.room
        outside = ev.kind is EventKind.OPEN and ev.entity_id in self._cfg.outside_doors
        # An outside door after an outside door is her coming back, whether
        # she was out or only at the bins: she is in the door's room, and
        # presence there right after it is her.
        returning = outside and iv is not None and iv.door is not None
        if ev.kind is not EventKind.OPEN or returning:
            self._last_room = ev.room
            self._room_rise = ev.timestamp
        if outside and not returning:
            self._door_room = ev.room
            self._begin(
                Interval(
                    ev.timestamp,
                    Where.HOME,
                    self._last_room,
                    self._tv_on_in(self._last_room),
                    ev.entity_id,
                )
            )
            return
        self._door_room = None
        tv = self._tv_on_in(self._last_room)
        self._begin(
            Interval(
                ev.timestamp,
                self._classify(ev.timestamp, self._last_room, tv),
                self._last_room,
                tv,
            )
        )

    def _burst_end(self, ev: ActivityEvent) -> None:
        """A burst end: someone was moving until its activity time.

        The activity time is its fall, but no later than
        ``burst_activity_max_min`` after its last rise, so a sensor stuck
        "on" for hours can't move the clock. Only an activity time later than
        the interval's start counts; stillness then counts from it. The room
        moves to the burst's room only if the burst last rose after the
        motion that set the current room; ties keep the current room. Not a
        waking. It closes the interval like any activity, so a long stretch
        in bed before it still cancels the waking seen before it.
        """
        iv = self._interval
        rise = ev.last_rise or ev.timestamp
        active = min(
            ev.timestamp,
            rise + timedelta(minutes=self._cfg.burst_activity_max_min),
        )
        if iv is not None and (iv.door is not None or active <= iv.start):
            return
        self._cancel_waking(active)
        if self._last_room is None or self._room_rise is None or rise > self._room_rise:
            self._last_room, self._room_rise = ev.room, rise
        room = self._last_room
        run = None
        if iv is not None and iv.room == room:
            run = iv.run_start or iv.start
        tv = self._tv_on_in(room)
        self._begin(
            Interval(
                active,
                self._classify(active, room, tv),
                room,
                tv,
                run_start=run,
            )
        )

    def _cancel_waking(self, now: datetime) -> None:
        """Back to bed for a long while before noon: she was not up after all.

        The next activity outside a bedroom becomes the day's waking instead.
        """
        cfg = self._cfg
        iv = self._interval
        if iv is None or cfg.bedrooms == frozenset() or not self.is_bedroom(iv.room):
            return
        begun = iv.run_start or iv.start
        if begun.hour >= 12 or now - begun < timedelta(minutes=cfg.sleep_min_min):
            return
        day = iso_day(begun.date())
        if self._wakes.get(day, 24 * 60) <= begun.hour * 60 + begun.minute:
            del self._wakes[day]

    def _note_waking(self, ev: ActivityEvent) -> None:
        """Remember the day's first activity outside a bedroom after 04:00."""
        minute = ev.timestamp.hour * 60 + ev.timestamp.minute
        if minute < self._cfg.waking_after_min or self._cfg.bedrooms == frozenset():
            return
        if self.is_bedroom(ev.room):
            return
        day = iso_day(ev.timestamp.date())
        if day not in self._wakes or minute < self._wakes[day]:
            self._wakes[day] = minute

    def out_spans(self, day: date) -> list[tuple[int, int]]:
        """Closed outings that began on ``day``: (start, end) minutes."""
        return list(self._out_spans.get(iso_day(day), []))

    def adopt_out_spans(self, spans: dict[str, list[tuple[int, int]]]) -> None:
        """Replace the stored outing spans (used when history is rebuilt)."""
        self._out_spans = {d: list(v) for d, v in spans.items()}

    def is_out(self, now: datetime) -> bool:
        iv = self.current(now)
        return iv is not None and iv.where is Where.OUT

    @property
    def outside_doors(self) -> frozenset[str]:
        """The chosen outside doors."""
        return self._cfg.outside_doors

    def sitting_rooms(self) -> set[str]:
        """Rooms with a sitting appliance on."""
        return set(self._tvs_on.values())

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

    def evaluate(
        self,
        now: datetime,
        live_fraction: float = 1.0,
        names: Callable[[str], str] | None = None,
    ) -> WhereAssessment:
        """Assess ``now``; raises no state change, so it may run every minute."""
        cfg = self._cfg
        iv = self.current(now)
        if iv is None:
            return WhereAssessment(None, None, None, None, None, None, False)
        start, room = iv.start, iv.room
        limit: float | None = None
        high_at: datetime
        if iv.where is Where.HOME:
            limit = self.home_limit_min(start.hour)
            deadline = start + timedelta(minutes=limit)
            high_at = start + timedelta(minutes=limit * cfg.high_factor)
            kind = "still_at_home"
        elif iv.where is Where.HOME_TV:
            limit = cfg.tv_allowance_min
            deadline = start + timedelta(minutes=limit)
            high_at = start + timedelta(minutes=limit * cfg.high_factor)
            kind = "still_tv"
        elif iv.where is Where.LYING_IN:
            limit = cfg.lie_in_allowance_min
            deadline = start + timedelta(minutes=limit)
            high_at = start + timedelta(minutes=limit * cfg.high_factor)
            kind = "not_up"
        elif iv.where is Where.ASLEEP:
            morning = start.date()
            if start.hour >= 12:
                morning += timedelta(days=1)
            deadline = datetime.combine(morning, datetime.min.time(), start.tzinfo)
            deadline += timedelta(
                minutes=self.usual_waking_min(now.date()) + cfg.not_up_offset_min
            )
            high_at = deadline + timedelta(minutes=cfg.high_after_min)
            kind = "not_up"
        else:
            longest = self.longest_out_min()
            base = longest if longest is not None else cfg.outing_fallback_min
            deadline = start + timedelta(minutes=base * cfg.outing_factor)
            high_at = deadline + timedelta(minutes=cfg.high_after_min)
            kind = "not_back"
        degraded = live_fraction < cfg.min_live_fraction
        alert: Alert | None = None
        if now >= deadline and not degraded:
            alert = self._alert(iv, kind, now, limit, high_at, names)
        return WhereAssessment(iv.where, start, room, limit, deadline, alert, degraded)

    def _alert(
        self,
        iv: Interval,
        kind: str,
        now: datetime,
        limit: float | None,
        high_at: datetime,
        names: Callable[[str], str] | None,
    ) -> Alert:
        start = iv.start
        room = iv.room or "house"
        at = start.strftime("%H:%M")
        elapsed = (now - start).total_seconds() / 60
        if iv.where is Where.HOME:
            text = (
                f"No movement for {_dur(elapsed)}; "
                f"last movement in the {room} at {at}"
            )
        elif iv.where is Where.HOME_TV:
            text = (
                f"No movement for {_dur(elapsed)} with the {room} TV on; "
                f"last movement at {at}"
            )
        elif iv.where is Where.LYING_IN:
            text = (
                f"Not up yet; movement in the {room} at {at}, "
                f"none for {_dur(elapsed)}"
            )
        elif iv.where is Where.ASLEEP:
            waking = self.usual_waking_min(now.date())
            text = (
                f"Not up yet; usually up by {waking // 60:02d}:{waking % 60:02d}, "
                f"last movement in the {room} at {at}"
            )
        else:
            longest = self.longest_out_min()
            usual = (
                f"longest {_dur(longest)}"
                if longest is not None
                else f"usual limit {_dur(self._cfg.outing_fallback_min)}"
            )
            door = iv.door or "door"
            door = names(door) if names is not None else door
            text = (
                f"House empty for {_dur(elapsed)}, longer than usual ({usual}); "
                f"last out by the {door} at {at}"
            )
        return Alert(
            AlertClass.WELFARE,
            "whereabouts",
            kind,
            Severity.HIGH if now >= high_at else Severity.MEDIUM,
            text,
            now,
            {
                "room": iv.room,
                "where": iv.where.value,
                "since": start.isoformat(),
                "limit_min": limit,
                "minutes": int(elapsed),
            },
        )

    def _tv_on_in(self, room: str | None) -> bool:
        return room is not None and room in self._tvs_on.values()

    def _classify(self, start: datetime, room: str | None, tv: bool) -> Where:
        if self.is_bedroom(room):
            minute = start.hour * 60 + start.minute
            today = start.date()
            if _in_window(minute, self.night_start(), self.night_end(today)):
                return Where.ASLEEP
            if _in_window(minute, self.night_end(today), self.lie_in_end(today)):
                return Where.LYING_IN
        return Where.HOME_TV if tv else Where.HOME
