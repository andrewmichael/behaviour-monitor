from datetime import datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alert_router import (
    AlertRouter,
    RouterConfig,
)
from custom_components.behaviour_monitor.core.alerts import Alert, AlertClass, Severity
from custom_components.behaviour_monitor.core.events import (
    ActivityEvent,
    Category,
    EventKind,
)

T0 = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)


def _house(sev: Severity, ts: datetime = T0) -> Alert:
    return Alert(AlertClass.WELFARE, "house", "inactivity", sev, "No activity", ts)


def _note(
    src: str = "sensor.kettle", ts: datetime = T0, fired_today: bool = True
) -> Alert:
    return Alert(
        AlertClass.STATISTICAL,
        src,
        "routine_missed",
        Severity.LOW,
        "missed",
        ts,
        {"fired_today": fired_today},
    )


def _stall(ts: datetime = T0) -> Alert:
    return Alert(
        AlertClass.STATISTICAL, "Bed → Bath", "chain_stall", Severity.LOW, "stalled", ts
    )


def _health(src: str = "binary_sensor.k", ts: datetime = T0) -> Alert:
    return Alert(AlertClass.HEALTH, src, "unavailable", Severity.MEDIUM, "down", ts)


def _acts(actions, kind):
    return [a.alert.key for a in actions if a.action == kind]


def test_welfare_push_threshold_repeat_and_clear():
    r = AlertRouter(RouterConfig(push_repeat_s=600))
    assert _acts(r.submit([_house(Severity.LOW)], T0), "push") == []
    acts = r.submit([_house(Severity.MEDIUM)], T0 + timedelta(minutes=1))
    assert _acts(acts, "push") == ["welfare:house:inactivity"]
    assert r.submit([_house(Severity.MEDIUM)], T0 + timedelta(minutes=5)) == []
    acts = r.submit([_house(Severity.MEDIUM)], T0 + timedelta(minutes=12))
    assert _acts(acts, "push") == ["welfare:house:inactivity"]
    acts = r.submit([], T0 + timedelta(minutes=13))
    assert _acts(acts, "push_clear") == ["welfare:house:inactivity"]
    assert r.open_alerts == []


def test_severity_rise_pushes_immediately_and_ack_stops_repeats():
    r = AlertRouter(RouterConfig(push_repeat_s=600))
    r.submit([_house(Severity.MEDIUM)], T0)
    acts = r.submit([_house(Severity.HIGH)], T0 + timedelta(minutes=1))
    assert _acts(acts, "push") == ["welfare:house:inactivity"]
    r.acknowledge(T0 + timedelta(minutes=2))
    assert r.submit([_house(Severity.HIGH)], T0 + timedelta(minutes=30)) == []
    assert r.welfare_severity is Severity.HIGH


def test_health_becomes_repair_and_statistical_becomes_log():
    r = AlertRouter(RouterConfig())
    acts = r.submit([_health(), _note()], T0)
    assert _acts(acts, "repair_create") == ["health:binary_sensor.k:unavailable"]
    assert _acts(acts, "log") == ["statistical:sensor.kettle:routine_missed"]
    assert r.submit([_health(), _note()], T0 + timedelta(hours=2)) == []
    acts = r.submit([], T0 + timedelta(hours=3))
    assert _acts(acts, "repair_delete") == ["health:binary_sensor.k:unavailable"]
    assert _acts(acts, "log_clear") == ["statistical:sensor.kettle:routine_missed"]


def test_note_escalates_open_house_alert_by_one_level():
    # one note is one chance miss, not agreement
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.LOW), _note()], T0)
    assert r.welfare_severity is Severity.LOW
    # two distinct sources that both fired today do escalate
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.LOW), _note("a"), _note("b")], T0)
    assert r.welfare_severity is Severity.MEDIUM
    # so does a single stall
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.LOW), _stall()], T0)
    assert r.welfare_severity is Severity.MEDIUM


def test_notes_from_entities_silent_today_do_not_escalate():
    r = AlertRouter(RouterConfig())
    silent = [_note("a", fired_today=False), _note("b", fired_today=False)]
    acts = r.submit([_house(Severity.LOW), *silent], T0)
    assert r.welfare_severity is Severity.LOW
    # the notes themselves are still logged
    assert sorted(_acts(acts, "log")) == [
        "statistical:a:routine_missed",
        "statistical:b:routine_missed",
    ]
    # and they cannot agree with each other into a welfare alert
    r2 = AlertRouter(RouterConfig())
    r2.submit(silent, T0)
    assert "welfare:house:routine_agreement" not in [a.key for a in r2.open_alerts]


