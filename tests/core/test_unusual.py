from __future__ import annotations


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
from custom_components.behaviour_monitor.core.unusual import Unusual, UnusualConfig
from custom_components.behaviour_monitor.core.whereabouts import (
    Whereabouts,
    WhereaboutsConfig,
)

KETTLE = "switch.kettle"
DOOR = "binary_sensor.back_door"
HALL = "binary_sensor.hall_motion"
FRI = date(2026, 11, 13)
NAMES = {KETTLE: "Kettle", DOOR: "Back door", HALL: "Hall"}
CATS = {KETTLE: Category.PLUG, DOOR: Category.CONTACT, HALL: Category.MOTION}
ROOMS = {KETTLE: "Kitchen", DOOR: "Hall", HALL: "Hall"}


def at(d: date, h: int, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)


def mins(d: date, minute: int) -> datetime:
    return at(d, 0) + timedelta(minutes=minute)


def hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


class Site:
    def __init__(self, doors: frozenset[str] = frozenset()) -> None:
        self.u = Unusual(UnusualConfig())
        self.w = Whereabouts(WhereaboutsConfig(outside_doors=doors))
        self.r = EntityRoutineModel(RoutineConfig())
        for eid in NAMES:
            self.r.add(eid, CATS[eid], ROOMS[eid])

    def feed(self, eid: str, ts: datetime) -> None:
        kind = {
            Category.PLUG: EventKind.APPLIANCE_ON,
            Category.CONTACT: EventKind.OPEN,
            Category.MOTION: EventKind.PRESENCE,
        }[CATS[eid]]
        ev = ActivityEvent(eid, CATS[eid], kind, ROOMS[eid], ts)
        self.r.record(ev)
        self.u.record(ev, self.w)
        self.w.record(ev)

    def end(self, d: date, active: bool = True) -> None:
        self.u.finalise_day(d, NAMES, active)

    def ev(self, now: datetime, down: set[str] | None = None, cats=None) -> list:
        return self.u.evaluate(
            now,
            self.w,
            self.r,
            down or set(),
            lambda e: NAMES.get(e, e),
            cats if cats is not None else CATS,
        )


def kinds(alerts: list, kind: str) -> list:
    return [a for a in alerts if a.kind == kind]


def kettle(alerts: list) -> list:
    return [a for a in kinds(alerts, "not_yet_today") if a.source == KETTLE]


def train_kettle(site: Site, firsts: list[int | None], today: date = FRI) -> None:
    """One learned day per entry, ending yesterday; None means not used."""
    n = len(firsts)
    for i, first in enumerate(firsts):
        d = today - timedelta(days=n - i)
        site.feed(HALL, at(d, 6, 30))
        if first is not None:
            site.feed(KETTLE, mins(d, first))
        site.feed(HALL, at(d, 21))
        site.end(d)


# ------------------------------------------------------------ not_yet_today

STEADY = [420 + 2 * i for i in range(20)]  # 07:00 .. 07:38
# P90 = sorted[18] = 456 (07:36), P50 = sorted[10] = 440, A = max(60, 16) = 60.
STEADY_DUE = 456 + 60


def test_not_yet_today_fires_after_usual_plus_allowance():
    s = Site()
    train_kettle(s, STEADY)
    s.feed(HALL, at(FRI, 6, 30))
    assert kettle(s.ev(mins(FRI, STEADY_DUE - 1))) == []
    [a] = kettle(s.ev(mins(FRI, STEADY_DUE)))
    assert a.cls is AlertClass.STATISTICAL and a.severity is Severity.LOW
    assert a.source == KETTLE
    assert a.explanation == "Kettle not used yet today; usually by 07:36"
    assert a.details["room"] == "Kitchen"
    assert a.details["usual_by"] == "07:36"
    # Still open on the next evaluate, gone once the kettle fires.
    assert kettle(s.ev(mins(FRI, STEADY_DUE + 5)))
    s.feed(KETTLE, mins(FRI, STEADY_DUE + 6))
    assert kettle(s.ev(mins(FRI, STEADY_DUE + 7))) == []


def test_not_yet_today_allowance_grows_with_spread():
    s = Site()
    train_kettle(s, [360 + 12 * i for i in range(20)])  # 06:00 .. 09:48
    # P90 = 576 (09:36), P50 = 480, A = 96 > 60: due at 672 (11:12).
    s.feed(HALL, at(FRI, 6, 30))
    assert kettle(s.ev(mins(FRI, 671))) == []
    [a] = kettle(s.ev(mins(FRI, 672)))
    assert a.details["usual_by"] == "09:36"


