"""Machine learning analyzer using River for streaming anomaly detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .const import MIN_SAMPLES_FOR_ML

_LOGGER = logging.getLogger(__name__)

# Try to import River ML library - it may not be available
try:
    from river import anomaly
    ML_AVAILABLE = True
    _LOGGER.info("River ML library available - ML features enabled")
except ImportError:
    ML_AVAILABLE = False
    anomaly = None  # type: ignore
    _LOGGER.warning(
        "River not available. ML features will be disabled. "
        "Install with: pip install river"
    )


@dataclass
class StateChangeEvent:
    """Record of a single state change event."""

    entity_id: str
    timestamp: datetime
    old_state: str | None = None
    new_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "entity_id": self.entity_id,
            "timestamp": self.timestamp.isoformat(),
            "old_state": self.old_state,
            "new_state": self.new_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateChangeEvent:
        """Create from dictionary."""
        return cls(
            entity_id=data["entity_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            old_state=data.get("old_state"),
            new_state=data.get("new_state"),
        )


@dataclass
class CrossSensorPattern:
    """Pattern of correlation between two sensors."""

    entity_a: str
    entity_b: str
    co_occurrence_count: int = 0
    avg_time_delta_seconds: float = 0.0
    a_before_b_count: int = 0
    b_before_a_count: int = 0

    @property
    def correlation_strength(self) -> float:
        """Calculate correlation strength (0-1)."""
        import math

        if self.co_occurrence_count == 0:
            return 0.0
        # Higher count and consistent ordering = stronger correlation
        total = self.a_before_b_count + self.b_before_a_count
        if total == 0:
            return 0.0
        consistency = max(self.a_before_b_count, self.b_before_a_count) / total
        # Scale by log of count to not over-weight high frequency
        count_factor = min(1.0, math.log1p(self.co_occurrence_count) / 5.0)
        return consistency * count_factor

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "co_occurrence_count": self.co_occurrence_count,
            "avg_time_delta_seconds": self.avg_time_delta_seconds,
            "a_before_b_count": self.a_before_b_count,
            "b_before_a_count": self.b_before_a_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrossSensorPattern:
        """Create from dictionary."""
        return cls(
            entity_a=data["entity_a"],
            entity_b=data["entity_b"],
            co_occurrence_count=data.get("co_occurrence_count", 0),
            avg_time_delta_seconds=data.get("avg_time_delta_seconds", 0.0),
            a_before_b_count=data.get("a_before_b_count", 0),
            b_before_a_count=data.get("b_before_a_count", 0),
        )


@dataclass
class MLAnomalyResult:
    """Result from ML-based anomaly detection."""

    is_anomaly: bool
    entity_id: str | None  # None for cross-sensor anomalies
    anomaly_score: float  # 0 to 1, higher = more anomalous
    anomaly_type: str  # "half_space_trees", "missing_correlation", "unexpected_correlation"
    description: str
    timestamp: datetime
    related_entities: list[str] = field(default_factory=list)


class MLPatternAnalyzer:
    """Analyzes patterns using River's Half-Space Trees for streaming anomaly detection."""

    def __init__(
        self,
        contamination: float = 0.05,
        cross_sensor_window_seconds: int = 300,
        n_trees: int = 10,
        height: int = 8,
    ) -> None:
        """Initialize the ML analyzer.

        Args:
            contamination: Expected proportion of anomalies (used for threshold)
            cross_sensor_window_seconds: Window for cross-sensor correlation
            n_trees: Number of trees in Half-Space Trees ensemble
            height: Height of each tree
        """
        self._contamination = contamination
        self._cross_sensor_window = timedelta(seconds=cross_sensor_window_seconds)
        self._n_trees = n_trees
        self._height = height
        self._events: list[StateChangeEvent] = []
        self._model: Any = None
        self._samples_processed: int = 0
        self._cross_sensor_patterns: dict[tuple[str, str], CrossSensorPattern] = {}
        self._entity_last_change: dict[str, datetime] = {}
        self._recent_events_window: list[StateChangeEvent] = []
        self._entity_indices: dict[str, int] = {}
        self._became_effective_at: datetime | None = None  # When model reached min samples
        self._last_warmup: datetime | None = None  # When train() was last called

        # Initialize model if River is available
        if ML_AVAILABLE:
            self._model = anomaly.HalfSpaceTrees(
                n_trees=n_trees,
                height=height,
                window_size=256,
            )

    @property
    def ml_available(self) -> bool:
        """Check if ML dependencies are available."""
        return ML_AVAILABLE

    @property
    def is_trained(self) -> bool:
        """Check if the model has enough data to make predictions.

        With streaming ML, we're always learning. We consider it 'trained'
        after processing enough samples.
        """
        return ML_AVAILABLE and self._samples_processed >= MIN_SAMPLES_FOR_ML

    @property
    def last_trained(self) -> datetime | None:
        """Get the timestamp of when the model became effective.

        With streaming ML, this returns when the model first reached
        the minimum sample threshold, or when it was last warmed up
        via train() after loading from storage.
        """
        return self._last_warmup or self._became_effective_at

    @property
    def sample_count(self) -> int:
        """Get the number of processed samples."""
        return self._samples_processed

    @property
    def cross_sensor_patterns(self) -> dict[tuple[str, str], CrossSensorPattern]:
        """Get cross-sensor patterns."""
        return self._cross_sensor_patterns

    def _get_entity_index(self, entity_id: str) -> int:
        """Get or create a numeric index for an entity."""
        if entity_id not in self._entity_indices:
            self._entity_indices[entity_id] = len(self._entity_indices)
        return self._entity_indices[entity_id]

    def record_event(
        self,
        entity_id: str,
        timestamp: datetime,
        old_state: str | None = None,
        new_state: str | None = None,
    ) -> None:
        """Record a state change event and update the model."""
        event = StateChangeEvent(
            entity_id=entity_id,
            timestamp=timestamp,
            old_state=old_state,
            new_state=new_state,
        )
        self._events.append(event)

        # Update cross-sensor correlations
        self._update_cross_sensor_patterns(event)

        # Update the streaming ML model
        if ML_AVAILABLE and self._model is not None:
            features = self._extract_features(event)
            # Learn from this event (streaming update)
            self._model.learn_one(features)
            self._samples_processed += 1

            # Track when model first became effective
            if (self._became_effective_at is None and
                    self._samples_processed >= MIN_SAMPLES_FOR_ML):
                self._became_effective_at = timestamp
                _LOGGER.info(
                    "ML model became effective after %d samples",
                    self._samples_processed,
                )

        # Track last change time per entity
        self._entity_last_change[entity_id] = timestamp

    def _update_cross_sensor_patterns(self, new_event: StateChangeEvent) -> None:
        """Update cross-sensor patterns based on recent events."""
        # Clean old events from recent window
        cutoff = new_event.timestamp - self._cross_sensor_window
        self._recent_events_window = [
            e for e in self._recent_events_window if e.timestamp >= cutoff
        ]

        # Check for co-occurrences with recent events from other entities
        for recent_event in self._recent_events_window:
            if recent_event.entity_id == new_event.entity_id:
                continue

            # Create ordered key (alphabetical) for consistent storage
            entities = sorted([recent_event.entity_id, new_event.entity_id])
            key = (entities[0], entities[1])

            if key not in self._cross_sensor_patterns:
                self._cross_sensor_patterns[key] = CrossSensorPattern(
                    entity_a=entities[0],
                    entity_b=entities[1],
                )

            pattern = self._cross_sensor_patterns[key]
            pattern.co_occurrence_count += 1

            # Calculate time delta
            time_delta = (new_event.timestamp - recent_event.timestamp).total_seconds()

            # Update average time delta using incremental mean
            old_avg = pattern.avg_time_delta_seconds
            n = pattern.co_occurrence_count
            pattern.avg_time_delta_seconds = old_avg + (abs(time_delta) - old_avg) / n

            # Track ordering
            if recent_event.entity_id == entities[0]:
                pattern.a_before_b_count += 1
            else:
                pattern.b_before_a_count += 1

        # Add to recent window
        self._recent_events_window.append(new_event)

    def _extract_features(self, event: StateChangeEvent) -> dict[str, float]:
        """Extract features from a state change event for the ML model.

        River uses dict-based features instead of numpy arrays.
        """
        ts = event.timestamp

        # Time-based features
        hour = ts.hour
        minute_bucket = ts.minute // 15
        day_of_week = ts.weekday()
        is_weekend = 1.0 if day_of_week >= 5 else 0.0

        # Time since last activity for this entity
        last_change = self._entity_last_change.get(event.entity_id)
        if last_change and last_change < ts:
            time_since_last = (ts - last_change).total_seconds()
        else:
            time_since_last = 0.0

        # Cap at 24 hours and normalize
        time_since_last = min(time_since_last, 86400) / 86400

        # Activity rate in last hour (count events for this entity)
        hour_ago = ts - timedelta(hours=1)
        recent_count = sum(
            1 for e in self._events[-1000:]  # Check last 1000 events max
            if e.entity_id == event.entity_id and e.timestamp >= hour_ago
        )

        # Entity index (normalized)
        entity_idx = self._get_entity_index(event.entity_id)
        total_entities = max(1, len(self._entity_indices))
        entity_idx_normalized = entity_idx / total_entities

        return {
            "hour": hour / 23.0,
            "minute_bucket": minute_bucket / 3.0,
            "day_of_week": day_of_week / 6.0,
            "is_weekend": is_weekend,
            "time_since_last": time_since_last,
            "recent_activity": min(recent_count, 20) / 20.0,
            "entity_idx": entity_idx_normalized,
        }

    def train(self) -> bool:
        """Train the model on historical data.

        With River's streaming approach, we can replay historical events
        to warm up the model. This is called when loading saved data.
        """
        if not ML_AVAILABLE or self._model is None:
            _LOGGER.debug("ML not available - River not installed")
            return False

        if len(self._events) < MIN_SAMPLES_FOR_ML:
            _LOGGER.debug(
                "Not enough samples for ML: %d < %d",
                len(self._events),
                MIN_SAMPLES_FOR_ML,
            )
            return False

        # Reset model and replay events
        self._model = anomaly.HalfSpaceTrees(
            n_trees=self._n_trees,
            height=self._height,
            window_size=256,
        )
        self._samples_processed = 0
        self._entity_last_change.clear()

        # Replay all events to train the model
        for event in self._events:
            features = self._extract_features(event)
            self._model.learn_one(features)
            self._samples_processed += 1
            self._entity_last_change[event.entity_id] = event.timestamp

        # Record warmup timestamp
        self._last_warmup = datetime.now(timezone.utc)

        # Set became_effective if not already set
        if self._became_effective_at is None and self._samples_processed >= MIN_SAMPLES_FOR_ML:
            self._became_effective_at = self._last_warmup

        _LOGGER.info(
            "Warmed up Half-Space Trees on %d samples (streaming model)",
            self._samples_processed,
        )
        return True

    def check_anomaly(self, event: StateChangeEvent) -> MLAnomalyResult | None:
        """Check if an event is anomalous using the streaming model."""
        if not self.is_trained or self._model is None:
            return None

        features = self._extract_features(event)

        # Get anomaly score (0 to 1, higher = more anomalous)
        score = self._model.score_one(features)

        # Use contamination as threshold
        # Higher contamination = lower threshold = more anomalies flagged
        threshold = 1.0 - self._contamination

        if score > threshold:
            return MLAnomalyResult(
                is_anomaly=True,
                entity_id=event.entity_id,
                anomaly_score=score,
                anomaly_type="half_space_trees",
                description=(
                    f"Unusual activity pattern detected for {event.entity_id} "
                    f"(ML score: {score:.3f}, threshold: {threshold:.3f})"
                ),
                timestamp=event.timestamp,
            )

        return None

    def check_cross_sensor_anomalies(
        self,
        recent_events: list[StateChangeEvent],
        check_window: timedelta | None = None,
    ) -> list[MLAnomalyResult]:
        """Check for anomalies in cross-sensor patterns."""
        if check_window is None:
            check_window = self._cross_sensor_window

        anomalies: list[MLAnomalyResult] = []
        now = datetime.now(timezone.utc)

        # Get strong patterns (correlation > 0.5)
        strong_patterns = [
            p for p in self._cross_sensor_patterns.values()
            if p.correlation_strength > 0.5 and p.co_occurrence_count >= 10
        ]

        if not strong_patterns:
            return anomalies

        # Check for missing correlations
        recent_entity_changes: dict[str, datetime] = {}
        for event in recent_events:
            if event.timestamp >= now - check_window:
                recent_entity_changes[event.entity_id] = event.timestamp

        for pattern in strong_patterns:
            a_changed = pattern.entity_a in recent_entity_changes
            b_changed = pattern.entity_b in recent_entity_changes

            # One triggered but not the other (when they usually correlate)
            if a_changed and not b_changed:
                # Check if enough time has passed for B to have triggered
                a_time = recent_entity_changes[pattern.entity_a]
                expected_window = timedelta(seconds=pattern.avg_time_delta_seconds * 2)

                if now - a_time > expected_window:
                    anomalies.append(
                        MLAnomalyResult(
                            is_anomaly=True,
                            entity_id=pattern.entity_b,
                            anomaly_score=0.5,
                            anomaly_type="missing_correlation",
                            description=(
                                f"Expected {pattern.entity_b} to change after "
                                f"{pattern.entity_a} (usually within "
                                f"{pattern.avg_time_delta_seconds:.0f}s, "
                                f"correlation: {pattern.correlation_strength:.2f})"
                            ),
                            timestamp=now,
                            related_entities=[pattern.entity_a],
                        )
                    )

            elif b_changed and not a_changed:
                b_time = recent_entity_changes[pattern.entity_b]
                expected_window = timedelta(seconds=pattern.avg_time_delta_seconds * 2)

                if now - b_time > expected_window:
                    # Only flag if A usually comes first
                    if pattern.a_before_b_count > pattern.b_before_a_count:
                        anomalies.append(
                            MLAnomalyResult(
                                is_anomaly=True,
                                entity_id=pattern.entity_a,
                                anomaly_score=0.5,
                                anomaly_type="missing_correlation",
                                description=(
                                    f"Expected {pattern.entity_a} to change before "
                                    f"{pattern.entity_b} (usually precedes by "
                                    f"{pattern.avg_time_delta_seconds:.0f}s, "
                                    f"correlation: {pattern.correlation_strength:.2f})"
                                ),
                                timestamp=now,
                                related_entities=[pattern.entity_b],
                            )
                        )

        return anomalies

    def get_strong_patterns(self, min_strength: float = 0.3) -> list[dict[str, Any]]:
        """Get cross-sensor patterns above a minimum strength threshold."""
        patterns = []
        for key, pattern in self._cross_sensor_patterns.items():
            if pattern.correlation_strength >= min_strength:
                patterns.append({
                    "entities": [pattern.entity_a, pattern.entity_b],
                    "strength": round(pattern.correlation_strength, 2),
                    "co_occurrences": pattern.co_occurrence_count,
                    "avg_delay_seconds": round(pattern.avg_time_delta_seconds, 1),
                    "usual_order": (
                        f"{pattern.entity_a} → {pattern.entity_b}"
                        if pattern.a_before_b_count > pattern.b_before_a_count
                        else f"{pattern.entity_b} → {pattern.entity_a}"
                    ),
                })
        return sorted(patterns, key=lambda p: p["strength"], reverse=True)

    def prune_old_events(self, max_age_days: int = 30) -> int:
        """Remove events older than the specified age."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        original_count = len(self._events)
        self._events = [e for e in self._events if e.timestamp >= cutoff]
        pruned = original_count - len(self._events)
        if pruned > 0:
            _LOGGER.debug("Pruned %d old events", pruned)
        return pruned

    def to_dict(self) -> dict[str, Any]:
        """Convert analyzer state to dictionary for storage."""
        return {
            "events": [e.to_dict() for e in self._events],
            "cross_sensor_patterns": {
                f"{k[0]}|{k[1]}": v.to_dict()
                for k, v in self._cross_sensor_patterns.items()
            },
            "samples_processed": self._samples_processed,
            "contamination": self._contamination,
            "cross_sensor_window_seconds": self._cross_sensor_window.total_seconds(),
            "entity_indices": self._entity_indices,
            "became_effective_at": (
                self._became_effective_at.isoformat()
                if self._became_effective_at else None
            ),
            "last_warmup": (
                self._last_warmup.isoformat()
                if self._last_warmup else None
            ),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        contamination: float | None = None,
        cross_sensor_window_seconds: int | None = None,
    ) -> MLPatternAnalyzer:
        """Create analyzer from stored dictionary."""
        analyzer = cls(
            contamination=contamination or data.get("contamination", 0.05),
            cross_sensor_window_seconds=cross_sensor_window_seconds
            or int(data.get("cross_sensor_window_seconds", 300)),
        )

        # Restore events
        for event_data in data.get("events", []):
            analyzer._events.append(StateChangeEvent.from_dict(event_data))

        # Restore cross-sensor patterns
        for key_str, pattern_data in data.get("cross_sensor_patterns", {}).items():
            parts = key_str.split("|")
            if len(parts) == 2:
                key = (parts[0], parts[1])
                analyzer._cross_sensor_patterns[key] = CrossSensorPattern.from_dict(
                    pattern_data
                )

        # Restore entity indices
        analyzer._entity_indices = data.get("entity_indices", {})

        # Restore sample count
        analyzer._samples_processed = data.get("samples_processed", 0)

        # Restore timestamps
        became_effective = data.get("became_effective_at")
        if became_effective:
            analyzer._became_effective_at = datetime.fromisoformat(became_effective)

        last_warmup = data.get("last_warmup")
        if last_warmup:
            analyzer._last_warmup = datetime.fromisoformat(last_warmup)

        # Rebuild entity last change map
        for event in analyzer._events:
            analyzer._entity_last_change[event.entity_id] = event.timestamp

        # Warm up the model with historical data if we have enough
        if len(analyzer._events) >= MIN_SAMPLES_FOR_ML:
            analyzer.train()

        return analyzer
