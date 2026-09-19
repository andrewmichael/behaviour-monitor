"""Activity pipeline: retrigger collapse, debounce, door open duration, excursions.

Pure Python stdlib only. Zero Home Assistant imports. Sits after ``EventGate``
(stage 1) and turns gated state events into activity events that the routine
model, correlation detector and daily counter consume. State is in-memory
only: after a restart the first rising edge for every entity counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from collections.abc import Iterable, Mapping
from typing import Any

from .const import (
    DEFAULT_DOOR_DEBOUNCE_SECONDS,
    DEFAULT_DOOR_OPEN_EXTENDED_SECONDS,
    DEFAULT_DOOR_OPEN_PROLONGED_SECONDS,
    DEFAULT_EXCURSION_WINDOW_SECONDS,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
    DEFAULT_RETRIGGER_COLLAPSE_SECONDS,
    DOOR_OPEN_BRIEF,
    DOOR_OPEN_EXTENDED,
    DOOR_OPEN_PROLONGED,
    EntityRole,
)
from .routine_model import is_binary_state

ACTIVATION = "activation"
EXCURSION = "excursion"
_DROPOUT = ("unavailable", "unknown")
_EDGE_KINDS = ("motion", "door")


def classify_open_duration(seconds: float, extended: int, prolonged: int) -> str:
    """Brief below ``extended``, extended below ``prolonged``, else prolonged."""
    if seconds < extended:
        return DOOR_OPEN_BRIEF
    if seconds < prolonged:
        return DOOR_OPEN_EXTENDED
    return DOOR_OPEN_PROLONGED


@dataclass(frozen=True)
class PipelineConfig:
    """Stage thresholds in seconds. Zero disables the stage it names."""

    motion_debounce_seconds: int = DEFAULT_MOTION_DEBOUNCE_SECONDS
    door_debounce_seconds: int = DEFAULT_DOOR_DEBOUNCE_SECONDS
    retrigger_collapse_seconds: int = DEFAULT_RETRIGGER_COLLAPSE_SECONDS
    excursion_window_seconds: int = DEFAULT_EXCURSION_WINDOW_SECONDS
    door_open_extended_seconds: int = DEFAULT_DOOR_OPEN_EXTENDED_SECONDS
    door_open_prolonged_seconds: int = DEFAULT_DOOR_OPEN_PROLONGED_SECONDS


@dataclass(frozen=True)
class PipelineEvent:
    """A state change after the event gate."""

    entity_id: str
    role: EntityRole
    old_state: str | None
    new_state: str
    timestamp: datetime


@dataclass(frozen=True)
class ActivityEvent:
    """One unit of activity. ``state`` is what the routine model records."""

    entity_id: str
    role: EntityRole
    timestamp: datetime
    kind: str = ACTIVATION
    state: str = "on"
    entities: tuple[str, ...] = ()  # excursion members, in arrival order
    duration_seconds: float | None = None  # excursion span


@dataclass
class _EntityState:
    role: EntityRole | None = None
    is_on: bool | None = None  # None = unknown (never seen, or after a dropout)
    last_on: datetime | None = None  # most recent on edge, counted or not
    last_counted: datetime | None = None  # most recent counted on edge
    pending_off: datetime | None = None
    last_open_seconds: float | None = None
    last_open_class: str | None = None


@dataclass
class _Excursion:
    entity_id: str
    role: EntityRole
    anchor: datetime
    last: datetime
    entities: list[str]


def _seconds(value: int) -> timedelta:
    return timedelta(seconds=max(0, int(value)))


class ActivityPipeline:
    """Turn gated state events into activity events."""

    def __init__(self, config: PipelineConfig) -> None:
        self._cfg = config
        self._motion = _seconds(config.motion_debounce_seconds)
        self._door = _seconds(config.door_debounce_seconds)
        self._collapse = _seconds(config.retrigger_collapse_seconds)
        self._excursion_window = _seconds(config.excursion_window_seconds)
        self._states: dict[str, _EntityState] = {}
        self._excursion: _Excursion | None = None

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def submit(self, event: PipelineEvent) -> list[ActivityEvent]:
        """Feed one gated event; return the activity events it produced."""
        st = self._states.setdefault(event.entity_id, _EntityState())
        st.role = event.role
        sv = event.new_state
        if sv.lower() in _DROPOUT:
            st.is_on = None
            st.pending_off = None
            return []
        if event.role.kind not in _EDGE_KINDS or not is_binary_state(sv):
            return [
                ActivityEvent(event.entity_id, event.role, event.timestamp, state=sv)
            ]
        prev_on = st.is_on
        if prev_on is None:
            prev_on = event.old_state is not None and event.old_state.lower() == "on"
        if sv.lower() == "on":
            return self._on_edge(event, st, prev_on)
        return self._off_edge(event, st, prev_on)

    def _on_edge(
        self, event: PipelineEvent, st: _EntityState, prev_on: bool
    ) -> list[ActivityEvent]:
        if st.pending_off is not None:
            if self._collapse and event.timestamp - st.pending_off < self._collapse:
                # off/on bounce: the entity never really turned off
                st.pending_off = None
                st.is_on = True
                return []
            self._confirm_off(st, st.pending_off)
            prev_on = False
        if prev_on:
            st.is_on = True
            return []
        st.is_on = True
        st.last_on = event.timestamp
        window = self._motion if event.role.kind == "motion" else self._door
        if (
            st.last_counted is not None
            and window
            and event.timestamp - st.last_counted < window
        ):
            return []
        st.last_counted = event.timestamp
        if event.role is EntityRole.DOOR_EXTERIOR and self._excursion_window:
            return self._join_excursion(event)
        return [ActivityEvent(event.entity_id, event.role, event.timestamp)]

    def _join_excursion(self, event: PipelineEvent) -> list[ActivityEvent]:
        ex = self._excursion
        if ex is not None and event.timestamp - ex.anchor < self._excursion_window:
            ex.entities.append(event.entity_id)
            ex.last = event.timestamp
            return []
        out = [self._close_excursion()] if ex is not None else []
        self._excursion = _Excursion(
            event.entity_id,
            event.role,
            event.timestamp,
            event.timestamp,
            [event.entity_id],
        )
        return out

    def _close_excursion(self) -> ActivityEvent:
        ex = self._excursion
        assert ex is not None
        self._excursion = None
        return ActivityEvent(
            ex.entity_id,
            ex.role,
            ex.anchor,
            kind=EXCURSION,
            entities=tuple(ex.entities),
            duration_seconds=(ex.last - ex.anchor).total_seconds(),
        )

    def _off_edge(
        self, event: PipelineEvent, st: _EntityState, prev_on: bool
    ) -> list[ActivityEvent]:
        st.is_on = False
        if not prev_on:
            return []
        if self._collapse:
            st.pending_off = event.timestamp
        else:
            self._confirm_off(st, event.timestamp)
        return []

    def _confirm_off(self, st: _EntityState, off_at: datetime) -> None:
        """The off edge is real: close the open interval for door roles."""
        st.pending_off = None
        if st.role is None or st.role.kind != "door" or st.last_on is None:
            return
        seconds = (off_at - st.last_on).total_seconds()
        st.last_open_seconds = seconds
        st.last_open_class = classify_open_duration(
            seconds,
            self._cfg.door_open_extended_seconds,
            self._cfg.door_open_prolonged_seconds,
        )

    # ------------------------------------------------------------------
    # Flush and status
    # ------------------------------------------------------------------

    def flush(self, now: datetime, *, force: bool = False) -> list[ActivityEvent]:
        """Release time-dependent output. ``force`` releases everything."""
        out: list[ActivityEvent] = []
        for st in self._states.values():
            if st.pending_off is not None and (
                force or now - st.pending_off >= self._collapse
            ):
                self._confirm_off(st, st.pending_off)
        ex = self._excursion
        if ex is not None and (force or now - ex.anchor >= self._excursion_window):
            out.append(self._close_excursion())
        return out

    def door_status(self, entity_id: str) -> dict[str, Any]:
        st = self._states.get(entity_id)
        return {
            "last_open_seconds": st.last_open_seconds if st else None,
            "last_open_class": st.last_open_class if st else None,
        }

    def seed_door_status(self, statuses: Mapping[str, Mapping[str, Any]]) -> None:
        """Restore per-door open-duration status (used after a recorder replay)."""
        for eid, status in statuses.items():
            st = self._states.setdefault(eid, _EntityState())
            st.last_open_seconds = status.get("last_open_seconds")
            st.last_open_class = status.get("last_open_class")


def replay(
    events: Iterable[PipelineEvent], config: PipelineConfig
) -> tuple[list[ActivityEvent], dict[str, dict[str, Any]]]:
    """Run one pipeline over a whole event list (recorder bootstrap, CLI).

    Events are sorted by timestamp; the pipeline is flushed at each event's
    timestamp so time-dependent stages advance, and force-flushed at the end.
    Returns the activity events and ``door_status`` for every door entity seen.
    """
    pipeline = ActivityPipeline(config)
    out: list[ActivityEvent] = []
    doors: set[str] = set()
    last: datetime | None = None
    for ev in sorted(events, key=lambda e: e.timestamp):
        if ev.role.kind == "door":
            doors.add(ev.entity_id)
        out.extend(pipeline.submit(ev))
        out.extend(pipeline.flush(ev.timestamp))
        last = ev.timestamp
    if last is not None:
        out.extend(pipeline.flush(last, force=True))
    return out, {eid: pipeline.door_status(eid) for eid in sorted(doors)}
