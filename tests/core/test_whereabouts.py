from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.events import (
    ActivityEvent,
    Category,
    EventKind,
)
from custom_components.behaviour_monitor.core.whereabouts import (
    Whereabouts,
    WhereaboutsConfig,
    Where,
)
from custom_components.behaviour_monitor.core.alerts import AlertClass, Severity

DOOR = "binary_sensor.front_door"
TV = "sensor.tv"
DOORS = frozenset({DOOR})
TVS = frozenset({TV})
CFG = WhereaboutsConfig(outside_doors=DOORS, sitting_appliances=TVS)


def T(h: int, m: int = 0) -> datetime:
    return datetime(2026, 11, 9, h, m, tzinfo=timezone.utc)


def _presence(ts: datetime, room: str) -> ActivityEvent:
    return ActivityEvent(
        "binary_sensor.m", Category.MOTION, EventKind.PRESENCE, room, ts
    )


def _tv(ts: datetime, room: str, on: bool = True) -> ActivityEvent:
    kind = EventKind.APPLIANCE_ON if on else EventKind.APPLIANCE_OFF
    return ActivityEvent(TV, Category.PLUG, kind, room, ts)


def _door(ts: datetime, room: str = "Hall", entity: str = DOOR) -> ActivityEvent:
    return ActivityEvent(entity, Category.CONTACT, EventKind.OPEN, room, ts)


def test_presence_starts_home_interval_in_that_room():
    w = Whereabouts(CFG)
    w.record(_presence(T(10, 0), "Kitchen"))
    iv = w.current(T(10, 30))
    assert (iv.where, iv.room, iv.start) == (Where.HOME, "Kitchen", T(10, 0))


def test_no_interval_before_any_activity():
    assert Whereabouts(CFG).current(T(10, 0)) is None


def test_lights_and_generic_and_close_do_not_start_intervals():
    w = Whereabouts(CFG)
    w.record(_presence(T(10, 0), "Kitchen"))
    for kind, cat in (
        (EventKind.LIGHT_ON, Category.LIGHT),
        (EventKind.GENERIC, Category.OTHER),
        (EventKind.CLOSE, Category.CONTACT),
        (EventKind.APPLIANCE_OFF, Category.PLUG),
    ):
        w.record(ActivityEvent("x.y", cat, kind, "Lounge", T(10, 5)))
    iv = w.current(T(10, 30))
    assert (iv.start, iv.room) == (T(10, 0), "Kitchen")


def test_tv_on_in_last_room_gives_home_tv_and_turning_off_does_not_reset():
    w = Whereabouts(CFG)
    w.record(_presence(T(19, 0), "Backroom"))
    w.record(_tv(T(19, 1), "Backroom"))
    iv = w.current(T(19, 10))
    assert (iv.where, iv.start, iv.tv) == (Where.HOME_TV, T(19, 1), True)
    w.record(_tv(T(19, 30), "Backroom", on=False))
    iv = w.current(T(19, 40))
    assert (iv.where, iv.start) == (Where.HOME_TV, T(19, 1))


def test_tv_off_then_later_presence_is_plain_home():
    w = Whereabouts(CFG)
    w.record(_tv(T(19, 0), "Backroom"))
    w.record(_tv(T(19, 30), "Backroom", on=False))
    w.record(_presence(T(19, 40), "Backroom"))
    assert w.current(T(19, 50)).where is Where.HOME


def test_tv_in_another_room_is_plain_home():
    w = Whereabouts(CFG)
    w.record(_tv(T(19, 0), "Backroom"))
    w.record(_presence(T(19, 5), "Kitchen"))
    iv = w.current(T(19, 10))
    assert (iv.where, iv.tv) == (Where.HOME, False)


def test_outside_door_then_quiet_is_out_after_ten_minutes():
    w = Whereabouts(CFG)
    w.record(_door(T(10, 0)))
    assert w.current(T(10, 9)).where is Where.HOME
    iv = w.current(T(10, 10))
    assert iv.where is Where.OUT
    assert iv.door == DOOR


