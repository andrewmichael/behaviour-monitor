from datetime import datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.events import (
    ActivityEvent,
    Category,
    EventKind,
    HealthEvent,
)
from custom_components.behaviour_monitor.core.normaliser import Normaliser, NormaliserConfig

T0 = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)


def _t(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _n() -> Normaliser:
    return Normaliser(NormaliserConfig())


def test_motion_rising_edge_is_presence_and_retrigger_is_merged():
    n = _n()
    ev = n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(0))
    assert [e.kind for e in ev] == [EventKind.PRESENCE]
    assert n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "off", _t(62)) == []
    # retrigger inside the 90 s window extends the burst
    assert n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(70)) == []
    assert n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "off", _t(132)) == []
    # next rise outside the window closes the old burst and opens a new one
    ev = n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(300))
    assert [e.kind for e in ev] == [EventKind.BURST_END, EventKind.PRESENCE]
    assert ev[0].duration_s == 132.0
    assert ev[0].timestamp == _t(132)


def test_flush_closes_a_burst_after_the_window():
    n = _n()
    n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(0))
    n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "off", _t(60))
    assert n.flush(_t(100)) == []
    out = n.flush(_t(151))
    assert [e.kind for e in out] == [EventKind.BURST_END]
    assert out[0].duration_s == 60.0
    assert n.flush(_t(200)) == []


def test_contact_open_close_with_duration():
    n = _n()
    ev = n.handle("binary_sensor.d", Category.CONTACT, "Hall", "off", "on", _t(0))
    assert ev[0].kind == EventKind.OPEN and ev[0].is_activity
    ev = n.handle("binary_sensor.d", Category.CONTACT, "Hall", "on", "off", _t(45))
    assert ev[0].kind == EventKind.CLOSE and ev[0].duration_s == 45.0 and not ev[0].is_activity


def test_panic_bypasses_and_release_is_recorded():
    n = _n()
    ev = n.handle("binary_sensor.p", Category.PANIC, "Hall", "off", "on", _t(0))
    assert ev[0].kind == EventKind.PANIC and ev[0].bypass is True
    ev = n.handle("binary_sensor.p", Category.PANIC, "Hall", "on", "off", _t(5))
    assert ev[0].kind == EventKind.PANIC_RELEASE and ev[0].bypass is False


def test_light_and_other():
    n = _n()
    assert n.handle("light.l", Category.LIGHT, "Lounge", "off", "on", _t(0))[0].kind == EventKind.LIGHT_ON
    assert n.handle("light.l", Category.LIGHT, "Lounge", "on", "off", _t(1))[0].kind == EventKind.LIGHT_OFF
    ev = n.handle("sensor.x", Category.OTHER, "Loft", "12", "13", _t(2))
    assert ev[0].kind == EventKind.GENERIC and ev[0].is_activity


def test_same_state_replay_emits_nothing():
    n = _n()
    assert n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "on", _t(0)) == []
    assert n.handle("sensor.x", Category.OTHER, "Loft", "12", "12", _t(0)) == []


def test_unavailable_transitions_are_health_not_activity():
    n = _n()
    ev = n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "unavailable", _t(0))
    assert ev == [HealthEvent("binary_sensor.k", Category.MOTION, "Kitchen", _t(0), available=False)]
    # coming back with state on is a restore, not the person
    ev = n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "unavailable", "on", _t(10))
    assert ev == [HealthEvent("binary_sensor.k", Category.MOTION, "Kitchen", _t(10), available=True)]
    # first ever state (old None) is also not activity
    ev = n.handle("binary_sensor.b", Category.MOTION, "Bath", None, "on", _t(20))
    assert ev == [HealthEvent("binary_sensor.b", Category.MOTION, "Bath", _t(20), available=True)]
    # repeated unavailable emits nothing
    n.handle("binary_sensor.b", Category.MOTION, "Bath", "on", "unavailable", _t(30))
    assert n.handle("binary_sensor.b", Category.MOTION, "Bath", "unavailable", "unknown", _t(31)) == []


def test_round_trip_serialisation_keeps_burst_state():
    n = _n()
    n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(0))
    n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "off", _t(60))
    n2 = Normaliser.from_dict(n.to_dict(), NormaliserConfig())
    out = n2.flush(_t(151))
    assert out and out[0].kind == EventKind.BURST_END
    assert Normaliser.from_dict({"garbage": 1}, NormaliserConfig()).flush(_t(0)) == []


def test_numeric_plug_learns_idle_and_fires_on_rise():
    n = Normaliser(NormaliserConfig(plug_min_samples=10, plug_margin_w=5.0))
    # TV on standby at ~85 W: idle should settle near 85, not 0
    prev = "0"
    for i in range(20):
        val = f"{85 + (i % 3)}"
        assert n.handle("sensor.tv", Category.PLUG, "Backroom", prev, val, _t(i)) == []
        prev = val
    assert 84.5 <= n.idle_level("sensor.tv") <= 86.0
    ev = n.handle("sensor.tv", Category.PLUG, "Backroom", prev, "120", _t(30))
    assert [e.kind for e in ev] == [EventKind.APPLIANCE_ON]
    assert n.handle("sensor.tv", Category.PLUG, "Backroom", "120", "125", _t(31)) == []
    ev = n.handle("sensor.tv", Category.PLUG, "Backroom", "125", "86", _t(90))
    assert ev[0].kind == EventKind.APPLIANCE_OFF and ev[0].duration_s == 60.0


def test_numeric_plug_before_min_samples_uses_minimum_seen():
    n = Normaliser(NormaliserConfig(plug_min_samples=10, plug_margin_w=5.0))
    assert n.handle("sensor.kettle", Category.PLUG, "Kitchen", None, "0", _t(0))  # health only
    assert n.handle("sensor.kettle", Category.PLUG, "Kitchen", "0", "0.5", _t(1)) == []
    ev = n.handle("sensor.kettle", Category.PLUG, "Kitchen", "0.5", "2800", _t(2))
    assert ev[0].kind == EventKind.APPLIANCE_ON


def test_switch_plug_uses_on_off():
    n = _n()
    assert n.handle("switch.p", Category.PLUG, "Loft", "off", "on", _t(0))[0].kind == EventKind.APPLIANCE_ON
    ev = n.handle("switch.p", Category.PLUG, "Loft", "on", "off", _t(30))
    assert ev[0].kind == EventKind.APPLIANCE_OFF and ev[0].duration_s == 30.0


def test_non_numeric_non_switch_plug_state_is_ignored():
    n = _n()
    assert n.handle("sensor.p", Category.PLUG, "Loft", "abc", "def", _t(0)) == []
