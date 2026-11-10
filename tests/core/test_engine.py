from __future__ import annotations


from dataclasses import replace
from datetime import datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import (
    Alert,
    AlertClass,
    Severity,
)
from custom_components.behaviour_monitor.core.engine import (
    Engine,
    EngineConfig,
    EntitySpec,
)
from custom_components.behaviour_monitor.core.events import Category
from custom_components.behaviour_monitor.core.unusual import UnusualConfig

MON = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
ENTS = [
    EntitySpec("binary_sensor.bed", Category.MOTION, "Bedroom"),
    EntitySpec("binary_sensor.bath", Category.MOTION, "Bathroom"),
    EntitySpec("binary_sensor.kit", Category.MOTION, "Kitchen"),
    EntitySpec("sensor.kettle", Category.PLUG, "Kitchen"),
    EntitySpec("binary_sensor.panic", Category.PANIC, "Hall"),
]


def _engine(**opts) -> Engine:
    return Engine(EngineConfig.from_options(opts), ENTS)


def _pulse(e: Engine, eid: str, ts: datetime, learn_only: bool = True) -> list:
    out = e.handle_state(eid, "off", "on", ts, learn_only=learn_only)
    e.handle_state(eid, "on", "off", ts + timedelta(seconds=60), learn_only=learn_only)
    return out


def _day(e: Engine, day: datetime, learn_only: bool = True) -> None:
    """07:00 bed, 07:04 bath, 07:08 kitchen + kettle, kitchen every 30 min
    until 21:00, then bed at 21:10."""
    _pulse(e, "binary_sensor.bed", day + timedelta(hours=7), learn_only)
    _pulse(e, "binary_sensor.bath", day + timedelta(hours=7, minutes=4), learn_only)
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=7, minutes=8), learn_only)
    e.handle_state(
        "sensor.kettle",
        "0",
        "2800",
        day + timedelta(hours=7, minutes=9),
        learn_only=learn_only,
    )
    e.handle_state(
        "sensor.kettle",
        "2800",
        "0",
        day + timedelta(hours=7, minutes=11),
        learn_only=learn_only,
    )
    t = day + timedelta(hours=7, minutes=40)
    while t < day + timedelta(hours=21):
        _pulse(e, "binary_sensor.kit", t, learn_only)
        t += timedelta(minutes=30)
    _pulse(e, "binary_sensor.bed", day + timedelta(hours=21, minutes=10), learn_only)
    e.poll(day + timedelta(hours=23, minutes=59))


def _train(e: Engine, days: int = 15) -> None:
    for d in range(days):
        _day(e, MON + timedelta(days=d))
    e.poll(MON + timedelta(days=days, minutes=1))  # rollover


def test_learn_only_produces_no_actions_and_snapshot_reports_learning():
    e = _engine()
    snap = e.snapshot(MON)
    assert (
        snap["learning"]["confidence"] == 0.0
        and snap["welfare"]["status"] == "learning"
    )
    _train(e, days=3)
    assert e.snapshot(MON + timedelta(days=3))["learning"]["days_remaining"] == 11


def test_no_silent_alerts_while_learning():
    """longest_gap only means "the longest so far" until learning is done, so
    an entity idling longer than it ever has looks broken on day one.

    The bathroom is used twice each morning and the kitchen keeps the house
    awake all day, so from mid-morning the bathroom has been quiet for far
    more than three times its one-hour learned gap.
    """
    e = _engine(learning_days=14)
    actions = []
    for d in range(3):
        day = MON + timedelta(days=d)
        _pulse(e, "binary_sensor.bath", day + timedelta(hours=7))
        _pulse(e, "binary_sensor.bath", day + timedelta(hours=8))
        t = day + timedelta(hours=8, minutes=30)
        while t < day + timedelta(hours=20):
            _pulse(e, "binary_sensor.kit", t)
            t += timedelta(minutes=30)
        actions += e.poll(day + timedelta(hours=21))
    actions += e.poll(MON + timedelta(days=2, hours=22))
    assert [a.alert.source for a in actions if a.alert.kind == "silent"] == []


def test_daytime_silence_raises_welfare_after_training():
    e = _engine(learning_days=14)
    _train(e, days=15)
    day = MON + timedelta(days=15)
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=9), learn_only=False)
    quiet = day + timedelta(hours=9, minutes=1)
    assert all(
        not (
            a.action == "event"
            and a.event in ("opened", "escalated", "reminder")
            and a.group == "attention"
        )
        for a in e.poll(quiet)
    )
    actions = []
    for m in range(5, 260, 5):
        actions += e.poll(quiet + timedelta(minutes=m))
    pushes = [
        a
        for a in actions
        if a.action == "event"
        and a.event in ("opened", "escalated", "reminder")
        and a.group == "attention"
    ]
    assert pushes and pushes[0].alert.kind == "still_at_home"
    snap = e.snapshot(quiet + timedelta(minutes=260))
    # Bed, bathroom and kettle not used yet today, and she hasn't been out:
    # those signs escalate the stillness one step.
    assert snap["welfare"]["status"] in ("high", "critical")
    escalated = [
        a for a in snap["welfare"]["attention"] if "routine sign" in a["explanation"]
    ]
    assert escalated
    assert "Kitchen" in snap["house"]["last_room"]


def test_night_silence_is_normal():
    e = _engine()
    _train(e, days=15)
    night = MON + timedelta(days=15, hours=2)
    acts = []
    for m in range(0, 180, 10):
        acts += e.poll(night + timedelta(minutes=m))
    assert [
        a
        for a in acts
        if a.action == "event"
        and a.event in ("opened", "escalated", "reminder")
        and a.group == "attention"
    ] == []


