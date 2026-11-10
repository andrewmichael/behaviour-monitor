"""What is really unusual: three learned, card-only kinds.

- ``not_yet_today``: an entity used on nearly every learned day has not been
  used by its usual time plus an allowance that grows with its spread.
- ``trip_missed``: a learned weekday outing window ended with no outing.
- ``unusual_now``: an entity fired in an hour it never fired in (±1 h) on
  any of its learned days.

Every time of day comes from learned values; the clock is always an
argument. All three are STATISTICAL and LOW, so they are never pushed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .entity_routine import EntityRoutineModel
from .events import ActivityEvent, Category
from .slots import iso_day
from .whereabouts import Whereabouts, _quantile

_DAY_MIN = 1440
_WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


@dataclass(frozen=True)
class UnusualConfig:
    """Fixed values (minutes unless stated)."""

    # not_yet_today: used on at least this share of learned days; the
    # allowance is never less than this.
    usual_fraction: float = 0.90
    allowance_floor_min: float = 60.0
    # trip_missed: bins out (±slack) on this share of at least this many
    # same-weekday days form a usual outing window.
    trip_fraction: float = 0.75
    trip_min_days: int = 4
    trip_slack_min: float = 60.0
    trip_bin_min: int = 15
    # unusual_now: hours either side that count as usual; how long it shows.
    unusual_neighbour_h: int = 1
    unusual_ttl_min: float = 120.0
    # Learned days needed, and how far back they are taken from.
    min_days: int = 14
    window_days: int = 28
    # Night parts (used by the night tracking).
    night_trip_min: float = 30.0
    upstairs: frozenset[str] = frozenset()


def _hhmm(minute: float) -> str:
    m = int(minute)
    return f"{m // 60:02d}:{m % 60:02d}"


def _at(day: date, minute: float, like: datetime) -> datetime:
    return datetime.combine(day, time(), tzinfo=like.tzinfo) + timedelta(minutes=minute)


def _minute(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


class Unusual:
    """Learns first uses, outing windows and usual hours; raises card kinds."""

    def __init__(self, config: UnusualConfig) -> None:
        self._cfg = config
        # Entity -> ISO day -> first activity minute at or after the morning
        # start, or None for a finalised active day with no use.
        self._first: dict[str, dict[str, int | None]] = {}
        # ISO days finalised with activity in the house.
        self._active: set[str] = set()
        # Today's first activity per (entity, hour), for unusual_now.
        self._hours_day: str | None = None
        self._hours: dict[str, dict[int, datetime]] = {}

    # ------------------------------------------------------------ learning

    def record(self, ev: ActivityEvent, where: Whereabouts) -> None:
        """Feed one event, before ``where`` records it."""
        if not ev.is_activity:
            return
        ts = ev.timestamp
        day = iso_day(ts.date())
        minute = _minute(ts)
        if minute >= where.night_end(ts.date()):
            days = self._first.setdefault(ev.entity_id, {})
            known = days.get(day)
            if known is None or minute < known:
                days[day] = minute
        if self._hours_day is None or day > self._hours_day:
            self._hours_day = day
            self._hours = {}
        if day == self._hours_day:
            hours = self._hours.setdefault(ev.entity_id, {})
            if ts.hour not in hours or ts < hours[ts.hour]:
                hours[ts.hour] = ts

    def finalise_day(self, day: date, entity_ids: Iterable[str], active: bool) -> None:
        """Close ``day``: an active day is learned, with None for no use."""
        if not active:
            return
        d = iso_day(day)
        self._active.add(d)
        for eid in entity_ids:
            self._first.setdefault(eid, {}).setdefault(d, None)

    def remove(self, entity_id: str) -> None:
        self._first.pop(entity_id, None)
        self._hours.pop(entity_id, None)

    def prune(self, before: date) -> None:
        """Forget days before ``before``."""
        cutoff = iso_day(before)
        self._first = {
            eid: {d: m for d, m in days.items() if d >= cutoff}
            for eid, days in self._first.items()
        }
        self._active = {d for d in self._active if d >= cutoff}
        if self._hours_day is not None and self._hours_day < cutoff:
            self._hours_day = None
            self._hours = {}

    def _window(self, today: date) -> tuple[str, str]:
        """ISO bounds [first, today) of the learned days."""
        start = today - timedelta(days=self._cfg.window_days)
        return iso_day(start), iso_day(today)

    def _learned_days(self, today: date) -> list[str]:
        lo, hi = self._window(today)
        return sorted(d for d in self._active if lo <= d < hi)

    # ---------------------------------------------------------- evaluation

    def evaluate(
        self,
        now: datetime,
        where: Whereabouts,
        routines: EntityRoutineModel,
        down: set[str],
        names: Callable[[str], str],
        categories: dict[str, Category],
    ) -> list[Alert]:
        """Every card alert open at ``now``."""
        return (
            self._not_yet_today(now, where, routines, down, names, categories)
            + self._trips_missed(now, where)
            + self._unusual_now(now, routines, down, names)
        )

    def _not_yet_today(
        self,
        now: datetime,
        where: Whereabouts,
        routines: EntityRoutineModel,
        down: set[str],
        names: Callable[[str], str],
        categories: dict[str, Category],
    ) -> list[Alert]:
        cfg = self._cfg
        today = now.date()
        learned = self._learned_days(today)
        if len(learned) < cfg.min_days:
            return []
        now_min = _minute(now)
        went_out = bool(where.out_spans(today)) or where.is_out(now)
        out: list[Alert] = []
        for eid, days in self._first.items():
            if eid in down or categories.get(eid) is Category.PANIC:
                continue
            if days.get(iso_day(today)) is not None:
                continue
            uses = [float(m) for d in learned if (m := days.get(d)) is not None]
            if not uses or len(uses) < cfg.usual_fraction * len(learned):
                continue
            usual = _quantile(uses, 0.9)
            allowance = max(cfg.allowance_floor_min, usual - _quantile(uses, 0.5))
            due = usual + allowance
            if now_min < due:
                continue
            routine = routines.get(eid)
            out.append(
                Alert(
                    cls=AlertClass.STATISTICAL,
                    source=eid,
                    kind="not_yet_today",
                    severity=Severity.LOW,
                    explanation=(
                        f"{names(eid)} not used yet today; "
                        f"usually by {_hhmm(usual)}"
                    ),
                    raised_at=_at(today, due, now),
                    details={
                        "room": routine.room if routine else "",
                        "usual_by": _hhmm(usual),
                        "went_out_today": went_out,
                    },
                )
            )
        return out

    def _outing_windows(self, today: date, where: Whereabouts) -> list[tuple[int, int]]:
        """Usual outing windows (start, end minutes) for today's weekday."""
        cfg = self._cfg
        days = [
            d
            for d in self._learned_days(today)
            if date.fromisoformat(d).weekday() == today.weekday()
        ]
        if len(days) < cfg.trip_min_days:
            return []
        step = cfg.trip_bin_min
        bins = _DAY_MIN // step
        counts = [0] * bins
        for d in days:
            marked = [False] * bins
            for start, end in where.out_spans(date.fromisoformat(d)):
                for b in range(bins):
                    lo, hi = b * step, (b + 1) * step
                    if (
                        lo < end + cfg.trip_slack_min
                        and hi > start - cfg.trip_slack_min
                    ):
                        marked[b] = True
            for b in range(bins):
                counts[b] += marked[b]
        windows: list[tuple[int, int]] = []
        for b in range(bins):
            if counts[b] < cfg.trip_fraction * len(days):
                continue
            if windows and windows[-1][1] == b * step:
                windows[-1] = (windows[-1][0], (b + 1) * step)
            else:
                windows.append((b * step, (b + 1) * step))
        return windows

    def _trips_missed(self, now: datetime, where: Whereabouts) -> list[Alert]:
        cfg = self._cfg
        today = now.date()
        if len(self._learned_days(today)) < cfg.min_days:
            return []
        now_min = _minute(now)
        spans = list(where.out_spans(today))
        iv = where.current(now)
        if where.is_out(now) and iv is not None:
            start = _minute(iv.start) if iv.start.date() == today else 0
            spans.append((start, now_min))
        slack = cfg.trip_slack_min
        out: list[Alert] = []
        for w_start, w_end in self._outing_windows(today, where):
            due = w_end + slack
            if now_min < due:
                continue
            if any(s < w_end + slack and e > w_start - slack for s, e in spans):
                continue
            # The window carries the slack on both sides; show the outing.
            shown_start, shown_end = w_start + slack, w_end - slack
            if shown_start > shown_end:
                shown_start = shown_end = (w_start + w_end) / 2
            out.append(
                Alert(
                    cls=AlertClass.STATISTICAL,
                    source=f"trip:{_hhmm(shown_start).replace(':', '')}",
                    kind="trip_missed",
                    severity=Severity.LOW,
                    explanation=(
                        f"Usual {_WEEKDAYS[today.weekday()]} outing (around "
                        f"{_hhmm(shown_start)} to {_hhmm(shown_end)}) didn't happen"
                    ),
                    raised_at=_at(today, due, now),
                    details={
                        "usual_from": _hhmm(shown_start),
                        "usual_to": _hhmm(shown_end),
                    },
                )
            )
        return out

    def _unusual_now(
        self,
        now: datetime,
        routines: EntityRoutineModel,
        down: set[str],
        names: Callable[[str], str],
    ) -> list[Alert]:
        cfg = self._cfg
        today = now.date()
        if self._hours_day != iso_day(today):
            return []
        lo, hi = self._window(today)
        ttl = timedelta(minutes=cfg.unusual_ttl_min)
        k = cfg.unusual_neighbour_h
        out: list[Alert] = []
        for eid, hours in self._hours.items():
            if eid in down:
                continue
            routine = routines.get(eid)
            if routine is None:
                continue
            learned = [d for d in routine.days_seen if lo <= d < hi]
            if len(learned) < cfg.min_days:
                continue
            latest: datetime | None = None
            for h, ts in hours.items():
                if not ts <= now < ts + ttl:
                    continue
                usual = any(
                    routine.slot_days[
                        date.fromisoformat(d).weekday() * 24 + (h + dh) % 24
                    ].get(d, 0)
                    > 0
                    for d in learned
                    for dh in range(-k, k + 1)
                )
                if not usual and (latest is None or ts > latest):
                    latest = ts
            if latest is None:
                continue
            out.append(
                Alert(
                    cls=AlertClass.STATISTICAL,
                    source=eid,
                    kind="unusual_now",
                    severity=Severity.LOW,
                    explanation=(
                        f"{names(eid)} active at {latest:%H:%M}, "
                        "unusual for this time"
                    ),
                    raised_at=latest,
                    details={"room": routine.room, "at": f"{latest:%H:%M}"},
                )
            )
        return out

    # --------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "first": {eid: dict(days) for eid, days in self._first.items()},
            "active": sorted(self._active),
            "hours_day": self._hours_day,
            "hours": {
                eid: {str(h): ts.isoformat() for h, ts in hours.items()}
                for eid, hours in self._hours.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Any, config: UnusualConfig) -> "Unusual":
        u = cls(config)
        try:
            u._first = {
                str(eid): {
                    str(d): (None if m is None else int(m)) for d, m in days.items()
                }
                for eid, days in data["first"].items()
            }
            active = data["active"]
            if not all(isinstance(d, str) for d in active):
                raise ValueError("active days must be ISO strings")
            u._active = set(active)
            hd = data.get("hours_day")
            u._hours_day = None if hd is None else str(hd)
            u._hours = {
                str(eid): {int(h): datetime.fromisoformat(ts) for h, ts in hrs.items()}
                for eid, hrs in data.get("hours", {}).items()
            }
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return u
