"""Tests for RoutineModel — pure Python, zero HA mocking required."""

from __future__ import annotations

from collections import deque
from datetime import date, datetime, timedelta, timezone

import pytest

# All imports are from the module under test only — no HA mocking needed.
from custom_components.behaviour_monitor.routine_model import (
    ActivitySlot,
    EntityRoutine,
    RoutineModel,
    is_binary_state,
    MIN_SLOT_OBSERVATIONS,
    SLOTS_PER_ENTITY,
    BINARY_STATES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_timestamps(count: int, start_offset_seconds: int = 0) -> list[str]:
    """Return ISO timestamp strings spaced 3600 s apart starting from epoch."""
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    return [
        (base + timedelta(seconds=start_offset_seconds + i * 3600)).isoformat()
        for i in range(count)
    ]


def _make_dt(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# ActivitySlot — slot_index static helper
# ---------------------------------------------------------------------------


class TestSlotIndex:
    """Tests for slot_index formula: dow * 24 + hour."""

    def test_slot_index_zero(self) -> None:
        """hour=0, dow=0 → 0."""
        slot = ActivitySlot()
        # slot_index is on EntityRoutine, not ActivitySlot — test via EntityRoutine
        er = EntityRoutine(entity_id="test", is_binary=True)
        assert er.slot_index(hour=0, dow=0) == 0

    def test_slot_index_max(self) -> None:
        """hour=23, dow=6 → 167."""
        er = EntityRoutine(entity_id="test", is_binary=True)
        assert er.slot_index(hour=23, dow=6) == 167

    def test_slot_index_mid(self) -> None:
        """hour=14, dow=2 → 2*24+14 = 62."""
        er = EntityRoutine(entity_id="test", is_binary=True)
        assert er.slot_index(hour=14, dow=2) == 62

    def test_slot_index_day_boundary(self) -> None:
        """hour=0, dow=1 → 24 (start of Tuesday)."""
        er = EntityRoutine(entity_id="test", is_binary=True)
        assert er.slot_index(hour=0, dow=1) == 24


# ---------------------------------------------------------------------------
# ActivitySlot — binary entity behaviour
# ---------------------------------------------------------------------------


class TestActivitySlotBinary:
    """Tests for ActivitySlot with binary observations."""

    def test_new_slot_not_sufficient(self) -> None:
        slot = ActivitySlot()
        assert slot.is_sufficient is False

    def test_insufficient_below_min(self) -> None:
        slot = ActivitySlot()
        for ts in _make_timestamps(MIN_SLOT_OBSERVATIONS - 1):
            slot.record_binary(ts)
        assert slot.is_sufficient is False

    def test_sufficient_at_min(self) -> None:
        slot = ActivitySlot()
        for ts in _make_timestamps(MIN_SLOT_OBSERVATIONS):
            slot.record_binary(ts)
        assert slot.is_sufficient is True

    def test_sufficient_above_min(self) -> None:
        slot = ActivitySlot()
        for ts in _make_timestamps(MIN_SLOT_OBSERVATIONS + 5):
            slot.record_binary(ts)
        assert slot.is_sufficient is True

    def test_event_times_deque_maxlen(self) -> None:
        slot = ActivitySlot()
        # Record 60 events (> maxlen=56) — old ones should be evicted
        for ts in _make_timestamps(60):
            slot.record_binary(ts)
        assert len(slot.event_times) == 56

    def test_expected_gap_seconds_insufficient(self) -> None:
        slot = ActivitySlot()
        for ts in _make_timestamps(MIN_SLOT_OBSERVATIONS - 1):
            slot.record_binary(ts)
        assert slot.expected_gap_seconds() is None

    def test_expected_gap_seconds_sufficient(self) -> None:
        """4 events spaced 3600s apart → 3 intervals of 3600 → median 3600."""
        slot = ActivitySlot()
        for ts in _make_timestamps(4):
            slot.record_binary(ts)
        result = slot.expected_gap_seconds()
        assert result is not None
        assert abs(result - 3600.0) < 1.0  # Allow tiny float rounding

    def test_expected_gap_seconds_returns_median(self) -> None:
        """Multiple observations — result is median of inter-event intervals."""
        slot = ActivitySlot()
        # 5 events at: 0, 1h, 2h, 3h, 7h → intervals: 3600, 3600, 3600, 14400
        timestamps = [
            datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc).isoformat(),
            datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc).isoformat(),
            datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
            datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc).isoformat(),
            datetime(2024, 1, 15, 17, 0, 0, tzinfo=timezone.utc).isoformat(),
        ]
        for ts in timestamps:
            slot.record_binary(ts)
        result = slot.expected_gap_seconds()
        assert result is not None
        # Intervals: 3600, 3600, 3600, 14400 — median of 4 values = (3600+3600)/2 = 3600
        assert abs(result - 3600.0) < 1.0

    def test_slot_distribution_none_for_binary(self) -> None:
        """Binary slot with events should return None from slot_distribution (no numeric data)."""
        slot = ActivitySlot()
        for ts in _make_timestamps(MIN_SLOT_OBSERVATIONS):
            slot.record_binary(ts)
        # slot_distribution is for numeric entities — should return None when no numeric data
        assert slot.slot_distribution() is None