def test_door_open_does_not_change_last_room():
    w = Whereabouts(CFG)
    w.record(_presence(T(9, 50), "Kitchen"))
    w.record(_door(T(10, 0), room="Hall"))
    assert w.current(T(10, 20)).room == "Kitchen"


def test_presence_in_door_room_within_two_minutes_is_ignored():
    w = Whereabouts(CFG)
    w.record(_door(T(10, 0), room="Hall"))
    w.record(_presence(T(10, 1), "Hall"))
    iv = w.current(T(10, 15))
    assert (iv.where, iv.start) == (Where.OUT, T(10, 0))


def test_presence_in_door_room_after_two_minutes_brings_her_home():
    w = Whereabouts(CFG)
    w.record(_door(T(10, 0), room="Hall"))
    w.record(_presence(T(10, 3), "Hall"))
    iv = w.current(T(10, 15))
    assert (iv.where, iv.start) == (Where.HOME, T(10, 3))


def test_presence_elsewhere_within_ten_minutes_is_home():
    w = Whereabouts(CFG)
    w.record(_door(T(10, 0), room="Hall"))
    w.record(_presence(T(10, 1), "Kitchen"))
    iv = w.current(T(10, 15))
    assert (iv.where, iv.start, iv.room) == (Where.HOME, T(10, 1), "Kitchen")


def test_non_outside_contact_is_plain_activity():
    w = Whereabouts(CFG)
    w.record(_door(T(10, 0), entity="binary_sensor.wardrobe"))
    iv = w.current(T(10, 30))
    assert (iv.where, iv.door, iv.start) == (Where.HOME, None, T(10, 0))


def test_bedroom_at_night_is_asleep_and_morning_is_lying_in_and_afternoon_is_home():
    w = Whereabouts(CFG)
    w.record(_presence(T(22, 30), "Back Bedroom"))
    assert w.current(T(23, 0)).where is Where.ASLEEP
    w = Whereabouts(CFG)
    w.record(_presence(T(6, 30), "Back Bedroom"))
    assert w.current(T(7, 0)).where is Where.LYING_IN
    w = Whereabouts(CFG)
    w.record(_presence(T(11, 30), "Back Bedroom"))
    assert w.current(T(12, 0)).where is Where.HOME


def test_night_boundaries_are_start_inclusive_end_exclusive():
    for ts, expected in (
        (T(20, 0), Where.ASLEEP),
        (T(19, 59), Where.HOME),
        (T(5, 0), Where.LYING_IN),
        (T(4, 59), Where.ASLEEP),
        (T(11, 0), Where.HOME),
        (T(10, 59), Where.LYING_IN),
    ):
        w = Whereabouts(CFG)
        w.record(_presence(ts, "Front Bedroom"))
        assert w.current(ts).where is expected, ts


def test_asleep_wins_over_bedroom_tv():
    w = Whereabouts(CFG)
    w.record(_tv(T(21, 0), "Front Bedroom"))
    w.record(_presence(T(21, 0), "Front Bedroom"))
    assert w.current(T(21, 30)).where is Where.ASLEEP


def test_bedrooms_none_matches_names_and_explicit_set_overrides():
    default = Whereabouts(CFG)
    assert default.is_bedroom("Front Bedroom")
    assert not default.is_bedroom("Lounge")
    assert not default.is_bedroom(None)
    explicit = Whereabouts(WhereaboutsConfig(bedrooms=frozenset({"Box room"})))
    assert not explicit.is_bedroom("Front Bedroom")
    assert explicit.is_bedroom("Box room")


def test_no_bedrooms_chosen_applies_night_rules_to_every_room():
    w = Whereabouts(WhereaboutsConfig(bedrooms=frozenset()))
    w.record(_presence(T(23, 0), "Lounge"))
    assert w.current(T(23, 30)).where is Where.ASLEEP


def test_events_older_than_current_interval_are_ignored():
    w = Whereabouts(CFG)
    w.record(_presence(T(10, 0), "Kitchen"))
    w.record(_presence(T(9, 0), "Lounge"))
    iv = w.current(T(10, 30))
    assert (iv.start, iv.room) == (T(10, 0), "Kitchen")


