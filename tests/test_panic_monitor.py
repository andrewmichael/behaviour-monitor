"""Tests for PanicMonitor — panic button state machine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.behaviour_monitor.panic_monitor import PanicMonitor

T0 = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
FIVE = timedelta(minutes=5)


class TestPress:
    def test_first_press_returns_true(self) -> None:
        m = PanicMonitor()
        assert m.press("binary_sensor.sos", T0) is True
        assert m.is_active("binary_sensor.sos") is True

    def test_repeat_press_returns_false_and_keeps_since(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.sos", T0)
        assert m.press("binary_sensor.sos", T0 + timedelta(seconds=30)) is False
        assert m.active_since("binary_sensor.sos") == T0

    def test_press_after_release_is_new(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.sos", T0)
        m.release("binary_sensor.sos")
        assert m.press("binary_sensor.sos", T0 + FIVE) is True
        assert m.active_since("binary_sensor.sos") == T0 + FIVE

    def test_active_since_none_when_inactive(self) -> None:
        assert PanicMonitor().active_since("binary_sensor.sos") is None


class TestRelease:
    def test_release_clears_entity(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.sos", T0)
        m.release("binary_sensor.sos")
        assert m.is_active("binary_sensor.sos") is False
        assert m.active() == []

    def test_release_clears_acknowledgement(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.sos", T0)
        m.acknowledge(T0)
        m.release("binary_sensor.sos")
        m.press("binary_sensor.sos", T0 + FIVE)
        assert m.unacknowledged() == ["binary_sensor.sos"]

    def test_release_unknown_is_noop(self) -> None:
        PanicMonitor().release("binary_sensor.nope")


class TestAcknowledge:
    def test_acknowledge_all(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.press("binary_sensor.b", T0)
        assert sorted(m.acknowledge(T0)) == ["binary_sensor.a", "binary_sensor.b"]
        assert m.unacknowledged() == []
        assert [acked for _, _, acked in m.active()] == [True, True]

    def test_acknowledge_one(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.press("binary_sensor.b", T0)
        assert m.acknowledge(T0, "binary_sensor.a") == ["binary_sensor.a"]
        assert m.unacknowledged() == ["binary_sensor.b"]

    def test_acknowledge_returns_only_newly_acked(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.acknowledge(T0)
        assert m.acknowledge(T0 + FIVE) == []

    def test_acknowledge_unknown_entity_returns_empty(self) -> None:
        m = PanicMonitor()
        assert m.acknowledge(T0, "binary_sensor.nope") == []

    def test_acknowledged_entity_stays_active(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.acknowledge(T0)
        assert m.is_active("binary_sensor.a") is True


class TestDue:
    def test_not_due_before_interval(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        assert m.due(T0 + timedelta(minutes=4, seconds=59), FIVE) == []

    def test_due_at_exact_interval(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        assert m.due(T0 + FIVE, FIVE) == ["binary_sensor.a"]

    def test_due_stamps_only_returned(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.press("binary_sensor.b", T0 + timedelta(minutes=3))
        assert m.due(T0 + FIVE, FIVE) == ["binary_sensor.a"]
        # a was stamped at T0+5, b still at T0+3
        assert m.due(T0 + timedelta(minutes=8), FIVE) == ["binary_sensor.b"]
        assert m.due(T0 + timedelta(minutes=10), FIVE) == ["binary_sensor.a"]

    def test_acknowledged_never_due(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.acknowledge(T0)
        assert m.due(T0 + timedelta(hours=1), FIVE) == []

    def test_released_never_due(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.release("binary_sensor.a")
        assert m.due(T0 + timedelta(hours=1), FIVE) == []


class TestActiveOrdering:
    def test_active_ordered_by_since(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.b", T0 + FIVE)
        m.press("binary_sensor.a", T0)
        assert [e for e, _, _ in m.active()] == ["binary_sensor.a", "binary_sensor.b"]


class TestSerialization:
    def test_round_trip(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.press("binary_sensor.b", T0 + FIVE)
        m.acknowledge(T0 + FIVE, "binary_sensor.a")
        m.due(T0 + timedelta(minutes=10), FIVE)  # stamps b
        restored = PanicMonitor.from_dict(m.to_dict())
        assert restored.active() == m.active()
        assert restored.unacknowledged() == ["binary_sensor.b"]
        assert restored.due(T0 + timedelta(minutes=14), FIVE) == []
        assert restored.due(T0 + timedelta(minutes=15), FIVE) == ["binary_sensor.b"]

    def test_from_dict_drops_malformed(self) -> None:
        data = {
            "binary_sensor.ok": {
                "active_since": T0.isoformat(),
                "last_notified": T0.isoformat(),
                "acknowledged": False,
            },
            "binary_sensor.bad": {
                "active_since": "not-a-date",
                "last_notified": T0.isoformat(),
                "acknowledged": False,
            },
            "binary_sensor.missing": {"acknowledged": True},
        }
        m = PanicMonitor.from_dict(data)
        assert [e for e, _, _ in m.active()] == ["binary_sensor.ok"]

    def test_from_dict_empty(self) -> None:
        assert PanicMonitor.from_dict({}).active() == []
        assert PanicMonitor.from_dict(None).active() == []  # type: ignore[arg-type]

    def test_from_dict_rejects_non_dict_payload(self) -> None:
        assert PanicMonitor.from_dict(["nonsense"]).active() == []  # type: ignore[arg-type]
        assert PanicMonitor.from_dict({"x": "bad"}).active() == []


H24 = timedelta(hours=24)
D30 = timedelta(days=30)


class TestDeviceLiveness:
    def test_update_and_status(self) -> None:
        m = PanicMonitor()
        m.update_device(
            "binary_sensor.sos", available=True, last_reported=T0, battery=87.0
        )
        s = m.device_status("binary_sensor.sos")
        assert s == {
            "available": True,
            "last_reported": T0.isoformat(),
            "battery": 87.0,
            "last_test": None,
        }
        assert m.known_devices() == ["binary_sensor.sos"]

    def test_status_unknown_device(self) -> None:
        assert PanicMonitor().device_status("binary_sensor.nope") == {
            "available": False,
            "last_reported": None,
            "battery": None,
            "last_test": None,
        }

    def test_test_window_and_record(self) -> None:
        m = PanicMonitor()
        m.update_device(
            "binary_sensor.sos", available=True, last_reported=T0, battery=None
        )
        assert m.open_test_window(T0, T0 + timedelta(seconds=120)) == [
            "binary_sensor.sos"
        ]
        assert (
            m.in_test_window("binary_sensor.sos", T0 + timedelta(seconds=119)) is True
        )
        assert (
            m.in_test_window("binary_sensor.sos", T0 + timedelta(seconds=120)) is False
        )
        m.record_test("binary_sensor.sos", T0 + timedelta(seconds=30))
        assert (
            m.device_status("binary_sensor.sos")["last_test"]
            == (T0 + timedelta(seconds=30)).isoformat()
        )
        assert (
            m.in_test_window("binary_sensor.sos", T0 + timedelta(seconds=31)) is False
        )
        # a test press never activates the panic
        assert m.is_active("binary_sensor.sos") is False

    def test_open_window_for_one_or_unknown(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=T0, battery=None)
        m.update_device("b", available=True, last_reported=T0, battery=None)
        assert m.open_test_window(T0, T0 + FIVE, "a") == ["a"]
        assert m.in_test_window("b", T0) is False
        assert m.open_test_window(T0, T0 + FIVE, "zzz") == []

    def test_device_alerts_unavailable(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=False, last_reported=T0, battery=None)
        alerts = m.device_alerts(T0, None, None, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "unavailable", "high")]

    def test_device_alerts_heartbeat(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=T0, battery=None)
        assert m.device_alerts(T0 + H24 - timedelta(seconds=1), H24, None, 20) == []
        alerts = m.device_alerts(T0 + H24, H24, None, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "heartbeat", "high")]
        assert "24h" in alerts[0][3]

    def test_device_alerts_no_report_ever_with_heartbeat(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=None, battery=None)
        alerts = m.device_alerts(T0, H24, None, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "heartbeat", "high")]
        assert "never" in alerts[0][3]

    def test_device_alerts_battery(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=T0, battery=20)
        alerts = m.device_alerts(T0, None, None, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "battery", "medium")]
        m.update_device("a", available=True, last_reported=T0, battery=21)
        assert m.device_alerts(T0, None, None, 20) == []

    def test_device_alerts_test_reminder(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=T0, battery=None)
        alerts = m.device_alerts(T0, None, D30, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "test_reminder", "low")]
        assert "never" in alerts[0][3]
        m.record_test("a", T0)
        assert m.device_alerts(T0 + D30 - timedelta(seconds=1), None, D30, 20) == []
        assert [k for _, k, _, _ in m.device_alerts(T0 + D30, None, D30, 20)] == [
            "test_reminder"
        ]

    def test_disabled_checks(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=None, battery=None)
        assert m.device_alerts(T0 + timedelta(days=400), None, None, 20) == []

    def test_multiple_conditions_ordered(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=False, last_reported=None, battery=5)
        kinds = [k for _, k, _, _ in m.device_alerts(T0, H24, D30, 20)]
        assert kinds == ["unavailable", "heartbeat", "battery", "test_reminder"]


class TestSerializationV2:
    def test_round_trip_with_devices(self) -> None:
        m = PanicMonitor()
        m.press("a", T0)
        m.update_device("a", available=True, last_reported=T0, battery=50)
        m.record_test("a", T0 - FIVE)
        m.update_device("b", available=False, last_reported=None, battery=None)
        d = m.to_dict()
        assert set(d) == {"active", "devices"}
        r = PanicMonitor.from_dict(d)
        assert r.active() == m.active()
        assert r.device_status("a") == m.device_status("a")
        assert r.device_status("b")["available"] is False
        # test window is not persisted
        assert r.in_test_window("a", T0) is False

    def test_legacy_flat_shape(self) -> None:
        legacy = {
            "a": {
                "active_since": T0.isoformat(),
                "last_notified": T0.isoformat(),
                "acknowledged": True,
            }
        }
        r = PanicMonitor.from_dict(legacy)
        assert [e for e, _, acked in r.active()] == ["a"]
        assert r.active()[0][2] is True
        assert r.known_devices() == []

    def test_malformed_devices_dropped(self) -> None:
        r = PanicMonitor.from_dict(
            {
                "active": {},
                "devices": {"a": "bad", "b": {"last_test": "nope", "available": True}},
            }
        )
        assert r.known_devices() == ["b"]
        assert r.device_status("b")["last_test"] is None