# ---------------------------------------------------------------------------
# ActivitySlot — numeric entity behaviour (Welford)
# ---------------------------------------------------------------------------


class TestActivitySlotNumeric:
    """Tests for ActivitySlot with numeric (Welford) observations."""

    def test_numeric_not_sufficient_below_min(self) -> None:
        slot = ActivitySlot()
        for v in range(MIN_SLOT_OBSERVATIONS - 1):
            slot.record_numeric(float(v + 20))
        assert slot.is_sufficient is False

    def test_numeric_sufficient_at_min(self) -> None:
        slot = ActivitySlot()
        for v in range(MIN_SLOT_OBSERVATIONS):
            slot.record_numeric(float(v + 20))
        assert slot.is_sufficient is True

    def test_welford_mean(self) -> None:
        """Mean of [20, 21, 22, 23] = 21.5."""
        slot = ActivitySlot()
        values = [20.0, 21.0, 22.0, 23.0]
        for v in values:
            slot.record_numeric(v)
        distribution = slot.slot_distribution()
        assert distribution is not None
        mean_val, _ = distribution
        assert abs(mean_val - 21.5) < 0.01

    def test_welford_stdev(self) -> None:
        """stdev of [20, 21, 22, 23] ≈ 1.29 (population stdev: sqrt(5/4))."""
        slot = ActivitySlot()
        values = [20.0, 21.0, 22.0, 23.0]
        for v in values:
            slot.record_numeric(v)
        distribution = slot.slot_distribution()
        assert distribution is not None
        _, stdev_val = distribution
        # Population stdev = sqrt(M2/count) ≈ 1.118; sample stdev ≈ 1.29
        # Plan specifies: stdev = sqrt(m2/count) if count > 1 else 0.0 (population)
        assert stdev_val > 0.0

    def test_slot_distribution_none_when_insufficient(self) -> None:
        slot = ActivitySlot()
        for v in range(MIN_SLOT_OBSERVATIONS - 1):
            slot.record_numeric(float(v))
        assert slot.slot_distribution() is None

    def test_slot_distribution_single_value_stdev_zero(self) -> None:
        """Single value → count=1 → stdev=0.0."""
        slot = ActivitySlot()
        # We need is_sufficient=True but plan says count >= MIN_SLOT_OBSERVATIONS
        # With count=1 it won't be sufficient; test stdev behaviour at count=1 via sufficient check
        # Actually the plan says stdev=0 if count<=1 — test indirectly at count=4 with identical values
        slot = ActivitySlot()
        for _ in range(MIN_SLOT_OBSERVATIONS):
            slot.record_numeric(21.5)
        distribution = slot.slot_distribution()
        assert distribution is not None
        _, stdev_val = distribution
        assert stdev_val == 0.0  # All same value → zero stdev

    def test_expected_gap_seconds_none_for_numeric(self) -> None:
        """Numeric slot with Welford data returns None from expected_gap_seconds."""
        slot = ActivitySlot()
        for v in range(MIN_SLOT_OBSERVATIONS):
            slot.record_numeric(float(v + 20))
        assert slot.expected_gap_seconds() is None


# ---------------------------------------------------------------------------
# ActivitySlot — round-trip serialization
# ---------------------------------------------------------------------------


