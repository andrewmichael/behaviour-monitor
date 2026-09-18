"""Tests for EventGate — start-up grace and same-second burst discard."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.behaviour_monitor.event_gate import EventGate, GatedEvent

T0 = datetime(2026, 9, 18, 12, 0, 0)


def _sub(
    g: EventGate, eid: str, t: datetime, old: str | None = "off", new: str = "on"
) -> bool:
    return g.submit(eid, old, new, t)


class TestGrace:
    def test_unarmed_has_no_grace(self) -> None:
        g = EventGate(90, 3)
        assert g.in_grace(T0) is False
        assert _sub(g, "a", T0) is True

    def test_events_dropped_during_grace(self) -> None:
        g = EventGate(90, 3)
        g.arm(T0)
        assert g.in_grace(T0 + timedelta(seconds=89)) is True
        assert _sub(g, "a", T0 + timedelta(seconds=10)) is False
        assert g.pending == 0

    def test_events_accepted_after_grace(self) -> None:
        g = EventGate(90, 3)
        g.arm(T0)
        assert _sub(g, "a", T0 + timedelta(seconds=90)) is True
        assert g.pending == 1

    def test_zero_grace_disables(self) -> None:
        g = EventGate(0, 3)
        g.arm(T0)
        assert _sub(g, "a", T0) is True


class TestBurst:
    def test_flush_returns_only_completed_seconds(self) -> None:
        g = EventGate(0, 3)
        _sub(g, "a", T0)
        _sub(g, "b", T0 + timedelta(seconds=1))
        out = g.flush(T0 + timedelta(seconds=1, milliseconds=500))
        assert [e.entity_id for e in out] == ["a"]
        assert g.pending == 1

    def test_force_flushes_current_second(self) -> None:
        g = EventGate(0, 3)
        _sub(g, "a", T0)
        out = g.flush(T0, force=True)
        assert [e.entity_id for e in out] == ["a"]
        assert g.pending == 0

    def test_burst_at_threshold_dropped(self) -> None:
        g = EventGate(0, 3)
        for eid in ("a", "b", "c"):
            _sub(g, eid, T0)
        assert g.flush(T0 + timedelta(seconds=2)) == []
        assert g.dropped_bursts == 1

    def test_below_threshold_kept(self) -> None:
        g = EventGate(0, 3)
        _sub(g, "a", T0)
        _sub(g, "b", T0 + timedelta(milliseconds=300))
        out = g.flush(T0 + timedelta(seconds=2))
        assert [e.entity_id for e in out] == ["a", "b"]
        assert g.dropped_bursts == 0

    def test_same_entity_repeated_is_one_distinct(self) -> None:
        g = EventGate(0, 3)
        for _ in range(5):
            _sub(g, "a", T0, "off", "on")
        assert len(g.flush(T0 + timedelta(seconds=2))) == 5

    def test_threshold_zero_disables(self) -> None:
        g = EventGate(0, 0)
        for eid in ("a", "b", "c", "d"):
            _sub(g, eid, T0)
        assert len(g.flush(T0 + timedelta(seconds=2))) == 4

    def test_events_preserve_order_and_fields(self) -> None:
        g = EventGate(0, 3)
        _sub(g, "a", T0, None, "on")
        _sub(g, "a", T0 + timedelta(milliseconds=10), "on", "off")
        out = g.flush(T0 + timedelta(seconds=2))
        assert out == [
            GatedEvent("a", None, "on", T0),
            GatedEvent("a", "on", "off", T0 + timedelta(milliseconds=10)),
        ]

    def test_buckets_independent(self) -> None:
        g = EventGate(0, 3)
        for eid in ("a", "b", "c"):
            _sub(g, eid, T0)  # burst second
        _sub(g, "d", T0 + timedelta(seconds=1))  # clean second
        out = g.flush(T0 + timedelta(seconds=3))
        assert [e.entity_id for e in out] == ["d"]
