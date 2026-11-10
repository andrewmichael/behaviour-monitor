from __future__ import annotations


from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
from custom_components.behaviour_monitor.core.slots import iso_day
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
    s.feed(DOOR, at(FRI, 6, 0))
    s.feed(HALL, at(FRI, 7, 20))
    assert s.w.out_spans(FRI)
    [a] = kettle(s.ev(now))  # back 07:20, so 08:20 is before the 08:36 due
    assert a.details["went_out_today"] is True


def test_not_yet_today_held_while_out():
    now = mins(FRI, STEADY_DUE)
    s = Site(doors=frozenset({DOOR}))
    train_kettle(s, STEADY)
    s.feed(HALL, at(FRI, 6, 30))
    s.feed(DOOR, at(FRI, 8, 0))
    assert s.w.is_out(now)
    assert kettle(s.ev(now)) == []
    assert kettle(s.ev(at(FRI, 11))) == []


def _out_until_1122() -> Site:
    s = Site(doors=frozenset({DOOR}))
    train_kettle(s, STEADY)
    s.feed(HALL, at(FRI, 6, 30))
    s.feed(DOOR, at(FRI, 8, 0))
    s.feed(DOOR, at(FRI, 11, 22))  # the door opening home ends the outing
    s.feed(HALL, at(FRI, 11, 23))
    assert not s.w.is_out(at(FRI, 11, 24))
    [(_, back)] = s.w.out_spans(FRI)
    assert back == 11 * 60 + 22
    return s


def test_not_yet_today_after_return_waits_allowance():
    # Due at 08:36 normally; back home at 11:22, so not before 12:22.
    s = _out_until_1122()
    assert kettle(s.ev(at(FRI, 11, 30))) == []
    s.feed(KETTLE, at(FRI, 11, 38))
    assert kettle(s.ev(at(FRI, 12, 30))) == []

    s = _out_until_1122()
    assert kettle(s.ev(mins(FRI, 12 * 60 + 21))) == []
    [a] = kettle(s.ev(mins(FRI, 12 * 60 + 22)))
    assert a.details["went_out_today"] is True
    assert a.raised_at == mins(FRI, 12 * 60 + 22)


def test_out_overnight_counts_as_going_out_on_the_day_back():
    # Out Thursday 18:00, back Friday 11:00: no kettle card before 12:00,
    # and the card says she went out today.
    thu = FRI - timedelta(days=1)
    s = Site(doors=frozenset({DOOR}))
    train_kettle(s, STEADY, today=thu)
    s.feed(HALL, at(thu, 6, 30))
    s.feed(KETTLE, at(thu, 7))
    s.feed(DOOR, at(thu, 18))
    s.end(thu)
    s.feed(DOOR, at(FRI, 11))
    s.feed(HALL, at(FRI, 11, 1))
    assert s.w.out_spans(FRI) == [(0, 660)]
    assert kettle(s.ev(at(FRI, 11, 59))) == []
    [a] = kettle(s.ev(at(FRI, 12)))
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


def test_out_overnight_covers_a_morning_outing_window():
    s = Site(doors=frozenset({DOOR}))
    thu = FRI - timedelta(days=1)
    train_house(s, 27, thu, friday_out=True)  # 4 Fridays out 10:00-12:30
    s.feed(HALL, at(thu, 7))
    s.feed(DOOR, at(thu, 18))
    s.end(thu)
    s.feed(DOOR, at(FRI, 11))  # back from the night away
    s.feed(HALL, at(FRI, 11, 1))
    assert s.u._outing_windows(FRI, s.w)
    assert kinds(s.ev(at(FRI, 20)), "trip_missed") == []


def test_zero_length_trip_window_is_not_learned():
    # Four Fridays with 15-minute outings at 13:00, 14:00, 14:30 and 15:30.
    # With the 60-minute slack, 13:30-15:15 is "out" on 3 of 4 Fridays, but
    # the outings never overlap, so the window has no core and isn't learned.
    s = Site(doors=frozenset({DOOR}))
    fridays = [FRI - timedelta(days=7 * k) for k in (4, 3, 2, 1)]
    starts = [13 * 60, 14 * 60, 14 * 60 + 30, 15 * 60 + 30]
    for i in range(28):
        d = FRI - timedelta(days=28 - i)
        s.feed(HALL, at(d, 7))
        if d in fridays:
            start = starts[fridays.index(d)]
            s.feed(DOOR, mins(d, start))
            s.feed(HALL, mins(d, start + 15))
            assert s.w.out_spans(d) == [(start, start + 15)]
        s.feed(HALL, at(d, 18))
        s.end(d)
    s.feed(HALL, at(FRI, 7))
    assert s.u._outing_windows(FRI, s.w) == []
    assert kinds(s.ev(at(FRI, 23)), "trip_missed") == []


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


