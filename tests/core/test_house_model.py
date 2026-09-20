from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import Severity
from custom_components.behaviour_monitor.core.events import (
    ActivityEvent,
    Category,
    EventKind,
)
from custom_components.behaviour_monitor.core.house_model import HouseConfig, HouseModel

MON = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def _ev(
    ts: datetime, room: str = "Kitchen", kind: EventKind = EventKind.PRESENCE
) -> ActivityEvent:
    return ActivityEvent("binary_sensor.x", Category.MOTION, kind, room, ts)


def _train(
    model: HouseModel, days: int = 14, gap_min: int = 5, start: datetime = MON
) -> None:
    """Every day, events every gap_min minutes from 09:00 to 11:00."""
    for d in range(days):
        base = start + timedelta(days=d)
        for m in range(0, 121, gap_min):
            model.record(_ev(base + timedelta(minutes=m)))


def test_non_activity_kinds_are_ignored():
    m = HouseModel(HouseConfig())
    m.record(_ev(MON, kind=EventKind.CLOSE))
    assert m.last_activity is None


def test_learns_expected_gap_for_slot():
    m = HouseModel(HouseConfig())
    _train(m)
    assert m.expected_gap(MON + timedelta(days=14, minutes=30)) == 300.0
    assert m.expected_gap(MON + timedelta(days=14, hours=5)) is None
    assert m.confidence(MON + timedelta(days=14)) == 1.0


def test_severity_ladder_and_sustain():
    m = HouseModel(HouseConfig(sustain_polls=2))
    _train(m)
    now = MON + timedelta(days=14)
    m.record(_ev(now))
    a = m.evaluate(now + timedelta(minutes=10))  # ratio 2
    assert a.severity is None and a.ratio == 2.0
    a = m.evaluate(now + timedelta(minutes=20))  # ratio 4 -> low, first poll
    assert a.severity is None
    a = m.evaluate(now + timedelta(minutes=21))  # second poll sustains
    assert a.severity is Severity.LOW
    a = m.evaluate(now + timedelta(minutes=35))  # ratio 7 -> medium after two polls
    a = m.evaluate(now + timedelta(minutes=36))
    assert a.severity is Severity.MEDIUM
    a = m.evaluate(now + timedelta(minutes=61))
    a = m.evaluate(now + timedelta(minutes=62))
    assert a.severity is Severity.HIGH
    # one poll below threshold drops one level
    m.record(_ev(now + timedelta(minutes=63)))
    a = m.evaluate(now + timedelta(minutes=64))
    assert a.severity is Severity.MEDIUM


def test_restart_clock_resets_gap_and_ladder():
    m = HouseModel(HouseConfig(sustain_polls=2))
    _train(m)
    now = MON + timedelta(days=14)
    m.record(_ev(now))
    m.evaluate(now + timedelta(minutes=20))  # ratio 4 -> low, first poll
    m.evaluate(now + timedelta(minutes=21))  # second poll sustains -> LOW
    m.evaluate(now + timedelta(minutes=35))  # ratio 7 -> medium, first poll
    m.evaluate(now + timedelta(minutes=36))  # second poll sustains -> MEDIUM
    m.evaluate(now + timedelta(minutes=61))  # ratio 12.2 -> high, first poll
    a = m.evaluate(now + timedelta(minutes=62))  # second poll sustains -> HIGH
    assert a.severity is Severity.HIGH
    t = now + timedelta(minutes=70)
    m.restart_clock(t)
    assert m.last_activity == t
    a = m.evaluate(t + timedelta(minutes=1))
    assert a.severity is None


def test_floor_prevents_tiny_median_blowing_up_ratio():
    m = HouseModel(HouseConfig(floor_s=300.0))
    _train(m, gap_min=1)
    now = MON + timedelta(days=14)
    m.record(_ev(now))
    a = m.evaluate(now + timedelta(minutes=5))
    assert a.expected_s == 60.0 and a.ratio == 1.0


def test_unknown_slot_reports_no_severity():
    m = HouseModel(HouseConfig())
    _train(m)
    now = MON + timedelta(days=14, hours=6)
    m.record(_ev(now))
    a = m.evaluate(now + timedelta(hours=3))
    assert a.severity is None and a.expected_s is None


