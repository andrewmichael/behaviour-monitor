"""Turn raw state changes into typed ActivityEvent / HealthEvent values."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any

from .events import ActivityEvent, Category, EventKind, HealthEvent, UNAVAILABLE_STATES

_ON = "on"
_OFF = "off"


@dataclass(frozen=True)
class NormaliserConfig:
    motion_debounce_s: float = 90.0
    plug_margin_w: float = 5.0
    plug_min_samples: int = 50
    plug_reservoir: int = 500


@dataclass
class _Burst:
    entity_id: str
    room: str
    start: datetime
    last_rise: datetime
    last_fall: datetime | None = None


@dataclass
class _PlugState:
    reservoir: deque[float]
    on_since: datetime | None = None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class Normaliser:
    """Stateful per-entity normalisation. One instance per site."""

    def __init__(self, config: NormaliserConfig) -> None:
        self._cfg = config
        self._bursts: dict[str, _Burst] = {}
        self._open_since: dict[str, datetime] = {}
        self._plugs: dict[str, _PlugState] = {}
        self._available: dict[str, bool] = {}

    # ------------------------------------------------------------------ public

    def handle(
        self,
        entity_id: str,
        category: Category,
        room: str,
        old_state: str | None,
        new_state: str,
        timestamp: datetime,
    ) -> list[ActivityEvent | HealthEvent]:
        new_unavail = new_state in UNAVAILABLE_STATES
        old_unavail = old_state is None or old_state in UNAVAILABLE_STATES

        if new_unavail:
            if self._available.get(entity_id, True):
                self._available[entity_id] = False
                return [
                    HealthEvent(entity_id, category, room, timestamp, available=False)
                ]
            return []

        out: list[ActivityEvent | HealthEvent] = []
        was_available = self._available.get(entity_id, not old_unavail)
        if not was_available:
            self._available[entity_id] = True
            out.append(
                HealthEvent(entity_id, category, room, timestamp, available=True)
            )
        if old_unavail:
            # restore of a real state is not the person acting
            return out
        if old_state == new_state:
            return out

        handler = {
            Category.MOTION: self._motion,
            Category.CONTACT: self._contact,
            Category.PLUG: self._plug,
            Category.PANIC: self._panic,
            Category.LIGHT: self._light,
            Category.OTHER: self._other,
        }[category]
        out.extend(handler(entity_id, room, old_state, new_state, timestamp))
        return out

    def flush(self, now: datetime) -> list[ActivityEvent]:
        """Close motion bursts whose last fall is older than the debounce window."""
        out: list[ActivityEvent] = []
        for eid in list(self._bursts):
            b = self._bursts[eid]
            if b.last_fall is None:
                continue
            if (now - b.last_fall).total_seconds() > self._cfg.motion_debounce_s:
                out.append(self._close_burst(b))
                del self._bursts[eid]
        return out

    def forget(self, entity_id: str) -> None:
        for store in (self._bursts, self._open_since, self._plugs, self._available):
            store.pop(entity_id, None)  # type: ignore[arg-type]

    # -------------------------------------------------------------- categories

    def _motion(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        out: list[ActivityEvent] = []
        burst = self._bursts.get(eid)
        if new == _ON:
            if burst is not None:
                if (
                    ts - burst.last_rise
                ).total_seconds() <= self._cfg.motion_debounce_s:
                    burst.last_rise = ts
                    burst.last_fall = None
                    return []
                out.append(self._close_burst(burst))
            self._bursts[eid] = _Burst(eid, room, ts, ts)
            out.append(
                ActivityEvent(eid, Category.MOTION, EventKind.PRESENCE, room, ts)
            )
        elif new == _OFF and burst is not None:
            burst.last_fall = ts
        return out

    def _close_burst(self, b: _Burst) -> ActivityEvent:
        end = b.last_fall or b.last_rise
        return ActivityEvent(
            b.entity_id,
            Category.MOTION,
            EventKind.BURST_END,
            b.room,
            end,
            duration_s=(end - b.start).total_seconds(),
        )

    def _contact(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        if new == _ON:
            self._open_since[eid] = ts
            return [ActivityEvent(eid, Category.CONTACT, EventKind.OPEN, room, ts)]
        if new == _OFF:
            opened = self._open_since.pop(eid, None)
            dur = (ts - opened).total_seconds() if opened else None
            return [
                ActivityEvent(
                    eid, Category.CONTACT, EventKind.CLOSE, room, ts, duration_s=dur
                )
            ]
        return []

    def _panic(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        if new == _ON:
            return [
                ActivityEvent(
                    eid, Category.PANIC, EventKind.PANIC, room, ts, bypass=True
                )
            ]
        if new == _OFF:
            return [
                ActivityEvent(eid, Category.PANIC, EventKind.PANIC_RELEASE, room, ts)
            ]
        return []

    def _light(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        if new == _ON:
            return [ActivityEvent(eid, Category.LIGHT, EventKind.LIGHT_ON, room, ts)]
        if new == _OFF:
            return [ActivityEvent(eid, Category.LIGHT, EventKind.LIGHT_OFF, room, ts)]
        return []

    def _other(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        return [ActivityEvent(eid, Category.OTHER, EventKind.GENERIC, room, ts)]

    def _plug(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        if new in (_ON, _OFF):
            return self._plug_switch(eid, room, new, ts)
        try:
            value = float(new)
        except (TypeError, ValueError):
            return []
        state = self._plugs.get(eid)
        if state is None:
            state = _PlugState(deque(maxlen=self._cfg.plug_reservoir))
            self._plugs[eid] = state
        state.reservoir.append(value)
        idle = self._idle(state)
        threshold = idle + self._cfg.plug_margin_w
        if state.on_since is None and value > threshold:
            state.on_since = ts
            return [ActivityEvent(eid, Category.PLUG, EventKind.APPLIANCE_ON, room, ts)]
        if state.on_since is not None and value <= threshold:
            dur = (ts - state.on_since).total_seconds()
            state.on_since = None
            return [
                ActivityEvent(
                    eid,
                    Category.PLUG,
                    EventKind.APPLIANCE_OFF,
                    room,
                    ts,
                    duration_s=dur,
                )
            ]
        return []

    def _plug_switch(
        self, eid: str, room: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        state = self._plugs.setdefault(
            eid, _PlugState(deque(maxlen=self._cfg.plug_reservoir))
        )
        if new == _ON and state.on_since is None:
            state.on_since = ts
            return [ActivityEvent(eid, Category.PLUG, EventKind.APPLIANCE_ON, room, ts)]
        if new == _OFF and state.on_since is not None:
            dur = (ts - state.on_since).total_seconds()
            state.on_since = None
            return [
                ActivityEvent(
                    eid,
                    Category.PLUG,
                    EventKind.APPLIANCE_OFF,
                    room,
                    ts,
                    duration_s=dur,
                )
            ]
        return []

    def _idle(self, state: _PlugState) -> float:
        vals = sorted(state.reservoir)
        if len(vals) < self._cfg.plug_min_samples:
            return vals[0] if vals else 0.0
        quintile = vals[: max(1, len(vals) // 5)]
        return float(median(quintile))

    def idle_level(self, entity_id: str) -> float | None:
        state = self._plugs.get(entity_id)
        return self._idle(state) if state and state.reservoir else None

    # ------------------------------------------------------------ persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "bursts": {
                eid: {
                    "room": b.room,
                    "start": b.start.isoformat(),
                    "last_rise": b.last_rise.isoformat(),
                    "last_fall": b.last_fall.isoformat() if b.last_fall else None,
                }
                for eid, b in self._bursts.items()
            },
            "open_since": {eid: ts.isoformat() for eid, ts in self._open_since.items()},
            "plugs": {
                eid: {
                    "reservoir": list(p.reservoir),
                    "on_since": p.on_since.isoformat() if p.on_since else None,
                }
                for eid, p in self._plugs.items()
            },
            "available": dict(self._available),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: NormaliserConfig) -> "Normaliser":
        n = cls(config)
        try:
            for eid, b in data.get("bursts", {}).items():
                start, rise = _parse_dt(b.get("start")), _parse_dt(b.get("last_rise"))
                if start and rise:
                    n._bursts[eid] = _Burst(
                        eid,
                        str(b.get("room", "")),
                        start,
                        rise,
                        _parse_dt(b.get("last_fall")),
                    )
            for eid, ts in data.get("open_since", {}).items():
                if (dt := _parse_dt(ts)) is not None:
                    n._open_since[eid] = dt
            for eid, p in data.get("plugs", {}).items():
                res: deque[float] = deque(maxlen=config.plug_reservoir)
                res.extend(float(v) for v in p.get("reservoir", []))
                n._plugs[eid] = _PlugState(res, _parse_dt(p.get("on_since")))
            n._available = {k: bool(v) for k, v in data.get("available", {}).items()}
        except (AttributeError, TypeError, ValueError):
            return cls(config)
        return n