# -------------------------------------------------------------------- night

KITCHEN = "binary_sensor.kitchen_motion"
BACK = "binary_sensor.back_room_motion"
TV = "switch.back_room_tv"
BED = "binary_sensor.bedroom_motion"
LANDING = "binary_sensor.landing_motion"
BATH = "binary_sensor.bathroom_motion"
FRONT = "binary_sensor.front_door"
KDOOR = "binary_sensor.kitchen_door"
N_ROOMS = {
    KITCHEN: "Kitchen",
    BACK: "Back room",
    TV: "Back room",
    BED: "Bedroom",
    LANDING: "Landing",
    BATH: "Bathroom",
    FRONT: "Hall",
    KDOOR: "Kitchen",
}
N_CATS = {
    eid: (
        Category.PLUG
        if eid == TV
        else Category.CONTACT if eid in (FRONT, KDOOR) else Category.MOTION
    )
    for eid in N_ROOMS
}
N_NAMES = {FRONT: "Front door", KDOOR: "Kitchen door", KITCHEN: "Kitchen"}
UPSTAIRS = frozenset({"Landing", "Bathroom"})
EVE = date(2026, 11, 21)  # the evening under test, after 20 trained nights
NIGHT_KINDS = ("night_downstairs", "night_door")
# 0-10 minute kitchen trips on some nights (index -> minutes).
TRIPS = {0: 0, 3: 4, 6: 10, 9: 2, 12: 7, 15: 10, 18: 5}


def nt(eve: date, h: int, m: int = 0, tz=timezone.utc, fold: int = 0) -> datetime:
    """A time in the night that follows evening ``eve`` (before noon: next day)."""
    d = eve + timedelta(days=1) if h < 12 else eve
    return datetime(d.year, d.month, d.day, h, m, tzinfo=tz, fold=fold)


class NightSite:
    def __init__(
        self,
        upstairs: frozenset[str] = UPSTAIRS,
        tz=timezone.utc,
        **where: object,
    ) -> None:
        self.tz = tz
        self.cfg = UnusualConfig(upstairs=upstairs)
        self.u = Unusual(self.cfg)
        self.w = Whereabouts(
            WhereaboutsConfig(
                outside_doors=frozenset({FRONT, KDOOR}),
                sitting_appliances=frozenset({TV}),
                **where,  # type: ignore[arg-type]
            )
        )
        self.r = EntityRoutineModel(RoutineConfig())

    def t(self, eve: date, h: int, m: int = 0, fold: int = 0) -> datetime:
        return nt(eve, h, m, self.tz, fold)

    def feed(
        self,
        eid: str,
        ts: datetime,
        kind: EventKind | None = None,
        last_rise: datetime | None = None,
    ) -> None:
        if kind is None:
            kind = {
                Category.PLUG: EventKind.APPLIANCE_ON,
                Category.CONTACT: EventKind.OPEN,
                Category.MOTION: EventKind.PRESENCE,
            }[N_CATS[eid]]
        ev = ActivityEvent(
            eid, N_CATS[eid], kind, N_ROOMS[eid], ts, last_rise=last_rise
        )
        self.u.record(ev, self.w)
        self.w.record(ev)

    def ev(self, now: datetime) -> list:
        return [
            a
            for a in self.u.evaluate(
                now, self.w, self.r, set(), lambda e: N_NAMES.get(e, e), N_CATS
            )
            if a.kind in NIGHT_KINDS
        ]

    def evening(self, eve: date, tv_off: bool = True) -> None:
        """Day rooms until 21:55, then up to the bedroom within 2 min."""
        t = self.t
        self.feed(KITCHEN, t(eve, 18))
        self.feed(TV, t(eve, 19))
        for h in (19, 20, 21):
            self.feed(BACK, t(eve, h, 30))
        if tv_off:
            self.feed(TV, t(eve, 21, 50), EventKind.APPLIANCE_OFF)
        self.feed(KITCHEN, t(eve, 21, 55))
        self.feed(BED, t(eve, 21, 57))

    def trip(self, eve: date, h: int, m: int, length: int, room=KITCHEN) -> None:
        start = self.t(eve, h, m)
        self.feed(BED, start - timedelta(minutes=1))  # coming down
        for k in [*range(0, length, 5), length]:  # moving about downstairs
            self.feed(room, start + timedelta(minutes=k))
        self.feed(BED, start + timedelta(minutes=length + 1))

    def door(self, eve: date, h: int, m: int, eid: str = KDOOR) -> None:
        """Down, a door, 14 min downstairs, back up after the door's hold."""
        at_ = self.t(eve, h, m)
        self.feed(BED, at_ - timedelta(minutes=3))
        self.feed(KITCHEN, at_ - timedelta(minutes=2))
        self.feed(eid, at_)
        self.feed(KITCHEN, at_ + timedelta(minutes=2))
        self.feed(KITCHEN, at_ + timedelta(minutes=12))
        self.feed(BED, at_ + timedelta(minutes=16))

    def morning(self, eve: date) -> None:
        self.feed(KITCHEN, self.t(eve, 7))

    def nights(self) -> dict:
        return self.u.to_dict()["night"]["nights"]


