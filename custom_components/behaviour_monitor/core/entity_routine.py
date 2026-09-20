"""Per-entity slot statistics, expected windows and routine notes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import median
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent, Category
from .slots import SLOTS, confidence, iso_day, slot_index


@dataclass(frozen=True)
class RoutineConfig:
    learning_days: int = 14
    window_days: int = 28
    window_min_fraction: float = 0.7
    min_window_days: int = 3


@dataclass
class EntityRoutine:
    entity_id: str
    category: Category
    room: str
    slot_days: list[dict[str, int]] = field(
        default_factory=lambda: [dict() for _ in range(SLOTS)]
    )
    durations: dict[str, list[float]] = field(default_factory=dict)
    last_event: datetime | None = None
    longest_gap_by_day: dict[str, float] = field(default_factory=dict)
    days_seen: set[str] = field(default_factory=set)
    first_observation: datetime | None = None

    @property
    def longest_gap_s(self) -> float | None:
        """Longest gap that started on a day still inside the window.

        Kept per day rather than as a running maximum so that one long
        absence stops desensitising the entity once it ages out; otherwise a
        single holiday makes the sensor permanently impossible to call silent.
        """
        return max(self.longest_gap_by_day.values(), default=None)

    def record(self, event: ActivityEvent) -> None:
        day = iso_day(event.timestamp.date())
        if event.duration_s is not None:
            self.durations.setdefault(day, []).append(float(event.duration_s))
        if not event.is_activity:
            return
        self.days_seen.add(day)
        slot = self.slot_days[slot_index(event.timestamp)]
        slot[day] = slot.get(day, 0) + 1
        if self.first_observation is None:
            self.first_observation = event.timestamp
        if self.last_event is not None:
            gap = (event.timestamp - self.last_event).total_seconds()
            started = iso_day(self.last_event.date())
            if gap > 0 and gap > self.longest_gap_by_day.get(started, 0.0):
                self.longest_gap_by_day[started] = gap
        if self.last_event is None or event.timestamp > self.last_event:
            self.last_event = event.timestamp

    def daily_count(self, day: date) -> int:
        d = iso_day(day)
        w = day.weekday()
        return sum(self.slot_days[w * 24 + h].get(d, 0) for h in range(24))

    def expected_windows(self, weekday: int, cfg: RoutineConfig) -> list[int]:
        days_for_weekday = {
            d for d in self.days_seen if date.fromisoformat(d).weekday() == weekday
        }
        if len(days_for_weekday) < cfg.min_window_days:
            return []
        out: list[int] = []
        for h in range(24):
            fired = sum(
                1
                for d in days_for_weekday
                if self.slot_days[weekday * 24 + h].get(d, 0) > 0
            )
            if fired / len(days_for_weekday) >= cfg.window_min_fraction:
                out.append(h)
        return out

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        for slot in self.slot_days:
            for d in [d for d in slot if d < cutoff]:
                del slot[d]
        self.durations = {d: v for d, v in self.durations.items() if d >= cutoff}
        self.longest_gap_by_day = {
            d: g for d, g in self.longest_gap_by_day.items() if d >= cutoff
        }
        self.days_seen = {d for d in self.days_seen if d >= cutoff}

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "category": self.category.value,
            "room": self.room,
            "slot_days": self.slot_days,
            "durations": self.durations,
            "last_event": self.last_event.isoformat() if self.last_event else None,
            "longest_gap_by_day": dict(self.longest_gap_by_day),
            "days_seen": sorted(self.days_seen),
            "first_observation": (
                self.first_observation.isoformat() if self.first_observation else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityRoutine":
        r = cls(
            str(data["entity_id"]),
            Category(data["category"]),
            str(data.get("room", "")),
        )
        slots = data.get("slot_days", [])
        for i in range(min(SLOTS, len(slots))):
            r.slot_days[i] = {str(d): int(c) for d, c in slots[i].items()}
        r.durations = {
            str(d): [float(x) for x in v] for d, v in data.get("durations", {}).items()
        }
        le = data.get("last_event")
        r.last_event = datetime.fromisoformat(le) if le else None
        r.longest_gap_by_day = {
            str(d): float(g) for d, g in data.get("longest_gap_by_day", {}).items()
        }
        r.days_seen = set(data.get("days_seen", []))
        fo = data.get("first_observation")
        r.first_observation = datetime.fromisoformat(fo) if fo else None
        return r


class EntityRoutineModel:
    def __init__(self, config: RoutineConfig) -> None:
        self._cfg = config
        self._entities: dict[str, EntityRoutine] = {}

    # ----------------------------------------------------------- membership

    def add(self, entity_id: str, category: Category, room: str) -> None:
        if entity_id in self._entities:
            self._entities[entity_id].room = room
            self._entities[entity_id].category = category
        else:
            self._entities[entity_id] = EntityRoutine(entity_id, category, room)

    def remove(self, entity_id: str) -> None:
        self._entities.pop(entity_id, None)

    @property
    def entity_ids(self) -> list[str]:
        return list(self._entities)

    def get(self, entity_id: str) -> EntityRoutine | None:
        return self._entities.get(entity_id)

    # ------------------------------------------------------------ recording

    def record(self, event: ActivityEvent) -> None:
        r = self._entities.get(event.entity_id)
        if r is not None:
            r.record(event)

    # -------------------------------------------------------------- queries

    def expected_windows(self, entity_id: str, weekday: int) -> list[int]:
        r = self._entities.get(entity_id)
        return r.expected_windows(weekday, self._cfg) if r else []

    def longest_gap(self, entity_id: str) -> float | None:
        r = self._entities.get(entity_id)
        return r.longest_gap_s if r else None

    def last_event(self, entity_id: str) -> datetime | None:
        r = self._entities.get(entity_id)
        return r.last_event if r else None

    def restart_clock(self, now: datetime) -> None:
        """Set every entity's last_event to now without recording a gap or a slot.

        Used when a paused period (e.g. holiday) ends: the silence during the
        pause must not be learned as this entity's longest gap, and it must
        not look silent relative to a house clock that has just jumped ahead.
        """
        for r in self._entities.values():
            r.last_event = now

    def daily_counts(self, day: date) -> dict[str, int]:
        return {eid: r.daily_count(day) for eid, r in self._entities.items()}

    def daily_duration_medians(self, day: date) -> dict[str, float]:
        d = iso_day(day)
        return {
            eid: float(median(r.durations[d]))
            for eid, r in self._entities.items()
            if r.durations.get(d)
        }

    def confidence(self, now: datetime) -> float:
        if not self._entities:
            return 0.0
        return sum(
            confidence(len(r.days_seen), self._cfg.learning_days)
            for r in self._entities.values()
        ) / len(self._entities)

    def evaluate(self, now: datetime) -> list[Alert]:
        """Routine notes for windows that closed today without an event."""
        out: list[Alert] = []
        today = now.date()
        for eid, r in self._entities.items():
            for hour in r.expected_windows(today.weekday(), self._cfg):
                if hour >= now.hour:
                    continue  # window not yet closed
                if r.slot_days[today.weekday() * 24 + hour].get(iso_day(today), 0) > 0:
                    continue
                if (
                    r.last_event is not None
                    and r.last_event.date() == today
                    and r.last_event.hour > hour
                ):
                    continue  # fired later today; the miss is stale
                out.append(
                    Alert(
                        AlertClass.STATISTICAL,
                        eid,
                        "routine_missed",
                        Severity.LOW,
                        f"{r.room}: {eid} usually fires around {hour:02d}:00 on this weekday but has not today",
                        now,
                        {
                            "hour": hour,
                            "room": r.room,
                            "fired_today": r.daily_count(today) > 0,
                        },
                    )
                )
        return out

    def prune(self, before: date) -> None:
        for r in self._entities.values():
            r.prune(before)

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {"entities": {eid: r.to_dict() for eid, r in self._entities.items()}}

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], config: RoutineConfig
    ) -> "EntityRoutineModel":
        m = cls(config)
        try:
            for eid, rd in data.get("entities", {}).items():
                m._entities[eid] = EntityRoutine.from_dict(rd)
        except (KeyError, TypeError, ValueError):
            return cls(config)
        return m
