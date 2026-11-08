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
    r.submit([_note("a"), _stall()], T0)
    keys = [a.key for a in r.open_alerts]
    assert "welfare:house:routine_agreement" in keys
    assert r.welfare_severity is Severity.LOW
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


def _ev(acts, event=None):
    return [
        (a.event, a.alert.key)
        for a in acts
        if a.action == "event" and (event is None or a.event == event)
    ]


def _panic(eid="binary_sensor.p", ts=T0):
    return ActivityEvent(eid, Category.PANIC, EventKind.PANIC, "Hall", ts, bypass=True)


def test_open_escalate_clear_events_keep_one_id():
    r = AlertRouter(RouterConfig())
    m1 = T0 + timedelta(minutes=1)
    m2 = T0 + timedelta(minutes=2)
    a1 = r.submit([_house(Severity.MEDIUM, T0)], T0)
    a2 = r.submit([_house(Severity.HIGH, m1)], m1)
    assert r.submit([_house(Severity.HIGH, m2)], m2) == []
    a3 = r.submit([], T0 + timedelta(minutes=3))
    assert [x.event for x in a1 + a2 + a3] == ["opened", "escalated", "cleared"]
    assert len({x.alert_id for x in a1 + a2 + a3}) == 1
    assert a1[0].alert_id == f"welfare:house:inactivity@{T0.isoformat()}"


def test_reopened_key_gets_new_id_after_clear():
    r = AlertRouter(RouterConfig())
    first = r.submit([_house(Severity.MEDIUM, T0)], T0)[0].alert_id
    cleared = r.submit([], T0 + timedelta(minutes=1))
    t2 = T0 + timedelta(minutes=2)
    second = r.submit([_house(Severity.MEDIUM, t2)], t2)[0].alert_id
    assert cleared[0].alert_id == first and second != first


def test_groups_threshold_panic_and_sticky_attention():
    r = AlertRouter(RouterConfig(attention_min_severity=Severity.HIGH))
    acts = r.submit([_house(Severity.MEDIUM), _note(), _health()], T0)
    groups = {a.alert.key: a.group for a in acts if a.action == "event"}
    assert groups == {
        "welfare:house:inactivity": "information",
        "statistical:sensor.kettle:routine_missed": "information",
        "health:binary_sensor.k:unavailable": "health",
    }
    m1 = T0 + timedelta(minutes=1)
    up = r.submit([_house(Severity.HIGH), _note(), _health()], m1)
    assert [(a.event, a.group) for a in up if a.alert.kind == "inactivity"] == [
        ("escalated", "attention")
    ]
    r.submit([_house(Severity.MEDIUM), _note(), _health()], T0 + timedelta(minutes=2))
    published = {p["key"]: p["group"] for p in r.published()}
    assert published["welfare:house:inactivity"] == "attention"
    p = r.submit_panic(_panic(), T0)
    assert p[0].group == "attention"  # panic is attention whatever the threshold


def test_snooze_holds_attention_then_reminds_but_never_holds_panic():
    r = AlertRouter(RouterConfig())
    assert _ev(r.submit([_house(Severity.HIGH)], T0, snoozed=True)) == []
    assert _ev(r.submit_panic(_panic(), T0)) == [
        ("opened", "welfare:binary_sensor.p:panic")
    ]
    m1 = T0 + timedelta(minutes=1)
    again = r.submit_panic(_panic(ts=m1), m1)
    assert [(a.event, a.reason) for a in again] == [("reminder", "pressed_again")]
    acts = r.submit([_house(Severity.HIGH)], T0 + timedelta(minutes=5))
    assert [(a.event, a.reason, a.alert.key) for a in acts] == [
        ("reminder", "snooze_ended", "welfare:house:inactivity")
    ]
    assert r.submit([_house(Severity.HIGH)], T0 + timedelta(minutes=6)) == []


