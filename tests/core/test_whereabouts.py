from datetime import datetime, timezone

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