def _night_house(
    site: NightSite,
    n: int = 20,
    before: date = EVE,
    trips: dict[int, int] | None = None,
    doors: dict[int, tuple[int, int]] | None = None,
) -> None:
    """Train ``n`` ordinary nights on the evenings before ``before``."""
    trips = TRIPS if trips is None else trips
    doors = doors or {}
    for i in range(n):
        d = before - timedelta(days=n - i)
        site.evening(d)
        site.ev(site.t(d, 22, 40))
        if i in doors:
            site.door(d, *doors[i])
        if i in trips:
            site.trip(d, 2, 0, trips[i])
        site.ev(site.t(d, 3))
        site.morning(d)


def polls(site: NightSite, start: datetime, end: datetime) -> list[list]:
    out = []
    now = start
    while now <= end:
        out.append(site.ev(now))
        now += timedelta(minutes=1)
    return out


def test_night_starts_only_after_going_up_and_quiet_and_tv_off():
    s = NightSite()
    _night_house(s)
    assert len(s.nights()) == 20
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 26))
    assert s.u.night_since is None
    s.ev(s.t(EVE, 22, 27))
    assert s.u.night_since == s.t(EVE, 21, 57)

    # TV left on in the back room: someone is still downstairs.
    s = NightSite()
    _night_house(s)
    s.evening(EVE, tv_off=False)
    s.ev(s.t(EVE, 23, 30))
    assert s.u.night_since is None
    s.feed(TV, s.t(EVE, 23, 31), EventKind.APPLIANCE_OFF)
    s.ev(s.t(EVE, 23, 32))
    assert s.u.night_since == s.t(EVE, 21, 57)


def test_tv_on_doze_is_not_night():
    s = NightSite()
    _night_house(s)
    s.feed(KITCHEN, s.t(EVE, 18))
    s.feed(TV, s.t(EVE, 19))
    s.feed(BACK, s.t(EVE, 21))
    s.ev(s.t(EVE, 23, 30))
    assert s.u.night_since is None
    # Someone fetches something from upstairs; the TV is still on.
    s.feed(KITCHEN, s.t(EVE, 23, 40))
    s.feed(BED, s.t(EVE, 23, 42))
    s.feed(KITCHEN, s.t(EVE, 1, 0))
    s.feed(KITCHEN, s.t(EVE, 1, 45))
    assert all(p == [] for p in polls(s, s.t(EVE, 23, 30), s.t(EVE, 2, 30)))
    assert s.u.night_since is None


def test_quiet_read_without_going_up_is_not_night():
    s = NightSite()
    _night_house(s)
    s.feed(KITCHEN, s.t(EVE, 18))
    s.feed(BACK, s.t(EVE, 21, 30))
    s.ev(s.t(EVE, 23, 30))
    assert s.u.night_since is None
    for m in range(0, 45, 5):
        s.feed(KITCHEN, s.t(EVE, 23, 40) + timedelta(minutes=m))
    assert all(p == [] for p in polls(s, s.t(EVE, 23, 30), s.t(EVE, 1, 0)))
    assert s.u.night_since is None


def test_first_to_bed_while_other_downstairs_is_not_night():
    s = NightSite()
    _night_house(s)
    s.feed(KITCHEN, s.t(EVE, 18))
    s.feed(BACK, s.t(EVE, 20, 28))
    s.feed(BED, s.t(EVE, 20, 30))  # the first goes up
    seen = []
    now = s.t(EVE, 20, 30)
    while now <= s.t(EVE, 22, 0):
        if now.minute % 10 == 0 and now > s.t(EVE, 20, 30):
            s.feed(BACK, now)  # the other is still in the back room
        if now.minute == 3:
            s.feed(BED, now)  # the first turns over
        seen.append(s.ev(now))
        assert s.u.night_since is None
        now += timedelta(minutes=1)
    s.feed(BED, s.t(EVE, 22, 1))  # the other goes up
    seen += polls(s, s.t(EVE, 22, 1), s.t(EVE, 22, 30))
    assert s.u.night_since is None
    s.ev(s.t(EVE, 22, 31))
    assert s.u.night_since == s.t(EVE, 22, 1)
    assert all(p == [] for p in seen)