# ------------------------------------------------------------------ learning


def D(day: int, h: int, m: int = 0) -> datetime:
    return datetime(2026, 11, day, h, m, tzinfo=timezone.utc)


def _learn_nights(w: Whereabouts) -> None:
    """Sleeps start 21:30, 22:00, 22:15; she is up at 06:30, 07:00, 08:00."""
    starts = [(21, 30), (22, 0), (22, 15)]
    wakes = [(6, 30), (7, 0), (8, 0)]
    for i, ((sh, sm), (wh, wm)) in enumerate(zip(starts, wakes)):
        w.record(_presence(D(1 + i, sh, sm), "Bedroom"))
        w.record(_presence(D(2 + i, wh, wm), "Kitchen"))


def test_home_limit_learns_995th_percentile_clamped_to_45_60():
    w = Whereabouts(CFG)
    for day in (1, 2, 3):
        w.record(_presence(D(day, 10, 0), "Kitchen"))
        w.record(_presence(D(day, 10, 20), "Lounge"))  # 20 min
        w.record(_presence(D(day, 10, 30), "Kitchen"))  # 10 min
        w.record(_presence(D(day, 11, 20), "Lounge"))  # 50 min at 10:30
        w.record(_presence(D(day, 11, 30), "Kitchen"))
    assert w.home_limit_min(10) == 50

    long = Whereabouts(CFG)
    for day in (1, 2, 3):
        long.record(_presence(D(day, 10, 0), "Kitchen"))
        long.record(_presence(D(day, 11, 10), "Lounge"))  # 70 min
    assert long.home_limit_min(10) == 60

    low = Whereabouts(CFG)
    for day in (1, 2, 3):
        low.record(_presence(D(day, 10, 0), "Kitchen"))
        low.record(_presence(D(day, 10, 20), "Lounge"))
        low.record(_presence(D(day, 10, 40), "Kitchen"))
        low.record(_presence(D(day, 11, 0), "Lounge"))
    assert low.home_limit_min(10) == 45

    one = Whereabouts(CFG)
    one.record(_presence(D(1, 10, 0), "Kitchen"))
    one.record(_presence(D(1, 10, 20), "Lounge"))
    assert one.home_limit_min(10) == 60


def test_tv_and_asleep_intervals_do_not_feed_home_limits():
    w = Whereabouts(CFG)
    for day in (1, 2, 3):
        w.record(_tv(D(day, 19, 0), "Lounge"))
        w.record(_presence(D(day, 19, 1), "Lounge"))
        w.record(_presence(D(day, 19, 56), "Kitchen"))
    assert w.home_limit_min(19) == 60


def test_usual_waking_is_95th_percentile_of_first_non_bedroom_activity_after_4am():
    w = Whereabouts(CFG)
    for day, (h, m) in zip((1, 2, 3), ((7, 0), (7, 30), (8, 40))):
        w.record(_presence(D(day, 3, 0), "Kitchen"))  # before 04:00, ignored
        w.record(_presence(D(day, 5, 0), "Bedroom"))
        w.record(_presence(D(day, h, m), "Kitchen"))
        w.record(_presence(D(day, h + 1, m), "Lounge"))
    assert w.usual_waking_min() == 8 * 60 + 40
    assert w.earliest_waking_min() == 7 * 60


def test_waking_uses_end_of_main_sleep_when_no_bedrooms_chosen():
    cfg = WhereaboutsConfig(bedrooms=frozenset())
    w = Whereabouts(cfg)
    for i in range(3):
        w.record(_presence(D(1 + i, 22, 0), "Room"))
        w.record(_presence(D(2 + i, 7, 0), "Room"))
    assert w.usual_waking_min() == 7 * 60


def test_learned_night_bounds_and_their_clamps():
    w = Whereabouts(CFG)
    _learn_nights(w)
    assert w.night_start() == 20 * 60 + 30
    assert w.night_end() == 5 * 60 + 30
    assert w.lie_in_end() == 10 * 60


