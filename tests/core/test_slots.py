from datetime import date, datetime, timezone

from custom_components.behaviour_monitor.core.slots import (
    SLOTS,
    confidence,
    day_type,
    is_weekend,
    iso_day,
    median_mad,
    slot_index,
    slot_label,
)


def test_slot_index_is_weekday_times_24_plus_hour():
    mon_8 = datetime(2026, 9, 21, 8, 30, tzinfo=timezone.utc)  # Monday
    sun_23 = datetime(2026, 9, 27, 23, 0, tzinfo=timezone.utc)
    assert slot_index(mon_8) == 8
    assert slot_index(sun_23) == 167
    assert SLOTS == 168
    assert slot_label(8) == "Mon 08:00"
    assert slot_label(167) == "Sun 23:00"


def test_median_mad():
    assert median_mad([1, 2, 3, 4, 100]) == (3.0, 1.0)
    assert median_mad([]) == (0.0, 0.0)
    assert median_mad([5.0]) == (5.0, 0.0)


def test_weekend_and_confidence():
    assert is_weekend(date(2026, 9, 26)) is True
    assert day_type(date(2026, 9, 21)) == "weekday"
    assert day_type(date(2026, 9, 27)) == "weekend"
    assert confidence(7, 14) == 0.5
    assert confidence(20, 14) == 1.0
    assert confidence(0, 14) == 0.0
    assert iso_day(date(2026, 9, 21)) == "2026-09-21"