def test_long_night_trip_pushes_once_at_30_min_and_clears_back_upstairs():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    opened = 0
    was_open = False
    raised = set()
    s.feed(BED, s.t(EVE, 1, 59))  # coming down
    for m in range(0, 46):
        now = s.t(EVE, 2, 0) + timedelta(minutes=m)
        if m <= 40 and m % 5 == 0:
            s.feed(KITCHEN, now)
        if m == 41:
            s.feed(BED, now)
        alerts = s.ev(now)
        if m < 30:
            assert alerts == []
        if m == 30:
            [a] = alerts
            assert a.kind == "night_downstairs" and a.source == "night"
            assert a.cls is AlertClass.WELFARE and a.severity is Severity.MEDIUM
            assert a.explanation == (
                "Someone has been downstairs for 30 min during the night "
                "(since 02:00, in the Kitchen)"
            )
            assert a.details == {"room": "Kitchen", "since": "02:00"}
        if 30 <= m < 45:
            assert [a.kind for a in alerts] == ["night_downstairs"]
        if m == 45:
            assert alerts == []  # back upstairs and 5 min quiet downstairs
        is_open = bool(alerts)
        opened += is_open and not was_open
        was_open = is_open
        raised |= {a.raised_at for a in alerts}
    assert opened == 1
    assert raised == {s.t(EVE, 2, 30)}


def test_short_trip_sends_nothing():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.trip(EVE, 2, 0, 10)
    assert all(p == [] for p in polls(s, s.t(EVE, 2, 0), s.t(EVE, 3, 0)))
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["trip"] == 10.0


def test_night_door_while_home_pushes_and_while_out_does_not():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 2, 11))
    s.feed(KITCHEN, s.t(EVE, 2, 12))
    s.feed(FRONT, s.t(EVE, 2, 14))
    # Held for 15 minutes in case someone is coming back to bed.
    assert all(p == [] for p in polls(s, s.t(EVE, 2, 14), s.t(EVE, 2, 28)))
    [a] = s.ev(s.t(EVE, 2, 29))
    assert a.kind == "night_door" and a.source == "night"
    assert a.cls is AlertClass.WELFARE and a.severity is Severity.MEDIUM
    assert a.explanation == "Front door opened during the night at 02:14"
    assert a.raised_at == s.t(EVE, 2, 29)
    s.feed(BED, s.t(EVE, 2, 35))
    assert s.ev(s.t(EVE, 2, 36)) == []

    # The other occupant goes out after the first is in bed and comes home
    # late: the house was OUT when the door opened.
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.feed(FRONT, s.t(EVE, 22, 0))
    s.ev(s.t(EVE, 22, 40))
    assert s.u.night_since == s.t(EVE, 21, 57)
    assert s.w.is_out(s.t(EVE, 1, 30))
    s.feed(FRONT, s.t(EVE, 1, 30))
    assert s.ev(s.t(EVE, 1, 31)) == []
    s.feed(BED, s.t(EVE, 1, 32))
    assert all(p == [] for p in polls(s, s.t(EVE, 1, 32), s.t(EVE, 2, 30)))


def test_regular_2330_back_door_is_learned_normal():
    s = NightSite()
    _night_house(s, doors={i: (23, 30) for i in range(0, 20, 3)})  # 7 of 20
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(KDOOR, s.t(EVE, 23, 30))
    assert s.ev(s.t(EVE, 23, 46)) == []
    # A door well away from the learned hour still pushes.
    s.feed(BED, s.t(EVE, 23, 50))
    s.feed(KDOOR, s.t(EVE, 2, 14))
    assert s.ev(s.t(EVE, 2, 28)) == []
    assert [a.kind for a in s.ev(s.t(EVE, 2, 29))] == ["night_door"]


def test_regular_long_trip_is_learned_normal():
    s = NightSite()
    _night_house(s, trips={i: 40 for i in range(0, 20, 5)})  # 4 of 20
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.trip(EVE, 2, 0, 40)
    assert all(p == [] for p in polls(s, s.t(EVE, 2, 0), s.t(EVE, 3, 0)))

    # 2 of 20 is not more than 10%: still unusual.
    s = NightSite()
    _night_house(s, trips={0: 40, 10: 40})
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 1, 59))
    for m in (0, 10, 20, 30):
        s.feed(KITCHEN, s.t(EVE, 2, m))
    assert [a.kind for a in s.ev(s.t(EVE, 2, 30))] == ["night_downstairs"]