def test_night_onset_is_earliest_long_bedroom_interval_not_the_longest():
    """A bathroom trip splits the night; bedtime is still the onset."""
    w = Whereabouts(CFG)
    for day in (1, 2, 3):
        w.record(_presence(D(day, 22, 10), "Bedroom"))
        w.record(_presence(D(day + 1, 0, 30), "Bathroom"))
        w.record(_presence(D(day + 1, 0, 36), "Bedroom"))
        w.record(_presence(D(day + 1, 7, 0), "Kitchen"))
    assert w.night_start() == 1270  # 22:10 less an hour


def test_a_long_return_to_bed_cancels_the_waking_candidate():
    w = Whereabouts(CFG)
    for day in (1, 2, 3):
        w.record(_presence(D(day, 5, 0), "Bathroom"))
        w.record(_presence(D(day, 5, 6), "Bedroom"))
        w.record(_presence(D(day, 7, 0), "Kitchen"))
    assert w.usual_waking_min() == 7 * 60
    assert w.night_end() == 360


def test_todays_waking_counts_only_once_the_day_is_over():
    w = Whereabouts(CFG)
    for day in (1, 2, 3, 4):
        w.record(_presence(D(day, 7, 0), "Kitchen"))
    w.record(_presence(D(5, 5, 0), "Bathroom"))  # may yet go back to bed
    assert w.earliest_waking_min(date(2026, 11, 5)) == 7 * 60
    assert w.earliest_waking_min(date(2026, 11, 6)) == 5 * 60


def test_overnight_evaluation_uses_yesterdays_finished_waking():
    """Before she moves in the morning, yesterday is over and its waking counts."""
    w = Whereabouts(CFG)
    for day in (1, 2, 3):
        w.record(_presence(D(day, 7, 0), "Kitchen"))
        w.record(_presence(D(day, 22, 0), "Bedroom"))
    a = w.evaluate(D(4, 6, 0))
    assert a.where is Where.ASLEEP
    assert a.deadline == D(4, 8, 0)  # usual waking 07:00, not the 09:00 fallback


def test_late_waking_clamps_night_end_and_lie_in_end():
    w = Whereabouts(CFG)
    for day, (h, m) in zip((1, 2, 3), ((10, 30), (11, 0), (11, 30))):
        w.record(_presence(D(day, h, m), "Kitchen"))
    assert w.night_end() == 9 * 60
    assert w.lie_in_end() == 13 * 60


def test_night_start_after_midnight_sorts_after_evening():
    w = Whereabouts(CFG)
    for i, (h, m) in enumerate(((23, 50), (0, 20), (1, 30))):
        day = 1 + i
        w.record(_presence(D(day + (1 if h < 12 else 0), h, m), "Bedroom"))
        w.record(_presence(D(day + 1, 8, 0), "Kitchen"))
    # earliest start 23:50 -> 22:50
    assert w.night_start() == 22 * 60 + 50


def test_naps_outside_the_sleep_window_are_not_main_sleeps():
    w = Whereabouts(CFG)
    for day in (1, 2, 3):
        w.record(_presence(D(day, 16, 0), "Bedroom"))  # 4 h nap
        w.record(_presence(D(day, 20, 0), "Kitchen"))
        w.record(_presence(D(day, 22, 0), "Bedroom"))  # 1 h
        w.record(_presence(D(day, 23, 0), "Kitchen"))
    assert w.night_start() == 21 * 60


def test_fallback_night_before_three_days():
    w = Whereabouts(CFG)
    assert (w.night_start(), w.night_end(), w.lie_in_end()) == (1200, 300, 660)
    assert (w.usual_waking_min(), w.earliest_waking_min()) == (540, 360)
    assert w.longest_out_min() is None
    for i in range(2):
        w.record(_presence(D(1 + i, 22, 0), "Bedroom"))
        w.record(_presence(D(2 + i, 7, 0), "Kitchen"))
    assert (w.night_start(), w.night_end(), w.lie_in_end()) == (1200, 300, 660)


