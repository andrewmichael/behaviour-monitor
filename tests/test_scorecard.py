"""Tests for scripts/scorecard.py."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import scorecard as sc  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "synthetic_normal_28d.jsonl"
UTC = timezone.utc
T0 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def _ev(t, event, group, kind, source="house", aid="a1", severity="medium"):
    return {
        "t": t,
        "action": "event",
        "event": event,
        "reason": None,
        "group": group,
        "id": aid,
        "kind": kind,
        "source": source,
        "severity": severity,
    }


def test_load_truth_reads_windows_points_and_entities(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "- {from: '2026-10-13 11:00', to: '2026-10-13 14:30', what: out}\n"
        "- {at: '2026-10-02 09:10', what: concern, note: fall}\n"
        "- {from: '2026-11-04 00:00', what: sensor_fault,"
        " entity: binary_sensor.hall}\n"
    )
    truth = sc.load_truth(p, end_default=datetime(2026, 11, 8, tzinfo=UTC))
    assert [t.what for t in truth] == ["out", "concern", "sensor_fault"]
    assert truth[0].start < truth[0].end
    assert truth[1].start == truth[1].end
    assert truth[2].entity == "binary_sensor.hall"
    assert truth[2].end == datetime(2026, 11, 8, tzinfo=UTC)


def test_welfare_alerts_are_explained_caught_or_unexplained():
    truth = [
        sc.Truth(T0 - timedelta(hours=1), T0 + timedelta(hours=2), "out"),
        sc.Truth(T0 + timedelta(days=1), T0 + timedelta(days=1, hours=3), "concern"),
    ]
    tl = [
        _ev(T0, "opened", "information", "inactivity", aid="a1"),
        _ev(
            T0 + timedelta(minutes=20), "escalated", "attention", "inactivity", aid="a1"
        ),
        _ev(
            T0 + timedelta(days=1, minutes=90),
            "opened",
            "attention",
            "inactivity",
            aid="a2",
        ),
        _ev(T0 + timedelta(days=3), "opened", "attention", "inactivity", aid="a3"),
    ]
    w = sc.score_welfare(tl, truth)
    assert w["alerts"] == 3
    assert w["explained"] == {"out": 1}
    assert w["concerns_caught"] == 1 and w["concerns"] == 1
    assert w["concern_latency_min"] == [90]
    assert [a["id"] for a in w["unexplained"]] == ["a3"]


def test_sensor_fault_caught_with_latency_and_restart_storms():
    fault = sc.Truth(
        T0, T0 + timedelta(days=2), "sensor_fault", entity="binary_sensor.hall"
    )
    missed = sc.Truth(
        T0, T0 + timedelta(days=1), "sensor_fault", entity="binary_sensor.land"
    )
    tl = [
        _ev(
            T0 + timedelta(hours=3),
            "opened",
            "health",
            "silent",
            "binary_sensor.hall",
            "h1",
        )
    ]
    storm_t = T0 + timedelta(days=5)
    for i in range(6):
        tl.append(
            _ev(
                storm_t + timedelta(seconds=i * 10),
                "opened",
                "health",
                "unavailable",
                f"binary_sensor.s{i}",
                f"u{i}",
            )
        )
    h = sc.score_health(tl, [fault, missed])
    assert h["faults"] == [
        {"entity": "binary_sensor.hall", "caught": True, "latency_min": 180},
        {"entity": "binary_sensor.land", "caught": False, "latency_min": None},
    ]
    assert h["restart_storms"] == 1 and h["storm_openings"] == 6
    assert h["opened"] == 7


def test_information_counts_and_top_sources():
    tl = [
        _ev(T0, "opened", "information", "routine_missed", "binary_sensor.a", "r1"),
        _ev(T0, "opened", "information", "routine_missed", "binary_sensor.a", "r2"),
        _ev(T0, "opened", "information", "routine_missed", "binary_sensor.b", "r3"),
        _ev(T0, "opened", "information", "drift", "count:x", "d1"),
        _ev(T0, "cleared", "information", "drift", "count:x", "d1"),
    ]
    i = sc.score_information(tl, days=2.0)
    assert i["opened"] == 4 and i["per_day"] == 2.0
    assert i["by_kind"] == {"routine_missed": 3, "drift": 1}
    assert i["top_sources"]["routine_missed"][0] == ["binary_sensor.a", 2]


def test_end_to_end_on_synthetic_fixture_with_injected_falls(tmp_path):
    truth = tmp_path / "t.yaml"
    truth.write_text(
        "- {from: '2026-09-20 00:00', to: '2026-09-21 00:00', what: gap}\n"
    )
    report = sc.run(FIX, truth_path=truth, fall_times=["10:00"], fall_days=3)
    assert set(report) >= {"span", "welfare", "health", "information", "panic", "falls"}
    falls = report["falls"]
    assert falls["injected"] == 3
    assert falls["caught"] == 3
    assert all(0 < m <= 12 * 60 for m in falls["latency_min"])
    # No fall is injected inside a gap or before learning completes.
    for f in falls["cases"]:
        assert not f["start"].startswith("2026-09-20")
    text = sc.render(report)
    assert "WELFARE" in text and "INJECTED FALLS" in text


def test_fall_points_use_every_time_on_each_chosen_day():
    start = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    events = [(start + timedelta(days=d), "binary_sensor.x", "on") for d in range(30)]
    points = sc._fall_points(events, [], 14, ["10:00", "15:00"], 4)
    assert len(points) == 8
    assert sorted({p.strftime("%H:%M") for p in points}) == ["10:00", "15:00"]
    assert len({p.date() for p in points}) == 4
