"""Ordered room chains: learning, live runs, stalls and completion timing."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent
from .slots import confidence, day_type, iso_day, median_mad

_HOPS_KEPT = 200
_COMPLETIONS_KEPT = 200
ARROW = " → "


@dataclass(frozen=True)
class ChainConfig:
    window_s: float = 900.0
    min_count: int = 10
    lift: float = 2.0
    learning_days: int = 14
    window_days: int = 28
    hop_tolerance_mads: float = 3.0
    max_chain_len: int = 6
    stall_ttl_s: float = 3600.0


@dataclass
class _Pair:
    days: dict[str, int] = field(default_factory=dict)
    hops: deque[tuple[str, float]] = field(
        default_factory=lambda: deque(maxlen=_HOPS_KEPT)
    )

    @property
    def count(self) -> int:
        return sum(self.days.values())


@dataclass
class Chain:
    rooms: list[str]
    hop_stats: list[tuple[float, float]]
    completions: dict[str, deque[tuple[str, float]]] = field(
        default_factory=lambda: {
            "weekday": deque(maxlen=_COMPLETIONS_KEPT),
            "weekend": deque(maxlen=_COMPLETIONS_KEPT),
        }
    )

    @property
    def name(self) -> str:
        return ARROW.join(self.rooms)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Chain) and other.rooms == self.rooms


@dataclass
class _Run:
    started: datetime
    step: int
    last_step_at: datetime


@dataclass
class _Stall:
    alert: Alert
    until: datetime


class ChainModel:
    def __init__(self, config: ChainConfig) -> None:
        self._cfg = config
        self._pairs: dict[tuple[str, str], _Pair] = {}
        self._steps_into: dict[str, int] = {}
        self._total_steps = 0
        self._recent: dict[str, datetime] = {}
        self._current_room: str | None = None
        self._days_seen: set[str] = set()
        self._chains: list[Chain] = []
        self._runs: dict[str, _Run] = {}
        self._stalls: dict[str, _Stall] = {}

    @property
    def chains(self) -> list[Chain]:
        return list(self._chains)

    # ------------------------------------------------------------ recording

    def record(self, event: ActivityEvent) -> None:
        if not event.is_activity:
            return
        ts, room = event.timestamp, event.room
        if room == self._current_room:
            return
        day = iso_day(ts.date())
        self._days_seen.add(day)
        for prev_room, prev_ts in list(self._recent.items()):
            age = (ts - prev_ts).total_seconds()
            if age > self._cfg.window_s:
                del self._recent[prev_room]
                continue
            if prev_room == room:
                continue
            pair = self._pairs.setdefault((prev_room, room), _Pair())
            pair.days[day] = pair.days.get(day, 0) + 1
            pair.hops.append((day, age))
        self._steps_into[room] = self._steps_into.get(room, 0) + 1
        self._total_steps += 1
        self._recent[room] = ts
        self._current_room = room
        self._advance_runs(room, ts)

    def _advance_runs(self, room: str, ts: datetime) -> None:
        for chain in self._chains:
            run = self._runs.get(chain.name)
            if run is None:
                if room == chain.rooms[0]:
                    self._runs[chain.name] = _Run(ts, 0, ts)
                continue
            nxt = run.step + 1
            if nxt < len(chain.rooms) and room == chain.rooms[nxt]:
                run.step, run.last_step_at = nxt, ts
                if nxt == len(chain.rooms) - 1:
                    dur = (ts - run.started).total_seconds()
                    chain.completions[day_type(ts.date())].append(
                        (iso_day(ts.date()), dur)
                    )
                    del self._runs[chain.name]
                    self._stalls.pop(chain.name, None)
            elif room == chain.rooms[0]:
                self._runs[chain.name] = _Run(ts, 0, ts)

    # ----------------------------------------------------------- learning

    def recompute(self) -> None:
        sig: dict[str, list[tuple[str, int]]] = {}
        preds: set[str] = set()
        total = max(1, self._total_steps)
        for (a, b), pair in self._pairs.items():
            if pair.count < self._cfg.min_count:
                continue
            steps_a = self._steps_into.get(a, 0)
            if steps_a == 0:
                continue
            p_b_given_a = pair.count / steps_a
            p_b = self._steps_into.get(b, 0) / total
            if p_b_given_a > self._cfg.lift * p_b:
                sig.setdefault(a, []).append((b, pair.count))
                preds.add(b)
        old = {c.name: c for c in self._chains}
        chains: list[Chain] = []
        for start in sorted(sig):
            if start in preds:
                continue
            rooms = [start]
            while rooms[-1] in sig and len(rooms) < self._cfg.max_chain_len:
                nxt = max(sig[rooms[-1]], key=lambda x: x[1])[0]
                if nxt in rooms:
                    break
                rooms.append(nxt)
            if len(rooms) < 2:
                continue
            stats = [
                median_mad(h for _, h in self._pairs[(rooms[i], rooms[i + 1])].hops)
                for i in range(len(rooms) - 1)
            ]
            chain = Chain(rooms, stats)
            prev = old.get(chain.name)
            if prev is not None:
                chain.completions = prev.completions
            chains.append(chain)
        self._chains = chains
        self._runs = {
            k: v for k, v in self._runs.items() if k in {c.name for c in chains}
        }

    # ------------------------------------------------------------ queries

    def evaluate(self, now: datetime) -> list[Alert]:
        for chain in self._chains:
            run = self._runs.get(chain.name)
            if run is None:
                continue
            med, mad = chain.hop_stats[run.step]
            tolerance = (
                med + self._cfg.hop_tolerance_mads * mad
                if mad > 0
                else max(med * 2, self._cfg.window_s)
            )
            if (now - run.last_step_at).total_seconds() > tolerance:
                missing = chain.rooms[run.step + 1]
                alert = Alert(
                    AlertClass.STATISTICAL,
                    chain.name,
                    "chain_stall",
                    Severity.LOW,
                    f"Routine {chain.name} started at {run.started:%H:%M} but {missing} was not reached",
                    now,
                    {"missing": missing, "step": run.step + 1},
                )
                self._stalls[chain.name] = _Stall(
                    alert, now + timedelta(seconds=self._cfg.stall_ttl_s)
                )
                del self._runs[chain.name]
        self._stalls = {k: s for k, s in self._stalls.items() if s.until > now}
        return [s.alert for s in self._stalls.values()]

    def completions_for_day(self, day: date) -> dict[str, float]:
        d = iso_day(day)
        out: dict[str, float] = {}
        for c in self._chains:
            vals = [v for dq in c.completions.values() for dd, v in dq if dd == d]
            if vals:
                out[c.name] = median_mad(vals)[0]
        return out

    def confidence(self, now: datetime) -> float:
        return confidence(len(self._days_seen), self._cfg.learning_days)

    # ------------------------------------------------------- maintenance

    def rename_room(self, old: str, new: str) -> None:
        self._pairs = {
            (new if a == old else a, new if b == old else b): p
            for (a, b), p in self._pairs.items()
        }
        if old in self._steps_into:
            self._steps_into[new] = self._steps_into.pop(old)
        if old in self._recent:
            self._recent[new] = self._recent.pop(old)
        if self._current_room == old:
            self._current_room = new
        for c in self._chains:
            c.rooms = [new if r == old else r for r in c.rooms]

    def remove_room(self, room: str) -> None:
        self._pairs = {k: p for k, p in self._pairs.items() if room not in k}
        self._steps_into.pop(room, None)
        self._recent.pop(room, None)
        self._chains = [c for c in self._chains if room not in c.rooms]
        self._runs = {
            k: v for k, v in self._runs.items() if k in {c.name for c in self._chains}
        }

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        for key in list(self._pairs):
            pair = self._pairs[key]
            pair.days = {d: c for d, c in pair.days.items() if d >= cutoff}
            kept = [(d, h) for d, h in pair.hops if d >= cutoff]
            pair.hops.clear()
            pair.hops.extend(kept)
            if pair.count == 0:
                del self._pairs[key]
        self._days_seen = {d for d in self._days_seen if d >= cutoff}
        for c in self._chains:
            for dt_key, dq in c.completions.items():
                kept_c = [(d, v) for d, v in dq if d >= cutoff]
                dq.clear()
                dq.extend(kept_c)

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "pairs": [
                {"a": a, "b": b, "days": dict(p.days), "hops": list(p.hops)}
                for (a, b), p in self._pairs.items()
            ],
            "steps_into": dict(self._steps_into),
            "total_steps": self._total_steps,
            "current_room": self._current_room,
            "days_seen": sorted(self._days_seen),
            "chains": [
                {
                    "rooms": c.rooms,
                    "hop_stats": c.hop_stats,
                    "completions": {k: list(v) for k, v in c.completions.items()},
                }
                for c in self._chains
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: ChainConfig) -> "ChainModel":
        m = cls(config)
        try:
            for p in data.get("pairs", []):
                pair = _Pair()
                for d, c in p.get("days", {}).items():
                    pair.days[str(d)] = int(c)
                pair.hops.extend((str(d), float(h)) for d, h in p.get("hops", []))
                m._pairs[(str(p["a"]), str(p["b"]))] = pair
            m._steps_into = {
                str(k): int(v) for k, v in data.get("steps_into", {}).items()
            }
            m._total_steps = int(data.get("total_steps", 0))
            m._current_room = data.get("current_room")
            m._days_seen = set(data.get("days_seen", []))
            for c in data.get("chains", []):
                chain = Chain(
                    [str(r) for r in c["rooms"]],
                    [(float(a), float(b)) for a, b in c.get("hop_stats", [])],
                )
                for k, v in c.get("completions", {}).items():
                    if k in chain.completions:
                        chain.completions[k].extend((str(d), float(x)) for d, x in v)
                m._chains.append(chain)
        except (KeyError, TypeError, ValueError):
            return cls(config)
        return m