def test_no_push_before_14_nights():
    for n, pushed in ((13, False), (14, True)):
        s = NightSite()
        _night_house(s, n=n)
        s.evening(EVE)
        s.ev(s.t(EVE, 22, 40))
        assert s.u.night_since is not None
        s.feed(BED, s.t(EVE, 1, 59))
        s.feed(KITCHEN, s.t(EVE, 2, 0))
        s.feed(FRONT, s.t(EVE, 2, 1))
        s.feed(KITCHEN, s.t(EVE, 2, 15))
        s.feed(KITCHEN, s.t(EVE, 2, 30))
        kinds_ = {a.kind for a in s.ev(s.t(EVE, 2, 30))}
        assert kinds_ == (set(NIGHT_KINDS) if pushed else set())


def test_bungalow_bedrooms_only():
    s = NightSite(upstairs=frozenset())
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    assert s.u.night_since == s.t(EVE, 21, 57)
    s.trip(EVE, 2, 0, 3, room=BATH)
    assert all(p == [] for p in polls(s, s.t(EVE, 2, 0), s.t(EVE, 3, 0)))
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["trip"] == 3.0  # the bathroom is a day room

    # With the bathroom ticked as upstairs, the same visit is no trip.
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.trip(EVE, 2, 0, 3, room=BATH)
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["trip"] == 0.0


def test_morning_ends_night_at_learned_night_end():
    s = NightSite()
    _night_house(s)
    nxt = EVE + timedelta(days=1)
    assert s.w.night_end(nxt) == 6 * 60  # earliest waking 07:00 less 60 min
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 5, 28))
    s.feed(KITCHEN, s.t(EVE, 5, 30))
    s.feed(KITCHEN, s.t(EVE, 5, 45))
    assert s.u.night_since == s.t(EVE, 21, 57)  # before night_end: a trip
    assert iso_day(EVE) not in s.nights()
    s.feed(KITCHEN, s.t(EVE, 6, 0))
    assert s.u.night_since is None
    assert s.nights()[iso_day(EVE)] == {"trip": 15.0, "doors": []}


def test_restart_mid_night_keeps_trip():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 1, 48))
    s.feed(KITCHEN, s.t(EVE, 1, 50))
    s.feed(KITCHEN, s.t(EVE, 2, 0))
    data = s.u.to_dict()
    s.u = Unusual.from_dict(data, s.cfg)
    assert s.u.to_dict() == data
    assert s.u.night_since == s.t(EVE, 21, 57)
    s.feed(KITCHEN, s.t(EVE, 2, 10))
    assert s.ev(s.t(EVE, 2, 19)) == []
    s.feed(KITCHEN, s.t(EVE, 2, 20))
    [a] = s.ev(s.t(EVE, 2, 20))
    assert a.kind == "night_downstairs"
    assert a.details["since"] == "01:50"
    assert a.raised_at == s.t(EVE, 2, 20)
    [b] = s.ev(s.t(EVE, 2, 25))
    assert b.raised_at == a.raised_at
    assert s.u.night_since == s.t(EVE, 21, 57)


def test_bedtime_after_midnight():
    s = NightSite(night_start_min=23 * 60)
    s.feed(KITCHEN, s.t(EVE, 22, 0))
    s.feed(BACK, s.t(EVE, 0, 28))
    s.feed(BED, s.t(EVE, 0, 30))
    s.ev(s.t(EVE, 0, 59))
    assert s.u.night_since is None
    s.ev(s.t(EVE, 1, 0))
    assert s.u.night_since == s.t(EVE, 0, 30)
    s.morning(EVE)
    assert s.u.night_since is None
    assert list(s.nights()) == [iso_day(EVE)]  # the previous evening's date

    # Going up before the learned night start is not night.
    s = NightSite(night_start_min=23 * 60)
    s.feed(KITCHEN, s.t(EVE, 22, 28))
    s.feed(BED, s.t(EVE, 22, 30))
    s.ev(s.t(EVE, 23, 30))
    assert s.u.night_since is None


