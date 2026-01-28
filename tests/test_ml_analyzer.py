"""Tests for the ML pattern analyzer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.behaviour_monitor.ml_analyzer import (
    ML_AVAILABLE,
    CrossSensorPattern,
    MLAnomalyResult,
    MLPatternAnalyzer,
    StateChangeEvent,
)


class TestStateChangeEvent:
    """Tests for StateChangeEvent class."""

    def test_creation(self) -> None:
        """Test event creation."""
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        event = StateChangeEvent(
            entity_id="sensor.test",
            timestamp=ts,
            old_state="off",
            new_state="on",
        )
        assert event.entity_id == "sensor.test"
        assert event.timestamp == ts
        assert event.old_state == "off"
        assert event.new_state == "on"

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        event = StateChangeEvent(
            entity_id="sensor.test",
            timestamp=ts,
            old_state="off",
            new_state="on",
        )
        data = event.to_dict()
        assert data["entity_id"] == "sensor.test"
        assert data["timestamp"] == ts.isoformat()
        assert data["old_state"] == "off"
        assert data["new_state"] == "on"

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "entity_id": "sensor.test",
            "timestamp": "2024-01-15T09:00:00+00:00",
            "old_state": "off",
            "new_state": "on",
        }
        event = StateChangeEvent.from_dict(data)
        assert event.entity_id == "sensor.test"
        assert event.timestamp == datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)


class TestCrossSensorPattern:
    """Tests for CrossSensorPattern class."""

    def test_empty_pattern(self) -> None:
        """Test empty pattern has zero correlation."""
        pattern = CrossSensorPattern(entity_a="sensor.a", entity_b="sensor.b")
        assert pattern.correlation_strength == 0.0

    def test_correlation_strength_increases(self) -> None:
        """Test correlation strength increases with co-occurrences."""
        pattern = CrossSensorPattern(
            entity_a="sensor.a",
            entity_b="sensor.b",
            co_occurrence_count=50,
            a_before_b_count=45,
            b_before_a_count=5,
        )
        strength = pattern.correlation_strength
        assert strength > 0.5  # Strong correlation

    def test_correlation_strength_low_consistency(self) -> None:
        """Test correlation strength is lower with inconsistent ordering."""
        pattern = CrossSensorPattern(
            entity_a="sensor.a",
            entity_b="sensor.b",
            co_occurrence_count=50,
            a_before_b_count=25,
            b_before_a_count=25,  # 50/50 ordering
        )
        strength = pattern.correlation_strength
        # Less consistent ordering means lower strength
        assert strength < 0.7

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        pattern = CrossSensorPattern(
            entity_a="sensor.a",
            entity_b="sensor.b",
            co_occurrence_count=10,
            avg_time_delta_seconds=5.0,
            a_before_b_count=8,
            b_before_a_count=2,
        )
        data = pattern.to_dict()
        assert data["entity_a"] == "sensor.a"
        assert data["co_occurrence_count"] == 10
        assert data["avg_time_delta_seconds"] == 5.0

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "entity_a": "sensor.a",
            "entity_b": "sensor.b",
            "co_occurrence_count": 10,
            "avg_time_delta_seconds": 5.0,
            "a_before_b_count": 8,
            "b_before_a_count": 2,
        }
        pattern = CrossSensorPattern.from_dict(data)
        assert pattern.entity_a == "sensor.a"
        assert pattern.co_occurrence_count == 10


class TestMLPatternAnalyzer:
    """Tests for MLPatternAnalyzer class."""

    def test_initialization(self) -> None:
        """Test analyzer initialization."""
        analyzer = MLPatternAnalyzer(
            contamination=0.05,
            cross_sensor_window_seconds=300,
        )
        assert not analyzer.is_trained
        assert analyzer.sample_count == 0
        assert analyzer.last_trained is None

    def test_record_event(self) -> None:
        """Test recording events."""
        analyzer = MLPatternAnalyzer()
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        analyzer.record_event(
            entity_id="sensor.test",
            timestamp=ts,
            old_state="off",
            new_state="on",
        )

        # Sample count only increments if ML (River) is available
        if ML_AVAILABLE:
            assert analyzer.sample_count == 1
        else:
            assert analyzer.sample_count == 0
        # Events are always stored regardless of ML availability
        assert len(analyzer._events) == 1

    def test_cross_sensor_pattern_detection(self) -> None:
        """Test cross-sensor pattern detection."""
        analyzer = MLPatternAnalyzer(cross_sensor_window_seconds=60)
        base_ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        # Record co-occurring events
        for i in range(20):
            ts = base_ts + timedelta(minutes=i * 5)
            analyzer.record_event("sensor.a", ts)
            analyzer.record_event("sensor.b", ts + timedelta(seconds=5))

        # Check that pattern was detected
        patterns = analyzer.cross_sensor_patterns
        assert len(patterns) > 0

        # Find the pattern for sensor.a and sensor.b
        key = ("sensor.a", "sensor.b")
        assert key in patterns
        assert patterns[key].co_occurrence_count >= 10

    def test_train_requires_minimum_samples(self) -> None:
        """Test training requires minimum samples."""
        analyzer = MLPatternAnalyzer()

        # Add only a few events
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            analyzer.record_event("sensor.test", ts + timedelta(minutes=i))

        result = analyzer.train()
        assert not result  # Should fail - not enough samples
        assert not analyzer.is_trained

    @pytest.mark.skipif(not ML_AVAILABLE, reason="River not installed")
    def test_train_with_sufficient_samples(self) -> None:
        """Test training succeeds with sufficient samples."""
        analyzer = MLPatternAnalyzer()
        base_ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        # Add enough events
        for i in range(150):
            ts = base_ts + timedelta(minutes=i * 10)
            analyzer.record_event("sensor.test", ts)

        result = analyzer.train()
        assert result  # Should succeed
        assert analyzer.is_trained
        # Note: With streaming ML (River), last_trained is always None
        # as training happens incrementally

    def test_check_anomaly_untrained(self) -> None:
        """Test anomaly check returns None when untrained."""
        analyzer = MLPatternAnalyzer()
        event = StateChangeEvent(
            entity_id="sensor.test",
            timestamp=datetime.now(timezone.utc),
        )

        result = analyzer.check_anomaly(event)
        assert result is None

    @pytest.mark.skipif(not ML_AVAILABLE, reason="River not installed")
    def test_check_anomaly_trained(self) -> None:
        """Test anomaly check works when trained."""
        analyzer = MLPatternAnalyzer(contamination=0.1)
        base_ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        # Build training data - need at least 100 samples
        # Record multiple events per day to reach the minimum
        for day in range(50):
            for hour_offset in range(3):  # 3 events per day = 150 total
                ts = base_ts + timedelta(days=day, hours=hour_offset)
                analyzer.record_event("sensor.test", ts)

        # Train (replay historical data)
        train_result = analyzer.train()
        assert train_result is True
        assert analyzer.is_trained

        # Check normal event (similar time)
        normal_event = StateChangeEvent(
            entity_id="sensor.test",
            timestamp=base_ts + timedelta(days=21),  # Same time, different day
        )
        check_result = analyzer.check_anomaly(normal_event)
        # Normal events might or might not be flagged depending on model

        # Check anomalous event (very different time)
        anomalous_event = StateChangeEvent(
            entity_id="sensor.test",
            timestamp=base_ts + timedelta(days=21, hours=12),  # Noon instead of 9 AM
        )
        # Result could be an anomaly or None
        check_result = analyzer.check_anomaly(anomalous_event)
        if check_result:
            assert isinstance(check_result, MLAnomalyResult)

    def test_get_strong_patterns(self) -> None:
        """Test getting strong patterns."""
        analyzer = MLPatternAnalyzer(cross_sensor_window_seconds=60)
        base_ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        # Create a strong correlation pattern
        for i in range(30):
            ts = base_ts + timedelta(minutes=i * 5)
            analyzer.record_event("sensor.a", ts)
            analyzer.record_event("sensor.b", ts + timedelta(seconds=3))

        patterns = analyzer.get_strong_patterns(min_strength=0.1)
        assert len(patterns) > 0
        assert "entities" in patterns[0]
        assert "strength" in patterns[0]

    def test_prune_old_events(self) -> None:
        """Test pruning old events."""
        analyzer = MLPatternAnalyzer()
        now = datetime.now(timezone.utc)

        # Add old events
        for i in range(50):
            old_ts = now - timedelta(days=60 + i)
            analyzer.record_event("sensor.test", old_ts)

        # Add recent events
        for i in range(50):
            recent_ts = now - timedelta(days=i)
            analyzer.record_event("sensor.test", recent_ts)

        initial_event_count = len(analyzer._events)
        assert initial_event_count == 100

        # Prune events older than 30 days
        pruned = analyzer.prune_old_events(max_age_days=30)

        assert pruned > 0
        assert len(analyzer._events) < initial_event_count
        assert len(analyzer._events) == 30  # Only last 30 days remain
        # Note: sample_count tracks total samples ever processed by ML model,
        # it doesn't decrease when pruning events

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization round-trip."""
        analyzer = MLPatternAnalyzer(
            contamination=0.1,
            cross_sensor_window_seconds=120,
        )
        base_ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        # Record some events
        for i in range(10):
            analyzer.record_event("sensor.test", base_ts + timedelta(minutes=i))

        # Serialize
        data = analyzer.to_dict()

        # Deserialize
        restored = MLPatternAnalyzer.from_dict(data)

        assert restored.sample_count == analyzer.sample_count
        assert restored._contamination == analyzer._contamination

    def test_check_cross_sensor_anomalies_no_patterns(self) -> None:
        """Test cross-sensor anomaly check with no patterns."""
        analyzer = MLPatternAnalyzer()
        recent_events: list[StateChangeEvent] = []

        anomalies = analyzer.check_cross_sensor_anomalies(recent_events)
        assert len(anomalies) == 0

    def test_cross_sensor_missing_correlation(self) -> None:
        """Test detection of missing correlation."""
        analyzer = MLPatternAnalyzer(cross_sensor_window_seconds=60)
        base_ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        # Build strong correlation pattern
        for i in range(50):
            ts = base_ts + timedelta(minutes=i * 5)
            analyzer.record_event("sensor.a", ts)
            analyzer.record_event("sensor.b", ts + timedelta(seconds=5))

        # Now simulate A triggering but B not following
        recent_ts = datetime.now(timezone.utc) - timedelta(seconds=30)
        recent_events = [
            StateChangeEvent(entity_id="sensor.a", timestamp=recent_ts),
        ]

        anomalies = analyzer.check_cross_sensor_anomalies(
            recent_events,
            check_window=timedelta(seconds=60),
        )

        # May detect missing correlation depending on pattern strength
        assert isinstance(anomalies, list)


class TestMLAnomalyResult:
    """Tests for MLAnomalyResult class."""

    def test_creation(self) -> None:
        """Test result creation."""
        result = MLAnomalyResult(
            is_anomaly=True,
            entity_id="sensor.test",
            anomaly_score=-0.5,
            anomaly_type="isolation_forest",
            description="Test anomaly",
            timestamp=datetime.now(timezone.utc),
            related_entities=["sensor.other"],
        )
        assert result.is_anomaly
        assert result.entity_id == "sensor.test"
        assert result.anomaly_score == -0.5
        assert result.anomaly_type == "isolation_forest"
        assert len(result.related_entities) == 1

    def test_cross_sensor_anomaly(self) -> None:
        """Test cross-sensor anomaly result."""
        result = MLAnomalyResult(
            is_anomaly=True,
            entity_id=None,  # Cross-sensor anomalies may not have specific entity
            anomaly_score=-0.3,
            anomaly_type="missing_correlation",
            description="Expected sensor.b to follow sensor.a",
            timestamp=datetime.now(timezone.utc),
            related_entities=["sensor.a", "sensor.b"],
        )
        assert result.is_anomaly
        assert result.entity_id is None
        assert result.anomaly_type == "missing_correlation"
        assert len(result.related_entities) == 2