def test_panic_opens_immediately_even_while_learning():
    e = _engine()
    acts = e.handle_state("binary_sensor.panic", "off", "on", MON)
    assert [(a.action, a.event) for a in acts] == [("event", "opened")]
    assert acts[0].alert.severity is Severity.CRITICAL
    assert e.poll(MON + timedelta(minutes=2)) == []
    cleared = e.clear_panic(None, MON + timedelta(minutes=3))
    assert [(a.action, a.event) for a in cleared] == [("event", "cleared")]
    assert e.reminders("manual") == []


def test_snapshot_splits_attention_and_information():
    e = _engine()
    high = Alert(
        AlertClass.WELFARE,
        "whereabouts",
        "still_at_home",
        Severity.HIGH,
        "quiet too long",
        MON,
    )
    low = Alert(
        AlertClass.WELFARE,
        "house",
        "routine_agreement",
        Severity.LOW,
        "routine slightly off",
        MON,
    )
    e._router.submit([high, low], MON)
    s = e.snapshot(MON)["welfare"]
    assert [a["group"] for a in s["attention"]] == ["attention"]
    assert s["information"] and all(
        a["group"] == "information" for a in s["information"]
    )
    assert "open_alerts" not in s and s["reasons"] == [s["attention"][0]["explanation"]]


def test_from_options_reads_attention_threshold():
    cfg = EngineConfig.from_options({"attention_min_severity": "high"})
    assert cfg.router.attention_min_severity is Severity.HIGH


def test_rollover_feeds_drift_and_recomputes_chains():
    e = _engine(learning_days=14)
    _train(e, days=15)
    snap = e.snapshot(MON + timedelta(days=15))
    assert any("Bedroom" in c["name"] for c in snap["chains"])
    assert "rooms" in e._drift.to_dict()["series"]  # rooms visited series exists


def test_set_entities_add_remove_and_reset():
    e = _engine()
    _train(e, days=3)
    added, removed = e.set_entities(
        ENTS[:3] + [EntitySpec("light.hall", Category.LIGHT, "Hall")]
    )
    assert added == {"light.hall"} and removed == {
        "sensor.kettle",
        "binary_sensor.panic",
    }
    assert "sensor.kettle" not in e.snapshot(MON)["entities"]
    e.reset()
    assert e.snapshot(MON)["learning"]["confidence"] == 0.0


def test_holiday_pauses_the_ladder_and_ends_cleanly():
    e = _engine(learning_days=14)
    _train(e, days=15)
    day15 = MON + timedelta(days=15)
    _pulse(e, "binary_sensor.kit", day15 + timedelta(hours=9), learn_only=False)
    e.holiday = True

    holiday_start = day15 + timedelta(hours=9, minutes=1)
    acts = []
    last_holiday_poll = holiday_start
    for h in range(72):
        last_holiday_poll = holiday_start + timedelta(hours=h)
        acts += e.poll(last_holiday_poll)
    assert [
        a
        for a in acts
        if a.action == "event"
        and a.event in ("opened", "escalated", "reminder")
        and a.group == "attention"
    ] == []
    assert e.snapshot(last_holiday_poll)["welfare"]["status"] != "degraded"

    day18_noon = MON + timedelta(days=18, hours=12)
    e.holiday = False
    post_holiday_acts = []
    acts = e.poll(day18_noon + timedelta(minutes=1))
    post_holiday_acts += acts
    assert [
        a
        for a in acts
        if a.action == "event"
        and a.event in ("opened", "escalated", "reminder")
        and a.group == "attention"
    ] == []
    acts = e.poll(day18_noon + timedelta(minutes=5))
    post_holiday_acts += acts
    assert [
        a
        for a in acts
        if a.action == "event"
        and a.event in ("opened", "escalated", "reminder")
        and a.group == "attention"
    ] == []

    pushes = []
    t = day18_noon + timedelta(minutes=5)
    end = day18_noon + timedelta(minutes=5) + timedelta(hours=4)
    while t <= end:
        acts = e.poll(t)
        post_holiday_acts += acts
        pushes += [
            a
            for a in acts
            if a.action == "event"
            and a.event in ("opened", "escalated", "reminder")
            and a.group == "attention"
        ]
        t += timedelta(minutes=10)
    assert pushes
    assert pushes[0].alert.kind == "still_at_home"
    assert pushes[0].alert.raised_at > day18_noon
    # the health clock also restarted, so no entity looks silent on return
    assert not any(
        a.action == "repair_create" and a.alert.kind == "silent"
        for a in post_holiday_acts
    )


def test_rollover_walks_every_skipped_day():
    e = _engine(learning_days=14)
    _train(e, days=15)  # last_poll_day lands on MON + 15

    skipped = [MON + timedelta(days=15 + i) for i in range(3)]
    for day in skipped:
        _pulse(e, "binary_sensor.kit", day + timedelta(hours=9))
    e.poll(MON + timedelta(days=18, minutes=1))  # walks days 15, 16, 17

    series = e._drift.to_dict()["series"]["count:binary_sensor.kit"]["values"]
    for day in skipped:
        assert day.date().isoformat() in series

    empty_days = [MON + timedelta(days=18 + i) for i in range(2)]
    e.poll(MON + timedelta(days=20, minutes=1))  # walks days 18, 19; no activity fed

    series = e._drift.to_dict()["series"]["count:binary_sensor.kit"]["values"]
    for day in empty_days:
        assert day.date().isoformat() not in series


def test_from_dict_drops_entities_no_longer_configured():
    e = _engine()
    _train(e, days=3)
    data = e.to_dict()
    assert "count:sensor.kettle" in data["drift"]["series"]  # sanity: it was learned
    e2 = Engine.from_dict(data, EngineConfig.from_options({}), ENTS[:3])
    assert "sensor.kettle" not in e2.snapshot(MON)["entities"]
    assert "sensor.kettle" not in e2._routines.entity_ids
    assert "count:sensor.kettle" not in e2._drift.to_dict()["series"]


