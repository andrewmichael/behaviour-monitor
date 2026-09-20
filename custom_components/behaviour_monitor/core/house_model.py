"""Whole-house activity gap model. The only sole source of welfare alerts."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .alerts import Severity
from .events import ActivityEvent
from .slots import SLOTS, confidence, iso_day, slot_index

MIN_GAPS_PER_SLOT = 8
EXPECTED_GAP_QUANTILE = 0.9
_GAPS_PER_SLOT = 400


@dataclass(frozen=True)
class HouseConfig:
    learning_days: int = 14
    window_days: int = 28
    low_ratio: float = 3.0
    medium_ratio: float = 6.0
    high_ratio: float = 12.0
    floor_s: float = 300.0
    min_live_fraction: float = 0.5
    sustain_polls: int = 2


@dataclass(frozen=True)
class HouseAssessment:
    gap_s: float | None
    expected_s: float | None
    ratio: float | None
    severity: Severity | None
    degraded: bool
    last_room: str | None


class HouseModel:
    def __init__(self, config: HouseConfig) -> None:
        self._cfg = config
        self._gaps: list[deque[tuple[str, float]]] = [
            deque(maxlen=_GAPS_PER_SLOT) for _ in range(SLOTS)
        ]
        self._last_activity: datetime | None = None
        self._last_room: str | None = None
        self._days_seen: set[str] = set()
        self._rooms_by_day: dict[str, set[str]] = {}
        self._current: Severity | None = None
        self._pending: Severity | None = None
        self._pending_count = 0
        self._below_count = 0

    # ------------------------------------------------------------ properties

    @property
    def last_activity(self) -> datetime | None:
        return self._last_activity

    @property
    def last_room(self) -> str | None:
        return self._last_room

    # ------------------------------------------------------------- recording

    def record(self, event: ActivityEvent) -> None:
        if not event.is_activity:
            return
        day = iso_day(event.timestamp.date())
        self._days_seen.add(day)
        self._rooms_by_day.setdefault(day, set()).add(event.room)
        if self._last_activity is not None and event.timestamp > self._last_activity:
            gap = (event.timestamp - self._last_activity).total_seconds()
            self._gaps[slot_index(event.timestamp)].append((day, gap))
        if self._last_activity is None or event.timestamp >= self._last_activity:
            self._last_activity = event.timestamp
            self._last_room = event.room

    # --------------------------------------------------------------- queries

    def expected_gap(self, now: datetime) -> float | None:
        """90th percentile of learned gaps for this slot.

        Activity comes in bursts (a morning routine is several events a few
        minutes apart followed by an hour of nothing), so the median gap is
        far too tight. The 90th percentile is "the longest gap that is still
        normal for this hour", which is what a welfare ratio must compare
        against.
        """
        gaps = self._gaps[slot_index(now)]
        if len(gaps) < MIN_GAPS_PER_SLOT:
            return None
        vals = sorted(g for _, g in gaps)
        return float(vals[min(len(vals) - 1, int(len(vals) * EXPECTED_GAP_QUANTILE))])

    def confidence(self, now: datetime) -> float:
        return confidence(len(self._days_seen), self._cfg.learning_days)

    def rooms_visited(self, day: date) -> set[str]:
        return set(self._rooms_by_day.get(iso_day(day), set()))

    def evaluate(self, now: datetime, live_fraction: float = 1.0) -> HouseAssessment:
        degraded = live_fraction < self._cfg.min_live_fraction
        gap = (
            (now - self._last_activity).total_seconds() if self._last_activity else None
        )
        expected = self.expected_gap(now)
        ratio = None
        raw: Severity | None = None
        if gap is not None and expected is not None and not degraded:
            ratio = gap / max(expected, self._cfg.floor_s)
            if ratio >= self._cfg.high_ratio:
                raw = Severity.HIGH
            elif ratio >= self._cfg.medium_ratio:
                raw = Severity.MEDIUM
            elif ratio >= self._cfg.low_ratio:
                raw = Severity.LOW
        if not degraded:
            self._sustain(raw)
        severity = None if degraded else self._current
        return HouseAssessment(
            gap, expected, ratio, severity, degraded, self._last_room
        )

    def _sustain(self, raw: Severity | None) -> None:
        if raw is not None and (self._current is None or raw > self._current):
            if raw == self._pending:
                self._pending_count += 1
            else:
                self._pending, self._pending_count = raw, 1
            self._below_count = 0
            if self._pending_count >= self._cfg.sustain_polls:
                self._current, self._pending, self._pending_count = raw, None, 0
        elif raw is not None and raw == self._current:
            self._pending, self._pending_count, self._below_count = None, 0, 0
        else:
            self._pending, self._pending_count = None, 0
            if self._current is not None:
                self._below_count += 1
                if self._below_count >= 1:
                    idx = [
                        Severity.LOW,
                        Severity.MEDIUM,
                        Severity.HIGH,
                        Severity.CRITICAL,
                    ].index(self._current)
                    self._current = (
                        None
                        if idx == 0
                        else [
                            Severity.LOW,
                            Severity.MEDIUM,
                            Severity.HIGH,
                            Severity.CRITICAL,
                        ][idx - 1]
                    )
                    if (
                        raw is not None
                        and self._current is not None
                        and raw < self._current
                    ):
                        self._current = raw
                    self._below_count = 0

    # --------------------------------------------------------------- window

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        for gaps in self._gaps:
            kept = [(d, g) for d, g in gaps if d >= cutoff]
            gaps.clear()
            gaps.extend(kept)
        self._days_seen = {d for d in self._days_seen if d >= cutoff}
        self._rooms_by_day = {
            d: r for d, r in self._rooms_by_day.items() if d >= cutoff
        }

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "gaps": [list(g) for g in self._gaps],
            "last_activity": (
                self._last_activity.isoformat() if self._last_activity else None
            ),
            "last_room": self._last_room,
            "days_seen": sorted(self._days_seen),
            "rooms_by_day": {d: sorted(r) for d, r in self._rooms_by_day.items()},
            "current": self._current.value if self._current else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: HouseConfig) -> "HouseModel":
        m = cls(config)
        try:
            gaps = data["gaps"]
            for i in range(min(SLOTS, len(gaps))):
                m._gaps[i].extend((str(d), float(g)) for d, g in gaps[i])
            la = data.get("last_activity")
            m._last_activity = datetime.fromisoformat(la) if la else None
            m._last_room = data.get("last_room")
            m._days_seen = set(data.get("days_seen", []))
            m._rooms_by_day = {
                d: set(r) for d, r in data.get("rooms_by_day", {}).items()
            }
            cur = data.get("current")
            m._current = Severity(cur) if cur else None
        except (KeyError, TypeError, ValueError):
            return cls(config)
        return m
