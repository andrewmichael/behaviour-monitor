"""Tests for the activity pipeline: pass-through, debounce, collapse, open duration, excursions, replay."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.behaviour_monitor.const import EntityRole
from custom_components.behaviour_monitor.pipeline import (
    ACTIVATION,
    ActivityEvent,
    ActivityPipeline,
    PipelineConfig,
    PipelineEvent,
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