def test_round_trip():
    e = _engine()
    _train(e, days=5)
    # yesterday's drift alerts are resubmitted on every poll, so losing them
    # across a restart silently clears and re-raises them
    e._last_stat = [
        Alert(
            AlertClass.STATISTICAL,
            "count:binary_sensor.kit",
            "drift",
            Severity.MEDIUM,
            "sustained increase for 4 days",
            MON + timedelta(days=5),
            {"direction": "increase", "days": 4},
        )
    ]
    e2 = Engine.from_dict(e.to_dict(), EngineConfig.from_options({}), ENTS)
    assert [a.to_dict() for a in e2._last_stat] == [a.to_dict() for a in e._last_stat]
    assert e2.snapshot(MON + timedelta(days=5)) == e.snapshot(MON + timedelta(days=5))
    assert (
        Engine.from_dict({"junk": 1}, EngineConfig.from_options({}), ENTS).snapshot(
            MON
        )["learning"]["confidence"]
        == 0.0
    )


def test_reset_preserves_holiday_and_snooze():
    """Relearning must not quietly take the site off holiday or unsnooze it."""
    e = _engine()
    _train(e, days=5)
    until = MON + timedelta(days=5, hours=2)
    e.holiday = True
    e.snooze_until = until

    e.reset()

    assert e.holiday is True
    assert e.snooze_until == until
    assert e.is_snoozed(MON + timedelta(days=5, hours=1))
    # The learning itself is gone, which is the point of the reset.
    assert e.snapshot(MON + timedelta(days=5))["learning"]["days_seen"] == 0

    # A single-entity reset never touched either field; confirm it still does not.
    e.reset("binary_sensor.bed")
    assert e.holiday is True and e.snooze_until == until


def test_snapshot_reports_whether_snooze_is_active():
    e = _engine()
    assert e.snapshot(MON)["snoozed"] is False
    e.snooze_until = MON + timedelta(hours=1)
    assert e.snapshot(MON)["snoozed"] is True
    assert e.snapshot(MON + timedelta(hours=2))["snoozed"] is False


def test_drift_names_use_room_and_type_and_disambiguate():
    e = Engine(
        EngineConfig(),
        ENTS
        + [
            EntitySpec("binary_sensor.back_door_door", Category.CONTACT, "Utility"),
            EntitySpec("binary_sensor.side_door_door", Category.CONTACT, "Utility"),
        ],
    )
    names = e.drift_names()
    assert names["binary_sensor.bed"] == "Bedroom motion"
    assert names["sensor.kettle"] == "Kitchen plug"
    assert names["binary_sensor.back_door_door"] == "Back door"
    assert names["binary_sensor.side_door_door"] == "Side door"


DOOR = EntitySpec("binary_sensor.side_door", Category.CONTACT, "Utility")


def _door_engine() -> Engine:
    e = Engine(
        EngineConfig.from_options(
            {"learning_days": 14, "outside_doors": ["binary_sensor.side_door"]}
        ),
        ENTS + [DOOR],
    )
    _train(e, days=15)
    return e


def _opened(actions: list) -> list:
    return [
        a.alert
        for a in actions
        if a.action == "event"
        and a.event in ("opened", "escalated", "reminder")
        and a.group == "attention"
    ]


def _open_where(e: Engine) -> list[Alert]:
    return [a for a in e._router.open_alerts if a.source == "whereabouts"]


def test_kitchen_stillness_raises_still_at_home_within_an_hour():
    e = _door_engine()
    day = MON + timedelta(days=15)
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=10), learn_only=False)
    acts = []
    for m in range(0, 66):
        acts += e.poll(day + timedelta(hours=10, minutes=m))
    opened = _opened(acts)
    assert opened
    assert (opened[0].cls, opened[0].source, opened[0].kind) == (
        AlertClass.WELFARE,
        "whereabouts",
        "still_at_home",
    )
    assert "Kitchen" in opened[0].details["room"]


def test_outing_through_side_door_raises_no_fall_alert():
    e = _door_engine()
    day = MON + timedelta(days=15)
    door_at = day + timedelta(hours=10)
    e.handle_state("binary_sensor.side_door", "off", "on", door_at)
    e.handle_state(
        "binary_sensor.side_door", "on", "off", door_at + timedelta(seconds=30)
    )
    acts = []
    for m in range(0, 181, 5):
        acts += e.poll(door_at + timedelta(minutes=m))
    assert [a for a in _opened(acts) if a.cls is AlertClass.WELFARE] == []
    assert e.snapshot(door_at + timedelta(hours=3))["whereabouts"]["where"] == "out"


def test_short_poll_gap_keeps_counting_and_long_gap_restarts():
    day = MON + timedelta(days=15)
    ten = day + timedelta(hours=10)

    e = _door_engine()
    _pulse(e, "binary_sensor.kit", ten)
    for m in (20, 45, 65):  # 25 and 20 minute gaps: the clock keeps running
        e.poll(ten + timedelta(minutes=m))
    assert [a.kind for a in _open_where(e)] == ["still_at_home"]

    e = _door_engine()
    _pulse(e, "binary_sensor.kit", ten)
    for m in (20, 50, 65):  # a 30 minute gap restarts the clock at 10:50
        e.poll(ten + timedelta(minutes=m))
    assert _open_where(e) == []
    m = 65
    while not _open_where(e):
        m += 5
        e.poll(ten + timedelta(minutes=m))
    assert m == 95  # 10:50 plus the 45 minute limit

    e = _door_engine()
    e.handle_state("binary_sensor.side_door", "off", "on", ten)
    e.handle_state("binary_sensor.side_door", "on", "off", ten + timedelta(seconds=30))
    e.poll(ten + timedelta(minutes=5))
    e.poll(ten + timedelta(minutes=15))
    late = ten + timedelta(minutes=55)  # 40 minute gap
    e.poll(late)
    assert e.snapshot(late)["whereabouts"]["where"] == "out"