def test_learned_night_changes_state_of_a_bedroom_interval():
    fresh = Whereabouts(CFG)
    fresh.record(_presence(D(5, 5, 15), "Bedroom"))
    assert fresh.current(D(5, 5, 20)).where is Where.LYING_IN

    w = Whereabouts(CFG)
    _learn_nights(w)
    w.record(_presence(D(5, 5, 15), "Bedroom"))
    assert w.current(D(5, 5, 20)).where is Where.ASLEEP


def _outing(w: Whereabouts, day: int, minutes: int) -> None:
    w.record(_door(D(day, 10, 0)))
    end = D(day, 10, 0) + timedelta(minutes=minutes)
    w.record(_presence(end, "Hall"))


def test_longest_outing_ignores_trips_of_a_day_or_more():
    w = Whereabouts(CFG)
    _outing(w, 1, 90)
    _outing(w, 2, 30 * 60)  # 30 h: a trip away, not counted
    _outing(w, 4, 45)
    _outing(w, 5, 60)
    assert w.longest_out_min() == 90


def test_longest_outing_waits_for_outings_on_three_days():
    w = Whereabouts(CFG)
    _outing(w, 1, 15)
    _outing(w, 2, 30)
    _outing(w, 2, 20)  # same day again does not add a day
    assert w.longest_out_min() is None
    _outing(w, 3, 25)
    assert w.longest_out_min() == 30


def test_short_door_interval_is_not_an_outing_and_counts_as_home():
    w = Whereabouts(CFG)
    w.record(_door(D(1, 10, 0)))
    w.record(_presence(D(1, 10, 5), "Kitchen"))
    assert w.longest_out_min() is None


def test_restart_clock_keeps_state_and_moves_start():
    w = Whereabouts(CFG)
    w.record(_tv(D(1, 19, 0), "Lounge"))
    w.restart_clock(D(1, 20, 0))
    iv = w.current(D(1, 20, 5))
    assert (iv.where, iv.room, iv.tv, iv.start) == (
        Where.HOME_TV,
        "Lounge",
        True,
        D(1, 20, 0),
    )
    Whereabouts(CFG).restart_clock(D(1, 20, 0))  # no interval: harmless


def test_restart_clock_keeps_out_and_the_outing_counts():
    w = Whereabouts(CFG)
    w.record(_door(D(1, 10, 0)))
    w.restart_clock(D(1, 10, 40))  # a long poll gap while she is out
    iv = w.current(D(1, 10, 40))
    assert (iv.where, iv.start) == (Where.OUT, D(1, 10, 40))
    w.record(_presence(D(1, 10, 45), "Hall"))  # back five minutes later
    assert w.to_dict()["outs"] == {"2026-11-01": [5.0]}


def test_poll_gap_restart_keeps_asleep_and_out_anchored():
    w = Whereabouts(CFG)
    w.record(_presence(D(1, 22, 30), "Bedroom"))
    w.restart_clock(D(2, 12, 20), keep_anchored=True)
    assert w.current(D(2, 12, 21)).start == D(1, 22, 30)
    assert w.evaluate(D(2, 12, 21)).alert.kind == "not_up"

    w = Whereabouts(CFG)
    w.record(_door(D(1, 10, 0)))
    w.restart_clock(D(1, 12, 0), keep_anchored=True)
    iv = w.current(D(1, 12, 0))
    assert (iv.where, iv.start) == (Where.OUT, D(1, 10, 0))

    w = Whereabouts(CFG)
    w.record(_tv(D(1, 19, 0), "Lounge"))
    w.restart_clock(D(1, 20, 0), keep_anchored=True)
    assert w.current(D(1, 20, 5)).start == D(1, 20, 0)


def test_door_while_out_is_her_return_and_hall_presence_counts():
    w = Whereabouts(CFG)
    w.record(_door(D(1, 10, 0)))
    w.record(_door(D(1, 12, 0)))
    w.record(_presence(D(1, 12, 0) + timedelta(seconds=40), "Hall"))
    a = w.evaluate(D(1, 13, 1))
    assert a.where is Where.HOME and a.room == "Hall"
    assert a.alert is not None and a.alert.kind == "still_at_home"
    assert w.to_dict()["outs"] == {"2026-11-01": [120.0]}