def test_poll_gap_during_trip_fires_once():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 2, 8))
    for m in range(10, 55, 5):
        s.feed(KITCHEN, s.t(EVE, 2, m))  # 02:10 .. 02:50, no polls
    [a] = s.ev(s.t(EVE, 2, 55))
    assert a.kind == "night_downstairs"
    assert a.explanation.startswith("Someone has been downstairs for 40 min")
    assert a.raised_at == s.t(EVE, 2, 40)
    [b] = s.ev(s.t(EVE, 2, 56))
    assert b.raised_at == a.raised_at


def test_clock_change_night():
    lon = ZoneInfo("Europe/London")
    eve = date(2026, 10, 24)  # clocks go back at 02:00 BST on 25 Oct
    s = NightSite(tz=lon)
    _night_house(s, before=eve)
    s.evening(eve)
    s.ev(s.t(eve, 22, 40))
    since = s.t(eve, 21, 57)
    assert s.u.night_since == since
    # 01:30 happens twice; neither ends nor restarts the night.
    s.feed(BED, s.t(eve, 1, 30, fold=0))
    assert s.u.night_since == since
    assert iso_day(eve) not in s.nights()
    # A trip from 01:40 BST to 01:05 GMT is 25 minutes, not -35.
    s.feed(BED, s.t(eve, 1, 38, fold=0))  # coming down
    s.feed(KITCHEN, s.t(eve, 1, 40, fold=0))
    s.feed(KITCHEN, s.t(eve, 1, 50, fold=0))
    s.feed(KITCHEN, s.t(eve, 1, 5, fold=1))
    assert s.ev(s.t(eve, 1, 9, fold=1)) == []
    s.feed(KITCHEN, s.t(eve, 1, 10, fold=1))
    [a] = s.ev(s.t(eve, 1, 10, fold=1))
    assert a.kind == "night_downstairs"
    assert a.explanation == (
        "Someone has been downstairs for 30 min during the night "
        "(since 01:40, in the Kitchen)"
    )
    utc = timezone.utc
    assert a.raised_at.astimezone(utc) == datetime(2026, 10, 25, 1, 10, tzinfo=utc)
    s.feed(BED, s.t(eve, 1, 12, fold=1))
    assert s.ev(s.t(eve, 1, 20, fold=1)) == []
    s.feed(BED, s.t(eve, 1, 30, fold=1))  # the second 01:30
    assert s.u.night_since == since
    s.morning(eve)
    assert s.u.night_since is None
    assert s.nights()[iso_day(eve)]["trip"] == 30.0

    # Back upstairs at 01:01 GMT is 3 min after 01:58 BST: the trip ends.
    s = NightSite(tz=lon)
    _night_house(s, before=eve)
    s.evening(eve)
    s.ev(s.t(eve, 22, 40))
    s.feed(BED, s.t(eve, 1, 43, fold=0))
    s.feed(KITCHEN, s.t(eve, 1, 45, fold=0))
    s.feed(KITCHEN, s.t(eve, 1, 58, fold=0))
    s.feed(BED, s.t(eve, 1, 1, fold=1))
    s.ev(s.t(eve, 1, 4, fold=1))
    assert s.u.to_dict()["night"]["trip_start"] is None
    assert s.u.to_dict()["night"]["trip_max"] == 13.0


def test_night_state_round_trip_old_store_and_clear():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(KDOOR, s.t(EVE, 2, 0))
    data = s.u.to_dict()
    assert Unusual.from_dict(data, s.cfg).to_dict() == data

    # A store from before the night parts keeps its card learning.
    old = {k: v for k, v in data.items() if k != "night"}
    back = Unusual.from_dict(old, s.cfg)
    assert back.to_dict()["first"] == data["first"]
    assert back.night_since is None and back.to_dict()["night"]["nights"] == {}

    fresh = Unusual(s.cfg).to_dict()
    for bad in (5, {"nights": {}}, dict(data["night"], night_since=3)):
        assert Unusual.from_dict(dict(data, night=bad), s.cfg).to_dict() == fresh

    # clear_night drops the night in progress and keeps the learned nights.
    assert s.ev(s.t(EVE, 2, 15))
    s.u.clear_night()
    assert s.u.night_since is None
    assert s.ev(s.t(EVE, 2, 16)) == []
    assert len(s.nights()) == 20


def test_outside_doors_property():
    w = Whereabouts(WhereaboutsConfig(outside_doors=frozenset({FRONT})))
    assert w.outside_doors == frozenset({FRONT})


