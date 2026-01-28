"""Pattern analyzer for learning entity behaviour and detecting anomalies."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# 15-minute intervals per day (96 buckets)
INTERVALS_PER_DAY = 96
MINUTES_PER_INTERVAL = 15

# Days of week (0=Monday, 6=Sunday)
DAYS_IN_WEEK = 7
DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass
class TimeBucket:
    """Statistics for a single time bucket."""

    count: int = 0
    sum_values: float = 0.0
    sum_squared: float = 0.0

    @property
    def mean(self) -> float:
        """Calculate mean activity count."""
        if self.count == 0:
            return 0.0
        return self.sum_values / self.count

    @property
    def std_dev(self) -> float:
        """Calculate standard deviation."""
        if self.count < 2:
            return 0.0
        variance = (self.sum_squared / self.count) - (self.mean**2)
        # Handle floating point errors that could make variance slightly negative
        return math.sqrt(max(0, variance))

    def add_observation(self, value: float) -> None:
        """Add a new observation to this bucket."""
        self.count += 1
        self.sum_values += value
        self.sum_squared += value**2

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "count": self.count,
            "sum_values": self.sum_values,
            "sum_squared": self.sum_squared,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimeBucket:
        """Create from dictionary."""
        return cls(
            count=data.get("count", 0),
            sum_values=data.get("sum_values", 0.0),
            sum_squared=data.get("sum_squared", 0.0),
        )


def _get_interval_index(timestamp: datetime) -> int:
    """Get the 15-minute interval index (0-95) for a timestamp."""
    minutes_since_midnight = timestamp.hour * 60 + timestamp.minute
    return minutes_since_midnight // MINUTES_PER_INTERVAL


def _interval_to_time_str(interval: int) -> str:
    """Convert interval index to human-readable time string."""
    minutes = interval * MINUTES_PER_INTERVAL
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


@dataclass
class EntityPattern:
    """Pattern data for a single entity with per-weekday 15-minute buckets."""

    entity_id: str
    # 7 days × 96 intervals = 672 buckets total
    day_buckets: dict[int, list[TimeBucket]] = field(default_factory=dict)
    total_observations: int = 0
    first_observation: datetime | None = None
    last_observation: datetime | None = None

    def __post_init__(self) -> None:
        """Initialize buckets for all days if empty."""
        for day in range(DAYS_IN_WEEK):
            if day not in self.day_buckets:
                self.day_buckets[day] = [TimeBucket() for _ in range(INTERVALS_PER_DAY)]

    def record_activity(self, timestamp: datetime) -> None:
        """Record an activity at the given timestamp."""
        day_of_week = timestamp.weekday()  # 0=Monday, 6=Sunday
        interval = _get_interval_index(timestamp)

        self.day_buckets[day_of_week][interval].add_observation(1.0)

        self.total_observations += 1
        if self.first_observation is None:
            self.first_observation = timestamp
        self.last_observation = timestamp

    def get_expected_activity(self, timestamp: datetime) -> tuple[float, float]:
        """Get expected activity (mean, std_dev) for the given time."""
        day_of_week = timestamp.weekday()
        interval = _get_interval_index(timestamp)

        bucket = self.day_buckets[day_of_week][interval]
        return bucket.mean, bucket.std_dev

    def get_time_description(self, timestamp: datetime) -> str:
        """Get human-readable description of the time slot."""
        day_name = DAY_NAMES[timestamp.weekday()]
        interval = _get_interval_index(timestamp)
        time_str = _interval_to_time_str(interval)
        return f"{day_name} {time_str}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "entity_id": self.entity_id,
            "day_buckets": {
                str(day): [b.to_dict() for b in buckets]
                for day, buckets in self.day_buckets.items()
            },
            "total_observations": self.total_observations,
            "first_observation": (
                self.first_observation.isoformat() if self.first_observation else None
            ),
            "last_observation": (
                self.last_observation.isoformat() if self.last_observation else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityPattern:
        """Create from dictionary."""
        pattern = cls(entity_id=data["entity_id"])

        # Load day buckets
        day_buckets_data = data.get("day_buckets", {})
        for day_str, buckets_data in day_buckets_data.items():
            day = int(day_str)
            pattern.day_buckets[day] = [
                TimeBucket.from_dict(b) for b in buckets_data
            ]

        # Ensure all days have correct number of buckets
        for day in range(DAYS_IN_WEEK):
            if day not in pattern.day_buckets:
                pattern.day_buckets[day] = [TimeBucket() for _ in range(INTERVALS_PER_DAY)]
            else:
                while len(pattern.day_buckets[day]) < INTERVALS_PER_DAY:
                    pattern.day_buckets[day].append(TimeBucket())

        pattern.total_observations = data.get("total_observations", 0)

        first_obs = data.get("first_observation")
        pattern.first_observation = (
            datetime.fromisoformat(first_obs) if first_obs else None
        )

        last_obs = data.get("last_observation")
        pattern.last_observation = datetime.fromisoformat(last_obs) if last_obs else None

        return pattern


@dataclass
class AnomalyResult:
    """Result of anomaly detection."""

    is_anomaly: bool
    entity_id: str
    anomaly_type: str  # "unusual_activity" or "unusual_inactivity"
    z_score: float
    expected_mean: float
    expected_std: float
    actual_value: float
    timestamp: datetime
    time_slot: str  # e.g., "monday 09:15"
    description: str


class PatternAnalyzer:
    """Analyzes entity patterns and detects anomalies."""

    def __init__(
        self,
        sensitivity_threshold: float,
        learning_period_days: int,
    ) -> None:
        """Initialize the pattern analyzer."""
        self._sensitivity_threshold = sensitivity_threshold
        self._learning_period_days = learning_period_days
        self._patterns: dict[str, EntityPattern] = {}
        self._daily_counts: dict[str, int] = {}
        self._daily_count_date: datetime | None = None
        self._current_interval_activity: dict[str, int] = {}
        self._current_interval: int = -1
        self._current_interval_day: int = -1

    @property
    def patterns(self) -> dict[str, EntityPattern]:
        """Get all entity patterns."""
        return self._patterns

    def get_pattern(self, entity_id: str) -> EntityPattern:
        """Get or create pattern for an entity."""
        if entity_id not in self._patterns:
            self._patterns[entity_id] = EntityPattern(entity_id=entity_id)
        return self._patterns[entity_id]

    def record_state_change(self, entity_id: str, timestamp: datetime) -> None:
        """Record a state change for an entity."""
        pattern = self.get_pattern(entity_id)
        pattern.record_activity(timestamp)

        # Track daily counts
        today = timestamp.date()
        if self._daily_count_date is None or self._daily_count_date != today:
            self._daily_counts = {}
            self._daily_count_date = today

        self._daily_counts[entity_id] = self._daily_counts.get(entity_id, 0) + 1

        # Track current interval activity for anomaly detection
        current_interval = _get_interval_index(timestamp)
        current_day = timestamp.weekday()

        if (
            current_interval != self._current_interval
            or current_day != self._current_interval_day
        ):
            self._current_interval = current_interval
            self._current_interval_day = current_day
            self._current_interval_activity = {}

        self._current_interval_activity[entity_id] = (
            self._current_interval_activity.get(entity_id, 0) + 1
        )

    def get_current_interval_activity(self) -> dict[str, int]:
        """Get activity counts for the current 15-minute interval."""
        now = datetime.now()
        current_interval = _get_interval_index(now)
        current_day = now.weekday()

        if (
            current_interval != self._current_interval
            or current_day != self._current_interval_day
        ):
            return {}

        return self._current_interval_activity.copy()

    def get_daily_count(self, entity_id: str) -> int:
        """Get today's activity count for an entity."""
        today = datetime.now().date()
        if self._daily_count_date != today:
            return 0
        return self._daily_counts.get(entity_id, 0)

    def get_total_daily_count(self) -> int:
        """Get total activity count across all entities today."""
        today = datetime.now().date()
        if self._daily_count_date != today:
            return 0
        return sum(self._daily_counts.values())

    def get_confidence(self) -> float:
        """Get baseline confidence level (0-100)."""
        if not self._patterns:
            return 0.0

        # Calculate days of data collection
        min_first_obs = None
        for pattern in self._patterns.values():
            if pattern.first_observation:
                if min_first_obs is None or pattern.first_observation < min_first_obs:
                    min_first_obs = pattern.first_observation

        if min_first_obs is None:
            return 0.0

        days_of_data = (datetime.now() - min_first_obs).days
        confidence = min(100.0, (days_of_data / self._learning_period_days) * 100)
        return confidence

    def is_learning_complete(self) -> bool:
        """Check if the learning period is complete."""
        return self.get_confidence() >= 100.0

    def calculate_activity_score(self) -> float:
        """Calculate current activity score (0-100)."""
        if not self._patterns:
            return 0.0

        now = datetime.now()
        total_expected = 0.0
        total_actual = 0.0

        for entity_id, pattern in self._patterns.items():
            expected_mean, _ = pattern.get_expected_activity(now)
            actual = self.get_daily_count(entity_id)

            # Normalize to expected interval activity (96 intervals per day)
            if expected_mean > 0:
                total_expected += expected_mean
                total_actual += min(actual / INTERVALS_PER_DAY, expected_mean * 2)

        if total_expected == 0:
            return 50.0  # No baseline yet, return neutral

        # Score is actual/expected ratio, capped at 100
        score = min(100.0, (total_actual / total_expected) * 100)
        return score

    def check_for_anomalies(
        self, current_interval_activity: dict[str, int] | None = None
    ) -> list[AnomalyResult]:
        """Check for anomalies in the current interval's activity."""
        if not self.is_learning_complete():
            return []

        if current_interval_activity is None:
            current_interval_activity = self.get_current_interval_activity()

        now = datetime.now()
        anomalies: list[AnomalyResult] = []

        for entity_id, pattern in self._patterns.items():
            expected_mean, expected_std = pattern.get_expected_activity(now)
            actual = current_interval_activity.get(entity_id, 0)
            time_slot = pattern.get_time_description(now)

            # Skip if we don't have enough data for this time period
            if expected_std == 0 and expected_mean == 0:
                continue

            # Calculate Z-score
            if expected_std > 0:
                z_score = abs(actual - expected_mean) / expected_std
            elif actual != expected_mean:
                # No variance but value differs from expected
                z_score = float("inf") if actual > 0 else self._sensitivity_threshold + 1
            else:
                z_score = 0.0

            # Check if anomaly exceeds threshold
            if z_score > self._sensitivity_threshold:
                if actual > expected_mean:
                    anomaly_type = "unusual_activity"
                    description = (
                        f"Unusual activity for {entity_id} on {time_slot}: "
                        f"expected ~{expected_mean:.1f} state changes, got {actual}"
                    )
                else:
                    anomaly_type = "unusual_inactivity"
                    description = (
                        f"Unusual inactivity for {entity_id} on {time_slot}: "
                        f"expected ~{expected_mean:.1f} state changes, got {actual}"
                    )

                anomalies.append(
                    AnomalyResult(
                        is_anomaly=True,
                        entity_id=entity_id,
                        anomaly_type=anomaly_type,
                        z_score=z_score,
                        expected_mean=expected_mean,
                        expected_std=expected_std,
                        actual_value=actual,
                        timestamp=now,
                        time_slot=time_slot,
                        description=description,
                    )
                )

        return anomalies

    def get_last_activity_time(self) -> datetime | None:
        """Get the timestamp of the most recent activity across all entities."""
        last_time = None
        for pattern in self._patterns.values():
            if pattern.last_observation:
                if last_time is None or pattern.last_observation > last_time:
                    last_time = pattern.last_observation
        return last_time

    def to_dict(self) -> dict[str, Any]:
        """Convert analyzer state to dictionary for storage."""
        return {
            "patterns": {
                entity_id: pattern.to_dict()
                for entity_id, pattern in self._patterns.items()
            },
            "sensitivity_threshold": self._sensitivity_threshold,
            "learning_period_days": self._learning_period_days,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        sensitivity_threshold: float | None = None,
        learning_period_days: int | None = None,
    ) -> PatternAnalyzer:
        """Create analyzer from stored dictionary."""
        analyzer = cls(
            sensitivity_threshold=sensitivity_threshold
            or data.get("sensitivity_threshold", 2.0),
            learning_period_days=learning_period_days
            or data.get("learning_period_days", 7),
        )

        patterns_data = data.get("patterns", {})
        for entity_id, pattern_data in patterns_data.items():
            analyzer._patterns[entity_id] = EntityPattern.from_dict(pattern_data)

        return analyzer