def test_cleared_fires_during_snooze_and_holiday():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.HIGH), _note()], T0)
    acts = r.submit([], T0 + timedelta(minutes=1), holiday=True)
    assert sorted(_ev(acts, "cleared")) == [
        ("cleared", "statistical:sensor.kettle:routine_missed"),
        ("cleared", "welfare:house:inactivity"),
    ]
    assert [a for a in acts if a.action == "log_clear"] == []


def test_panic_stays_until_cleared_by_user():
    r = AlertRouter(RouterConfig())
    pid = r.submit_panic(_panic(), T0)[0].alert_id
    assert _ev(r.submit([], T0 + timedelta(hours=5), holiday=True)) == []
    assert r.clear_panic("welfare:house:inactivity@x", T0) == []
    acts = r.clear_panic(pid, T0 + timedelta(hours=6))
    assert [(a.event, a.cleared_by, a.alert_id) for a in acts] == [
        ("cleared", "user", pid)
    ]
    assert r.open_alerts == []


def test_clear_panic_without_id_clears_all_real_panics_not_test():
    r = AlertRouter(RouterConfig())
    r.submit_panic(_panic("binary_sensor.a"), T0)
    r.submit_panic(_panic("binary_sensor.b"), T0)
    r.submit_test(T0)
    acts = r.clear_panic(None, T0 + timedelta(minutes=1))
    assert sorted(a.alert.source for a in acts) == [
        "binary_sensor.a",
        "binary_sensor.b",
    ]


def test_test_alert_flags_events_and_never_touches_real_panic():
    r = AlertRouter(RouterConfig())
    r.submit_panic(_panic(), T0)
    t = r.submit_test(T0 + timedelta(minutes=1))
    assert [(a.event, a.test) for a in t] == [("opened", True)]
    c = r.submit([], T0 + timedelta(minutes=2))
    assert [(a.event, a.test, a.alert.source) for a in c] == [("cleared", True, "test")]
    assert [a.key for a in r.open_alerts] == ["welfare:binary_sensor.p:panic"]
    assert [a.alert.source for a in r.reminders("restart")] == ["binary_sensor.p"]


def test_reminders_cover_open_attention_only():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.HIGH), _note(), _health()], T0)
    assert [(a.event, a.reason, a.alert.key) for a in r.reminders("restart")] == [
        ("reminder", "restart", "welfare:house:inactivity")
    ]


def test_round_trip_keeps_ids_groups_and_held():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.HIGH), _health()], T0, snoozed=True)
    r2 = AlertRouter.from_dict(r.to_dict(), RouterConfig())
    assert r2.published() == r.published()
    acts = r2.submit([_house(Severity.HIGH), _health()], T0)
    assert [a.reason for a in acts] == ["snooze_ended"]


def test_loads_v11_router_state():
    def entry(alert: Alert, acknowledged: bool, panic: bool, last_push):
        return {
            "alert": alert.to_dict(),
            "opened_at": T0.isoformat(),
            "last_push": last_push,
            "acknowledged": acknowledged,
            "panic": panic,
        }

    def panic_alert(src: str) -> Alert:
        return Alert(AlertClass.WELFARE, src, "panic", Severity.CRITICAL, src, T0)

    old = {
        "open": {
            "welfare:binary_sensor.p:panic": entry(
                panic_alert("binary_sensor.p"), False, True, T0.isoformat()
            ),
            "welfare:binary_sensor.q:panic": entry(
                panic_alert("binary_sensor.q"), True, True, T0.isoformat()
            ),
            "welfare:house:inactivity": entry(_house(Severity.LOW), False, False, None),
        }
    }
    r = AlertRouter.from_dict(old, RouterConfig())
    pub = {p["key"]: p for p in r.published()}
    assert set(pub) == {"welfare:binary_sensor.p:panic", "welfare:house:inactivity"}
    pid = f"welfare:binary_sensor.p:panic@{T0.isoformat()}"
    assert pub["welfare:binary_sensor.p:panic"]["id"] == pid
    assert pub["welfare:binary_sensor.p:panic"]["group"] == "attention"
    assert pub["welfare:house:inactivity"]["group"] == "information"
