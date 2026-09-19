"""Replay the synthetic seven-day fixture through the pipeline and the CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from custom_components.behaviour_monitor.const import (
    DOOR_OPEN_BRIEF,
    DOOR_OPEN_PROLONGED,
)
from custom_components.behaviour_monitor.entity_role import parse_role_overrides
from custom_components.behaviour_monitor.pipeline import (
    EXCURSION,
    PipelineConfig,
    replay,
)

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "tests" / "fixtures" / "replay_week.csv"
ROLES = ROOT / "tests" / "fixtures" / "replay_week_roles.txt"


def _load():
    sys.path.insert(0, str(ROOT / "scripts"))
    import replay as cli  # noqa: E402

    roles = {
        eid: value for eid, value in parse_role_overrides(ROLES.read_text()).items()
    }
    return cli, cli.load_events(CSV, roles)


def test_fixture_counts() -> None:
    cli, events = _load()
    assert len(events) == 252
    activity, doors = replay(events, PipelineConfig())
    per_entity: dict[str, int] = {}
    excursions = [e for e in activity if e.kind == EXCURSION]
    for e in activity:
        if e.kind != EXCURSION:
            per_entity[e.entity_id] = per_entity.get(e.entity_id, 0) + 1
    assert per_entity == {
        "switch.teasmade": 14,
        "binary_sensor.pir_bathroom": 7,
        "binary_sensor.pir_hall": 7,
        "binary_sensor.pir_kitchen": 14,
        "binary_sensor.door_lounge": 7,
    }
    assert len(excursions) == 35
    assert (
        sum(
            1
            for e in excursions
            if e.entities == ("binary_sensor.door_back", "binary_sensor.door_side")
        )
        == 28
    )
    assert doors["binary_sensor.door_side"]["last_open_class"] == DOOR_OPEN_PROLONGED
    assert doors["binary_sensor.door_back"] == {
        "last_open_seconds": 6.0,
        "last_open_class": DOOR_OPEN_BRIEF,
    }


def test_cli_json_runs_without_home_assistant() -> None:
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": ""}
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "replay.py"),
            "--events",
            str(CSV),
            "--roles",
            str(ROLES),
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["entities"]["binary_sensor.pir_bathroom"]["activations"] == 7
    assert out["excursions"]["count"] == 35
    assert len(out["days"]) == 7
