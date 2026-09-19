"""Tests for the activity pipeline: pass-through, debounce, collapse, open duration, excursions, replay."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.behaviour_monitor.const import (
    DOOR_OPEN_BRIEF,
    DOOR_OPEN_EXTENDED,
    DOOR_OPEN_PROLONGED,
    EntityRole,
)
from custom_components.behaviour_monitor.pipeline import (
    ACTIVATION,
    ActivityEvent,
    ActivityPipeline,
    PipelineConfig,
    PipelineEvent,
    classify_open_duration,
)

T0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _ev(eid: str, role: EntityRole, old: str | None, new: str, seconds: float) -> PipelineEvent:
    return PipelineEvent(eid, role, old, new, _at(seconds))


def _run(pipeline: ActivityPipeline, events: list[PipelineEvent]) -> list[ActivityEvent]:
    out: list[ActivityEvent] = []
    for ev in events:
        out.extend(pipeline.submit(ev))
    return out


@pytest.fixture
def cfg() -> PipelineConfig:
    return PipelineConfig()


class TestDefaults:
    def test_config_defaults(self, cfg: PipelineConfig) -> None:
        assert (cfg.motion_debounce_seconds, cfg.door_debounce_seconds, cfg.retrigger_collapse_seconds) == (120, 60, 5)
        assert (cfg.excursion_window_seconds, cfg.door_open_extended_seconds, cfg.door_open_prolonged_seconds) == (60, 15, 120)

    def test_activity_event_defaults(self) -> None:
        ev = ActivityEvent("a.b", EntityRole.OTHER, T0)
        assert (ev.kind, ev.state, ev.entities, ev.duration_seconds) == (ACTIVATION, "on", (), None)


class TestPassThrough:
    @pytest.mark.parametrize("role", [EntityRole.APPLIANCE, EntityRole.OTHER])
    def test_every_change_counts_with_raw_state(self, cfg: PipelineConfig, role: EntityRole) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [_ev("switch.k", role, "off", "on", 0), _ev("switch.k", role, "on", "off", 1)])
        assert [(e.kind, e.state) for e in out] == [(ACTIVATION, "on"), (ACTIVATION, "off")]

    def test_numeric_motion_role_passes_through(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [_ev("sensor.lux", EntityRole.MOTION_KITCHEN, "1", "2", 0), _ev("sensor.lux", EntityRole.MOTION_KITCHEN, "2", "3", 1)])
        assert [e.state for e in out] == ["2", "3"]

    @pytest.mark.parametrize("state", ["unavailable", "unknown"])
    def test_unavailable_emits_nothing(self, cfg: PipelineConfig, state: str) -> None:
        p = ActivityPipeline(cfg)
        assert _run(p, [_ev("switch.k", EntityRole.APPLIANCE, "on", state, 0)]) == []


class TestRisingEdgeDebounce:
    def test_motion_counts_rising_edge_only(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
        ])
        assert len(out) == 1 and out[0].timestamp == _at(0) and out[0].role is EntityRole.MOTION_LIVING

    def test_first_sighting_on_counts(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert len(_run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, None, "on", 0)])) == 1

    def test_on_to_on_is_not_an_edge(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "on", "on", 0)]) == []

    def test_motion_debounce_120(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "on", "off", 30),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 119),  # inside the window: dropped
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "on", "off", 125),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 130),  # 130 s after the last counted edge
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(130)]

    def test_exactly_the_window_counts(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "on", "off", 30),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 120),
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(120)]

    def test_door_debounce_60(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 20),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 59),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 65),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 90),
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(90)]

    def test_debounce_is_per_entity(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.a", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.b", EntityRole.MOTION_KITCHEN, "off", "on", 10),
        ])
        assert [e.entity_id for e in out] == ["b.a", "b.b"]

    def test_zero_window_counts_every_edge(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0, retrigger_collapse_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 20),
        ])
        assert len(out) == 2

    def test_unavailable_resets_edge_tracking(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0, retrigger_collapse_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "unavailable", 100),
            _ev("b.pir", EntityRole.MOTION_LIVING, "unavailable", "on", 200),  # on after dropout is a rising edge
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(200)]

    def test_flush_returns_nothing_when_idle(self, cfg: PipelineConfig) -> None:
        assert ActivityPipeline(cfg).flush(_at(0)) == []


class TestRetriggerCollapse:
    def test_pair_inside_window_is_discarded(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 10.023),  # 23 ms retrigger
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 30),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 40),  # 10 s later: real edge
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(40)]

    def test_pair_outside_window_is_two_edges(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 15),  # exactly the window: not collapsed
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(15)]

    def test_collapse_zero_disables(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0, retrigger_collapse_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 10.5),
        ])
        assert len(out) == 2

    def test_collapsed_off_does_not_close_open_interval(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 20),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 21),   # bounce: still open
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 50),
        ])
        p.flush(_at(60))
        assert p.door_status("b.door") == {"last_open_seconds": 50.0, "last_open_class": DOOR_OPEN_EXTENDED}


class TestOpenDuration:
    @pytest.mark.parametrize(
        ("seconds", "cls"),
        [(0.0, DOOR_OPEN_BRIEF), (14.999, DOOR_OPEN_BRIEF), (15.0, DOOR_OPEN_EXTENDED), (119.9, DOOR_OPEN_EXTENDED), (120.0, DOOR_OPEN_PROLONGED), (4000.0, DOOR_OPEN_PROLONGED)],
    )
    def test_classify(self, seconds: float, cls: str) -> None:
        assert classify_open_duration(seconds, 15, 120) == cls

    def test_status_none_until_first_close(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert p.door_status("b.door") == {"last_open_seconds": None, "last_open_class": None}
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0)])
        assert p.door_status("b.door")["last_open_seconds"] is None

    def test_off_confirmed_by_flush_after_collapse_window(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0), _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 8)])
        p.flush(_at(12))  # 4 s after the off: still pending
        assert p.door_status("b.door")["last_open_seconds"] is None
        p.flush(_at(13))  # 5 s: confirmed
        assert p.door_status("b.door") == {"last_open_seconds": 8.0, "last_open_class": DOOR_OPEN_BRIEF}

    def test_force_flush_confirms_immediately(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0), _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 200)])
        p.flush(_at(200), force=True)
        assert p.door_status("b.door")["last_open_class"] == DOOR_OPEN_PROLONGED

    def test_next_on_confirms_pending_off(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 10),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 100),
        ])
        assert p.door_status("b.door")["last_open_seconds"] == 10.0

    def test_debounced_reopen_starts_new_interval(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 5),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 30),   # debounced (< 60 s), but it IS the new last_on
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 40),
        ])
        p.flush(_at(100))
        assert len(out) == 1
        assert p.door_status("b.door")["last_open_seconds"] == 10.0

    def test_open_at_start_records_nothing(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 0)])
        p.flush(_at(100))
        assert p.door_status("b.door")["last_open_seconds"] is None

    def test_motion_never_gets_open_duration(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0), _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 30)])
        p.flush(_at(100))
        assert p.door_status("b.pir")["last_open_seconds"] is None

    def test_seed_door_status(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        p.seed_door_status({"b.door": {"last_open_seconds": 7.5, "last_open_class": DOOR_OPEN_BRIEF}})
        assert p.door_status("b.door") == {"last_open_seconds": 7.5, "last_open_class": DOOR_OPEN_BRIEF}