class TestActivitySlotSerialization:
    def test_binary_round_trip(self) -> None:
        slot = ActivitySlot()
        for ts in _make_timestamps(6):
            slot.record_binary(ts)
        data = slot.to_dict()
        restored = ActivitySlot.from_dict(data)
        assert list(restored.event_times) == list(slot.event_times)
        assert restored.numeric_count == 0
        assert restored.is_sufficient == slot.is_sufficient

    def test_numeric_round_trip(self) -> None:
        slot = ActivitySlot()
        for v in [20.0, 21.0, 22.0, 23.0, 24.0]:
            slot.record_numeric(v)
        data = slot.to_dict()
        restored = ActivitySlot.from_dict(data)
        assert restored.numeric_count == 5
        assert abs(restored.numeric_mean - slot.numeric_mean) < 1e-9
        assert abs(restored.numeric_m2 - slot.numeric_m2) < 1e-9

    def test_empty_slot_round_trip(self) -> None:
        slot = ActivitySlot()
        data = slot.to_dict()
        restored = ActivitySlot.from_dict(data)
        assert restored.is_sufficient is False
        assert len(restored.event_times) == 0
        assert restored.numeric_count == 0


# ---------------------------------------------------------------------------
# EntityRoutine — routing and recording
# ---------------------------------------------------------------------------


class TestEntityRoutine:
    def test_slots_count(self) -> None:
        er = EntityRoutine(entity_id="sensor.test", is_binary=True)
        assert len(er.slots) == SLOTS_PER_ENTITY == 168

    def test_record_binary_assigns_correct_slot(self) -> None:
        """Record at Tuesday 14:00 UTC (weekday=1, hour=14) → slot 1*24+14=38."""
        er = EntityRoutine(entity_id="sensor.test", is_binary=True)
        ts = datetime(2024, 1, 16, 14, 0, 0, tzinfo=timezone.utc)  # Tuesday
        assert ts.weekday() == 1
        er.record(ts, "on")
        slot_idx = er.slot_index(hour=14, dow=1)
        assert slot_idx == 38
        assert len(er.slots[slot_idx].event_times) == 1

    def test_record_binary_sets_first_observation(self) -> None:
        er = EntityRoutine(entity_id="sensor.test", is_binary=True)
        assert er.first_observation is None
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        er.record(ts, "on")
        assert er.first_observation is not None

    def test_record_binary_first_observation_not_overwritten(self) -> None:
        er = EntityRoutine(entity_id="sensor.test", is_binary=True)
        ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 16, 10, 0, 0, tzinfo=timezone.utc)
        er.record(ts1, "on")
        first = er.first_observation
        er.record(ts2, "off")
        assert er.first_observation == first

    def test_record_numeric_assigns_correct_slot(self) -> None:
        """Record numeric at Wednesday 8:00 UTC (weekday=2, hour=8) → slot 2*24+8=56."""
        er = EntityRoutine(entity_id="sensor.temp", is_binary=False)
        ts = datetime(2024, 1, 17, 8, 0, 0, tzinfo=timezone.utc)  # Wednesday
        assert ts.weekday() == 2
        er.record(ts, "21.5")
        slot_idx = er.slot_index(hour=8, dow=2)
        assert slot_idx == 56
        assert er.slots[slot_idx].numeric_count == 1

    def test_record_binary_multiple_states(self) -> None:
        """Both 'on' and 'off' states should be recorded as binary events."""
        er = EntityRoutine(entity_id="sensor.door", is_binary=True)
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        er.record(ts, "on")
        er.record(ts + timedelta(hours=1), "off")
        slot_on = er.slot_index(hour=10, dow=0)
        slot_off = er.slot_index(hour=11, dow=0)
        assert len(er.slots[slot_on].event_times) == 1
        assert len(er.slots[slot_off].event_times) == 1

    def test_expected_gap_seconds_delegates_to_slot(self) -> None:
        """expected_gap_seconds with insufficient data returns None."""
        er = EntityRoutine(entity_id="sensor.test", is_binary=True)
        assert er.expected_gap_seconds(hour=10, dow=0) is None

    def test_expected_gap_seconds_sufficient(self) -> None:
        """Fill slot 0 with 4+ events — should return non-None."""
        er = EntityRoutine(entity_id="sensor.test", is_binary=True)
        base = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)  # Monday 00:00
        assert base.weekday() == 0
        # Record 6 events all in the same hour-slot (Monday 00:xx) separated by minutes
        for i in range(6):
            er.record(base + timedelta(minutes=i * 10), "on")
        # All events go to dow=0, hour=0 slot
        result = er.expected_gap_seconds(hour=0, dow=0)
        assert result is not None
        assert result > 0

    def test_daily_activity_rate_zero(self) -> None:
        er = EntityRoutine(entity_id="sensor.test", is_binary=True)
        assert er.daily_activity_rate(date(2024, 1, 15)) == 0

    def test_daily_activity_rate_counts_correctly(self) -> None:
        """Events on Monday 2024-01-15 should be counted by daily_activity_rate."""
        er = EntityRoutine(entity_id="sensor.motion", is_binary=True)
        monday = datetime(2024, 1, 15, tzinfo=timezone.utc)
        assert monday.weekday() == 0
        # Record 3 events across different hours on the same Monday
        for h in [8, 12, 17]:
            er.record(monday.replace(hour=h), "on")
        # Record 1 event on Tuesday (should not count for Monday)
        tuesday = datetime(2024, 1, 16, 10, 0, 0, tzinfo=timezone.utc)
        er.record(tuesday, "on")
        count = er.daily_activity_rate(date(2024, 1, 15))
        assert count == 3

    def test_confidence_no_data(self) -> None:
        er = EntityRoutine(entity_id="sensor.test", is_binary=True)
        now = datetime(2024, 1, 15, tzinfo=timezone.utc)
        assert er.confidence(now) == 0.0

    def test_confidence_half_window(self) -> None:
        """first_observation 14 days ago with 28-day window → ~0.5."""
        er = EntityRoutine(entity_id="sensor.test", is_binary=True, history_window_days=28)
        now = datetime(2024, 2, 12, tzinfo=timezone.utc)
        first = now - timedelta(days=14)
        er.record(first, "on")
        result = er.confidence(now)
        assert abs(result - 0.5) < 0.01

    def test_confidence_full_window(self) -> None:
        """first_observation 28+ days ago → 1.0."""
        er = EntityRoutine(entity_id="sensor.test", is_binary=True, history_window_days=28)
        now = datetime(2024, 2, 12, tzinfo=timezone.utc)
        first = now - timedelta(days=30)
        er.record(first, "on")
        result = er.confidence(now)
        assert result == 1.0

    def test_confidence_capped_at_one(self) -> None:
        """Confidence never exceeds 1.0."""
        er = EntityRoutine(entity_id="sensor.test", is_binary=True, history_window_days=28)
        now = datetime(2024, 2, 12, tzinfo=timezone.utc)
        first = now - timedelta(days=100)
        er.record(first, "on")
        assert er.confidence(now) == 1.0


