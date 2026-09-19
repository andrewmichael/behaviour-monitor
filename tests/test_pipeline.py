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
    EXCURSION,
    ActivityEvent,
    ActivityPipeline,
    PipelineConfig,
    PipelineEvent,
    classify_open_duration,
    replay,
)

T0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _ev(
    eid: str, role: EntityRole, old: str | None, new: str, seconds: float
) -> PipelineEvent:
    return PipelineEvent(eid, role, old, new, _at(seconds))


def _run(
    pipeline: ActivityPipeline, events: list[PipelineEvent]
) -> list[ActivityEvent]:
    out: list[ActivityEvent] = []
    for ev in events:
        out.extend(pipeline.submit(ev))
    return out


@pytest.fixture
def cfg() -> PipelineConfig:
    return PipelineConfig()


class TestDefaults:
    def test_config_defaults(self, cfg: PipelineConfig) -> None:
        assert (
            cfg.motion_debounce_seconds,
            cfg.door_debounce_seconds,
            cfg.retrigger_collapse_seconds,
        ) == (120, 60, 5)
        assert (
            cfg.excursion_window_seconds,
            cfg.door_open_extended_seconds,
            cfg.door_open_prolonged_seconds,
        ) == (60, 15, 120)

    def test_activity_event_defaults(self) -> None:
        ev = ActivityEvent("a.b", EntityRole.OTHER, T0)
        assert (ev.kind, ev.state, ev.entities, ev.duration_seconds) == (
            ACTIVATION,
            "on",
            (),
            None,
        )


class TestPassThrough:
    @pytest.mark.parametrize("role", [EntityRole.APPLIANCE, EntityRole.OTHER])
    def test_every_change_counts_with_raw_state(
        self, cfg: PipelineConfig, role: EntityRole
    ) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("switch.k", role, "off", "on", 0),
                _ev("switch.k", role, "on", "off", 1),
            ],
        )
        assert [(e.kind, e.state) for e in out] == [
            (ACTIVATION, "on"),
            (ACTIVATION, "off"),
        ]

    def test_numeric_motion_role_passes_through(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("sensor.lux", EntityRole.MOTION_KITCHEN, "1", "2", 0),
                _ev("sensor.lux", EntityRole.MOTION_KITCHEN, "2", "3", 1),
            ],
        )
        assert [e.state for e in out] == ["2", "3"]

    @pytest.mark.parametrize("state", ["unavailable", "unknown"])
    def test_unavailable_emits_nothing(self, cfg: PipelineConfig, state: str) -> None:
        p = ActivityPipeline(cfg)
        assert _run(p, [_ev("switch.k", EntityRole.APPLIANCE, "on", state, 0)]) == []


class TestRisingEdgeDebounce:
    def test_motion_counts_rising_edge_only(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
                _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
            ],
        )
        assert (
            len(out) == 1
            and out[0].timestamp == _at(0)
            and out[0].role is EntityRole.MOTION_LIVING
        )

    def test_first_sighting_on_counts(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert (
            len(_run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, None, "on", 0)])) == 1
        )

    def test_on_to_on_is_not_an_edge(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "on", "on", 0)]) == []

    def test_motion_debounce_120(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 0),
                _ev("b.pir", EntityRole.MOTION_BATHROOM, "on", "off", 30),
                _ev(
                    "b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 119
                ),  # inside the window: dropped
                _ev("b.pir", EntityRole.MOTION_BATHROOM, "on", "off", 125),
                _ev(
                    "b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 130
                ),  # 130 s after the last counted edge
            ],
        )
        assert [e.timestamp for e in out] == [_at(0), _at(130)]

    def test_exactly_the_window_counts(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 0),
                _ev("b.pir", EntityRole.MOTION_BATHROOM, "on", "off", 30),
                _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 120),
            ],
        )
        assert [e.timestamp for e in out] == [_at(0), _at(120)]

    def test_door_debounce_60(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 20),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 59),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 65),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 90),
            ],
        )
        assert [e.timestamp for e in out] == [_at(0), _at(90)]

    def test_debounce_is_per_entity(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("b.a", EntityRole.MOTION_LIVING, "off", "on", 0),
                _ev("b.b", EntityRole.MOTION_KITCHEN, "off", "on", 10),
            ],
        )
        assert [e.entity_id for e in out] == ["b.a", "b.b"]

    def test_zero_window_counts_every_edge(self) -> None:
        p = ActivityPipeline(
            PipelineConfig(motion_debounce_seconds=0, retrigger_collapse_seconds=0)
        )
        out = _run(
            p,
            [
                _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
                _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
                _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 20),
            ],
        )
        assert len(out) == 2

    def test_unavailable_resets_edge_tracking(self) -> None:
        p = ActivityPipeline(
            PipelineConfig(motion_debounce_seconds=0, retrigger_collapse_seconds=0)
        )
        out = _run(
            p,
            [
                _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
                _ev("b.pir", EntityRole.MOTION_LIVING, "on", "unavailable", 100),
                _ev(
                    "b.pir", EntityRole.MOTION_LIVING, "unavailable", "on", 200
                ),  # on after dropout is a rising edge
            ],
        )
        assert [e.timestamp for e in out] == [_at(0), _at(200)]

    def test_flush_returns_nothing_when_idle(self, cfg: PipelineConfig) -> None:
        assert ActivityPipeline(cfg).flush(_at(0)) == []


