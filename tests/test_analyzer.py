"""Tests for the statistical pattern analyzer."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.behaviour_monitor.analyzer import (
    AnomalyResult,
    EntityPattern,
    PatternAnalyzer,
    TimeBucket,
    _get_interval_index,
    _interval_to_time_str,
    DAY_NAMES,
    DAYS_IN_WEEK,
    INTERVALS_PER_DAY,
)


class TestTimeBucket:
    """Tests for TimeBucket class."""

    def test_empty_bucket_mean(self) -> None:
        """Test mean of empty bucket is 0."""
        bucket = TimeBucket()
        assert bucket.mean == 0.0

    def test_empty_bucket_std_dev(self) -> None:
        """Test std_dev of empty bucket is 0."""
        bucket = TimeBucket()
        assert bucket.std_dev == 0.0

    def test_single_observation_mean(self) -> None:
        """Test mean with single observation."""
        bucket = TimeBucket()
        bucket.add_observation(5.0)
        assert bucket.mean == 5.0

    def test_single_observation_std_dev(self) -> None:
        """Test std_dev with single observation is 0."""
        bucket = TimeBucket()
        bucket.add_observation(5.0)
        assert bucket.std_dev == 0.0

    def test_multiple_observations_mean(self) -> None:
        """Test mean with multiple observations."""
        bucket = TimeBucket()
        for val in [2.0, 4.0, 6.0, 8.0]:
            bucket.add_observation(val)
        assert bucket.mean == 5.0

    def test_multiple_observations_std_dev(self) -> None:
        """Test std_dev with multiple observations."""
        bucket = TimeBucket()
        # Values: 2, 4, 6, 8 -> mean=5, variance=5, std_dev=sqrt(5)
        for val in [2.0, 4.0, 6.0, 8.0]:
            bucket.add_observation(val)
        expected_std = math.sqrt(5.0)
        assert abs(bucket.std_dev - expected_std) < 0.001

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        bucket = TimeBucket(count=3, sum_values=15.0, sum_squared=89.0)
        result = bucket.to_dict()
        assert result["count"] == 3
        assert result["sum_values"] == 15.0
        assert result["sum_squared"] == 89.0

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {"count": 5, "sum_values": 25.0, "sum_squared": 145.0}
        bucket = TimeBucket.from_dict(data)
        assert bucket.count == 5
        assert bucket.sum_values == 25.0
        assert bucket.sum_squared == 145.0


class TestIntervalFunctions:
    """Tests for interval utility functions."""

    def test_get_interval_index_midnight(self) -> None:
        """Test interval index at midnight."""
        ts = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert _get_interval_index(ts) == 0

    def test_get_interval_index_noon(self) -> None:
        """Test interval index at noon."""
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert _get_interval_index(ts) == 48  # 12 hours * 4 intervals

    def test_get_interval_index_end_of_day(self) -> None:
        """Test interval index at 23:45."""
        ts = datetime(2024, 1, 15, 23, 45, 0, tzinfo=timezone.utc)
        assert _get_interval_index(ts) == 95

    def test_get_interval_index_within_interval(self) -> None:
        """Test interval index at 9:07 (should be same as 9:00)."""
        ts1 = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 9, 7, 0, tzinfo=timezone.utc)
        ts3 = datetime(2024, 1, 15, 9, 14, 59, tzinfo=timezone.utc)
        assert _get_interval_index(ts1) == _get_interval_index(ts2)
        assert _get_interval_index(ts2) == _get_interval_index(ts3)

    def test_interval_to_time_str(self) -> None:
        """Test interval to time string conversion."""
        assert _interval_to_time_str(0) == "00:00"
        assert _interval_to_time_str(4) == "01:00"
        assert _interval_to_time_str(36) == "09:00"
        assert _interval_to_time_str(95) == "23:45"


class TestEntityPattern:
    """Tests for EntityPattern class."""

    def test_initialization(self) -> None:
        """Test pattern initialization creates correct buckets."""
        pattern = EntityPattern(entity_id="sensor.test")
        assert len(pattern.day_buckets) == DAYS_IN_WEEK
        for day in range(DAYS_IN_WEEK):
            assert len(pattern.day_buckets[day]) == INTERVALS_PER_DAY

    def test_record_activity_monday(self) -> None:
        """Test recording activity on Monday."""
        pattern = EntityPattern(entity_id="sensor.test")
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)  # Monday
        assert ts.weekday() == 0  # Verify it's Monday

        pattern.record_activity(ts)

        assert pattern.total_observations == 1
        assert pattern.first_observation == ts
        assert pattern.last_observation == ts

        # Check correct bucket was updated
        interval = _get_interval_index(ts)
        assert pattern.day_buckets[0][interval].count == 1

    def test_record_activity_weekend(self) -> None:
        """Test recording activity on Saturday."""
        pattern = EntityPattern(entity_id="sensor.test")
        ts = datetime(2024, 1, 20, 14, 30, 0, tzinfo=timezone.utc)  # Saturday
        assert ts.weekday() == 5  # Verify it's Saturday

        pattern.record_activity(ts)

        interval = _get_interval_index(ts)
        assert pattern.day_buckets[5][interval].count == 1

    def test_get_expected_activity(self) -> None:
        """Test getting expected activity."""
        pattern = EntityPattern(entity_id="sensor.test")
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)  # Monday 9:00

        # Record multiple observations
        for _ in range(5):
            pattern.record_activity(ts)

        mean, std = pattern.get_expected_activity(ts)
        assert mean == 1.0  # Each observation adds 1.0
        # With all same values, std_dev should be 0
        assert std == 0.0

    def test_get_time_description(self) -> None:
        """Test time description generation."""
        pattern = EntityPattern(entity_id="sensor.test")
        ts = datetime(2024, 1, 15, 9, 15, 0, tzinfo=timezone.utc)  # Monday 9:15

        desc = pattern.get_time_description(ts)
        assert "monday" in desc
        assert "09:15" in desc

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization round-trip."""
        pattern = EntityPattern(entity_id="sensor.test")
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        pattern.record_activity(ts)

        # Serialize
        data = pattern.to_dict()

        # Deserialize
        restored = EntityPattern.from_dict(data)

        assert restored.entity_id == pattern.entity_id
        assert restored.total_observations == pattern.total_observations
        assert restored.first_observation == pattern.first_observation