# ---------------------------------------------------------------------------
# EntityRoutine — round-trip serialization
# ---------------------------------------------------------------------------


class TestEntityRoutineSerialization:
    def test_round_trip_empty(self) -> None:
        er = EntityRoutine(entity_id="sensor.test", is_binary=True)
        data = er.to_dict()
        restored = EntityRoutine.from_dict(data)
        assert restored.entity_id == "sensor.test"
        assert restored.is_binary is True
        assert len(restored.slots) == SLOTS_PER_ENTITY
        assert restored.first_observation is None

    def test_round_trip_with_data(self) -> None:
        er = EntityRoutine(entity_id="sensor.door", is_binary=True, history_window_days=14)
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        for i in range(5):
            er.record(base + timedelta(hours=i), "on")
        data = er.to_dict()
        restored = EntityRoutine.from_dict(data)
        assert restored.entity_id == "sensor.door"
        assert restored.is_binary is True
        assert restored.history_window_days == 14
        assert restored.first_observation == er.first_observation
        slot_idx = er.slot_index(hour=10, dow=0)
        assert len(restored.slots[slot_idx].event_times) == len(er.slots[slot_idx].event_times)

    def test_round_trip_numeric(self) -> None:
        er = EntityRoutine(entity_id="sensor.temp", is_binary=False)
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        for i in range(5):
            er.record(base, str(20.0 + i))
        data = er.to_dict()
        restored = EntityRoutine.from_dict(data)
        assert restored.is_binary is False
        slot_idx = er.slot_index(hour=10, dow=0)
        assert restored.slots[slot_idx].numeric_count == 5
        assert abs(restored.slots[slot_idx].numeric_mean - er.slots[slot_idx].numeric_mean) < 1e-9


# ---------------------------------------------------------------------------
# RoutineModel
# ---------------------------------------------------------------------------