class TestRetriggerCollapse:
    def test_pair_inside_window_is_discarded(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0))
        out = _run(
            p,
            [
                _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
                _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
                _ev(
                    "b.pir", EntityRole.MOTION_LIVING, "off", "on", 10.023
                ),  # 23 ms retrigger
                _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 30),
                _ev(
                    "b.pir", EntityRole.MOTION_LIVING, "off", "on", 40
                ),  # 10 s later: real edge
            ],
        )
        assert [e.timestamp for e in out] == [_at(0), _at(40)]

    def test_pair_outside_window_is_two_edges(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0))
        out = _run(
            p,
            [
                _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
                _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
                _ev(
                    "b.pir", EntityRole.MOTION_LIVING, "off", "on", 15
                ),  # exactly the window: not collapsed
            ],
        )
        assert [e.timestamp for e in out] == [_at(0), _at(15)]

    def test_collapse_zero_disables(self) -> None:
        p = ActivityPipeline(
            PipelineConfig(motion_debounce_seconds=0, retrigger_collapse_seconds=0)
        )
        out = _run(
            p,
            [
                _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
                _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
                _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 10.5),
            ],
        )
        assert len(out) == 2

    def test_collapsed_off_does_not_close_open_interval(
        self, cfg: PipelineConfig
    ) -> None:
        p = ActivityPipeline(cfg)
        _run(
            p,
            [
                _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 20),
                _ev(
                    "b.door", EntityRole.DOOR_INTERIOR, "off", "on", 21
                ),  # bounce: still open
                _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 50),
            ],
        )
        p.flush(_at(60))
        assert p.door_status("b.door") == {
            "last_open_seconds": 50.0,
            "last_open_class": DOOR_OPEN_EXTENDED,
        }


