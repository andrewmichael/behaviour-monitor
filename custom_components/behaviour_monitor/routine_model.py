"""RoutineModel — Per-entity baseline learning engine.

Pure Python stdlib only. Zero Home Assistant imports.
All datetime objects are passed as parameters; no HA utilities used here.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from math import sqrt
from statistics import median
from typing import Any

from .const import ActivityTier, TIER_BOUNDARY_HIGH, TIER_BOUNDARY_LOW

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_SLOT_OBSERVATIONS: int = 4
"""Minimum events in a slot before detection activates (sparse slot guard)."""

SLOTS_PER_ENTITY: int = 168
"""7 days × 24 hours = 168 hour-of-day × day-of-week slots per entity."""

DEFAULT_HISTORY_WINDOW_DAYS: int = 28
"""Default rolling history window for confidence calculation."""

BINARY_STATES: frozenset[str] = frozenset(
    {"on", "off", "open", "closed", "locked", "unlocked"}
)
"""Canonical binary state values (lower-cased)."""

_DEQUE_MAXLEN: int = 56
"""Maximum number of event timestamps stored per slot (2 observations/day × 28 days)."""


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def is_binary_state(state_value: str) -> bool:
    """Return True if state_value represents a binary entity state.

    Case-insensitive. Numeric strings, "idle", "unavailable", etc. return False.
    """
    return state_value.lower() in BINARY_STATES


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string.

    Returns minutes only for sub-hour durations (e.g. "45m"),
    hours and minutes for longer durations (e.g. "2h 15m").
    No day rollover — 25 hours is "25h 0m", not "1d 1h 0m".
    """
    total_seconds = int(seconds)
    total_minutes = total_seconds // 60
    if total_minutes < 60:
        return f"{total_minutes}m"
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours}h {minutes}m"


# ---------------------------------------------------------------------------
# ActivitySlot
# ---------------------------------------------------------------------------