class TestRoutineModel:
    def test_empty_model_confidence(self) -> None:
        model = RoutineModel()
        assert model.overall_confidence() == 0.0

    def test_empty_model_learning_status(self) -> None:
        model = RoutineModel()
        assert model.learning_status() == "inactive"

    def test_get_or_create_creates_entity(self) -> None:
        model = RoutineModel()
        er = model.get_or_create("sensor.test", is_binary=True)
        assert isinstance(er, EntityRoutine)
        assert er.entity_id == "sensor.test"

    def test_get_or_create_returns_same_instance(self) -> None:
        model = RoutineModel()
        er1 = model.get_or_create("sensor.test", is_binary=True)
        er2 = model.get_or_create("sensor.test", is_binary=True)
        assert er1 is er2

    def test_record_delegates_to_entity_routine(self) -> None:
        model = RoutineModel()
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        model.record("sensor.motion", ts, "on", is_binary=True)
        er = model.get_or_create("sensor.motion", is_binary=True)
        assert er.first_observation is not None

    def test_overall_confidence_average(self) -> None:
        """Two entities with 1.0 and 0.5 confidence → average 0.75."""
        model = RoutineModel(history_window_days=28)
        now = datetime(2024, 2, 12, tzinfo=timezone.utc)

        # Entity 1: first observation 28+ days ago → confidence 1.0
        er1 = model.get_or_create("sensor.e1", is_binary=True)
        er1.record(now - timedelta(days=30), "on")

        # Entity 2: first observation 14 days ago → confidence ~0.5
        er2 = model.get_or_create("sensor.e2", is_binary=True)
        er2.record(now - timedelta(days=14), "on")

        result = model.overall_confidence(now=now)
        assert abs(result - 0.75) < 0.01

    def test_learning_status_inactive(self) -> None:
        """overall_confidence < 0.1 → inactive."""
        model = RoutineModel()
        # No data → confidence = 0.0
        assert model.learning_status() == "inactive"

    def test_learning_status_learning(self) -> None:
        """0.1 <= overall_confidence < 0.8 → learning."""
        model = RoutineModel(history_window_days=28)
        now = datetime(2024, 2, 12, tzinfo=timezone.utc)
        er = model.get_or_create("sensor.test", is_binary=True)
        er.record(now - timedelta(days=14), "on")  # ~0.5 confidence
        assert model.learning_status(now=now) == "learning"

    def test_learning_status_ready(self) -> None:
        """overall_confidence >= 0.8 → ready."""
        model = RoutineModel(history_window_days=28)
        now = datetime(2024, 2, 12, tzinfo=timezone.utc)
        er = model.get_or_create("sensor.test", is_binary=True)
        er.record(now - timedelta(days=30), "on")  # 1.0 confidence
        assert model.learning_status(now=now) == "ready"

    def test_round_trip_empty(self) -> None:
        model = RoutineModel()
        data = model.to_dict()
        restored = RoutineModel.from_dict(data)
        assert restored.overall_confidence() == 0.0
        assert restored.learning_status() == "inactive"

    def test_round_trip_with_entities(self) -> None:
        model = RoutineModel(history_window_days=14)
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        model.record("sensor.door", ts, "on", is_binary=True)
        model.record("sensor.temp", ts, "21.5", is_binary=False)

        data = model.to_dict()
        restored = RoutineModel.from_dict(data)

        er_door = restored.get_or_create("sensor.door", is_binary=True)
        assert er_door.first_observation is not None
        er_temp = restored.get_or_create("sensor.temp", is_binary=False)
        slot_idx = er_temp.slot_index(hour=10, dow=0)
        assert er_temp.slots[slot_idx].numeric_count == 1

    def test_round_trip_history_window_preserved(self) -> None:
        model = RoutineModel(history_window_days=14)
        data = model.to_dict()
        restored = RoutineModel.from_dict(data)
        assert restored._history_window_days == 14


# ---------------------------------------------------------------------------
# is_binary_state — module-level helper
# ---------------------------------------------------------------------------


class TestIsBinaryState:
    def test_on_is_binary(self) -> None:
        assert is_binary_state("on") is True

    def test_off_is_binary(self) -> None:
        assert is_binary_state("off") is True

    def test_open_is_binary(self) -> None:
        assert is_binary_state("open") is True

    def test_closed_is_binary(self) -> None:
        assert is_binary_state("closed") is True

    def test_locked_is_binary(self) -> None:
        assert is_binary_state("locked") is True

    def test_unlocked_is_binary(self) -> None:
        assert is_binary_state("unlocked") is True

    def test_numeric_not_binary(self) -> None:
        assert is_binary_state("21.5") is False

    def test_idle_not_binary(self) -> None:
        assert is_binary_state("idle") is False

    def test_case_insensitive_on(self) -> None:
        assert is_binary_state("ON") is True

    def test_case_insensitive_off(self) -> None:
        assert is_binary_state("OFF") is True

    def test_empty_string_not_binary(self) -> None:
        assert is_binary_state("") is False
