"""Device health: unavailable, site-wide dropout, silent sensor, panic liveness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent, Category, HealthEvent
from .slots import iso_day


@dataclass(frozen=True)
class HealthConfig:
    grace_s: float = 900.0
    silent_multiplier: float = 3.0
    sitewide_fraction: float = 0.5
    sitewide_window_s: float = 60.0


@dataclass
class _EntityHealth:
    category: Category
    room: str
    down_since: datetime | None = None
    last_event: datetime | None = None
    silent: bool = False


def _dt(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


class HealthTracker:
    def __init__(self, config: HealthConfig) -> None:
        self._cfg = config
        self._ent: dict[str, _EntityHealth] = {}
        self._recent_downs: list[tuple[str, datetime]] = []
        self._sitewide_open: datetime | None = None
        self._sitewide_by_day: dict[str, int] = {}

    # ----------------------------------------------------------- membership

    def register(self, entity_id: str, category: Category, room: str) -> None:
        cur = self._ent.get(entity_id)
        if cur is None:
            self._ent[entity_id] = _EntityHealth(category, room)
        else:
            cur.category, cur.room = category, room

    def remove(self, entity_id: str) -> None:
        self._ent.pop(entity_id, None)
        self._recent_downs = [(e, t) for e, t in self._recent_downs if e != entity_id]

    # ------------------------------------------------------------ recording

    def record_health(self, event: HealthEvent) -> None:
        e = self._ent.get(event.entity_id)
        if e is None:
            return
        if event.available:
            e.down_since = None
        elif e.down_since is None:
            e.down_since = event.timestamp
            self._recent_downs.append((event.entity_id, event.timestamp))
            self._maybe_open_sitewide(event.timestamp)

    def record_activity(self, event: ActivityEvent) -> None:
        e = self._ent.get(event.entity_id)
        if e is not None and (e.last_event is None or event.timestamp > e.last_event):
            e.last_event = event.timestamp

    def _maybe_open_sitewide(self, now: datetime) -> None:
        self._recent_downs = [
            (e, t) for e, t in self._recent_downs if (now - t).total_seconds() <= self._cfg.sitewide_window_s
        ]
        if not self._ent:
            return
        if (
            len({e for e, _ in self._recent_downs}) > self._cfg.sitewide_fraction * len(self._ent)
            and self._sitewide_open is None
        ):
            self._sitewide_open = now
            day = iso_day(now.date())
            self._sitewide_by_day[day] = self._sitewide_by_day.get(day, 0) + 1

    # -------------------------------------------------------------- queries

    def _unavailable(self, now: datetime) -> set[str]:
        return {
            eid
            for eid, e in self._ent.items()
            if e.down_since is not None and (now - e.down_since).total_seconds() > self._cfg.grace_s
        }

    def _silent(
        self, now: datetime, longest_gap: Callable[[str], float | None], house_last: datetime | None
    ) -> dict[str, float]:
        out: dict[str, float] = {}
        if house_last is None:
            return out
        for eid, e in self._ent.items():
            if e.category is Category.PANIC or e.last_event is None or e.down_since is not None:
                continue
            gap = longest_gap(eid)
            if gap is None or gap <= 0:
                continue
            silent = (now - e.last_event).total_seconds()
            if silent > self._cfg.silent_multiplier * gap and house_last > e.last_event:
                out[eid] = silent
        return out

    def down_entities(self, now: datetime) -> set[str]:
        return self._unavailable(now) | {eid for eid, e in self._ent.items() if e.silent}

    def live_fraction(self, now: datetime) -> float:
        if not self._ent:
            return 1.0
        return 1.0 - len(self.down_entities(now)) / len(self._ent)

    def sitewide_dropouts_today(self, day: date) -> int:
        return self._sitewide_by_day.get(iso_day(day), 0)

    def entity_states(self, now: datetime) -> dict[str, str]:
        unavail = self._unavailable(now)
        return {
            eid: "unavailable" if eid in unavail else ("silent" if e.silent else "ok")
            for eid, e in self._ent.items()
        }

    def evaluate(
        self,
        now: datetime,
        longest_gap: Callable[[str], float | None],
        house_last_activity: datetime | None,
    ) -> list[Alert]:
        out: list[Alert] = []
        down_now = {eid for eid, e in self._ent.items() if e.down_since is not None}
        if self._sitewide_open is not None:
            if len(down_now) <= self._cfg.sitewide_fraction * len(self._ent):
                self._sitewide_open = None
            else:
                out.append(
                    Alert(
                        AlertClass.HEALTH,
                        "site",
                        "dropout",
                        Severity.MEDIUM,
                        f"{len(down_now)} of {len(self._ent)} sensors went unavailable together",
                        now,
                        {"count": len(down_now)},
                    )
                )
        for eid in sorted(self._unavailable(now)):
            e = self._ent[eid]
            sev = Severity.HIGH if e.category is Category.PANIC else Severity.MEDIUM
            out.append(
                Alert(
                    AlertClass.HEALTH,
                    eid,
                    "unavailable",
                    sev,
                    f"{e.room}: {eid} has been unavailable since {e.down_since:%H:%M}",
                    now,
                    {"since": e.down_since.isoformat() if e.down_since else None, "room": e.room},
                )
            )
        silent = self._silent(now, longest_gap, house_last_activity)
        for eid, e in self._ent.items():
            e.silent = eid in silent
        for eid, secs in sorted(silent.items()):
            e = self._ent[eid]
            out.append(
                Alert(
                    AlertClass.HEALTH,
                    eid,
                    "silent",
                    Severity.MEDIUM,
                    f"{e.room}: {eid} has reported nothing for {secs / 3600:.1f} h while the house was active",
                    now,
                    {"silent_s": secs, "room": e.room},
                )
            )
        return out

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": {
                eid: {
                    "category": e.category.value,
                    "room": e.room,
                    "down_since": e.down_since.isoformat() if e.down_since else None,
                    "last_event": e.last_event.isoformat() if e.last_event else None,
                }
                for eid, e in self._ent.items()
            },
            "sitewide_open": self._sitewide_open.isoformat() if self._sitewide_open else None,
            "sitewide_by_day": dict(self._sitewide_by_day),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: HealthConfig) -> "HealthTracker":
        t = cls(config)
        try:
            for eid, e in data.get("entities", {}).items():
                t._ent[eid] = _EntityHealth(
                    Category(e["category"]),
                    str(e.get("room", "")),
                    _dt(e.get("down_since")),
                    _dt(e.get("last_event")),
                )
            t._sitewide_open = _dt(data.get("sitewide_open"))
            t._sitewide_by_day = {str(k): int(v) for k, v in data.get("sitewide_by_day", {}).items()}
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return t