@dataclass
class ActivitySlot:
    """Per-entity, per-hour-of-day × day-of-week observation store.

    Binary entities: tracks ISO timestamp strings in a bounded deque.
    Numeric entities: tracks (mean, M2, count) via Welford online algorithm.
    A slot may contain both types if an entity changes character, but in
    practice each EntityRoutine is typed (is_binary) so only one path is used.
    """

    # Binary fields
    event_times: deque[str] = field(
        default_factory=lambda: deque(maxlen=_DEQUE_MAXLEN)
    )

    # Numeric fields (Welford online algorithm accumulators)
    numeric_mean: float = 0.0
    numeric_m2: float = 0.0
    numeric_count: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_sufficient(self) -> bool:
        """True when at least MIN_SLOT_OBSERVATIONS have been recorded."""
        return (
            len(self.event_times) >= MIN_SLOT_OBSERVATIONS
            or self.numeric_count >= MIN_SLOT_OBSERVATIONS
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_binary(self, iso_timestamp: str) -> None:
        """Append an ISO timestamp string to the event_times deque."""
        self.event_times.append(iso_timestamp)

    def record_numeric(self, value: float) -> None:
        """Update Welford online accumulators with a new numeric observation."""
        self.numeric_count += 1
        delta = value - self.numeric_mean
        self.numeric_mean += delta / self.numeric_count
        delta2 = value - self.numeric_mean
        self.numeric_m2 += delta * delta2

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def expected_gap_seconds(self) -> float | None:
        """Return median inter-event interval in seconds.

        Returns None when the slot has fewer than MIN_SLOT_OBSERVATIONS events,
        or when there are no numeric events (wrong entity type).
        If the slot has sufficient binary events but only 1 event (no intervals
        possible), returns None as well.
        """
        if len(self.event_times) < MIN_SLOT_OBSERVATIONS:
            return None
        # Parse timestamps and compute inter-event intervals
        try:
            times = sorted(
                datetime.fromisoformat(ts) for ts in self.event_times
            )
        except (ValueError, TypeError):
            return None
        intervals = [
            (times[i + 1] - times[i]).total_seconds()
            for i in range(len(times) - 1)
        ]
        if not intervals:
            return None
        return float(median(intervals))

    def interval_cv(self) -> float | None:
        """Return the coefficient of variation (stdev/mean) of inter-event intervals.

        Returns None when the slot has fewer than MIN_SLOT_OBSERVATIONS events,
        when timestamps cannot be parsed, or when fewer than 2 intervals are
        available (stdev is undefined for a single-element list).
        Returns 0.0 when mean is zero (all events at identical timestamps).
        """
        if len(self.event_times) < MIN_SLOT_OBSERVATIONS:
            return None
        try:
            times = sorted(
                datetime.fromisoformat(ts) for ts in self.event_times
            )
        except (ValueError, TypeError):
            return None
        intervals = [
            (times[i + 1] - times[i]).total_seconds()
            for i in range(len(times) - 1)
        ]
        if len(intervals) < 2:
            return None
        from statistics import mean, stdev

        m = mean(intervals)
        if m == 0.0:
            return 0.0
        return stdev(intervals) / m

    def slot_distribution(self) -> tuple[float, float] | None:
        """Return (mean, stdev) for numeric observations.

        Returns None when fewer than MIN_SLOT_OBSERVATIONS numeric values have
        been recorded.
        stdev = sqrt(M2 / count) (population stdev). Returns 0.0 when count <= 1.
        """
        if self.numeric_count < MIN_SLOT_OBSERVATIONS:
            return None
        stdev = (
            sqrt(self.numeric_m2 / self.numeric_count)
            if self.numeric_count > 1
            else 0.0
        )
        return (self.numeric_mean, stdev)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "event_times": list(self.event_times),
            "numeric_mean": self.numeric_mean,
            "numeric_m2": self.numeric_m2,
            "numeric_count": self.numeric_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivitySlot":
        """Restore from a serialized dict."""
        slot = cls()
        for ts in data.get("event_times", []):
            slot.event_times.append(ts)
        slot.numeric_mean = float(data.get("numeric_mean", 0.0))
        slot.numeric_m2 = float(data.get("numeric_m2", 0.0))
        slot.numeric_count = int(data.get("numeric_count", 0))
        return slot


# ---------------------------------------------------------------------------
# EntityRoutine
# ---------------------------------------------------------------------------


@dataclass
class EntityRoutine:
    """Baseline model for a single monitored entity.

    Holds 168 ActivitySlot instances indexed by (day-of-week, hour-of-day).
    """

    entity_id: str
    is_binary: bool
    slots: list[ActivitySlot] = field(
        default_factory=lambda: [ActivitySlot() for _ in range(SLOTS_PER_ENTITY)]
    )
    history_window_days: int = DEFAULT_HISTORY_WINDOW_DAYS
    first_observation: str | None = None

    # Tier classification state (not serialized — recomputed on startup)
    _activity_tier: ActivityTier | None = field(
        default=None, init=False, repr=False
    )
    _tier_classified_date: date | None = field(
        default=None, init=False, repr=False
    )

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    @staticmethod
    def slot_index(hour: int, dow: int) -> int:
        """Return the flat slot index for (hour, day-of-week).

        Args:
            hour: 0–23 (hour of day, UTC).
            dow: 0–6 (0=Monday per Python datetime.weekday()).

        Returns:
            Integer in range [0, 167].
        """
        return dow * 24 + hour

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, timestamp: datetime, state_value: str) -> None:
        """Record a state change observation into the appropriate slot.

        Sets first_observation on the first call.
        """
        if self.first_observation is None:
            self.first_observation = timestamp.isoformat()

        idx = self.slot_index(hour=timestamp.hour, dow=timestamp.weekday())
        slot = self.slots[idx]

        if self.is_binary:
            slot.record_binary(timestamp.isoformat())
        else:
            try:
                value = float(state_value)
                slot.record_numeric(value)
            except (ValueError, TypeError):
                # Cannot parse as float — skip silently
                pass

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def expected_gap_seconds(self, hour: int, dow: int) -> float | None:
        """Return median inter-event interval for the specified slot.

        Returns None when the slot has insufficient data.
        """
        return self.slots[self.slot_index(hour, dow)].expected_gap_seconds()

    def interval_cv(self, hour: int, dow: int) -> float | None:
        """Return the coefficient of variation for the specified slot.

        Returns None when the slot has insufficient data or fewer than 2 intervals.
        Returns 0.0 when mean is zero.
        """
        return self.slots[self.slot_index(hour, dow)].interval_cv()

    def daily_activity_rate(self, target_date: date) -> int:
        """Count the number of state change events recorded on target_date.

        Counts across all 24 hour-slots for the day-of-week matching target_date,
        filtering event_times that fall on the exact calendar date.
        """
        target_dow = target_date.weekday()
        count = 0
        for hour in range(24):
            slot = self.slots[self.slot_index(hour, target_dow)]
            for ts_str in slot.event_times:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    if dt.date() == target_date:
                        count += 1
                except (ValueError, TypeError):
                    pass
        return count

    def confidence(self, now: datetime) -> float:
        """Return 0.0–1.0 confidence based on observation history vs window.

        0.0 if no observations; proportional otherwise; capped at 1.0.
        """
        if self.first_observation is None:
            return 0.0
        try:
            first_dt = datetime.fromisoformat(self.first_observation)
            # Ensure both datetimes are comparable (both tz-aware or both naive)
            if first_dt.tzinfo is not None and now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            elif first_dt.tzinfo is None and now.tzinfo is not None:
                first_dt = first_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return 0.0

        days_elapsed = (now - first_dt).total_seconds() / 86400.0
        return min(1.0, days_elapsed / self.history_window_days)

    # ------------------------------------------------------------------
    # Tier classification
    # ------------------------------------------------------------------

    @property
    def activity_tier(self) -> ActivityTier | None:
        """Return the current activity tier, or None if unclassified."""
        return self._activity_tier

    def _compute_median_daily_rate(self) -> float | None:
        """Compute the median daily event rate across all slots.

        Scans all slots' event_times deques, groups by calendar date,
        and returns the median of the per-date event counts.
        Returns None if no dates are found.
        """
        date_counts: dict[date, int] = {}
        for slot in self.slots:
            for ts_str in slot.event_times:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    d = dt.date()
                    date_counts[d] = date_counts.get(d, 0) + 1
                except (ValueError, TypeError):
                    pass
        if not date_counts:
            return None
        return float(median(list(date_counts.values())))

    def classify_tier(self, now: datetime) -> None:
        """Classify entity into an activity tier based on median daily event rate.

        Gates on confidence >= 0.8. Recomputes at most once per calendar day.
        Logs tier changes at DEBUG level.
        """
        # Confidence gate
        if self.confidence(now) < 0.8:
            self._activity_tier = None
            return

        # Once-per-day guard
        if self._tier_classified_date == now.date():
            return

        # Compute median rate
        median_rate = self._compute_median_daily_rate()
        if median_rate is None:
            self._activity_tier = None
            self._tier_classified_date = now.date()
            return

        # Map rate to tier
        if median_rate >= TIER_BOUNDARY_HIGH:
            new_tier = ActivityTier.HIGH
        elif median_rate <= TIER_BOUNDARY_LOW:
            new_tier = ActivityTier.LOW
        else:
            new_tier = ActivityTier.MEDIUM

        # Log tier changes (skip first classification)
        old_tier = self._activity_tier
        if old_tier is not None and old_tier != new_tier:
            _LOGGER.debug(
                "Tier reclassified for %s: %s -> %s (median_rate=%.1f)",
                self.entity_id,
                old_tier.value,
                new_tier.value,
                median_rate,
            )

        self._activity_tier = new_tier
        self._tier_classified_date = now.date()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "entity_id": self.entity_id,
            "is_binary": self.is_binary,
            "history_window_days": self.history_window_days,
            "first_observation": self.first_observation,
            "slots": [slot.to_dict() for slot in self.slots],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityRoutine":
        """Restore from a serialized dict."""
        slots = [
            ActivitySlot.from_dict(s) for s in data.get("slots", [])
        ]
        # Pad with empty slots if fewer than expected (forward-compat guard)
        while len(slots) < SLOTS_PER_ENTITY:
            slots.append(ActivitySlot())

        return cls(
            entity_id=data["entity_id"],
            is_binary=bool(data.get("is_binary", True)),
            history_window_days=int(
                data.get("history_window_days", DEFAULT_HISTORY_WINDOW_DAYS)
            ),
            first_observation=data.get("first_observation"),
            slots=slots,
        )