def test_door_while_out_and_nothing_else_is_home():
    w = Whereabouts(CFG)
    w.record(_presence(D(1, 9, 0), "Kitchen"))
    w.record(_door(D(1, 10, 0)))
    w.record(_door(D(1, 12, 0)))
    a = w.evaluate(D(1, 12, 30))
    assert (a.where, a.room, a.since) == (Where.HOME, "Hall", D(1, 12, 0))
    assert a.alert is None
    a = w.evaluate(D(1, 13, 0))
    assert a.where is Where.HOME
    assert a.alert is not None and a.alert.kind == "still_at_home"


def test_round_trip_and_prune():
    w = Whereabouts(CFG)
    _learn_nights(w)
    for day in (5, 6, 7):
        _outing(w, day, 90)
    w.record(_tv(D(7, 19, 0), "Lounge"))
    clone = Whereabouts.from_dict(w.to_dict(), CFG)
    assert clone.to_dict() == w.to_dict()
    assert clone.current(D(7, 19, 10)) == w.current(D(7, 19, 10))
    assert (clone.night_start(), clone.night_end(), clone.lie_in_end()) == (
        w.night_start(),
        w.night_end(),
        w.lie_in_end(),
    )
    assert clone.longest_out_min() == 90
    clone.record(_tv(D(7, 19, 30), "Lounge", on=False))
    clone.record(_presence(D(7, 19, 40), "Lounge"))
    assert clone.current(D(7, 19, 50)).where is Where.HOME

    w.prune(date(2026, 11, 5))
    assert w.longest_out_min() == 90
    assert w.night_start() == 1200  # earlier days gone: back to the fallback
    w.prune(date(2026, 11, 7))
    assert w.longest_out_min() is None


def test_from_dict_with_bad_data_is_fresh():
    assert (
        Whereabouts.from_dict({"junk": 1}, CFG).to_dict() == Whereabouts(CFG).to_dict()
    )
    assert Whereabouts.from_dict({}, CFG).current(T(10)) is None


def test_still_at_home_opens_medium_at_limit_and_high_at_one_and_a_half():
    w = Whereabouts(CFG)
    w.record(_presence(T(10, 0), "Kitchen"))
    assert w.evaluate(T(10, 59)).alert is None
    a = w.evaluate(T(11, 0))
    assert a.where is Where.HOME and a.deadline == T(11, 0)
    assert a.alert.kind == "still_at_home" and a.alert.severity is Severity.MEDIUM
    assert a.alert.cls is AlertClass.WELFARE and a.alert.source == "whereabouts"
    assert a.alert.explanation == (
        "No movement for 1h 0m; last seen in the Kitchen at 10:00"
    )
    assert w.evaluate(T(11, 29)).alert.severity is Severity.MEDIUM
    assert w.evaluate(T(11, 30)).alert.severity is Severity.HIGH


def test_still_tv_uses_ninety_minutes():
    w = Whereabouts(CFG)
    w.record(_tv(T(20, 0), "Lounge"))
    w.record(_presence(T(20, 1), "Lounge"))
    assert w.evaluate(T(21, 30)).alert is None
    a = w.evaluate(T(21, 31)).alert
    assert a.kind == "still_tv" and a.severity is Severity.MEDIUM
    assert a.explanation == (
        "No movement for 1h 30m with the Lounge TV on; last seen at 20:01"
    )
    assert w.evaluate(T(22, 16)).alert.severity is Severity.HIGH


def test_lying_in_alerts_as_not_up_after_ninety_minutes():
    w = Whereabouts(CFG)
    w.record(_presence(T(7, 0), "Bedroom"))
    assert w.current(T(7, 0)).where is Where.LYING_IN
    assert w.evaluate(T(8, 29)).alert is None
    a = w.evaluate(T(8, 30)).alert
    assert a.kind == "not_up" and a.severity is Severity.MEDIUM
    assert a.explanation == (
        "Not up yet; stirred in the Bedroom at 07:00, no movement for 1h 30m"
    )
    assert w.evaluate(T(9, 15)).alert.severity is Severity.HIGH