def test_snapshot_has_whereabouts_block():
    e = _door_engine()
    day = MON + timedelta(days=15)
    e.poll(day + timedelta(hours=9, minutes=59))
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=10))
    now = day + timedelta(hours=10, minutes=5)
    e.poll(now)
    w = e.snapshot(now)["whereabouts"]
    assert set(w) == {"where", "where_since", "last_room", "limit_min", "night_since"}
    assert w["where"] == "home" and w["last_room"] == "Kitchen"
    # The pulse's burst ended at 10:01: stillness counts from there.
    assert w["where_since"] == (day + timedelta(hours=10, minutes=1)).isoformat()
    assert w["limit_min"] == 45.0
    assert _engine().snapshot(MON)["whereabouts"] == {
        "where": None,
        "where_since": None,
        "last_room": None,
        "limit_min": None,
        "night_since": None,
    }


def test_schema_3_round_trip_keeps_whereabouts_state():
    e = _door_engine()
    day = MON + timedelta(days=15)
    e.poll(day + timedelta(hours=9, minutes=59))
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=10))
    now = day + timedelta(hours=10, minutes=5)
    e.poll(now)
    data = e.to_dict()
    assert data["schema"] == 3
    assert data["meta"]["last_poll"] == now.isoformat()
    e2 = Engine.from_dict(data, e._cfg, ENTS + [DOOR])
    assert e2._where.to_dict() == e._where.to_dict()
    assert e2.snapshot(now)["whereabouts"] == e.snapshot(now)["whereabouts"]
    # The restored last poll still drives the gap check: a 25 minute gap
    # keeps counting from 10:00, so the alert is due at 10:45.
    e2.poll(day + timedelta(hours=10, minutes=30))
    e2.poll(day + timedelta(hours=10, minutes=46))
    assert [a.kind for a in _open_where(e2)] == ["still_at_home"]


def test_poll_gap_after_noon_keeps_an_open_not_up():
    day = MON + timedelta(days=15)
    e = _door_engine()
    _pulse(e, "binary_sensor.bed", day + timedelta(hours=22, minutes=30))
    t = day + timedelta(hours=22, minutes=35)
    while t <= day + timedelta(days=1, hours=11, minutes=50):
        e.poll(t)
        t += timedelta(minutes=5)
    assert [a.kind for a in _open_where(e)] == ["not_up"]
    e.poll(day + timedelta(days=1, hours=12, minutes=20))  # a 30 minute gap
    e.poll(day + timedelta(days=1, hours=12, minutes=21))
    assert [a.kind for a in _open_where(e)] == ["not_up"]
    snap = e.snapshot(day + timedelta(days=1, hours=12, minutes=21))
    assert (
        snap["whereabouts"]["where_since"]
        == (day + timedelta(hours=22, minutes=31)).isoformat()  # burst end
    )


def test_poll_gap_while_out_keeps_the_time_she_left():
    day = MON + timedelta(days=15)
    ten = day + timedelta(hours=10)
    e = _door_engine()
    e.poll(ten - timedelta(minutes=1))
    e.handle_state("binary_sensor.side_door", "off", "on", ten)
    e.handle_state("binary_sensor.side_door", "on", "off", ten + timedelta(seconds=30))
    for m in range(5, 31, 5):
        e.poll(ten + timedelta(minutes=m))
    noon = day + timedelta(hours=12)
    e.poll(noon)  # a 90 minute gap while she is out
    w = e.snapshot(noon)["whereabouts"]
    assert w["where"] == "out" and w["where_since"] == ten.isoformat()
    a = e._where.evaluate(day + timedelta(days=1))
    assert a.deadline == ten + timedelta(minutes=240 * 1.25)
    assert (
        "last out by the" in a.alert.explanation and "at 10:00" in a.alert.explanation
    )


def test_rename_room_renames_whereabouts_rooms():
    day = MON + timedelta(days=15)
    e = _door_engine()
    e._where._tvs_on = {"sensor.tv": "Kitchen"}
    e.handle_state("binary_sensor.side_door", "off", "on", day + timedelta(hours=10))
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=10, minutes=5))
    e.handle_state(
        "binary_sensor.side_door", "on", "off", day + timedelta(hours=10, minutes=6)
    )
    e._where._door_room = "Kitchen"
    e.rename_room("Kitchen", "Scullery")
    w = e._where.to_dict()
    assert w["last_room"] == "Scullery"
    assert w["door_room"] == "Scullery"
    assert w["tvs_on"] == {"sensor.tv": "Scullery"}
    assert w["interval"]["room"] == "Scullery"