class TestOpenDuration:
    @pytest.mark.parametrize(
        ("seconds", "cls"),
        [
            (0.0, DOOR_OPEN_BRIEF),
            (14.999, DOOR_OPEN_BRIEF),
            (15.0, DOOR_OPEN_EXTENDED),
            (119.9, DOOR_OPEN_EXTENDED),
            (120.0, DOOR_OPEN_PROLONGED),
            (4000.0, DOOR_OPEN_PROLONGED),
        ],
    )
    def test_classify(self, seconds: float, cls: str) -> None:
        assert classify_open_duration(seconds, 15, 120) == cls

    def test_status_none_until_first_close(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert p.door_status("b.door") == {
            "last_open_seconds": None,
            "last_open_class": None,
        }
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0)])
        assert p.door_status("b.door")["last_open_seconds"] is None

    def test_off_confirmed_by_flush_after_collapse_window(
        self, cfg: PipelineConfig
    ) -> None:
        p = ActivityPipeline(cfg)
        _run(
            p,
            [
                _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 8),
            ],
        )
        p.flush(_at(12))  # 4 s after the off: still pending
        assert p.door_status("b.door")["last_open_seconds"] is None
        p.flush(_at(13))  # 5 s: confirmed
        assert p.door_status("b.door") == {
            "last_open_seconds": 8.0,
            "last_open_class": DOOR_OPEN_BRIEF,
        }

    def test_force_flush_confirms_immediately(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(
            p,
            [
                _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 200),
            ],
        )
        p.flush(_at(200), force=True)
        assert p.door_status("b.door")["last_open_class"] == DOOR_OPEN_PROLONGED

    def test_next_on_confirms_pending_off(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(
            p,
            [
                _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 10),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 100),
            ],
        )
        assert p.door_status("b.door")["last_open_seconds"] == 10.0

    def test_debounced_reopen_starts_new_interval(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
                _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 5),
                _ev(
                    "b.door", EntityRole.DOOR_INTERIOR, "off", "on", 30
                ),  # debounced (< 60 s), but it IS the new last_on
                _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 40),
            ],
        )
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
        _run(
            p,
            [
                _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
                _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 30),
            ],
        )
        p.flush(_at(100))
        assert p.door_status("b.pir")["last_open_seconds"] is None

    def test_seed_door_status(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        p.seed_door_status(
            {"b.door": {"last_open_seconds": 7.5, "last_open_class": DOOR_OPEN_BRIEF}}
        )
        assert p.door_status("b.door") == {
            "last_open_seconds": 7.5,
            "last_open_class": DOOR_OPEN_BRIEF,
        }


class TestExcursions:
    def test_two_doors_inside_window_is_one_excursion(
        self, cfg: PipelineConfig
    ) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
                _ev("b.back", EntityRole.DOOR_EXTERIOR, "on", "off", 6),
                _ev("b.side", EntityRole.DOOR_EXTERIOR, "off", "on", 45),
            ],
        )
        assert out == []
        out = p.flush(_at(59))
        assert out == []
        out = p.flush(_at(60))
        assert len(out) == 1
        ex = out[0]
        assert (ex.kind, ex.entity_id, ex.role, ex.timestamp) == (
            EXCURSION,
            "b.back",
            EntityRole.DOOR_EXTERIOR,
            _at(0),
        )
        assert ex.entities == ("b.back", "b.side")
        assert ex.duration_seconds == 45.0
        assert ex.state == "on"

    def test_single_door_excursion_has_zero_span(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0)])
        out = p.flush(_at(0), force=True)
        assert (
            len(out) == 1
            and out[0].entities == ("b.back",)
            and out[0].duration_seconds == 0.0
        )

    def test_activation_after_window_closes_and_starts_new(
        self, cfg: PipelineConfig
    ) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
                _ev("b.side", EntityRole.DOOR_EXTERIOR, "off", "on", 200),
            ],
        )
        assert len(out) == 1 and out[0].entities == ("b.back",)
        out = p.flush(_at(260))
        assert (
            len(out) == 1
            and out[0].entities == ("b.side",)
            and out[0].timestamp == _at(200)
        )

    def test_debounced_exterior_edge_does_not_join(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(
            p,
            [
                _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
                _ev("b.back", EntityRole.DOOR_EXTERIOR, "on", "off", 10),
                _ev(
                    "b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 30
                ),  # < 60 s door debounce
            ],
        )
        out = p.flush(_at(100))
        assert out[0].entities == ("b.back",)

    def test_interior_doors_never_group(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(
            p,
            [
                _ev("b.hall", EntityRole.DOOR_INTERIOR, "off", "on", 0),
                _ev("b.lounge", EntityRole.DOOR_INTERIOR, "off", "on", 5),
            ],
        )
        assert [e.kind for e in out] == [ACTIVATION, ACTIVATION]

    def test_window_zero_disables(self) -> None:
        p = ActivityPipeline(PipelineConfig(excursion_window_seconds=0))
        out = _run(p, [_ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0)])
        assert len(out) == 1 and out[0].kind == ACTIVATION

    def test_idle_flush_after_excursion_emitted_is_empty(
        self, cfg: PipelineConfig
    ) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0)])
        assert len(p.flush(_at(0), force=True)) == 1
        assert p.flush(_at(1000)) == []


class TestReplay:
    def test_sorts_flushes_and_reports_doors(self, cfg: PipelineConfig) -> None:
        events = [
            _ev("b.side", EntityRole.DOOR_EXTERIOR, "off", "on", 40),
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "on", "off", 8),
            _ev("b.pir", EntityRole.MOTION_KITCHEN, "off", "on", 500),
            _ev("b.hall", EntityRole.DOOR_INTERIOR, "off", "on", 600),
            _ev("b.hall", EntityRole.DOOR_INTERIOR, "on", "off", 630),
        ]
        out, doors = replay(events, cfg)
        assert [(e.kind, e.entity_id, e.timestamp) for e in out] == [
            (ACTIVATION, "b.pir", _at(500)),
            (EXCURSION, "b.back", _at(0)),
            (ACTIVATION, "b.hall", _at(600)),
        ]
        ex = next(e for e in out if e.kind == EXCURSION)
        assert ex.entities == ("b.back", "b.side")
        assert set(doors) == {"b.back", "b.side", "b.hall"}
        assert doors["b.back"] == {
            "last_open_seconds": 8.0,
            "last_open_class": DOOR_OPEN_BRIEF,
        }
        assert doors["b.hall"] == {
            "last_open_seconds": 30.0,
            "last_open_class": DOOR_OPEN_EXTENDED,
        }
        assert doors["b.side"] == {"last_open_seconds": None, "last_open_class": None}

    def test_empty(self, cfg: PipelineConfig) -> None:
        assert replay([], cfg) == ([], {})

    def test_final_force_flush_emits_open_excursion_and_pending_off(
        self, cfg: PipelineConfig
    ) -> None:
        events = [
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "on", "off", 3),
        ]
        out, doors = replay(events, cfg)
        assert len(out) == 1 and out[0].kind == EXCURSION
        assert doors["b.back"]["last_open_seconds"] == 3.0