def test_asleep_alerts_at_usual_waking_plus_an_hour_next_morning():
    w = Whereabouts(CFG)
    w.record(_presence(T(22, 30), "Bedroom"))
    nxt = lambda h, m=0: T(h, m) + timedelta(days=1)  # noqa: E731
    r = w.evaluate(nxt(9, 59))
    assert r.where is Where.ASLEEP and r.alert is None and r.limit_min is None
    a = w.evaluate(nxt(10, 0)).alert
    assert a.kind == "not_up" and a.severity is Severity.MEDIUM
    assert a.explanation == (
        "Not up yet; usually up by 09:00, last seen in the Bedroom at 22:30"
    )
    assert w.evaluate(nxt(10, 59)).alert.severity is Severity.MEDIUM
    assert w.evaluate(nxt(11, 0)).alert.severity is Severity.HIGH


def test_asleep_started_after_midnight_uses_same_morning():
    w = Whereabouts(CFG)
    w.record(_presence(T(1, 0), "Bedroom"))
    assert w.evaluate(T(9, 59)).alert is None
    assert w.evaluate(T(10, 0)).alert.kind == "not_up"


FRONT = lambda _e: "Front door"  # noqa: E731


def test_out_alerts_not_back_after_longest_outing_times_one_and_a_quarter():
    w = Whereabouts(CFG)
    w.record(_door(T(10, 0)))
    r = w.evaluate(T(10, 30))
    assert r.where is Where.OUT and r.limit_min is None
    assert r.deadline == T(10, 0) + timedelta(minutes=300)
    assert w.evaluate(T(14, 59)).alert is None
    a = w.evaluate(T(15, 0), names=FRONT).alert
    assert a.kind == "not_back" and a.severity is Severity.MEDIUM
    assert "left by the Front door at 10:00" in a.explanation
    assert a.explanation == (
        "Out for 5h 0m, longer than usual (usual limit 4h 0m); "
        "left by the Front door at 10:00"
    )
    assert w.evaluate(T(15, 59), names=FRONT).alert.severity is Severity.MEDIUM
    assert w.evaluate(T(16, 0), names=FRONT).alert.severity is Severity.HIGH


def test_out_names_longest_outing_when_learned():
    w = Whereabouts(CFG)
    _outing(w, 1, 60)
    _outing(w, 2, 120)
    _outing(w, 3, 30)
    base = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
    w.record(_door(base))
    a = w.evaluate(base + timedelta(minutes=150)).alert
    assert a.explanation.startswith("Out for 2h 30m, longer than usual (longest 2h 0m)")


def test_names_callable_is_used_for_the_door():
    w = Whereabouts(CFG)
    w.record(_door(T(10, 0)))
    a = w.evaluate(T(15, 0), names=lambda e: "Back gate").alert
    assert "left by the Back gate at 10:00" in a.explanation


def test_degraded_suppresses_alert():
    w = Whereabouts(CFG)
    w.record(_presence(T(10, 0), "Kitchen"))
    r = w.evaluate(T(12, 0), live_fraction=0.4)
    assert r.alert is None and r.degraded
    assert not w.evaluate(T(12, 0), live_fraction=0.5).degraded


def test_details_carry_room_and_limit():
    w = Whereabouts(CFG)
    w.record(_presence(T(10, 0), "Kitchen"))
    r = w.evaluate(T(11, 5))
    assert r.room == "Kitchen" and r.limit_min == 60 and r.since == T(10, 0)
    assert r.alert.details == {
        "room": "Kitchen",
        "where": "home",
        "since": T(10, 0).isoformat(),
        "limit_min": 60,
        "minutes": 65,
    }


def test_evaluate_without_activity_and_does_not_mutate():
    w = Whereabouts(CFG)
    r = w.evaluate(T(10, 0))
    assert r.where is None and r.alert is None
    w.record(_presence(T(10, 0), "Kitchen"))
    before = w.to_dict()
    w.evaluate(T(12, 0))
    assert w.to_dict() == before
