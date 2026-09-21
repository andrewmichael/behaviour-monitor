from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import AlertClass, Severity
from custom_components.behaviour_monitor.core.entity_routine import (
    EntityRoutineModel,
    RoutineConfig,
)
from custom_components.behaviour_monitor.core.events import (
    ActivityEvent,
    Category,
    EventKind,
)

MON = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
KETTLE = "sensor.kettle"


def _model() -> EntityRoutineModel:
    m = EntityRoutineModel(RoutineConfig())
    m.add(KETTLE, Category.PLUG, "Kitchen")
    m.add("binary_sensor.front", Category.CONTACT, "Hall")
    return m


def _kettle(ts: datetime, kind: EventKind = EventKind.APPLIANCE_ON) -> ActivityEvent:
    return ActivityEvent(KETTLE, Category.PLUG, kind, "Kitchen", ts)


def _train(
    m: EntityRoutineModel, days: int = 14, hour: int = 8, skip: set[int] = frozenset()
) -> None:
    for d in range(days):
        if d in skip:
            continue
        m.record(_kettle(MON + timedelta(days=d, hours=hour, minutes=5)))


def test_expected_window_learned_when_fired_on_most_days():
    m = _model()
    _train(m, days=14)
    assert m.expected_windows(KETTLE, weekday=0) == []  # only 2 Mondays seen; min is 3
    _train(m, days=21)  # now 3 Mondays
    assert m.expected_windows(KETTLE, weekday=0) == [8]
    assert m.expected_windows("binary_sensor.front", weekday=0) == []


def test_window_needs_fraction_of_days():
    m = _model()
    # Mondays only on 2 of 4 weeks -> 50% < 70%
    _train(m, days=28, skip={7, 21})
    # The skipped Mondays still need to be observed days (just not at hour 8),
    # otherwise the min_window_days gate returns [] before the fraction is checked.
    for d in (7, 21):
        m.record(_kettle(MON + timedelta(days=d, hours=15, minutes=5)))
    assert (
        len(
            {d for d in m.get(KETTLE).days_seen if date.fromisoformat(d).weekday() == 0}
        )
        == 4
    )
    assert m.expected_windows(KETTLE, weekday=0) == []
    assert m.expected_windows(KETTLE, weekday=1) == [8]


def test_missed_window_raises_routine_note_until_event_arrives():
    m = _model()
    _train(m, days=28)
    day = MON + timedelta(days=28)  # Monday
    assert m.evaluate(day + timedelta(hours=8, minutes=30)) == []  # window still open
    notes = m.evaluate(day + timedelta(hours=9, minutes=1))
    assert len(notes) == 1
    n = notes[0]
    assert n.cls is AlertClass.STATISTICAL and n.severity is Severity.LOW
    assert n.source == KETTLE and n.kind == "routine_missed" and n.details["hour"] == 8
    assert "Kitchen" in n.explanation
    m.record(_kettle(day + timedelta(hours=9, minutes=30)))
    assert m.evaluate(day + timedelta(hours=9, minutes=31)) == []


def test_longest_gap_last_event_and_daily_counts():
    m = _model()
    _train(m, days=3)
    assert m.longest_gap(KETTLE) == 86400.0
    assert m.longest_gap("binary_sensor.front") is None
    assert m.last_event(KETTLE) == MON + timedelta(days=2, hours=8, minutes=5)
    assert m.daily_counts(date(2026, 9, 22)) == {KETTLE: 1, "binary_sensor.front": 0}
    # a week away leaves one very long gap, filed under the day it started
    for d in (10, 11, 12):
        m.record(_kettle(MON + timedelta(days=d, hours=8, minutes=5)))
    assert m.longest_gap(KETTLE) == 8 * 86400.0
    # once that day drops out of the window the entity is sensitive again
    m.prune(date(2026, 10, 1))
    assert m.longest_gap(KETTLE) == 86400.0


def test_duration_medians_per_day():
    m = _model()
    for i, dur in enumerate((10.0, 30.0, 20.0)):
        m.record(
            ActivityEvent(
                "binary_sensor.front",
                Category.CONTACT,
                EventKind.CLOSE,
                "Hall",
                MON + timedelta(hours=i),
                duration_s=dur,
            )
        )
    assert m.daily_duration_medians(date(2026, 9, 21)) == {"binary_sensor.front": 20.0}


def test_restart_clock_sets_last_event_without_learning():
    m = _model()
    _train(m, days=3)
    before_slots = [dict(s) for s in m.get(KETTLE).slot_days]
    before_days_seen = set(m.get(KETTLE).days_seen)
    before_gap = m.longest_gap(KETTLE)
    t = MON + timedelta(days=10)
    m.restart_clock(t)
    assert m.last_event(KETTLE) == t
    assert m.last_event("binary_sensor.front") == t  # never fired, still gets set
    assert [dict(s) for s in m.get(KETTLE).slot_days] == before_slots
    assert set(m.get(KETTLE).days_seen) == before_days_seen
    assert m.longest_gap(KETTLE) == before_gap


def test_prune_remove_and_round_trip():
    m = _model()
    _train(m, days=28)
    m.prune(date(2026, 10, 12))
    assert m.daily_counts(date(2026, 9, 21))[KETTLE] == 0
    m2 = EntityRoutineModel.from_dict(m.to_dict(), RoutineConfig())
    assert set(m2.entity_ids) == {KETTLE, "binary_sensor.front"}
    assert m2.last_event(KETTLE) == m.last_event(KETTLE)
    m2.remove(KETTLE)
    assert KETTLE not in m2.entity_ids
    assert EntityRoutineModel.from_dict({"x": 1}, RoutineConfig()).entity_ids == []
