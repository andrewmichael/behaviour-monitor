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
    assert snap["welfare"]["status"] in ("medium", "high")
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
    assert set(w) == {"where", "where_since", "last_room", "limit_min"}
    assert w["where"] == "home" and w["last_room"] == "Kitchen"
    assert w["where_since"] == (day + timedelta(hours=10)).isoformat()
    assert w["limit_min"] == 45.0
    assert _engine().snapshot(MON)["whereabouts"] == {
        "where": None,
        "where_since": None,
        "last_room": None,
        "limit_min": None,
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
    assert snap["whereabouts"]["where_since"] == (
        day + timedelta(hours=22, minutes=30)
    ).isoformat()


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
    assert "left by the" in a.alert.explanation and "at 10:00" in a.alert.explanation