def test_not_yet_today_needs_fraction_and_min_days():
    s = Site()
    firsts: list[int | None] = list(STEADY)
    firsts[2] = firsts[9] = firsts[15] = None  # used on 17 of 20 = 85%
    train_kettle(s, firsts)
    assert kettle(s.ev(mins(FRI, 23 * 60))) == []

    s = Site()
    train_kettle(s, STEADY[:13])
    assert kettle(s.ev(mins(FRI, 23 * 60))) == []
    # Inactive days (no one home) do not count as learned days.
    s = Site()
    train_kettle(s, STEADY[:13])
    s.end(FRI - timedelta(days=14), active=False)
    assert kettle(s.ev(mins(FRI, 23 * 60))) == []


def test_not_yet_today_skips_down_and_panic():
    s = Site()
    train_kettle(s, STEADY)
    now = mins(FRI, STEADY_DUE + 10)
    assert kettle(s.ev(now))
    assert kettle(s.ev(now, down={KETTLE})) == []
    panic = dict(CATS, **{KETTLE: Category.PANIC})
    assert kettle(s.ev(now, cats=panic)) == []


def test_not_yet_today_went_out_flag():
    now = mins(FRI, STEADY_DUE)

    s = Site(doors=frozenset({DOOR}))
    train_kettle(s, STEADY)
    s.feed(HALL, at(FRI, 6, 30))
    [a] = kettle(s.ev(now))
    assert a.details["went_out_today"] is False

    s = Site(doors=frozenset({DOOR}))
    train_kettle(s, STEADY)
    s.feed(DOOR, at(FRI, 7, 0))
    s.feed(HALL, at(FRI, 7, 40))
    assert s.w.out_spans(FRI)
    [a] = kettle(s.ev(now))
    assert a.details["went_out_today"] is True

    s = Site(doors=frozenset({DOOR}))
    train_kettle(s, STEADY)
    s.feed(DOOR, at(FRI, 8, 0))
    assert s.w.is_out(now)
    [a] = kettle(s.ev(now))
    assert a.details["went_out_today"] is True


# -------------------------------------------------------------- trip_missed


def train_house(site: Site, days: int, today: date, friday_out: bool) -> None:
    for i in range(days):
        d = today - timedelta(days=days - i)
        site.feed(HALL, at(d, 7))
        if friday_out and d.weekday() == 4:
            site.feed(DOOR, at(d, 10))
            site.feed(HALL, at(d, 12, 30))
        site.feed(HALL, at(d, 15))
        site.end(d)


def test_trip_missed_learns_weekday_window_and_fires_after_slack():
    s = Site(doors=frozenset({DOOR}))
    train_house(s, 28, FRI, friday_out=True)  # 4 Fridays out 10:00-12:30
    s.feed(HALL, at(FRI, 7))
    # Window is 09:00-13:30 (outing +-60 min); due at 13:30 + 60 = 14:30.
    assert kinds(s.ev(at(FRI, 14, 29)), "trip_missed") == []
    [a] = kinds(s.ev(at(FRI, 14, 30)), "trip_missed")
    assert a.cls is AlertClass.STATISTICAL and a.severity is Severity.LOW
    assert a.source == "trip:1000"
    assert a.explanation == (
        "Usual Friday outing (around 10:00 to 12:30) didn't happen"
    )
    assert kinds(s.ev(at(FRI, 20)), "trip_missed")
    # Another weekday has no window.
    sat = FRI + timedelta(days=1)
    s.feed(HALL, at(sat, 7))
    assert kinds(s.ev(at(sat, 20)), "trip_missed") == []

    # A Friday with the outing raises nothing.
    s = Site(doors=frozenset({DOOR}))
    train_house(s, 28, FRI, friday_out=True)
    s.feed(HALL, at(FRI, 7))
    s.feed(DOOR, at(FRI, 10, 30))
    s.feed(HALL, at(FRI, 12))
    assert kinds(s.ev(at(FRI, 20)), "trip_missed") == []

    # Still out at the deadline counts as the outing.
    s = Site(doors=frozenset({DOOR}))
    train_house(s, 28, FRI, friday_out=True)
    s.feed(DOOR, at(FRI, 13))
    assert kinds(s.ev(at(FRI, 14, 30)), "trip_missed") == []


