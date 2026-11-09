"""Whole-house activity gap model: learning-progress days, rooms and usual gaps.

168 slots (weekday x hour) hold full weekly structure once the house is learned, but
early on a slot only fills from occurrences of its own weekday: 14 learning days give
each slot two days at most, short of MIN_DAYS_PER_SLOT. ``expected_gap`` copes by
pooling: first the exact slot, then the same hour across every day of the same type
(weekday/weekend), then that hour across all seven weekdays, so the model still has an
opinion about "normal" before a full week's worth of weekday recurrences exist.

Each slot keeps one number per day: the longest silence that started in that hour.
A burst of motion contributes twenty tiny gaps and one real silence, and it is the
silence that matters, so the chatter is never stored. This
also makes the sample count equal the day count, which is what the trust check reads.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .events import ActivityEvent
from .slots import SLOTS, confidence, is_weekend, iso_day, slot_index

MIN_DAYS_PER_SLOT = 3
EXPECTED_GAP_QUANTILE = 0.9
_WEEKDAY_INDICES = range(0, 5)
_WEEKEND_INDICES = range(5, 7)
_ALL_INDICES = range(0, 7)


@dataclass(frozen=True)
class HouseConfig:
    learning_days: int = 14
    window_days: int = 28


def _load_slot(raw: Any) -> dict[str, float]:
    """Read one slot from a store. Current stores hold {day: longest_gap};
    earlier ones held every gap as [day, gap] pairs, which fold to the same."""
    out: dict[str, float] = {}
    pairs = raw.items() if isinstance(raw, dict) else raw
    for d, g in pairs:
        day, gap = str(d), float(g)
        if gap > out.get(day, 0.0):
            out[day] = gap
    return out


class HouseModel:
    def __init__(self, config: HouseConfig) -> None:
        self._cfg = config
        # Per slot: iso day -> longest gap (seconds) that started in that slot.
        self._gaps: list[dict[str, float]] = [dict() for _ in range(SLOTS)]
        self._last_activity: datetime | None = None
        self._last_room: str | None = None
        self._days_seen: set[str] = set()
        self._rooms_by_day: dict[str, set[str]] = {}

    # ------------------------------------------------------------ properties

    @property
    def last_activity(self) -> datetime | None:
        return self._last_activity

    @property
    def last_room(self) -> str | None:
        return self._last_room

    @property
    def days_observed(self) -> int:
        """Distinct days with activity still inside the window."""
        return len(self._days_seen)

    # ------------------------------------------------------------- recording

    def record(self, event: ActivityEvent) -> None:
        if not event.is_activity:
            return
        day = iso_day(event.timestamp.date())
        self._days_seen.add(day)
        self._rooms_by_day.setdefault(day, set()).add(event.room)
        started = self._last_activity
        if started is not None and event.timestamp > started:
            # A silence belongs to the slot it starts in, not the one it ends
            # in: an hour whose activity is one tight burst followed by quiet
            # must learn the quiet, or its own idle tail looks like an anomaly.
            gap = (event.timestamp - started).total_seconds()
            slot = self._gaps[slot_index(started)]
            day_started = iso_day(started.date())
            if gap > slot.get(day_started, 0.0):
                slot[day_started] = gap
        if self._last_activity is None or event.timestamp >= self._last_activity:
            self._last_activity = event.timestamp
            self._last_room = event.room

    # --------------------------------------------------------------- queries

    def expected_gap(self, ts: datetime) -> float | None:
        """90th percentile length of a silence that starts at ``ts``.

        Activity comes in bursts (a morning routine is several events a few
        minutes apart followed by an hour of nothing), so the median gap is
        far too tight. The 90th percentile is "the longest gap that is still
        normal for this hour".

        Falls back to pooling by hour of day when the exact weekday+hour slot
        is still sparse: same day type (weekday/weekend) first, then all seven
        weekdays, before giving up. A rung is trusted once it holds gaps from
        MIN_DAYS_PER_SLOT distinct days; one busy day never counts as a
        distribution however many gaps it produced.
        """
        direct = list(self._gaps[slot_index(ts)].values())
        if len(direct) >= MIN_DAYS_PER_SLOT:
            return self._quantile(direct)
        hour = ts.hour
        same_type = _WEEKEND_INDICES if is_weekend(ts.date()) else _WEEKDAY_INDICES
        pooled = self._pool(hour, same_type)
        if len(pooled) >= MIN_DAYS_PER_SLOT:
            return self._quantile(pooled)
        all_days = self._pool(hour, _ALL_INDICES)
        if len(all_days) >= MIN_DAYS_PER_SLOT:
            return self._quantile(all_days)
        return None

    def _pool(self, hour: int, weekdays: Iterable[int]) -> list[float]:
        """One value per (day, slot) across the given weekdays at ``hour``."""
        out: list[float] = []
        for wd in weekdays:
            out.extend(self._gaps[wd * 24 + hour].values())
        return out

    @staticmethod
    def _quantile(gaps: Iterable[float]) -> float:
        vals = sorted(gaps)
        return float(vals[min(len(vals) - 1, int(len(vals) * EXPECTED_GAP_QUANTILE))])

    def confidence(self, now: datetime) -> float:
        return confidence(len(self._days_seen), self._cfg.learning_days)

    def rooms_visited(self, day: date) -> set[str]:
        return set(self._rooms_by_day.get(iso_day(day), set()))

    def restart_clock(self, now: datetime) -> None:
        """Reset the gap clock without recording a gap.

        Used when a paused period (e.g. holiday) ends: the silence during the
        pause must not be treated as an activity gap.
        """
        self._last_activity = now

    # --------------------------------------------------------------- window

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        for gaps in self._gaps:
            for d in [d for d in gaps if d < cutoff]:
                del gaps[d]
        self._days_seen = {d for d in self._days_seen if d >= cutoff}
        self._rooms_by_day = {
            d: r for d, r in self._rooms_by_day.items() if d >= cutoff
        }

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "gaps": [dict(g) for g in self._gaps],
            "last_activity": (
                self._last_activity.isoformat() if self._last_activity else None
            ),
            "last_room": self._last_room,
            "days_seen": sorted(self._days_seen),
            "rooms_by_day": {d: sorted(r) for d, r in self._rooms_by_day.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: HouseConfig) -> "HouseModel":
        m = cls(config)
        try:
            gaps = data["gaps"]
            for i in range(min(SLOTS, len(gaps))):
                m._gaps[i] = _load_slot(gaps[i])
            la = data.get("last_activity")
            m._last_activity = datetime.fromisoformat(la) if la else None
            m._last_room = data.get("last_room")
            m._days_seen = set(data.get("days_seen", []))
            m._rooms_by_day = {
                d: set(r) for d, r in data.get("rooms_by_day", {}).items()
            }
        except (KeyError, TypeError, ValueError):
            return cls(config)
        return m