# ---------------------------------------------------------------------------
# RoutineModel
# ---------------------------------------------------------------------------


class RoutineModel:
    """Top-level per-entity baseline learning engine.

    Manages a collection of EntityRoutine objects keyed by entity_id.
    Provides aggregate confidence and learning status.
    """

    def __init__(self, history_window_days: int = DEFAULT_HISTORY_WINDOW_DAYS) -> None:
        self._history_window_days = history_window_days
        self._entities: dict[str, EntityRoutine] = {}

    # ------------------------------------------------------------------
    # Entity management
    # ------------------------------------------------------------------

    def get_or_create(self, entity_id: str, is_binary: bool) -> EntityRoutine:
        """Return the EntityRoutine for entity_id, creating it if needed."""
        if entity_id not in self._entities:
            self._entities[entity_id] = EntityRoutine(
                entity_id=entity_id,
                is_binary=is_binary,
                history_window_days=self._history_window_days,
            )
        return self._entities[entity_id]

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        entity_id: str,
        timestamp: datetime,
        state_value: str,
        is_binary: bool,
    ) -> None:
        """Record a state change for an entity."""
        er = self.get_or_create(entity_id, is_binary)
        er.record(timestamp, state_value)

    # ------------------------------------------------------------------
    # Aggregate metrics
    # ------------------------------------------------------------------

    def overall_confidence(self, now: datetime | None = None) -> float:
        """Return the average confidence across all tracked entities.

        Returns 0.0 when no entities are tracked.
        """
        if not self._entities:
            return 0.0
        if now is None:
            now = datetime.now(tz=timezone.utc)
        total = sum(er.confidence(now) for er in self._entities.values())
        return total / len(self._entities)

    def learning_status(self, now: datetime | None = None) -> str:
        """Return the current learning phase.

        Returns:
            "inactive"  — overall_confidence < 0.1
            "learning"  — 0.1 <= overall_confidence < 0.8
            "ready"     — overall_confidence >= 0.8
        """
        conf = self.overall_confidence(now=now)
        if conf < 0.1:
            return "inactive"
        if conf < 0.8:
            return "learning"
        return "ready"

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "history_window_days": self._history_window_days,
            "entities": {
                entity_id: er.to_dict()
                for entity_id, er in self._entities.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoutineModel":
        """Restore from a serialized dict."""
        history_window_days = int(
            data.get("history_window_days", DEFAULT_HISTORY_WINDOW_DAYS)
        )
        model = cls(history_window_days=history_window_days)
        for entity_id, er_data in data.get("entities", {}).items():
            model._entities[entity_id] = EntityRoutine.from_dict(er_data)
        return model