def test_back_room_burst_end_reaches_whereabouts_through_the_normaliser():
    """9 Nov: kitchen presence inside a back room burst with the TV on."""
    back = EntitySpec("binary_sensor.back", Category.MOTION, "Back room")
    tv = EntitySpec("sensor.tv", Category.PLUG, "Back room")
    ents = ENTS + [DOOR, back, tv]
    e = Engine(
        EngineConfig.from_options(
            {
                "learning_days": 14,
                "outside_doors": ["binary_sensor.side_door"],
                "sitting_appliances": ["sensor.tv"],
            }
        ),
        ents,
    )
    _train(e, days=15)
    day = MON + timedelta(days=15)

    def at(h: int, m: int, s: int = 0) -> datetime:
        return day + timedelta(hours=h, minutes=m, seconds=s)

    e.handle_state("sensor.tv", None, "0", at(16, 30))
    e.handle_state("sensor.tv", "0", "82", at(16, 40))
    feed = [
        ("binary_sensor.back", "off", "on", at(16, 53, 1)),
        ("binary_sensor.back", "on", "off", at(16, 53, 30)),
        ("binary_sensor.kit", "off", "on", at(16, 53, 49)),
        ("binary_sensor.back", "off", "on", at(16, 54, 18)),
        ("binary_sensor.kit", "on", "off", at(16, 54, 53)),
        ("binary_sensor.back", "on", "off", at(16, 55, 20)),
    ]
    t = at(16, 40)
    acts: list = []
    first = None
    while t <= at(18, 30):
        while feed and feed[0][3] <= t:
            eid, old, new, ts = feed.pop(0)
            acts += e.handle_state(eid, old, new, ts, learn_only=False)
        acts += e.poll(t)
        if t == at(17, 40):
            w = e.snapshot(t)["whereabouts"]
            assert w["where"] == "home_tv" and w["last_room"] == "Back room"
            assert w["where_since"] == at(16, 55, 20).isoformat()
            assert _open_where(e) == []
        if first is None and _open_where(e):
            first = t
        t += timedelta(minutes=1)
    assert [a.kind for a in _open_where(e)] == ["still_tv"]
    assert first == at(18, 26)  # 16:55:20 plus 90 minutes, polled each minute


def test_walk_back_to_bed_through_the_normaliser_stays_asleep():
    """7 Nov: the landing clears in the same second as the bedroom."""
    landing = EntitySpec("binary_sensor.landing", Category.MOTION, "Landing")
    e = Engine(
        EngineConfig.from_options(
            {"learning_days": 14, "outside_doors": ["binary_sensor.side_door"]}
        ),
        ENTS + [DOOR, landing],
    )
    _train(e, days=15)
    night = MON + timedelta(days=16)

    def at(h: int, m: int, s: int = 0) -> datetime:
        return night + timedelta(hours=h, minutes=m, seconds=s)

    feed = [
        ("binary_sensor.bath", "off", "on", at(0, 0, 0)),
        ("binary_sensor.landing", "off", "on", at(0, 0, 11)),
        ("binary_sensor.bed", "off", "on", at(0, 0, 12)),
        ("binary_sensor.bath", "on", "off", at(0, 0, 57)),
        ("binary_sensor.bed", "on", "off", at(0, 1, 15)),
        ("binary_sensor.landing", "on", "off", at(0, 1, 15)),
    ]
    t = at(0, 0)
    while t <= at(2, 0):
        while feed and feed[0][3] <= t:
            eid, old, new, ts = feed.pop(0)
            e.handle_state(eid, old, new, ts, learn_only=False)
        e.poll(t)
        t += timedelta(minutes=1)
    w = e.snapshot(t)["whereabouts"]
    assert (w["where"], w["last_room"]) == ("asleep", "Bedroom")
    assert w["where_since"] == at(0, 1, 15).isoformat()
    assert _open_where(e) == []


def _battery_actions(acts: list) -> list:
    return [a for a in acts if a.alert is not None and a.alert.kind == "battery_low"]


def test_low_battery_is_a_health_repair_while_learning_and_learned():
    """Device health does not wait for learning, holiday or snooze."""
    e = _engine()
    e.record_battery("binary_sensor.panic", 12.0, MON)
    acts = _battery_actions(e.poll(MON + timedelta(minutes=1)))
    assert {a.action for a in acts} == {"repair_create", "event"}
    (ev,) = [a for a in acts if a.action == "event"]
    assert ev.group == "health" and ev.alert.severity is Severity.HIGH
    assert ev.alert.details == {"room": "Hall", "level": 12.0}
    assert ev.alert.explanation == "Hall panic button: battery low (12%)"
    e.record_battery("binary_sensor.panic", 100.0, MON + timedelta(minutes=2))
    acts = _battery_actions(e.poll(MON + timedelta(minutes=3)))
    assert "repair_delete" in {a.action for a in acts}

    e = _engine()
    _train(e)
    now = MON + timedelta(days=15, minutes=2)
    e.holiday = True
    e.snooze_until = now + timedelta(hours=1)
    e.record_battery("binary_sensor.kit", 15.0, now)
    acts = _battery_actions(e.poll(now))
    assert "repair_create" in {a.action for a in acts}
    assert "battery" not in str(e.to_dict()["health"])


def test_low_battery_threshold_comes_from_options():
    e = _engine(low_battery_pct=30)
    e.record_battery("binary_sensor.kit", 28.0, MON)
    assert _battery_actions(e.poll(MON))
    assert EngineConfig.from_options({}).health.low_battery_pct == 20.0


def test_restart_without_a_reading_neither_clears_nor_raises_battery_alert():
    """Levels are not stored, so an open alert's own level carries it over."""
    e = _engine()
    e.record_battery("binary_sensor.panic", 12.0, MON)
    e.poll(MON)
    # Still open inside the hysteresis band when Home Assistant restarts.
    e.record_battery("binary_sensor.panic", 22.0, MON)
    e.poll(MON)
    e2 = Engine.from_dict(e.to_dict(), EngineConfig.from_options({}), ENTS)
    assert not _battery_actions(e2.poll(MON + timedelta(minutes=1)))
    assert any(a.kind == "battery_low" for a in e2._router.open_alerts)
    # A real reading still clears it, with the usual hysteresis.
    e2.record_battery("binary_sensor.panic", 24.0, MON + timedelta(minutes=2))
    assert not _battery_actions(e2.poll(MON + timedelta(minutes=2)))
    e2.record_battery("binary_sensor.panic", 25.0, MON + timedelta(minutes=3))
    acts = _battery_actions(e2.poll(MON + timedelta(minutes=3)))
    assert "repair_delete" in {a.action for a in acts}


