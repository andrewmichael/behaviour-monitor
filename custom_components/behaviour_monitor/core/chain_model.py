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
BUCKET_HOURS = 3


def bucket_of(ts: datetime) -> int:
    """Three-hour time-of-day bucket a step falls in.

    The same two rooms mean different things at different times of day: a
    bedroom-to-bathroom step at 03:00 is a night trip, at 07:00 it starts the
    morning routine. Pair statistics and chain assembly are therefore kept per
    bucket, so a frequent night pattern cannot drown out a morning one.
    """
    return ts.hour // BUCKET_HOURS


@dataclass(frozen=True)
class ChainConfig:
    window_s: float = 1800.0
    min_count: int = 10
    lift: float = 2.0
    learning_days: int = 14
    window_days: int = 28
    hop_tolerance_mads: float = 3.0
    max_chain_len: int = 6
    stall_ttl_s: float = 21600.0


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
    buckets: set[int] = field(default_factory=set)
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
        self._pairs: dict[tuple[int, str, str], _Pair] = {}
        self._steps_into: dict[tuple[int, str], dict[str, int]] = {}
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
        self._expire(ts)
        if room == self._current_room and room in self._recent:
            # Same room, still inside the window: not a new step, but it is
            # the latest sighting there, so a hop out of this room measures
            # from here and not from whenever the room was entered. Once the
            # window has passed the room is no longer current and the event
            # below starts a fresh occupancy.
            self._recent[room] = ts
            return
        day = iso_day(ts.date())
        self._days_seen.add(day)
        for prev_room, prev_ts in self._recent.items():
            if prev_room == room:
                continue
            key = (bucket_of(prev_ts), prev_room, room)
            pair = self._pairs.setdefault(key, _Pair())
            pair.days[day] = pair.days.get(day, 0) + 1
            pair.hops.append((day, (ts - prev_ts).total_seconds()))
        bucket = bucket_of(ts)
        into = self._steps_into.setdefault((bucket, room), {})
        into[day] = into.get(day, 0) + 1
        self._recent[room] = ts
        self._current_room = room
        # The person has moved, so whatever routine was stalled is moot. A
        # stall is only interesting while nothing at all is happening; the TTL
        # is just a safety cap for a house that never reports again.
        self._stalls.clear()
        self._advance_runs(room, ts)

    def _steps_in(self, bucket: int, room: str) -> int:
        return sum(self._steps_into.get((bucket, room), {}).values())

    def _bucket_totals(self) -> dict[int, int]:
        """Steps into any room, per bucket, over the days still retained."""
        totals: dict[int, int] = {}
        for (bucket, _), days in self._steps_into.items():
            totals[bucket] = totals.get(bucket, 0) + sum(days.values())
        return totals

    def _expire(self, now: datetime) -> None:
        """Forget rooms last seen longer ago than the pair window."""
        for room in [
            r
            for r, t in self._recent.items()
            if (now - t).total_seconds() > self._cfg.window_s
        ]:
            del self._recent[room]

    def _advance_runs(self, room: str, ts: datetime) -> None:
        bucket = bucket_of(ts)
        for chain in self._chains:
            run = self._runs.get(chain.name)
            starts_here = room == chain.rooms[0] and bucket in chain.buckets
            if run is None:
                if starts_here:
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
            elif starts_here:
                self._runs[chain.name] = _Run(ts, 0, ts)

    # ----------------------------------------------------------- learning

    def recompute(self) -> None:
        """Assemble chains within each time bucket, then merge equal paths."""
        old = {c.name: c for c in self._chains}
        totals = self._bucket_totals()
        order: list[tuple[str, ...]] = []
        buckets_by_path: dict[tuple[str, ...], set[int]] = {}
        for bucket in sorted({b for b, _, _ in self._pairs}):
            for rooms in self._assemble(bucket, totals.get(bucket, 0)):
                path = tuple(rooms)
                if path not in buckets_by_path:
                    buckets_by_path[path] = set()
                    order.append(path)
                buckets_by_path[path].add(bucket)
        chains: list[Chain] = []
        for path in order:
            buckets = buckets_by_path[path]
            stats = [
                median_mad(self._pooled_hops(buckets, path[i], path[i + 1]))
                for i in range(len(path) - 1)
            ]
            chain = Chain(list(path), stats, buckets)
            prev = old.get(chain.name)
            if prev is not None:
                chain.completions = prev.completions
            chains.append(chain)
        self._chains = chains
        self._runs = {
            k: v for k, v in self._runs.items() if k in {c.name for c in chains}
        }

    def _assemble(self, bucket: int, bucket_steps: int) -> list[list[str]]:
        """Significant pairs and the chains they form inside one bucket."""
        sig: dict[str, list[tuple[str, int]]] = {}
        preds: set[str] = set()
        total = max(1, bucket_steps)
        for (b, a, nxt), pair in self._pairs.items():
            if b != bucket or pair.count < self._cfg.min_count:
                continue
            steps_a = self._steps_in(bucket, a)
            if steps_a == 0:
                continue
            p_b_given_a = pair.count / steps_a
            p_b = self._steps_in(bucket, nxt) / total
            if p_b_given_a > self._cfg.lift * p_b:
                sig.setdefault(a, []).append((nxt, pair.count))
                preds.add(nxt)
        out: list[list[str]] = []
        for start in sorted(sig):
            if start in preds:
                continue
            rooms = [start]
            while rooms[-1] in sig and len(rooms) < self._cfg.max_chain_len:
                nxt_room = max(sig[rooms[-1]], key=lambda x: x[1])[0]
                if nxt_room in rooms:
                    break
                rooms.append(nxt_room)
            if len(rooms) >= 2:
                out.append(rooms)
        return out

    def _pooled_hops(self, buckets: set[int], a: str, b: str) -> list[float]:
        out: list[float] = []
        for bucket in sorted(buckets):
            pair = self._pairs.get((bucket, a, b))
            if pair is not None:
                out.extend(h for _, h in pair.hops)
        return out

    # ------------------------------------------------------------ queries

    def evaluate(self, now: datetime) -> list[Alert]:
        for chain in self._chains:
            run = self._runs.get(chain.name)
            if run is None:
                continue
            med, mad = chain.hop_stats[run.step]
            # Three times slower than usual is a routine drifting, not one
            # abandoned, and the detector needs those slow days to keep
            # arriving. Only past that is the step really missing.
            tolerance = max(
                med + self._cfg.hop_tolerance_mads * mad,
                3 * med,
                2 * self._cfg.window_s,
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

    def clear_runs(self) -> None:
        """Drop in-progress runs and stalls without touching learned chains.

        Used when a paused period (e.g. holiday) ends: a run that started
        before the pause, or a stall accumulated across it, no longer means
        anything about the resumed routine.
        """
        self._runs.clear()
        self._stalls.clear()

    def rename_room(self, old: str, new: str) -> None:
        self._pairs = {
            (bucket, new if a == old else a, new if b == old else b): p
            for (bucket, a, b), p in self._pairs.items()
        }
        self._steps_into = {
            (bucket, new if room == old else room): days
            for (bucket, room), days in self._steps_into.items()
        }
        if old in self._recent:
            self._recent[new] = self._recent.pop(old)
        if self._current_room == old:
            self._current_room = new
        for c in self._chains:
            c.rooms = [new if r == old else r for r in c.rooms]

    def remove_room(self, room: str) -> None:
        self._pairs = {k: p for k, p in self._pairs.items() if room not in (k[1], k[2])}
        self._steps_into = {k: c for k, c in self._steps_into.items() if k[1] != room}
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
        for key_s in list(self._steps_into):
            kept_s = {d: c for d, c in self._steps_into[key_s].items() if d >= cutoff}
            if kept_s:
                self._steps_into[key_s] = kept_s
            else:
                del self._steps_into[key_s]
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
                {
                    "bucket": bucket,
                    "a": a,
                    "b": b,
                    "days": dict(p.days),
                    "hops": list(p.hops),
                }
                for (bucket, a, b), p in self._pairs.items()
            ],
            "steps_into": [
                {"bucket": bucket, "room": room, "days": dict(days)}
                for (bucket, room), days in self._steps_into.items()
            ],
            # derived, for readers of the store; from_dict recomputes it
            "total_steps": {str(b): c for b, c in self._bucket_totals().items()},
            "current_room": self._current_room,
            "days_seen": sorted(self._days_seen),
            "chains": [
                {
                    "rooms": c.rooms,
                    "hop_stats": c.hop_stats,
                    "buckets": sorted(c.buckets),
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
                m._pairs[(int(p["bucket"]), str(p["a"]), str(p["b"]))] = pair
            m._steps_into = {
                (int(s["bucket"]), str(s["room"])): {
                    str(d): int(c) for d, c in s["days"].items()
                }
                for s in data.get("steps_into", [])
            }
            m._current_room = data.get("current_room")
            m._days_seen = set(data.get("days_seen", []))
            for c in data.get("chains", []):
                chain = Chain(
                    [str(r) for r in c["rooms"]],
                    [(float(a), float(b)) for a, b in c.get("hop_stats", [])],
                    {int(b) for b in c.get("buckets", [])},
                )
                for k, v in c.get("completions", {}).items():
                    if k in chain.completions:
                        chain.completions[k].extend((str(d), float(x)) for d, x in v)
                m._chains.append(chain)
        except (AttributeError, KeyError, TypeError, ValueError):
            # Any section written in an older shape (pairs without a bucket,
            # steps_into as a flat mapping, total_steps as a single int) means
            # the whole store predates bucketed chains: start clean instead of
            # half-loading it.
            return cls(config)
        return m