def test_trip_missed_needs_four_days_and_doors():
    s = Site(doors=frozenset({DOOR}))
    train_house(s, 21, FRI, friday_out=True)  # 3 Fridays
    s.feed(HALL, at(FRI, 7))
    assert kinds(s.ev(at(FRI, 20)), "trip_missed") == []

    s = Site()  # no outside doors: no OUT history
    train_house(s, 28, FRI, friday_out=True)
    s.feed(HALL, at(FRI, 7))
    assert kinds(s.ev(at(FRI, 20)), "trip_missed") == []


# -------------------------------------------------------------- unusual_now


def train_door(site: Site, days: int, today: date = FRI) -> None:
    for i in range(days):
        d = today - timedelta(days=days - i)
        for h in range(8, 21):
            site.feed(DOOR, at(d, h, 5))
        site.end(d)


def test_unusual_now_fires_only_outside_learned_hours_and_ttl():
    s = Site()
    train_door(s, 20)
    s.feed(DOOR, at(FRI, 2, 14))
    s.feed(DOOR, at(FRI, 2, 40))
    [a] = kinds(s.ev(at(FRI, 2, 45)), "unusual_now")
    assert a.cls is AlertClass.STATISTICAL and a.severity is Severity.LOW
    assert a.source == DOOR
    assert a.explanation == "Back door active at 02:14, unusual for this time"
    assert a.raised_at == at(FRI, 2, 14)
    assert a.details["room"] == "Hall"
    assert kinds(s.ev(at(FRI, 4, 13)), "unusual_now")
    assert kinds(s.ev(at(FRI, 4, 15)), "unusual_now") == []

    s.feed(DOOR, at(FRI, 21, 0))  # neighbour of the learned 20:00
    s.feed(DOOR, at(FRI, 7, 30))  # neighbour of the learned 08:00
    assert kinds(s.ev(at(FRI, 21, 5)), "unusual_now") == []


def test_unusual_now_latest_wins_and_wraps_midnight():
    s = Site()
    train_door(s, 20)
    s.feed(DOOR, at(FRI, 2, 14))
    s.feed(DOOR, at(FRI, 3, 20))
    [a] = kinds(s.ev(at(FRI, 3, 30)), "unusual_now")
    assert a.raised_at == at(FRI, 3, 20)

    # Learned at 23:00 only: 00:10 is its neighbour across midnight.
    s = Site()
    for i in range(20):
        d = FRI - timedelta(days=20 - i)
        s.feed(DOOR, at(d, 23, 5))
        s.end(d)
    s.feed(DOOR, at(FRI, 0, 10))
    assert kinds(s.ev(at(FRI, 0, 20)), "unusual_now") == []


def test_unusual_now_new_sensor_and_down_sensor_silent():
    s = Site()
    train_door(s, 13)
    s.feed(DOOR, at(FRI, 2, 14))
    assert kinds(s.ev(at(FRI, 2, 20)), "unusual_now") == []

    s = Site()
    train_door(s, 20)
    s.feed(DOOR, at(FRI, 2, 14))
    assert kinds(s.ev(at(FRI, 2, 20), down={DOOR}), "unusual_now") == []


# -------------------------------------------------------------- persistence


def test_round_trip_and_tolerant_from_dict():
    s = Site(doors=frozenset({DOOR}))
    for i in range(28):
        d = FRI - timedelta(days=28 - i)
        s.feed(HALL, at(d, 7))
        s.feed(KETTLE, at(d, 7, 20))
        if d.weekday() == 4:
            s.feed(DOOR, at(d, 10))
            s.feed(HALL, at(d, 12, 30))
        s.feed(HALL, at(d, 15))
        s.end(d)
    s.feed(DOOR, at(FRI, 2, 14))
    s.feed(HALL, at(FRI, 2, 20))
    data = s.u.to_dict()
    back = Unusual.from_dict(data, UnusualConfig())
    assert back.to_dict() == data
    now = at(FRI, 20)
    before = [a.to_dict() for a in s.ev(now)]
    assert {a["kind"] for a in before} == {"not_yet_today", "trip_missed"}
    s.u = back
    assert [a.to_dict() for a in s.ev(now)] == before

    fresh = Unusual(UnusualConfig()).to_dict()
    for bad in ({}, {"first": 5}, {"first": {}, "active": [1, 2]}, None, []):
        assert Unusual.from_dict(bad, UnusualConfig()).to_dict() == fresh


def test_remove_and_prune():
    s = Site()
    train_kettle(s, STEADY)
    s.u.prune(FRI - timedelta(days=10))
    assert kettle(s.ev(mins(FRI, STEADY_DUE))) == []
    s = Site()
    train_kettle(s, STEADY)
    s.u.remove(KETTLE)
    assert kettle(s.ev(mins(FRI, STEADY_DUE))) == []
