"""Activity pipeline: retrigger collapse, debounce, door open duration, excursions.

Pure Python stdlib only. Zero Home Assistant imports. Sits after ``EventGate``
(stage 1) and turns gated state events into activity events that the routine
model, correlation detector and daily counter consume. State is in-memory
only: after a restart the first rising edge for every entity counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .const import (
    DEFAULT_DOOR_DEBOUNCE_SECONDS,
    DEFAULT_DOOR_OPEN_EXTENDED_SECONDS,
    DEFAULT_DOOR_OPEN_PROLONGED_SECONDS,
    DEFAULT_EXCURSION_WINDOW_SECONDS,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
    DEFAULT_RETRIGGER_COLLAPSE_SECONDS,
    EntityRole,
)
from .routine_model import is_binary_state

ACTIVATION = "activation"
EXCURSION = "excursion"
_DROPOUT = ("unavailable", "unknown")
_EDGE_KINDS = ("motion", "door")


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
        return [ActivityEvent(event.entity_id, event.role, event.timestamp)]

    def _off_edge(
        self, event: PipelineEvent, st: _EntityState, prev_on: bool
    ) -> list[ActivityEvent]:
        st.is_on = False
        return []

    # ------------------------------------------------------------------
    # Flush
    # ------------------------------------------------------------------

    def flush(self, now: datetime, *, force: bool = False) -> list[ActivityEvent]:
        """Release time-dependent output. ``force`` releases everything."""
        return []