def test_forget_battery_clears_the_alert():
    e = _engine()
    e.record_battery("binary_sensor.kit", 10.0, MON)
    e.poll(MON)
    e.forget_battery("binary_sensor.kit")
    acts = _battery_actions(e.poll(MON + timedelta(minutes=1)))
    assert "repair_delete" in {a.action for a in acts}


def test_restored_battery_alert_closes_when_the_threshold_was_lowered():
    e = _engine()
    e.record_battery("binary_sensor.kit", 18.0, MON)
    e.poll(MON)
    e2 = Engine.from_dict(
        e.to_dict(), EngineConfig.from_options({"low_battery_pct": 10}), ENTS
    )
    acts = _battery_actions(e2.poll(MON + timedelta(minutes=1)))
    assert "repair_delete" in {a.action for a in acts}


def test_full_reset_keeps_an_open_panic_until_it_is_cleared():
    """Resetting learning must not drop a panic without a cleared event, or the
    blueprint keeps repeating it with nothing left that can stop it."""
    e = _engine()
    _train(e, days=5)
    now = MON + timedelta(days=5)
    e.handle_state("binary_sensor.panic", "off", "on", now)

    e.reset()

    assert [a.kind for a in e._router.open_alerts] == ["panic"]
    assert not [a for a in e.poll(now + timedelta(minutes=1)) if a.event == "cleared"]
    cleared = e.clear_panic(None, now + timedelta(minutes=2))
    assert [(a.event, a.cleared_by) for a in cleared] == [("cleared", "user")]


def test_full_reset_clears_learned_alerts_with_cleared_events():
    """Alerts that depended on what was learned close properly, not silently."""
    e = _engine()
    _train(e, days=15)
    now = MON + timedelta(days=15, hours=14)
    opened = [a for a in e.poll(now) if a.event == "opened"]
    assert opened, "training should leave a welfare alert open"

    e.reset()

    cleared = {
        a.alert.key for a in e.poll(now + timedelta(minutes=1)) if a.event == "cleared"
    }
    assert {a.alert.key for a in opened} <= cleared


def test_full_reset_keeps_a_low_battery_alert():
    e = _engine()
    e.record_battery("binary_sensor.panic", 12.0, MON)
    assert _battery_actions(e.poll(MON))

    e.reset()

    assert not _battery_actions(e.poll(MON + timedelta(minutes=1)))
    assert [a.kind for a in e._router.open_alerts] == ["battery_low"]


# ------------------------------------------------------------ really unusual

UNUSUAL_KINDS = {"not_yet_today", "trip_missed", "unusual_now"}


def _unusual_open(e: Engine) -> list[Alert]:
    return [a for a in e._router.open_alerts if a.kind in UNUSUAL_KINDS]


def _day_without_kettle(e: Engine, day: datetime, until_h: int = 10) -> list:
    """The usual morning with no kettle, polled each 10 min until ``until_h``."""
    _pulse(e, "binary_sensor.bed", day + timedelta(hours=7), learn_only=False)
    _pulse(e, "binary_sensor.bath", day + timedelta(hours=7, minutes=4), False)
    acts: list = []
    t = day + timedelta(hours=7, minutes=8)
    while t <= day + timedelta(hours=until_h):
        _pulse(e, "binary_sensor.kit", t, learn_only=False)
        acts += e.poll(t + timedelta(minutes=2))
        t += timedelta(minutes=10)
    return acts


def test_from_options_reads_unusual_settings():
    cfg = EngineConfig.from_options(
        {
            "upstairs_rooms": ["Landing", "Bedroom"],
            "night_trip_min": 45,
            "learning_days": 10,
            "window_days": 21,
        }
    ).unusual
    assert cfg.upstairs == frozenset({"Landing", "Bedroom"})
    assert cfg.night_trip_min == 45.0
    assert (cfg.min_days, cfg.window_days) == (10, 21)
    default = EngineConfig.from_options({}).unusual
    assert default.upstairs == frozenset() and default.night_trip_min == 30.0


def test_unusual_alerts_flow_through_poll_after_learning():
    e = _engine(learning_days=14)
    _train(e, days=15)
    acts = _day_without_kettle(e, MON + timedelta(days=15))
    logged = [
        a.alert for a in acts if a.action == "log" and a.alert.kind == "not_yet_today"
    ]
    assert [a.source for a in logged] == ["sensor.kettle"]
    a = logged[0]
    assert (a.cls, a.severity) == (AlertClass.STATISTICAL, Severity.LOW)
    assert a.explanation.startswith("Kitchen plug not used yet today")
    assert a.details["went_out_today"] is False


def test_no_unusual_alerts_while_learning_or_on_holiday():
    # Unusual has learned enough after 5 days; the engine has not.
    cfg = replace(
        EngineConfig.from_options({"learning_days": 14}),
        unusual=UnusualConfig(min_days=3),
    )
    e = Engine(cfg, ENTS)
    _train(e, days=5)
    _day_without_kettle(e, MON + timedelta(days=5))
    assert _unusual_open(e) == []

    e = _engine(learning_days=14)
    _train(e, days=15)
    e.holiday = True
    _day_without_kettle(e, MON + timedelta(days=15))
    assert _unusual_open(e) == []


def _go_up(e: Engine, day: datetime) -> datetime:
    """Kitchen at 22:00, bedroom at 22:03: going up. Returns the going-up."""
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=22), learn_only=False)
    up = day + timedelta(hours=22, minutes=3)
    _pulse(e, "binary_sensor.bed", up, learn_only=False)
    return up