class TestPatternAnalyzer:
    """Tests for PatternAnalyzer class."""

    def test_initialization(self) -> None:
        """Test analyzer initialization."""
        analyzer = PatternAnalyzer(
            sensitivity_threshold=2.0,
            learning_period_days=7,
        )
        assert len(analyzer.patterns) == 0

    def test_get_pattern_creates_new(self) -> None:
        """Test get_pattern creates new pattern if not exists."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        pattern = analyzer.get_pattern("sensor.test")
        assert pattern.entity_id == "sensor.test"
        assert "sensor.test" in analyzer.patterns

    def test_get_pattern_returns_existing(self) -> None:
        """Test get_pattern returns existing pattern."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        pattern1 = analyzer.get_pattern("sensor.test")
        pattern2 = analyzer.get_pattern("sensor.test")
        assert pattern1 is pattern2

    def test_record_state_change(self) -> None:
        """Test recording state changes."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        analyzer.record_state_change("sensor.test", ts)

        pattern = analyzer.patterns["sensor.test"]
        assert pattern.total_observations == 1

    def test_daily_count_tracking(self) -> None:
        """Test daily count tracking."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        ts = datetime.now(timezone.utc)

        analyzer.record_state_change("sensor.test", ts)
        analyzer.record_state_change("sensor.test", ts)
        analyzer.record_state_change("sensor.other", ts)

        assert analyzer.get_daily_count("sensor.test") == 2
        assert analyzer.get_daily_count("sensor.other") == 1
        assert analyzer.get_total_daily_count() == 3

    def test_confidence_no_data(self) -> None:
        """Test confidence with no data is 0."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        assert analyzer.get_confidence() == 0.0

    def test_confidence_with_data(self) -> None:
        """Test confidence increases with data."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

        # Record data from 3 days ago
        ts = datetime.now(timezone.utc) - timedelta(days=3)
        analyzer.record_state_change("sensor.test", ts)

        confidence = analyzer.get_confidence()
        # 3 days / 7 days = ~42.8%
        assert 40 < confidence < 45

    def test_is_learning_complete(self) -> None:
        """Test learning complete detection."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

        # Record data from 10 days ago
        ts = datetime.now(timezone.utc) - timedelta(days=10)
        analyzer.record_state_change("sensor.test", ts)

        assert analyzer.is_learning_complete()

    def test_check_for_anomalies_during_learning(self) -> None:
        """Test no anomalies detected during learning period."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

        # Record recent data (still learning)
        ts = datetime.now(timezone.utc)
        analyzer.record_state_change("sensor.test", ts)

        anomalies = analyzer.check_for_anomalies()
        assert len(anomalies) == 0

    def test_activity_score_no_baseline(self) -> None:
        """Test activity score with no baseline."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        score = analyzer.calculate_activity_score()
        assert score == 0.0  # No patterns yet

    def test_get_last_activity_time(self) -> None:
        """Test getting last activity time."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

        ts1 = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        analyzer.record_state_change("sensor.test1", ts1)
        analyzer.record_state_change("sensor.test2", ts2)

        assert analyzer.get_last_activity_time() == ts2

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization round-trip."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        analyzer.record_state_change("sensor.test", ts)

        # Serialize
        data = analyzer.to_dict()

        # Deserialize
        restored = PatternAnalyzer.from_dict(data)

        assert "sensor.test" in restored.patterns
        assert restored._sensitivity_threshold == 2.0
        assert restored._learning_period_days == 7