def test_two_notes_open_low_welfare_without_house_alert():
    r = AlertRouter(RouterConfig())
    acts = r.submit([_note("a"), _stall()], T0)
    keys = [a.key for a in r.open_alerts]
    assert "welfare:house:routine_agreement" in keys
    assert r.welfare_severity is Severity.LOW
    assert _acts(acts, "push") == []  # low is below push threshold
    r.submit([_note("a")], T0 + timedelta(minutes=5))
    assert "welfare:house:routine_agreement" not in [a.key for a in r.open_alerts]


def test_chain_timing_drift_promotes_after_days():
    r = AlertRouter(RouterConfig(timing_promote_days=7))
    d6 = Alert(
        AlertClass.STATISTICAL,
        "chain:Bed → Kitchen",
        "drift",
        Severity.MEDIUM,
        "slower",
        T0,
        {"days": 6, "direction": "increase"},
    )
    r.submit([d6], T0)
    assert [a.key for a in r.open_alerts] == ["statistical:chain:Bed → Kitchen:drift"]
    d7 = Alert(
        AlertClass.STATISTICAL,
        "chain:Bed → Kitchen",
        "drift",
        Severity.MEDIUM,
        "slower",
        T0,
        {"days": 7, "direction": "increase"},
    )
    r.submit([d7], T0 + timedelta(days=1))
    assert "welfare:chain:Bed → Kitchen:timing_drift" in [a.key for a in r.open_alerts]
    dec = Alert(
        AlertClass.STATISTICAL,
        "chain:Other",
        "drift",
        Severity.MEDIUM,
        "faster",
        T0,
        {"days": 9, "direction": "decrease"},
    )
    r.submit([d7, dec], T0 + timedelta(days=2))
    assert "welfare:chain:Other:timing_drift" not in [a.key for a in r.open_alerts]


def test_panic_is_immediate_critical_and_survives_submit_until_ack():
    r = AlertRouter(RouterConfig())
    ev = ActivityEvent(
        "binary_sensor.p", Category.PANIC, EventKind.PANIC, "Hall", T0, bypass=True
    )
    acts = r.submit_panic(ev, T0)
    assert [(a.action, a.alert.severity) for a in acts] == [("push", Severity.CRITICAL)]
    assert r.submit([], T0 + timedelta(minutes=1), snoozed=True, holiday=True) == []
    assert "welfare:binary_sensor.p:panic" in [a.key for a in r.open_alerts]
    acts = r.submit([], T0 + timedelta(minutes=31))
    assert _acts(acts, "push") == [
        "welfare:binary_sensor.p:panic"
    ]  # repeats until acknowledged
    r.acknowledge(T0 + timedelta(minutes=32))
    acts = r.submit([], T0 + timedelta(minutes=33))
    assert _acts(acts, "push_clear") == ["welfare:binary_sensor.p:panic"]


def test_snooze_suppresses_delivery_but_keeps_state_and_holiday_drops_alerts():
    r2 = AlertRouter(RouterConfig())
    acts = r2.submit([_house(Severity.HIGH), _health()], T0, snoozed=True)
    assert _acts(acts, "push") == [] and _acts(acts, "repair_create") == [
        "health:binary_sensor.k:unavailable"
    ]
    assert r2.welfare_severity is Severity.HIGH
    r3 = AlertRouter(RouterConfig())
    acts = r3.submit([_house(Severity.HIGH), _note(), _health()], T0, holiday=True)
    assert [a.key for a in r3.open_alerts] == ["health:binary_sensor.k:unavailable"]


def test_holiday_clears_silently():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.HIGH)], T0)
    acts = r.submit([], T0 + timedelta(minutes=1), holiday=True)
    assert _acts(acts, "push_clear") == []
    assert "welfare:house:inactivity" not in [a.key for a in r.open_alerts]

    r2 = AlertRouter(RouterConfig())
    r2.submit([_health(), _note()], T0)
    acts = r2.submit([], T0 + timedelta(minutes=1), holiday=True)
    assert _acts(acts, "repair_delete") == ["health:binary_sensor.k:unavailable"]
    assert _acts(acts, "log_clear") == []


def test_round_trip():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.MEDIUM), _health()], T0)
    r2 = AlertRouter.from_dict(r.to_dict(), RouterConfig())
    assert sorted(a.key for a in r2.open_alerts) == sorted(a.key for a in r.open_alerts)
    assert AlertRouter.from_dict({"x": 1}, RouterConfig()).open_alerts == []