def test_degraded_when_live_fraction_low():
    m = HouseModel(HouseConfig(min_live_fraction=0.5))
    _train(m)
    now = MON + timedelta(days=14)
    m.record(_ev(now))
    for _ in range(2):
        a = m.evaluate(now + timedelta(hours=2), live_fraction=0.4)
    assert a.degraded is True and a.severity is None


def test_degraded_polls_hold_the_ladder():
    m = HouseModel(HouseConfig(sustain_polls=2, min_live_fraction=0.5))
    _train(m)
    now = MON + timedelta(days=14)
    m.record(_ev(now))
    m.evaluate(now + timedelta(minutes=10))  # ratio 2
    m.evaluate(now + timedelta(minutes=20))  # ratio 4 -> low, first poll
    m.evaluate(now + timedelta(minutes=21))  # second poll sustains -> LOW
    m.evaluate(now + timedelta(minutes=35))  # ratio 7 -> medium, first poll
    m.evaluate(now + timedelta(minutes=36))  # second poll sustains -> MEDIUM
    m.evaluate(now + timedelta(minutes=61))  # ratio 12.2 -> high, first poll
    a = m.evaluate(now + timedelta(minutes=62))  # second poll sustains -> HIGH
    assert a.severity is Severity.HIGH
    for minutes in (63, 64, 65):
        a = m.evaluate(now + timedelta(minutes=minutes), live_fraction=0.4)
        assert a.degraded is True and a.severity is None
    a = m.evaluate(now + timedelta(minutes=66), live_fraction=1.0)  # ratio 13.2
    assert a.degraded is False and a.severity is Severity.HIGH


def test_rooms_visited_and_prune():
    m = HouseModel(HouseConfig(window_days=28))
    m.record(_ev(MON, room="Kitchen"))
    m.record(_ev(MON + timedelta(minutes=1), room="Bath"))
    assert m.rooms_visited(date(2026, 9, 21)) == {"Kitchen", "Bath"}
    m.prune(date(2026, 9, 22))
    assert m.rooms_visited(date(2026, 9, 21)) == set()


def test_expected_gap_pools_across_days_when_slot_is_sparse():
    """The 11:00 boundary event only fires once a day, so the exact weekday+hour
    slot stays sparse for weeks; expected_gap should pool by hour of day instead
    of returning None until a full month of weekday recurrences pile up."""
    m = HouseModel(HouseConfig())
    _train(m, days=7)  # one of each weekday, events every 5 min from 09:00-11:00
    sparse = MON + timedelta(days=7, hours=2, minutes=30)  # next Monday, 11:30
    assert m.expected_gap(sparse) is None  # slot=1, weekday pool=5, all-days pool=7
    _train(m, days=3, start=MON + timedelta(days=7))  # 3 more days -> 10 trained
    dense = MON + timedelta(days=14, hours=2, minutes=30)  # a later Monday, 11:30
    assert m.expected_gap(dense) == 300.0  # weekday pool reaches 8


def test_expected_gap_falls_back_to_all_days_pool():
    """When the same-day-type pool is also sparse, pool across all seven weekdays."""
    m = HouseModel(HouseConfig())
    m.record(_ev(datetime(2026, 9, 23, 15, 10, tzinfo=timezone.utc)))  # one Wednesday
    weekends = (
        date(2026, 9, 26),  # Sat
        date(2026, 9, 27),  # Sun
        date(2026, 10, 3),  # Sat
        date(2026, 10, 4),  # Sun
    )
    for d in weekends:
        base = datetime(d.year, d.month, d.day, 15, 0, tzinfo=timezone.utc)
        for mins in range(0, 61, 5):
            m.record(_ev(base + timedelta(minutes=mins)))
    query = datetime(2026, 9, 30, 15, 30, tzinfo=timezone.utc)  # following Wednesday
    assert query.weekday() == 2  # a weekday, so the weekend pool can't serve it
    assert m.expected_gap(query) == 300.0  # served by the all-days pool
    assert m.expected_gap(datetime(2026, 9, 30, 3, 30, tzinfo=timezone.utc)) is None


def test_round_trip():
    m = HouseModel(HouseConfig())
    _train(m)
    m2 = HouseModel.from_dict(m.to_dict(), HouseConfig())
    assert m2.expected_gap(MON + timedelta(days=14, minutes=30)) == 300.0
    assert m2.last_activity == m.last_activity
    assert HouseModel.from_dict({"bad": True}, HouseConfig()).last_activity is None