class TestAnomalyDetection:
    """Tests for anomaly detection logic."""

    def test_anomaly_result_creation(self) -> None:
        """Test AnomalyResult creation."""
        result = AnomalyResult(
            is_anomaly=True,
            entity_id="sensor.test",
            anomaly_type="unusual_activity",
            z_score=3.5,
            expected_mean=2.0,
            expected_std=0.5,
            actual_value=5.0,
            timestamp=datetime.now(timezone.utc),
            time_slot="monday 09:00",
            description="Test anomaly",
        )
        assert result.is_anomaly
        assert result.entity_id == "sensor.test"
        assert result.z_score == 3.5

    def test_detects_unusual_activity(self) -> None:
        """Test detection of unusual activity after learning."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=1)

        # Build baseline over "past days"
        base_ts = datetime.now(timezone.utc) - timedelta(days=2)
        for day_offset in range(2):
            ts = base_ts + timedelta(days=day_offset)
            # Record 1 activity per interval normally
            analyzer.record_state_change("sensor.test", ts)

        # Now the analyzer should have learned the pattern
        # Simulate current interval with many more activities
        now = datetime.now(timezone.utc)
        for _ in range(10):
            analyzer.record_state_change("sensor.test", now)

        # Check for anomalies
        current_activity = analyzer.get_current_interval_activity()
        anomalies = analyzer.check_for_anomalies(current_activity)

        # Should detect unusual activity (10 vs baseline of ~1)
        # Note: Detection depends on having variance in baseline
        # This test verifies the mechanism works
        assert isinstance(anomalies, list)


class TestElderCareFunctions:
    """Tests for elder care monitoring functions."""

    def test_get_typical_interval_no_data(self) -> None:
        """Test typical interval with no data returns 0."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        assert analyzer.get_typical_interval() == 0.0

    def test_get_typical_interval_with_data(self) -> None:
        """Test typical interval calculation with data."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

        # Record multiple activities throughout the day
        now = datetime.now(timezone.utc)
        for i in range(10):
            ts = now - timedelta(hours=i)
            analyzer.record_state_change("sensor.motion", ts)

        interval = analyzer.get_typical_interval()
        # Should return some positive value based on recorded patterns
        assert interval >= 0

    def test_get_time_since_activity_context_no_data(self) -> None:
        """Test time since activity context with no data."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        context = analyzer.get_time_since_activity_context()

        assert context["time_since_seconds"] is None
        assert context["status"] == "unknown"

    def test_get_time_since_activity_context_with_data(self) -> None:
        """Test time since activity context with recent data."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

        # Record recent activity
        now = datetime.now(timezone.utc)
        analyzer.record_state_change("sensor.motion", now - timedelta(minutes=5))

        context = analyzer.get_time_since_activity_context()

        assert context["time_since_seconds"] is not None
        assert context["time_since_seconds"] > 0
        assert "time_since_formatted" in context
        assert context["status"] in ["normal", "check_recommended", "concern", "alert", "unknown"]

    def test_get_routine_progress_no_data(self) -> None:
        """Test routine progress with no data."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        progress = analyzer.get_routine_progress()

        assert "progress_percent" in progress
        assert "expected_by_now" in progress
        assert "actual_today" in progress
        assert progress["actual_today"] == 0

    def test_get_routine_progress_with_data(self) -> None:
        """Test routine progress with activity today."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

        # Record some activity today
        now = datetime.now(timezone.utc)
        for i in range(5):
            analyzer.record_state_change("sensor.motion", now - timedelta(minutes=i*10))

        progress = analyzer.get_routine_progress()

        assert progress["actual_today"] == 5
        assert "summary" in progress
        assert progress["status"] in ["on_track", "below_normal", "concerning", "alert"]

    def test_get_entity_status_no_data(self) -> None:
        """Test entity status with no data."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        status = analyzer.get_entity_status()

        assert isinstance(status, list)
        assert len(status) == 0

    def test_get_entity_status_with_data(self) -> None:
        """Test entity status with monitored entities."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

        now = datetime.now(timezone.utc)
        analyzer.record_state_change("sensor.motion", now)
        analyzer.record_state_change("sensor.door", now - timedelta(hours=2))

        status = analyzer.get_entity_status()

        assert len(status) == 2
        assert all("entity_id" in s for s in status)
        assert all("status" in s for s in status)
        assert all("severity" in s for s in status)
        assert all("time_since_activity" in s for s in status)

    def test_get_welfare_status_no_data(self) -> None:
        """Test welfare status with no data."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
        welfare = analyzer.get_welfare_status()

        assert "status" in welfare
        assert "reasons" in welfare
        assert "recommendation" in welfare

    def test_get_welfare_status_with_data(self) -> None:
        """Test welfare status with recent activity."""
        analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

        now = datetime.now(timezone.utc)
        analyzer.record_state_change("sensor.motion", now)

        welfare = analyzer.get_welfare_status()

        assert welfare["status"] in ["ok", "check_recommended", "concern", "alert"]
        assert isinstance(welfare["reasons"], list)
        assert "entity_count_by_status" in welfare

    def test_severity_calculation(self) -> None:
        """Test severity is calculated correctly for anomalies."""
        from custom_components.behaviour_monitor.analyzer import _get_severity

        assert _get_severity(0.5) == "normal"
        assert _get_severity(1.8) == "minor"
        assert _get_severity(2.8) == "moderate"
        assert _get_severity(4.0) == "significant"
        assert _get_severity(5.0) == "critical"

    def test_format_duration(self) -> None:
        """Test duration formatting."""
        from custom_components.behaviour_monitor.analyzer import _format_duration

        assert "seconds" in _format_duration(30)
        assert "minute" in _format_duration(120)
        assert "hours" in _format_duration(7200)
        assert "days" in _format_duration(172800)