def test_holiday_nights_not_learned_and_night_cleared_on_return():
    e = _engine(learning_days=14)
    _train(e, days=15)
    day = MON + timedelta(days=15)

    # A night begins before the holiday does.
    up = _go_up(e, day)
    e.poll(day + timedelta(hours=22, minutes=45))
    assert e._unusual.night_since == up
    assert (
        e.snapshot(day + timedelta(hours=22, minutes=45))["whereabouts"]["night_since"]
        == up.isoformat()
    )
    nights = e._unusual.to_dict()["night"]["nights"]

    e.holiday = True
    # Nothing on holiday is learned: not tonight's trip, not tomorrow's night.
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=23), learn_only=False)
    for h in range(1, 48):
        e.poll(day + timedelta(hours=23) + timedelta(hours=h))
    second = day + timedelta(days=1)
    _go_up(e, second)
    _day_without_kettle(e, second + timedelta(days=1), until_h=9)
    assert e._unusual.to_dict()["night"]["nights"] == nights
    assert e._unusual.night_since == up

    # Back from holiday: the interrupted night is dropped, not finalised.
    e.holiday = False
    back = day + timedelta(days=3, hours=12)
    e.poll(back)
    assert e._unusual.night_since is None
    assert e._unusual.to_dict()["night"]["nights"] == nights
    assert e.snapshot(back)["whereabouts"]["night_since"] is None


def test_old_store_without_unusual_keeps_learning_and_flags_rebuild():
    e = _engine(learning_days=14)
    _train(e, days=15)
    data = e.to_dict()
    assert "unusual" in data
    e_new = Engine.from_dict(data, e._cfg, ENTS)
    assert not e_new.needs_unusual_history
    assert e_new._unusual.to_dict() == e._unusual.to_dict()

    data.pop("unusual")
    old = Engine.from_dict(data, e._cfg, ENTS)
    now = MON + timedelta(days=15, minutes=1)
    assert old.snapshot(now)["learning"]["days_seen"] == 15
    assert old.needs_unusual_history
    assert old._unusual.to_dict()["active"] == []
    assert not _engine().needs_unusual_history
    assert not Engine.from_dict({"junk": 1}, e._cfg, ENTS).needs_unusual_history


def _outing_rows(days: int) -> list[tuple[datetime, str, str | None, str]]:
    """The usual day as recorder rows, with a side door outing 10:00 to 11:00."""
    rows: list[tuple[datetime, str, str | None, str]] = []

    def pulse(eid: str, ts: datetime) -> None:
        rows.append((ts, eid, "off", "on"))
        rows.append((ts + timedelta(seconds=60), eid, "on", "off"))

    for d in range(days):
        day = MON + timedelta(days=d)
        pulse("binary_sensor.bed", day + timedelta(hours=7))
        pulse("binary_sensor.bath", day + timedelta(hours=7, minutes=4))
        pulse("binary_sensor.kit", day + timedelta(hours=7, minutes=8))
        rows.append((day + timedelta(hours=7, minutes=9), "sensor.kettle", "0", "2800"))
        rows.append(
            (day + timedelta(hours=7, minutes=11), "sensor.kettle", "2800", "0")
        )
        for h in (10, 11):
            door = day + timedelta(hours=h)
            rows.append((door, "binary_sensor.side_door", "off", "on"))
            rows.append(
                (door + timedelta(seconds=30), "binary_sensor.side_door", "on", "off")
            )
        t = day + timedelta(hours=11, minutes=2)
        while t < day + timedelta(hours=21):
            pulse("binary_sensor.kit", t)
            t += timedelta(minutes=30)
        pulse("binary_sensor.bed", day + timedelta(hours=21, minutes=10))
    rows.append((MON, "sensor.not_monitored", "off", "on"))
    return sorted(rows, key=lambda r: r[0])


def test_rebuild_unusual_from_rows_learns_without_alerts():
    cfg = EngineConfig.from_options(
        {"learning_days": 14, "outside_doors": ["binary_sensor.side_door"]}
    )
    ents = ENTS + [DOOR]
    rows = _outing_rows(15)
    # The reference engine learned the same rows live.
    ref = Engine(cfg, ents)
    for d in range(15):
        day = MON + timedelta(days=d)
        for ts, eid, old, new in rows:
            if day <= ts < day + timedelta(days=1):
                ref.handle_state(eid, old, new, ts, learn_only=True)
        ref.poll(day + timedelta(hours=23, minutes=59))
    now = MON + timedelta(days=15, minutes=1)
    ref.poll(now)
    assert ref._where.out_spans((MON + timedelta(days=3)).date())

    data = ref.to_dict()
    data.pop("unusual")
    # An old store kept no outing spans either.
    data["whereabouts"].pop("out_spans", None)
    e = Engine.from_dict(data, cfg, ents)
    assert e.needs_unusual_history
    before = e.to_dict()
    e.rebuild_unusual(rows, now)
    assert not e.needs_unusual_history
    assert e._unusual.to_dict()["first"] == ref._unusual.to_dict()["first"]
    assert e._unusual.to_dict()["active"] == ref._unusual.to_dict()["active"]
    assert e._unusual.to_dict()["night"]["nights"] == (
        ref._unusual.to_dict()["night"]["nights"]
    )
    assert e._where.out_spans((MON + timedelta(days=3)).date()) == (
        ref._where.out_spans((MON + timedelta(days=3)).date())
    )
    after = e.to_dict()
    for key in ("normaliser", "house", "routines", "chains", "drift", "health"):
        assert after[key] == before[key], key
    assert after["router"] == before["router"]
    assert e.poll(now + timedelta(minutes=1)) == []


