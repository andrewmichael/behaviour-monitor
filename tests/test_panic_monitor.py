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
