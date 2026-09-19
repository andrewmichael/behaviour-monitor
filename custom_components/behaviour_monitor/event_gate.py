"""Start-up grace period and same-second burst discard for state events.

Pure Python stdlib only. Zero Home Assistant imports. Integration reloads and
Home Assistant restarts write synthetic states to every entity at once; this
gate drops events during a grace window after setup and drops any one-second
bucket in which too many distinct entities change together.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class GatedEvent:
    entity_id: str
    old_state: str | None
    new_state: str
    timestamp: datetime


class EventGate:
    """Buffer state events by wall-clock second and discard artifacts."""

    def __init__(self, grace_seconds: int, burst_threshold: int) -> None:
        self._grace = timedelta(seconds=max(0, int(grace_seconds)))
        self._threshold = max(0, int(burst_threshold))
        self._grace_until: datetime | None = None
        self._buckets: dict[int, list[GatedEvent]] = {}
        self._dropped_bursts = 0

    def arm(self, now: datetime) -> None:
        """Start the grace window at ``now`` (no-op when grace is 0)."""
        self._grace_until = now + self._grace if self._grace else None

    def in_grace(self, now: datetime) -> bool:
        return self._grace_until is not None and now < self._grace_until

    def submit(
        self, entity_id: str, old_state: str | None, new_state: str, now: datetime
    ) -> bool:
        """Buffer an event. Returns False when it was dropped by the grace window."""
        if self.in_grace(now):
            return False
        key = int(now.timestamp())
        self._buckets.setdefault(key, []).append(
            GatedEvent(entity_id, old_state, new_state, now)
        )
        return True

    def flush(
        self, now: datetime, *, force: bool = False
    ) -> tuple[list[GatedEvent], list[GatedEvent]]:
        """Release buckets for seconds earlier than ``now`` (all when ``force``).

        A bucket in which at least ``burst_threshold`` distinct entities appear
        is dropped entirely and counted in ``dropped_bursts``. Returns
        ``(kept, dropped)``: the caller still owes dropped events a
        last-seen update, just not learning, correlation or the daily count.
        """
        current = int(now.timestamp())
        out: list[GatedEvent] = []
        dropped: list[GatedEvent] = []
        for key in sorted(self._buckets):
            if not force and key >= current:
                continue
            events = self._buckets.pop(key)
            distinct = {e.entity_id for e in events}
            if self._threshold and len(distinct) >= self._threshold:
                self._dropped_bursts += 1
                dropped.extend(events)
                continue
            out.extend(events)
        return out, dropped

    @property
    def pending(self) -> int:
        return sum(len(v) for v in self._buckets.values())

    @property
    def dropped_bursts(self) -> int:
        return self._dropped_bursts
