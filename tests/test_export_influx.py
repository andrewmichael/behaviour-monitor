"""Tests for scripts/export_influx.py (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import export_influx as ex  # noqa: E402

LONDON = ZoneInfo("Europe/London")


def test_parse_creds_ignores_blanks_comments_and_spaces():
    text = "# influx\nhost = 192.168.0.243\nport=8086\n\ndatabase=homeassistant\n"
    text += "username=ro\npassword=a=b\n"
    c = ex.parse_creds(text)
    assert c == {
        "host": "192.168.0.243",
        "port": "8086",
        "database": "homeassistant",
        "username": "ro",
        "password": "a=b",
    }


def test_rows_to_events_prefers_state_then_value_and_uses_local_time():
    # 2026-11-09 12:00 UTC is 12:00 GMT; 2026-10-01 12:00 UTC is 13:00 BST.
    nov = 1794225600000
    oct_ = 1790856000000
    rows = [[nov, "on", 1.0], [oct_, None, 12.5], [nov + 1000, None, 3.0]]
    events = ex.rows_to_events("sensor.kettle_power", rows, LONDON)
    assert events[0] == {
        "t": "2026-11-09T12:00:00+00:00",
        "e": "sensor.kettle_power",
        "s": "on",
    }
    assert events[1]["t"] == "2026-10-01T13:00:00+01:00" and events[1]["s"] == "12.5"
    assert events[2]["s"] == "3.0"


def test_rows_without_state_or_value_are_skipped():
    assert ex.rows_to_events("sensor.x", [[1794225600000, None, None]], LONDON) == []


def test_merge_dedupes_and_sorts():
    a = [{"t": "2026-11-09T12:00:00+00:00", "e": "x", "s": "on"}]
    b = [
        {"t": "2026-11-09T12:00:00+00:00", "e": "x", "s": "on"},
        {"t": "2026-11-09T11:00:00+00:00", "e": "y", "s": "off"},
    ]
    merged = ex.merge_events(a, b)
    assert [e["e"] for e in merged] == ["y", "x"]


def test_merge_orders_across_offsets_by_instant():
    a = [{"t": "2026-10-25T01:30:00+01:00", "e": "x", "s": "on"}]  # 00:30 UTC
    b = [{"t": "2026-10-25T01:00:00+00:00", "e": "y", "s": "on"}]  # 01:00 UTC
    assert [e["e"] for e in ex.merge_events(b, a)] == ["x", "y"]


def test_query_selects_time_range_for_one_measurement():
    q = ex.build_query(
        "binary_sensor.front_room_motion",
        "2026-11-08T23:36:00+00:00",
        "2026-11-09T00:00:00+00:00",
    )
    assert q == (
        'SELECT "state","value" FROM "binary_sensor.front_room_motion" '
        "WHERE time >= '2026-11-08T23:36:00+00:00' "
        "AND time < '2026-11-09T00:00:00+00:00' ORDER BY time ASC"
    )


def test_main_writes_fixture_merge_and_context(tmp_path, monkeypatch):
    sidecar = tmp_path / "site.sidecar.json"
    sidecar.write_text(
        json.dumps(
            {
                "site": "S",
                "entities": [
                    {"entity_id": "binary_sensor.m", "category": "motion", "room": "R"}
                ],
            }
        )
    )
    existing = tmp_path / "old.jsonl"
    existing.write_text(
        json.dumps(
            {"t": "2026-11-01T10:00:00+00:00", "e": "binary_sensor.m", "s": "on"}
        )
        + "\n"
    )
    creds = tmp_path / "creds"
    creds.write_text("host=h\nport=1\ndatabase=d\nusername=u\npassword=p\n")

    def fake_query(c, q):
        assert c["host"] == "h"
        if "SHOW MEASUREMENTS" in q:
            return ["binary_sensor.m", "sensor.m_battery", "sensor.uptime"]
        if '"binary_sensor.m"' in q:
            return [[1794225600000, "off", 0.0]]
        if '"sensor.m_battery"' in q:
            return [[1794225600000, None, 80.0]]
        return [[1794225600000, "2026-11-09T12:00:00+00:00", None]]

    monkeypatch.setattr(ex, "run_query", fake_query)
    out = tmp_path / "site.jsonl"
    ctx = tmp_path / "site.context.jsonl"
    rc = ex.main(
        [
            "--creds",
            str(creds),
            "--sidecar",
            str(sidecar),
            "--start",
            "2026-11-08T23:36:00+00:00",
            "--end",
            "2026-11-10T00:00:00+00:00",
            "--merge",
            str(existing),
            "--out",
            str(out),
            "--context",
            str(ctx),
        ]
    )
    assert rc == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [r["s"] for r in rows] == ["on", "off"]
    context = [json.loads(line) for line in ctx.read_text().splitlines()]
    assert {r["e"] for r in context} == {"sensor.m_battery", "sensor.uptime"}