class TestNoteState:
    """``note_state`` resynchronises edge state for events ``submit`` never saw
    (burst-dropped events), without emitting, counting or joining excursions.
    """

    def test_returns_none(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert p.note_state("b.pir", EntityRole.MOTION_LIVING, "on", _at(0)) is None

    def test_on_sets_is_on_and_last_on_without_counting(
        self, cfg: PipelineConfig
    ) -> None:
        p = ActivityPipeline(cfg)
        p.note_state("b.door", EntityRole.DOOR_INTERIOR, "on", _at(0))
        st = p._states["b.door"]
        assert st.is_on is True
        assert st.last_on == _at(0)
        assert st.last_counted is None

    def test_on_when_already_on_is_a_no_op(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0)])
        p.note_state("b.door", EntityRole.DOOR_INTERIOR, "on", _at(5))
        assert p._states["b.door"].last_on == _at(0)

    def test_off_when_on_holds_pending_off_like_off_edge(
        self, cfg: PipelineConfig
    ) -> None:
        p = ActivityPipeline(cfg)
        p.note_state("b.door", EntityRole.DOOR_INTERIOR, "on", _at(0))
        p.note_state("b.door", EntityRole.DOOR_INTERIOR, "off", _at(10))
        st = p._states["b.door"]
        assert st.is_on is False
        assert st.pending_off == _at(10)
        assert (
            st.last_open_seconds is None
        )  # held for retrigger collapse, not confirmed yet

    def test_off_confirms_immediately_when_collapse_disabled(self) -> None:
        p = ActivityPipeline(PipelineConfig(retrigger_collapse_seconds=0))
        p.note_state("b.door", EntityRole.DOOR_INTERIOR, "on", _at(0))
        p.note_state("b.door", EntityRole.DOOR_INTERIOR, "off", _at(10))
        assert p.door_status("b.door") == {
            "last_open_seconds": 10.0,
            "last_open_class": DOOR_OPEN_BRIEF,
        }

    def test_off_when_not_on_is_a_no_op(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        p.note_state("b.door", EntityRole.DOOR_INTERIOR, "off", _at(0))
        st = p._states["b.door"]
        assert st.is_on is None  # never seen on: untouched, not forced to False
        assert st.pending_off is None

    def test_dropout_clears_is_on_and_pending_off(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0)])
        p.note_state("b.door", EntityRole.DOOR_INTERIOR, "unavailable", _at(5))
        st = p._states["b.door"]
        assert st.is_on is None
        assert st.pending_off is None

    def test_non_edge_role_only_sets_role(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        p.note_state("switch.k", EntityRole.APPLIANCE, "on", _at(0))
        st = p._states["switch.k"]
        assert st.role is EntityRole.APPLIANCE
        assert st.is_on is None
        assert st.last_on is None

    def test_numeric_state_only_sets_role(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        p.note_state("sensor.lux", EntityRole.MOTION_KITCHEN, "42", _at(0))
        st = p._states["sensor.lux"]
        assert st.role is EntityRole.MOTION_KITCHEN
        assert st.is_on is None

    def test_never_touches_last_counted(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0)])
        before = p._states["b.pir"].last_counted
        p.note_state("b.pir", EntityRole.MOTION_LIVING, "off", _at(60))
        p.note_state("b.pir", EntityRole.MOTION_LIVING, "on", _at(65))
        assert p._states["b.pir"].last_counted == before

    def test_does_not_join_excursion(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        p.note_state("b.back", EntityRole.DOOR_EXTERIOR, "on", _at(0))
        assert p._excursion is None

    def test_resyncs_burst_dropped_off_so_next_rising_edge_counts(self) -> None:
        """Important-1 regression: a dropped off must not leave ``is_on`` stale."""
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0))
        out0 = _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0)])
        assert len(out0) == 1
        # off @60 dropped by the burst gate: only note_state ever sees it.
        p.note_state("b.pir", EntityRole.MOTION_LIVING, "off", _at(60))
        out1 = _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 200)])
        assert len(out1) == 1
        out2 = _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 260)])
        assert out2 == []
        out3 = _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 400)])
        assert len(out3) == 1

    def test_door_open_duration_measured_from_noted_on_edge(self) -> None:
        """A door role's ``last_on`` must resync too, or the open interval is
        measured from the stale pre-dropout edge."""
        p = ActivityPipeline(PipelineConfig(retrigger_collapse_seconds=0))
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0)])
        # off @60 dropped by the burst gate
        p.note_state("b.door", EntityRole.DOOR_INTERIOR, "off", _at(60))
        # on @200: the real reopening
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 200)])
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 210)])
        assert p.door_status("b.door") == {
            "last_open_seconds": 10.0,
            "last_open_class": DOOR_OPEN_BRIEF,
        }
