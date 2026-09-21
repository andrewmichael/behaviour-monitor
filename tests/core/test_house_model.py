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
    m = HouseModel(HouseConfig(sustain_polls=2, floor_s=300.0))
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
    m = HouseModel(HouseConfig(sustain_polls=2, floor_s=300.0))
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
    m = HouseModel(HouseConfig(sustain_polls=2, min_live_fraction=0.5, floor_s=300.0))
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


def _burst(m: HouseModel, start: datetime, minutes: int, gap_min: int = 5) -> None:
    """Events every gap_min minutes for `minutes` minutes from `start`."""
    for mins in range(0, minutes + 1, gap_min):
        m.record(_ev(start + timedelta(minutes=mins)))


def test_expected_gap_pools_across_days_when_slot_is_sparse():
    """A single day of events leaves the exact weekday+hour slot short of
    MIN_DAYS_PER_SLOT; expected_gap should pool by hour of day across the same
    day type instead of returning None. Bursts run to 10:00 so the trailing
    silence is filed under hour 10, not hour 9."""
    m = HouseModel(HouseConfig())
    _burst(m, MON, 60)  # Monday 09:00-10:00 -> one day filed under Mon 09
    query = MON + timedelta(days=7, minutes=15)  # the next Monday, 09:15
    assert m.expected_gap(query) is None  # slot 1 day, weekday pool 1, all 1
    _burst(m, MON + timedelta(days=1), 60)  # Tuesday -> weekday pool 2 days
    assert m.expected_gap(query) is None
    _burst(m, MON + timedelta(days=2), 60)  # Wednesday -> weekday pool 3 days
    assert m.expected_gap(query) == 300.0


def test_expected_gap_falls_back_to_all_days_pool():
    """When the same-day-type pool is also sparse, pool across all seven weekdays."""
    m = HouseModel(HouseConfig())
    # Two weekend days, 09:00-10:00 every 5 min: twelve gaps each under hour 9.
    # The last event of each day sits in hour 10, so the overnight silence is
    # filed under hour 10 and never pollutes the hour 9 pool.
    for d in (date(2026, 9, 26), date(2026, 9, 27)):  # Sat, Sun
        _burst(m, datetime(d.year, d.month, d.day, 9, 0, tzinfo=timezone.utc), 60)
    wed = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    _burst(m, wed, 10)  # one Wednesday, 09:00/09:05/09:10 -> two gaps
    query = wed + timedelta(days=7, minutes=7)  # the following Wednesday, 09:07
    assert query.weekday() == 2  # a weekday, so the weekend pool can't serve it
    assert m.expected_gap(query) == 300.0  # slot 1 day, weekday 1, all-days 3
    assert m.expected_gap(query.replace(hour=3)) is None


def test_round_trip():
    m = HouseModel(HouseConfig())
    _train(m)
    m2 = HouseModel.from_dict(m.to_dict(), HouseConfig())
    assert m2.expected_gap(MON + timedelta(days=14, minutes=30)) == 300.0
    assert m2.last_activity == m.last_activity
    assert HouseModel.from_dict({"bad": True}, HouseConfig()).last_activity is None


def test_default_floor_is_twenty_minutes():
    assert HouseConfig().floor_s == 1200.0


def test_one_busy_day_does_not_make_a_slot_trusted():
    """Trust is earned by distinct days, not by the number of gaps: thirty
    gaps from a single day say nothing about what is normal for the hour."""
    m = HouseModel(HouseConfig())
    _burst(m, MON, 60, gap_min=2)  # thirty gaps, all on one Monday
    assert m.expected_gap(MON + timedelta(days=7, minutes=15)) is None


def test_expected_gap_uses_longest_silence_per_day():
    """Within-burst chatter must not drown the real silence: each day
    contributes only the longest gap that started in the slot."""
    m = HouseModel(HouseConfig())
    for d in range(5):  # Mon..Fri
        base = MON + timedelta(days=d)
        _burst(m, base, 20, gap_min=2)  # 09:00..09:20, ten 120 s gaps
        for mins in (50, 55, 60):  # a 1800 s silence, then two 300 s gaps
            m.record(_ev(base + timedelta(minutes=mins)))
    assert m.expected_gap(MON + timedelta(days=7, minutes=5)) == 1800.0


def test_prune_drops_slot_days_before_cutoff():
    m = HouseModel(HouseConfig())
    for d in range(3):
        _burst(m, MON + timedelta(days=d), 60)
    query = MON + timedelta(days=7, minutes=15)
    assert m.expected_gap(query) == 300.0
    m.prune(date(2026, 9, 23))  # drops Mon and Tue, leaves Wed alone
    assert m.expected_gap(query) is None


def test_from_dict_accepts_gap_lists_from_earlier_stores():
    """Stores written before per-day maxima hold every gap as [day, gap]
    pairs; the longest per day must be kept rather than the store dropped."""
    m = HouseModel(HouseConfig())
    for d in range(3):
        _burst(m, MON + timedelta(days=d), 60)
    old = m.to_dict()
    old["gaps"] = [
        [[day, g] for day, g in slot.items()] + [[day, 60.0] for day in slot]
        for slot in old["gaps"]
    ]
    m2 = HouseModel.from_dict(old, HouseConfig())
    assert m2.expected_gap(MON + timedelta(days=7, minutes=15)) == 300.0