def test_reset_entity_forgets_unusual_learning():
    e = _engine(learning_days=14)
    _train(e, days=15)
    assert "sensor.kettle" in e._unusual.to_dict()["first"]
    e.reset("sensor.kettle")
    assert "sensor.kettle" not in e._unusual.to_dict()["first"]
    assert "binary_sensor.kit" in e._unusual.to_dict()["first"]
    _day_without_kettle(e, MON + timedelta(days=15))
    assert _unusual_open(e) == []

    e.set_entities(ENTS[:3])
    assert set(e._unusual.to_dict()["first"]) <= {s.entity_id for s in ENTS[:3]}


def _window(e: Engine, start: datetime, end: datetime) -> list:
    """Poll each minute from ``start`` to ``end``; the open alerts each time."""
    seen = []
    t = start
    while t <= end:
        e.poll(t)
        seen.append(list(e._router.open_alerts))
        t += timedelta(minutes=1)
    return seen


def _no_cards_or_signs(seen: list) -> bool:
    return all(
        a.kind not in UNUSUAL_KINDS and "escalated_by" not in a.details
        for open_ in seen
        for a in open_
    )


def test_back_from_holiday_waits_the_allowance_before_not_yet_today():
    e = _engine(learning_days=14)
    _train(e, days=15)
    day = MON + timedelta(days=15)
    e.holiday = True
    for h in range(0, 18):
        e.poll(day + timedelta(hours=h))
    e.holiday = False
    back = day + timedelta(hours=18)
    e.poll(back)
    _pulse(e, "binary_sensor.kit", back + timedelta(minutes=1), learn_only=False)
    seen = _window(e, back + timedelta(minutes=1), back + timedelta(minutes=59))
    assert any(a.source == "whereabouts" for a in seen[-1])  # still_at_home
    assert _no_cards_or_signs(seen)
    e.poll(back + timedelta(minutes=60))
    assert {a.source for a in _unusual_open(e)} == {
        "binary_sensor.bed",
        "binary_sensor.bath",
        "sensor.kettle",
    }
    # Past the wait the cards are signs again, and they escalate.
    [where] = _open_where(e)
    assert where.details["escalated_by"]


def test_ha_down_all_morning_waits_the_allowance_after_it_is_back():
    e = _engine(learning_days=14)
    _train(e, days=15)
    day = MON + timedelta(days=15)
    e.poll(day + timedelta(hours=6))
    up = day + timedelta(hours=11)  # nothing seen or polled 06:00-11:00
    e.poll(up)
    _pulse(e, "binary_sensor.kit", up, learn_only=False)
    seen = _window(e, up + timedelta(minutes=1), up + timedelta(minutes=59))
    assert any(a.source == "whereabouts" for a in seen[-1])
    assert _no_cards_or_signs(seen)
    e.poll(up + timedelta(minutes=60))
    assert {a.source for a in _unusual_open(e)} == {
        "binary_sensor.bed",
        "binary_sensor.bath",
        "sensor.kettle",
    }


def test_restart_from_an_old_store_waits_the_allowance():
    e = _engine(learning_days=14)
    _train(e, days=15)
    day = MON + timedelta(days=15)
    e.poll(day + timedelta(hours=6))
    up = day + timedelta(hours=11)
    restored = Engine.from_dict(e.to_dict(), e._cfg, ENTS)
    _pulse(restored, "binary_sensor.kit", up, learn_only=False)
    seen = _window(restored, up, up + timedelta(minutes=59))
    assert _no_cards_or_signs(seen)
    # A restart inside the wait keeps it.
    again = Engine.from_dict(restored.to_dict(), e._cfg, ENTS)
    assert _no_cards_or_signs(
        _window(again, up + timedelta(minutes=30), up + timedelta(minutes=59))
    )
    again.poll(up + timedelta(minutes=60))
    assert _unusual_open(again)


def test_unreadable_unusual_store_flags_a_rebuild():
    e = _engine(learning_days=14)
    _train(e, days=15)
    data = e.to_dict()
    for bad in ({"first": 5}, 7, dict(data["unusual"], night=3)):
        back = Engine.from_dict(dict(data, unusual=bad), e._cfg, ENTS)
        assert back.needs_unusual_history
        assert back._unusual.to_dict()["active"] == []
    assert not Engine.from_dict(data, e._cfg, ENTS).needs_unusual_history


def test_out_overnight_cards_wait_for_the_return_and_say_went_out():
    e = _door_engine()
    day = MON + timedelta(days=15)
    out_at = day + timedelta(hours=18)
    _pulse(e, "binary_sensor.kit", out_at - timedelta(minutes=1), learn_only=False)
    e.handle_state("binary_sensor.side_door", "off", "on", out_at, learn_only=False)
    e.handle_state(
        "binary_sensor.side_door", "on", "off", out_at + timedelta(seconds=30), False
    )
    t = out_at
    back = day + timedelta(days=1, hours=11)
    while t < back:
        e.poll(t)
        t += timedelta(minutes=10)
    assert _unusual_open(e) == []
    e.handle_state("binary_sensor.side_door", "off", "on", back, learn_only=False)
    e.handle_state(
        "binary_sensor.side_door", "on", "off", back + timedelta(seconds=30), False
    )
    _pulse(e, "binary_sensor.kit", back + timedelta(minutes=1), learn_only=False)
    for m in range(2, 60, 5):
        e.poll(back + timedelta(minutes=m))
        assert _unusual_open(e) == []
    e.poll(back + timedelta(minutes=61))
    opened = _unusual_open(e)
    assert opened and all(a.details["went_out_today"] is True for a in opened)