def test_held_on_sensor_trip_measured_from_burst_end():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 1, 59))
    s.feed(KITCHEN, s.t(EVE, 2, 0))  # one presence, then held on
    assert all(p == [] for p in polls(s, s.t(EVE, 2, 0), s.t(EVE, 2, 44)))
    s.feed(KITCHEN, s.t(EVE, 2, 45), EventKind.BURST_END, s.t(EVE, 2, 40))
    [a] = s.ev(s.t(EVE, 2, 45))
    assert a.kind == "night_downstairs"
    assert a.explanation.startswith("Someone has been downstairs for 45 min")
    assert a.raised_at == s.t(EVE, 2, 30)
    s.feed(BED, s.t(EVE, 2, 47))
    assert s.ev(s.t(EVE, 2, 50)) == []
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["trip"] == 45.0

    # The burst end counts no later than its last rise plus 10 minutes.
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 1, 59))
    s.feed(KITCHEN, s.t(EVE, 2, 0))
    s.feed(KITCHEN, s.t(EVE, 3, 0), EventKind.BURST_END, s.t(EVE, 2, 15))
    assert s.ev(s.t(EVE, 3, 0)) == []
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["trip"] == 25.0


def test_burst_end_counts_for_going_up():
    s = NightSite()
    _night_house(s)
    s.feed(KITCHEN, s.t(EVE, 21, 40))
    s.feed(KITCHEN, s.t(EVE, 21, 56), EventKind.BURST_END, s.t(EVE, 21, 50))
    s.feed(BED, s.t(EVE, 21, 57))
    s.ev(s.t(EVE, 22, 27))
    assert s.u.night_since == s.t(EVE, 21, 57)


def test_partner_bedroom_motion_does_not_close_trip():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 1, 59))
    s.feed(KITCHEN, s.t(EVE, 2, 0))
    s.feed(KITCHEN, s.t(EVE, 2, 10))
    s.feed(BED, s.t(EVE, 2, 20))  # 10 min after the kitchen: not going up
    assert s.ev(s.t(EVE, 2, 26)) == []
    assert s.u.to_dict()["night"]["trip_start"] == s.t(EVE, 2, 0).isoformat()
    s.feed(KITCHEN, s.t(EVE, 2, 30))
    [a] = s.ev(s.t(EVE, 2, 30))
    assert a.kind == "night_downstairs"
    assert a.details["since"] == "02:00"
    assert a.raised_at == s.t(EVE, 2, 30)


def test_lone_blip_then_nothing_never_pushes():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 1, 59))
    s.feed(KITCHEN, s.t(EVE, 2, 0))
    assert all(p == [] for p in polls(s, s.t(EVE, 2, 0), s.t(EVE, 6, 59)))
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["trip"] == 0.0


def test_night_ends_after_20_hours_without_morning():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    nxt = EVE + timedelta(days=1)
    s.ev(s.t(nxt, 17, 56))
    assert s.u.night_since == s.t(EVE, 21, 57)
    s.ev(s.t(nxt, 17, 57))
    assert s.u.night_since is None
    assert iso_day(EVE) in s.nights()


def test_night_door_clears_at_morning_and_morning_door_is_not_night():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(FRONT, s.t(EVE, 5, 0))
    assert [a.kind for a in s.ev(s.t(EVE, 5, 15))] == ["night_door"]
    s.feed(KITCHEN, s.t(EVE, 6, 0))  # morning
    assert s.ev(s.t(EVE, 6, 1)) == []
    assert s.u.night_since is None

    # A door after night_end with no downstairs activity first is morning.
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(FRONT, s.t(EVE, 6, 10))
    assert s.ev(s.t(EVE, 6, 11)) == []
    assert s.u.night_since is None
    assert s.nights()[iso_day(EVE)]["doors"] == []


def test_two_blips_far_apart_are_two_trips():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 1, 59))
    s.feed(KITCHEN, s.t(EVE, 2, 0))
    s.feed(BED, s.t(EVE, 2, 39))
    s.feed(KITCHEN, s.t(EVE, 2, 40))  # 40 min of quiet downstairs: a new trip
    assert s.u.to_dict()["night"]["trip_start"] == s.t(EVE, 2, 40).isoformat()
    assert all(p == [] for p in polls(s, s.t(EVE, 2, 0), s.t(EVE, 4, 0)))
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["trip"] == 0.0


# ------------------------------------------------- coming down, door holds


