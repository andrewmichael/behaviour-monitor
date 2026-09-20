from datetime import datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import Severity
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
    """07:00 bed, 07:04 bath, 07:08 kitchen + kettle, then kitchen every 30 min until 21:00."""
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


def test_daytime_silence_raises_welfare_after_training():
    e = _engine(learning_days=14)
    _train(e, days=15)
    day = MON + timedelta(days=15)
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=9), learn_only=False)
    quiet = day + timedelta(hours=9, minutes=1)
    assert all(a.action != "push" for a in e.poll(quiet))
    actions = []
    for m in range(5, 260, 5):
        actions += e.poll(quiet + timedelta(minutes=m))
    pushes = [a for a in actions if a.action == "push"]
    assert pushes and pushes[0].alert.kind == "inactivity"
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
    assert [a for a in acts if a.action == "push"] == []


def test_panic_pushes_immediately_even_while_learning():
    e = _engine()
    acts = e.handle_state("binary_sensor.panic", "off", "on", MON)
    assert [a.action for a in acts] == ["push"] and acts[
        0
    ].alert.severity is Severity.CRITICAL
    e.acknowledge(MON + timedelta(minutes=1))
    assert [a.action for a in e.poll(MON + timedelta(minutes=2))] == ["push_clear"]


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
    assert [a for a in acts if a.action == "push"] == []
    assert e.snapshot(last_holiday_poll)["welfare"]["status"] != "degraded"

    day18_noon = MON + timedelta(days=18, hours=12)
    e.holiday = False
    post_holiday_acts = []
    acts = e.poll(day18_noon + timedelta(minutes=1))
    post_holiday_acts += acts
    assert [a for a in acts if a.action == "push"] == []
    acts = e.poll(day18_noon + timedelta(minutes=5))
    post_holiday_acts += acts
    assert [a for a in acts if a.action == "push"] == []

    pushes = []
    t = day18_noon + timedelta(minutes=5)
    end = day18_noon + timedelta(minutes=5) + timedelta(hours=4)
    while t <= end:
        acts = e.poll(t)
        post_holiday_acts += acts
        pushes += [a for a in acts if a.action == "push"]
        t += timedelta(minutes=10)
    assert pushes
    assert pushes[0].alert.kind == "inactivity"
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
    e2 = Engine.from_dict(e.to_dict(), EngineConfig.from_options({}), ENTS)
    assert e2.snapshot(MON + timedelta(days=5)) == e.snapshot(MON + timedelta(days=5))
    assert (
        Engine.from_dict({"junk": 1}, EngineConfig.from_options({}), ENTS).snapshot(
            MON
        )["learning"]["confidence"]
        == 0.0
    )
