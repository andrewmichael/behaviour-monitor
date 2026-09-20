"""End-to-end expectations on synthetic fixtures via the replay runner."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from replay import run_fixture, run_fixture_full  # noqa: E402

from tests.core import synth

OPTS = {"learning_days": 14}


def _run(tmp_path: Path, events, name: str = "fx"):
    path = tmp_path / f"{name}.jsonl"
    synth.write_fixture(path, events, options=OPTS)
    return run_fixture(path, poll_minutes=5)


def _pushes(tl):
    return [(t, a.alert) for t, a in tl if a.action == "push"]


def test_normal_days_raise_no_welfare_push(tmp_path):
    tl = _run(tmp_path, synth.normal_days(days=28))
    assert [a.kind for _, a in _pushes(tl) if a.cls.value == "welfare"] == []


def test_panic_press_pushes_critical_once_then_repeats(tmp_path):
    tl = _run(tmp_path, synth.panic_press())
    p = [(t, a) for t, a in _pushes(tl) if a.kind == "panic"]
    assert p and p[0][1].severity.value == "critical"
    assert p[0][0] == synth.START + timedelta(days=21, hours=14)
    assert len(p) >= 2  # repeats until acknowledged


def test_silent_kitchen_is_device_health_not_welfare(tmp_path):
    tl = _run(tmp_path, synth.silent_kitchen())
    repairs = [a.alert for _, a in tl if a.action == "repair_create"]
    assert any(
        a.kind == "silent" and a.source == "binary_sensor.kitchen_motion"
        for a in repairs
    )
    assert [a for _, a in _pushes(tl) if a.kind == "inactivity"] == []


def test_sitewide_dropout_is_one_health_alert(tmp_path):
    tl = _run(tmp_path, synth.sitewide_dropout())
    created = [a.alert for _, a in tl if a.action == "repair_create"]
    assert [a.kind for a in created].count("dropout") == 1
    assert not any(a.kind == "unavailable" for a in created)


def test_chain_stall_logs_missing_kitchen_and_silence_escalates(tmp_path):
    tl = _run(tmp_path, synth.chain_stall_at_kettle())
    logs = [a.alert for _, a in tl if a.action == "log"]
    assert any(
        a.kind == "chain_stall" and a.details.get("missing") == "Kitchen" for a in logs
    )
    day = synth.START + timedelta(days=21)
    pushes = [
        (t, a)
        for t, a in _pushes(tl)
        if a.kind == "inactivity" and t.date() == day.date()
    ]
    assert pushes, "daytime silence after the stall should raise welfare"
    assert pushes[0][0] < day + timedelta(hours=12)


def test_kettle_absent_three_days_becomes_routine_notes(tmp_path):
    tl = _run(tmp_path, synth.kettle_absent_days())
    logs = [
        (t, a.alert)
        for t, a in tl
        if a.action == "log"
        and a.alert.kind == "routine_missed"
        and a.alert.source == "sensor.kettle_power"
    ]
    assert {t.date() for t, _ in logs} >= {
        (synth.START + timedelta(days=21 + i)).date() for i in range(3)
    }
    assert all(a.details["hour"] == 7 for _, a in logs)


def test_gradual_lengthening_reports_drift_within_two_weeks(tmp_path):
    path = tmp_path / "lengthen.jsonl"
    synth.write_fixture(path, synth.chain_lengthening(), options=OPTS)
    tl, engine, last_poll = run_fixture_full(path, poll_minutes=5)
    drifts = [
        (t, a.alert)
        for t, a in tl
        if a.action == "log"
        and a.alert.kind == "drift"
        and a.alert.source.startswith("chain:")
    ]
    assert drifts
    first_day = (drifts[0][0].date() - synth.START.date()).days
    assert 24 <= first_day <= 35
    open_keys = [a["key"] for a in engine.snapshot(last_poll)["welfare"]["open_alerts"]]
    assert any(
        k.startswith("welfare:chain:") and k.endswith(":timing_drift")
        for k in open_keys
    ), open_keys


def test_sudden_jump_is_reported_by_day_three_after_the_jump(tmp_path):
    tl = _run(tmp_path, synth.chain_jump(after=7, tail=10))
    drifts = [
        t
        for t, a in tl
        if a.action == "log"
        and a.alert.kind == "drift"
        and a.alert.source.startswith("chain:")
    ]
    assert drifts
    jump_day = 21 + 7
    first = (drifts[0].date() - synth.START.date()).days
    assert jump_day + 2 <= first <= jump_day + 4


@pytest.mark.parametrize(
    "builder", [synth.normal_days, synth.panic_press, synth.silent_kitchen]
)
def test_replay_cli_runs(tmp_path, builder, capsys):
    path = tmp_path / "cli.jsonl"
    synth.write_fixture(path, builder(), options=OPTS)
    from replay import main

    assert main([str(path)]) == 0
    out = capsys.readouterr().out
    if builder is synth.panic_press:
        assert "push" in out and "panic" in out