def test_still_reader_after_partner_goes_up_cancels_the_night():
    s = NightSite()
    _night_house(s)
    s.feed(KITCHEN, s.t(EVE, 18))
    s.feed(BACK, s.t(EVE, 21, 58))
    s.feed(BED, s.t(EVE, 22, 0))  # A goes up; B reads on, TV off, 35 min
    seen = polls(s, s.t(EVE, 22, 0), s.t(EVE, 22, 34))
    assert s.u.night_since == s.t(EVE, 22, 0)
    now = s.t(EVE, 22, 35)
    for k in range(0, 70, 8):  # B moves now and then for an hour
        s.feed(BACK, now + timedelta(minutes=k))
        assert s.u.night_since is None  # no coming down: cancelled
        seen += polls(s, now + timedelta(minutes=k), now + timedelta(minutes=k + 7))
    assert s.u.night_since is None
    up = now + timedelta(minutes=66)
    s.feed(LANDING, up)  # B goes up
    seen += polls(s, up, up + timedelta(minutes=29))
    assert s.u.night_since is None
    seen += polls(s, up + timedelta(minutes=30), up + timedelta(minutes=90))
    assert s.u.night_since == up
    assert all(p == [] for p in seen)
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)] == {"trip": 0.0, "doors": []}


def test_real_night_trip_after_coming_down_still_pushes():
    for upstairs in (UPSTAIRS, frozenset()):  # two floors, and a bungalow
        s = NightSite(upstairs=upstairs)
        _night_house(s)
        s.evening(EVE)
        s.ev(s.t(EVE, 22, 40))
        s.feed(BED, s.t(EVE, 2, 0))
        for m in range(1, 41, 5):
            s.feed(KITCHEN, s.t(EVE, 2, m))
        assert s.u.night_since == s.t(EVE, 21, 57)
        [a] = s.ev(s.t(EVE, 2, 40))
        assert a.kind == "night_downstairs" and a.details["since"] == "02:01"
        assert a.raised_at == s.t(EVE, 2, 31)


def test_late_return_with_a_cup_of_tea_is_not_a_night_door():
    s = NightSite()
    _night_house(s)
    s.feed(KITCHEN, s.t(EVE, 18))
    s.feed(FRONT, s.t(EVE, 19))  # B goes out
    s.feed(BACK, s.t(EVE, 21, 58))
    s.feed(BED, s.t(EVE, 22, 0))  # A goes to bed
    seen = polls(s, s.t(EVE, 22, 0), s.t(EVE, 23, 44))
    assert s.u.night_since == s.t(EVE, 22, 0)
    s.feed(FRONT, s.t(EVE, 23, 45))  # B comes home
    seen += polls(s, s.t(EVE, 23, 45), s.t(EVE, 23, 46))
    s.feed(KITCHEN, s.t(EVE, 23, 47))
    seen += polls(s, s.t(EVE, 23, 47), s.t(EVE, 23, 51))
    s.feed(LANDING, s.t(EVE, 23, 52))
    s.feed(BED, s.t(EVE, 23, 53))
    seen += polls(s, s.t(EVE, 23, 52), s.t(EVE, 1, 0))
    assert all(p == [] for p in seen)
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["doors"] == []


def test_door_then_back_to_bed_inside_the_hold_is_dropped_unlearned():
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 1, 0))
    s.feed(KITCHEN, s.t(EVE, 1, 2))
    s.feed(KDOOR, s.t(EVE, 1, 3))  # the cat out
    seen = polls(s, s.t(EVE, 1, 3), s.t(EVE, 1, 8))
    data = s.u.to_dict()  # a restart inside the hold keeps it
    assert data["night"]["door_held"] is True
    s.u = Unusual.from_dict(data, s.cfg)
    s.feed(KITCHEN, s.t(EVE, 1, 9))
    s.feed(LANDING, s.t(EVE, 1, 12))
    seen += polls(s, s.t(EVE, 1, 9), s.t(EVE, 2, 0))
    assert all(p == [] for p in seen)
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["doors"] == []

    # Going up only after the hold: the door opened at 01:18.
    s = NightSite()
    _night_house(s)
    s.evening(EVE)
    s.ev(s.t(EVE, 22, 40))
    s.feed(BED, s.t(EVE, 1, 0))
    s.feed(KITCHEN, s.t(EVE, 1, 2))
    s.feed(KDOOR, s.t(EVE, 1, 3))
    s.feed(KITCHEN, s.t(EVE, 1, 15))
    assert s.ev(s.t(EVE, 1, 17)) == []
    [a] = s.ev(s.t(EVE, 1, 18))
    assert a.kind == "night_door" and a.raised_at == s.t(EVE, 1, 18)
    assert a.explanation == "Kitchen door opened during the night at 01:03"
    s.feed(LANDING, s.t(EVE, 1, 19))
    assert s.ev(s.t(EVE, 1, 20)) == []
    s.morning(EVE)
    assert s.nights()[iso_day(EVE)]["doors"] == [1]
