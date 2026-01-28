"""Pattern analyzer for learning entity behaviour and detecting anomalies."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


def _get_severity(z_score: float) -> str:
    """Get severity level based on Z-score."""
    from .const import (
        SEVERITY_CRITICAL,
        SEVERITY_MINOR,
        SEVERITY_MODERATE,
        SEVERITY_NORMAL,
        SEVERITY_SIGNIFICANT,
        SEVERITY_THRESHOLDS,
    )

    if z_score >= SEVERITY_THRESHOLDS[SEVERITY_CRITICAL]:
        return SEVERITY_CRITICAL
    elif z_score >= SEVERITY_THRESHOLDS[SEVERITY_SIGNIFICANT]:
        return SEVERITY_SIGNIFICANT
    elif z_score >= SEVERITY_THRESHOLDS[SEVERITY_MODERATE]:
        return SEVERITY_MODERATE
    elif z_score >= SEVERITY_THRESHOLDS[SEVERITY_MINOR]:
        return SEVERITY_MINOR
    return SEVERITY_NORMAL


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{int(seconds)} seconds"
    elif seconds < 3600:
        mins = int(seconds / 60)
        return f"{mins} minute{'s' if mins != 1 else ''}"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f} hours"
    else:
        days = seconds / 86400
        return f"{days:.1f} days"


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
    severity: str = "normal"  # normal, minor, moderate, significant, critical


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
        now = datetime.now(timezone.utc)
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
        today = datetime.now(timezone.utc).date()
        if self._daily_count_date != today:
            return 0
        return self._daily_counts.get(entity_id, 0)

    def get_total_daily_count(self) -> int:
        """Get total activity count across all entities today."""
        today = datetime.now(timezone.utc).date()
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

        days_of_data = (datetime.now(timezone.utc) - min_first_obs).days
        confidence = min(100.0, (days_of_data / self._learning_period_days) * 100)
        return confidence

    def is_learning_complete(self) -> bool:
        """Check if the learning period is complete."""
        return self.get_confidence() >= 100.0

    def calculate_activity_score(self) -> float:
        """Calculate current activity score (0-100)."""
        if not self._patterns:
            return 0.0

        now = datetime.now(timezone.utc)
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

        now = datetime.now(timezone.utc)
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
                        severity=_get_severity(z_score),
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

    def get_typical_interval(self, entity_id: str | None = None) -> float:
        """Get typical interval between activities in seconds.

        If entity_id is None, calculates across all entities.
        Returns average time between state changes based on learned patterns.
        """
        now = datetime.now(timezone.utc)
        day_of_week = now.weekday()

        if entity_id:
            patterns = [self._patterns.get(entity_id)] if entity_id in self._patterns else []
        else:
            patterns = list(self._patterns.values())

        if not patterns:
            return 0.0

        total_rate = 0.0
        for pattern in patterns:
            if pattern is None:
                continue
            # Sum expected activity across all intervals today
            daily_expected = sum(
                bucket.mean for bucket in pattern.day_buckets[day_of_week]
            )
            if daily_expected > 0:
                # Typical interval = seconds in day / expected activities
                total_rate += daily_expected

        if total_rate == 0:
            return 0.0

        # Return typical interval in seconds
        return 86400 / total_rate

    def get_time_since_activity_context(self) -> dict[str, Any]:
        """Get time since last activity with context for elder care."""
        last_activity = self.get_last_activity_time()
        if last_activity is None:
            return {
                "time_since_seconds": None,
                "time_since_formatted": "No activity recorded",
                "typical_interval_seconds": 0,
                "typical_interval_formatted": "Unknown",
                "status": "unknown",
                "concern_level": 0.0,
            }

        now = datetime.now(timezone.utc)
        time_since = (now - last_activity).total_seconds()
        typical_interval = self.get_typical_interval()

        # Calculate concern level (0.0 to 1.0+)
        if typical_interval > 0:
            concern_level = time_since / typical_interval
        else:
            concern_level = 0.0

        # Determine status
        if concern_level < 1.5:
            status = "normal"
        elif concern_level < 2.5:
            status = "check_recommended"
        elif concern_level < 4.0:
            status = "concern"
        else:
            status = "alert"

        return {
            "time_since_seconds": time_since,
            "time_since_formatted": _format_duration(time_since),
            "typical_interval_seconds": typical_interval,
            "typical_interval_formatted": _format_duration(typical_interval) if typical_interval > 0 else "Unknown",
            "status": status,
            "concern_level": round(concern_level, 2),
            "context": (
                f"Last activity {_format_duration(time_since)} ago "
                f"(usually every {_format_duration(typical_interval)})"
                if typical_interval > 0
                else f"Last activity {_format_duration(time_since)} ago"
            ),
        }

    def get_routine_progress(self) -> dict[str, Any]:
        """Calculate routine progress for today.

        Returns expected vs actual activity counts up to current time.
        """
        now = datetime.now(timezone.utc)
        day_of_week = now.weekday()
        current_interval = _get_interval_index(now)

        expected_total = 0.0
        actual_total = 0

        for entity_id, pattern in self._patterns.items():
            # Sum expected activity from midnight to current interval
            for interval in range(current_interval + 1):
                bucket = pattern.day_buckets[day_of_week][interval]
                expected_total += bucket.mean

            # Get actual count for today
            actual_total += self.get_daily_count(entity_id)

        # Calculate progress percentage
        if expected_total > 0:
            progress = min(100.0, (actual_total / expected_total) * 100)
        else:
            progress = 100.0 if actual_total == 0 else 100.0

        # Calculate expected for full day
        expected_full_day = 0.0
        for pattern in self._patterns.values():
            for bucket in pattern.day_buckets[day_of_week]:
                expected_full_day += bucket.mean

        return {
            "progress_percent": round(progress, 1),
            "expected_by_now": round(expected_total, 1),
            "actual_today": actual_total,
            "expected_full_day": round(expected_full_day, 1),
            "time_of_day": _interval_to_time_str(current_interval),
            "day_name": DAY_NAMES[day_of_week],
            "status": (
                "on_track" if progress >= 70
                else "below_normal" if progress >= 40
                else "concerning" if progress >= 20
                else "alert"
            ),
            "summary": (
                f"{actual_total} of ~{expected_total:.0f} expected activities "
                f"by {_interval_to_time_str(current_interval)} ({progress:.0f}%)"
            ),
        }

    def get_entity_status(self) -> list[dict[str, Any]]:
        """Get status for each monitored entity for elder care dashboard."""
        now = datetime.now(timezone.utc)
        entity_statuses = []

        for entity_id, pattern in self._patterns.items():
            expected_mean, expected_std = pattern.get_expected_activity(now)
            actual = self._current_interval_activity.get(entity_id, 0)
            daily_count = self.get_daily_count(entity_id)

            # Calculate Z-score
            if expected_std > 0:
                z_score = abs(actual - expected_mean) / expected_std
            elif actual != expected_mean and expected_mean > 0:
                z_score = 3.0  # Significant deviation with no variance
            else:
                z_score = 0.0

            # Time since last activity for this entity
            last_obs = pattern.last_observation
            if last_obs:
                time_since = (now - last_obs).total_seconds()
                time_since_formatted = _format_duration(time_since)
            else:
                time_since = None
                time_since_formatted = "Never"

            entity_statuses.append({
                "entity_id": entity_id,
                "last_activity": last_obs.isoformat() if last_obs else None,
                "time_since_activity": time_since_formatted,
                "time_since_seconds": time_since,
                "daily_count": daily_count,
                "current_interval_count": actual,
                "expected_interval_count": round(expected_mean, 1),
                "z_score": round(z_score, 2),
                "severity": _get_severity(z_score),
                "status": (
                    "normal" if z_score < 1.5
                    else "attention" if z_score < 2.5
                    else "concern" if z_score < 3.5
                    else "alert"
                ),
            })

        # Sort by severity (most concerning first)
        severity_order = {"alert": 0, "concern": 1, "attention": 2, "normal": 3}
        entity_statuses.sort(key=lambda x: severity_order.get(x["status"], 4))

        return entity_statuses

    def get_welfare_status(self) -> dict[str, Any]:
        """Get overall welfare status for elder care monitoring.

        Aggregates all signals into a single welfare assessment.
        """
        from .const import WELFARE_ALERT, WELFARE_CHECK, WELFARE_CONCERN, WELFARE_OK

        activity_context = self.get_time_since_activity_context()
        routine_progress = self.get_routine_progress()
        entity_statuses = self.get_entity_status()

        # Count concerning entities
        alert_count = sum(1 for e in entity_statuses if e["status"] == "alert")
        concern_count = sum(1 for e in entity_statuses if e["status"] == "concern")
        attention_count = sum(1 for e in entity_statuses if e["status"] == "attention")

        # Determine overall welfare status
        reasons = []

        if activity_context["status"] == "alert":
            welfare = WELFARE_ALERT
            reasons.append(f"No activity for {activity_context['time_since_formatted']}")
        elif alert_count > 0:
            welfare = WELFARE_ALERT
            reasons.append(f"{alert_count} sensor(s) showing alert-level anomalies")
        elif activity_context["status"] == "concern" or concern_count > 0:
            welfare = WELFARE_CONCERN
            if activity_context["status"] == "concern":
                reasons.append(f"Extended time since last activity")
            if concern_count > 0:
                reasons.append(f"{concern_count} sensor(s) showing concerning patterns")
        elif routine_progress["status"] in ["concerning", "alert"]:
            welfare = WELFARE_CONCERN
            reasons.append(f"Daily routine only {routine_progress['progress_percent']:.0f}% complete")
        elif activity_context["status"] == "check_recommended" or attention_count > 1:
            welfare = WELFARE_CHECK
            if activity_context["status"] == "check_recommended":
                reasons.append("Longer than usual since last activity")
            if attention_count > 1:
                reasons.append(f"{attention_count} sensors need attention")
        else:
            welfare = WELFARE_OK
            reasons.append("Activity patterns are normal")

        return {
            "status": welfare,
            "reasons": reasons,
            "summary": reasons[0] if reasons else "Normal activity",
            "time_since_activity": activity_context,
            "routine_progress": routine_progress,
            "entity_count_by_status": {
                "alert": alert_count,
                "concern": concern_count,
                "attention": attention_count,
                "normal": len(entity_statuses) - alert_count - concern_count - attention_count,
            },
            "recommendation": (
                "Immediate welfare check recommended" if welfare == WELFARE_ALERT
                else "Welfare check recommended soon" if welfare == WELFARE_CONCERN
                else "Consider checking in" if welfare == WELFARE_CHECK
                else "No action needed"
            ),
        }

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
