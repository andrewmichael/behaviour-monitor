from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import AlertClass, Severity
from custom_components.behaviour_monitor.core.events import (
    ActivityEvent,
    Category,
    EventKind,
    HealthEvent,
)
from custom_components.behaviour_monitor.core.health_tracker import (
    HealthConfig,
    HealthTracker,
)

T0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
ENTS = [
    ("binary_sensor.k", Category.MOTION, "Kitchen"),
    ("binary_sensor.b", Category.MOTION, "Bath"),
    ("binary_sensor.p", Category.PANIC, "Hall"),
    ("sensor.kettle", Category.PLUG, "Kitchen"),
]


def _tracker() -> HealthTracker:
    t = HealthTracker(HealthConfig())
    for e in ENTS:
        t.register(*e)
    return t


def _down(t: HealthTracker, eid: str, ts: datetime, available: bool = False) -> None:
    cat, room = next((c, r) for e, c, r in ENTS if e == eid)
    t.record_health(HealthEvent(eid, cat, room, ts, available))


def test_short_dropout_inside_grace_is_ignored():
    t = _tracker()
    _down(t, "binary_sensor.k", T0)
    assert t.evaluate(T0 + timedelta(minutes=5), lambda e: None, None) == []
    _down(t, "binary_sensor.k", T0 + timedelta(seconds=10), available=True)
    assert t.evaluate(T0 + timedelta(minutes=20), lambda e: None, None) == []


def test_unavailable_beyond_grace_alerts_and_panic_is_high():
    t = _tracker()
    _down(t, "binary_sensor.k", T0)
    _down(t, "binary_sensor.p", T0)
    alerts = t.evaluate(T0 + timedelta(minutes=16), lambda e: None, None)
    by = {a.source: a for a in alerts}
    assert (
        by["binary_sensor.k"].kind == "unavailable"
        and by["binary_sensor.k"].severity is Severity.MEDIUM
    )
    assert by["binary_sensor.p"].severity is Severity.HIGH
    assert all(a.cls is AlertClass.HEALTH for a in alerts)
    assert t.down_entities(T0 + timedelta(minutes=16)) == {
        "binary_sensor.k",
        "binary_sensor.p",
    }
    assert t.live_fraction(T0 + timedelta(minutes=16)) == 0.5


def test_sitewide_dropout_is_one_alert_and_counted():
    t = _tracker()
    for eid, _, _ in ENTS[:3]:
        _down(t, eid, T0 + timedelta(seconds=5))
    alerts = t.evaluate(T0 + timedelta(seconds=30), lambda e: None, None)
    assert [a.kind for a in alerts] == ["dropout"]
    assert alerts[0].source == "site" and alerts[0].details["count"] == 3
    for eid, _, _ in ENTS[:3]:
        _down(t, eid, T0 + timedelta(seconds=40), available=True)
    assert t.evaluate(T0 + timedelta(seconds=60), lambda e: None, None) == []
    assert t.sitewide_dropouts_today(date(2026, 9, 21)) == 1


def test_silent_sensor_needs_house_activity_elsewhere():
    t = _tracker()
    t.record_activity(
        ActivityEvent(
            "binary_sensor.k", Category.MOTION, EventKind.PRESENCE, "Kitchen", T0
        )
    )

    def longest(e):
        return 3600.0 if e == "binary_sensor.k" else None

    # house quiet too: not the sensor's fault
    assert t.evaluate(T0 + timedelta(hours=4), longest, T0) == []
    # house active after the sensor went quiet
    alerts = t.evaluate(T0 + timedelta(hours=4), longest, T0 + timedelta(hours=3))
    assert [a.kind for a in alerts] == ["silent"] and alerts[
        0
    ].source == "binary_sensor.k"
    assert alerts[0].details["silent_s"] == 4 * 3600.0
    assert "binary_sensor.k" in t.down_entities(T0 + timedelta(hours=4))


def test_panic_is_never_silent_candidate_and_states_exposed():
    t = _tracker()
    t.record_activity(
        ActivityEvent(
            "binary_sensor.p", Category.PANIC, EventKind.PANIC_RELEASE, "Hall", T0
        )
    )
    assert (
        t.evaluate(T0 + timedelta(days=30), lambda e: 60.0, T0 + timedelta(days=29))
        == []
    )
    states = t.entity_states(T0)
    assert states == {e: "ok" for e, _, _ in ENTS}


def test_restart_clock_sets_last_event_without_touching_down_state():
    t = _tracker()
    t.record_activity(
        ActivityEvent(
            "binary_sensor.k", Category.MOTION, EventKind.PRESENCE, "Kitchen", T0
        )
    )
    _down(t, "sensor.kettle", T0 + timedelta(minutes=1))
    now = T0 + timedelta(days=5)
    t.restart_clock(now)
    entities = t.to_dict()["entities"]
    assert all(e["last_event"] == now.isoformat() for e in entities.values())
    # down/unavailable bookkeeping is untouched by restart_clock
    assert t.down_entities(now + timedelta(minutes=20)) == {"sensor.kettle"}


def test_remove_and_round_trip():
    t = _tracker()
    _down(t, "binary_sensor.k", T0)
    t2 = HealthTracker.from_dict(t.to_dict(), HealthConfig())
    assert t2.down_entities(T0 + timedelta(minutes=16)) == {"binary_sensor.k"}
    t2.remove("binary_sensor.k")
    assert t2.down_entities(T0 + timedelta(minutes=16)) == set()
    assert HealthTracker.from_dict({"bad": 1}, HealthConfig()).entity_states(T0) == {}
