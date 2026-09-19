#!/usr/bin/env python3
"""Replay a recorder CSV export through the Behaviour Monitor activity pipeline.

Runs without Home Assistant installed: the integration's pure modules are
loaded through a stub package so the integration's __init__ never executes.

    python scripts/replay.py --events history.csv --roles roles.txt [--json]

CSV columns (any order): entity_id, last_changed (ISO 8601), state.
Roles file: one "entity_id: role" per line, full roles only.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
import types
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "custom_components" / "behaviour_monitor"


def _load_pure_modules() -> tuple[Any, Any, Any]:
    """Import const, entity_role and pipeline without running the package __init__."""
    if "custom_components.behaviour_monitor" not in sys.modules:
        parent = types.ModuleType("custom_components")
        parent.__path__ = [str(ROOT / "custom_components")]  # type: ignore[attr-defined]
        pkg = types.ModuleType("custom_components.behaviour_monitor")
        pkg.__path__ = [str(SRC)]  # type: ignore[attr-defined]
        sys.modules["custom_components"] = parent
        sys.modules["custom_components.behaviour_monitor"] = pkg
    const = importlib.import_module("custom_components.behaviour_monitor.const")
    roles = importlib.import_module("custom_components.behaviour_monitor.entity_role")
    pipeline = importlib.import_module("custom_components.behaviour_monitor.pipeline")
    return const, roles, pipeline


CONST, ENTITY_ROLE, PIPELINE = _load_pure_modules()
EntityRole = CONST.EntityRole


def load_roles(path: Path) -> dict[str, str]:
    """Parse the roles file; every value must resolve to a full role, not an
    ambiguous bare kind. ``appliance`` and ``other`` have no sub-roles, so
    their kind name and full role value coincide and both are accepted;
    ``motion`` and ``door`` need a specific sub-role (e.g. ``motion.kitchen``,
    ``door.interior``) and are rejected bare.
    """
    parsed = ENTITY_ROLE.parse_role_overrides(path.read_text())
    bad = []
    for eid, value in parsed.items():
        try:
            EntityRole.from_string(value)
        except ValueError:
            bad.append(eid)
    if bad:
        raise SystemExit(
            f"roles file: full roles required (not a bare kind) for: {', '.join(sorted(bad))}"
        )
    return parsed


def load_events(path: Path, roles: dict[str, str]) -> list[Any]:
    """Read the CSV into PipelineEvents, deriving old_state per entity in time order."""
    rows: list[tuple[str, datetime, str]] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            eid = row["entity_id"].strip().lower()
            if eid not in roles:
                continue
            ts = datetime.fromisoformat(
                row["last_changed"].strip().replace("Z", "+00:00")
            )
            rows.append((eid, ts, row["state"].strip()))
    rows.sort(key=lambda r: r[1])
    prev: dict[str, str | None] = {}
    events = []
    for eid, ts, state in rows:
        events.append(
            PIPELINE.PipelineEvent(
                eid, EntityRole.from_string(roles[eid]), prev.get(eid), state, ts
            )
        )
        prev[eid] = None if state in ("unavailable", "unknown") else state
    return events


def summarise(
    activity: list[Any],
    doors: dict[str, dict[str, Any]],
    raw_counts: Counter,
    roles: dict[str, str],
) -> dict[str, Any]:
    per_entity: dict[str, dict[str, Any]] = {
        eid: {
            "role": roles[eid],
            "raw_rows": raw_counts.get(eid, 0),
            "activations": 0,
            **doors.get(eid, {}),
        }
        for eid in sorted(roles)
    }
    excursions = []
    days: dict[str, int] = defaultdict(int)
    for ev in activity:
        days[ev.timestamp.date().isoformat()] += 1
        if ev.kind == PIPELINE.EXCURSION:
            excursions.append(
                {
                    "at": ev.timestamp.isoformat(),
                    "entities": list(ev.entities),
                    "span_seconds": ev.duration_seconds,
                }
            )
        else:
            per_entity[ev.entity_id]["activations"] += 1
    return {
        "entities": per_entity,
        "excursions": {"count": len(excursions), "items": excursions},
        "days": dict(sorted(days.items())),
    }


def _print_text(summary: dict[str, Any]) -> None:
    print(f"{'entity':40} {'role':18} {'raw':>6} {'acts':>6}  last open")
    for eid, info in summary["entities"].items():
        last = ""
        if info.get("last_open_seconds") is not None:
            last = f"{info['last_open_seconds']:.0f}s {info['last_open_class']}"
        print(
            f"{eid:40} {info['role']:18} {info['raw_rows']:6d} {info['activations']:6d}  {last}"
        )
    print(f"\nexcursions: {summary['excursions']['count']}")
    for ex in summary["excursions"]["items"]:
        print(
            f"  {ex['at']}  {' + '.join(ex['entities'])}  span {ex['span_seconds']:.0f}s"
        )
    print("\nactivity per day:")
    for day, n in summary["days"].items():
        print(f"  {day}  {n}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--roles", type=Path, required=True)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--motion-debounce", type=int, default=CONST.DEFAULT_MOTION_DEBOUNCE_SECONDS
    )
    p.add_argument(
        "--door-debounce", type=int, default=CONST.DEFAULT_DOOR_DEBOUNCE_SECONDS
    )
    p.add_argument(
        "--collapse", type=int, default=CONST.DEFAULT_RETRIGGER_COLLAPSE_SECONDS
    )
    p.add_argument(
        "--excursion-window", type=int, default=CONST.DEFAULT_EXCURSION_WINDOW_SECONDS
    )
    p.add_argument(
        "--open-extended", type=int, default=CONST.DEFAULT_DOOR_OPEN_EXTENDED_SECONDS
    )
    p.add_argument(
        "--open-prolonged", type=int, default=CONST.DEFAULT_DOOR_OPEN_PROLONGED_SECONDS
    )
    args = p.parse_args(argv)

    roles = load_roles(args.roles)
    events = load_events(args.events, roles)
    config = PIPELINE.PipelineConfig(
        motion_debounce_seconds=args.motion_debounce,
        door_debounce_seconds=args.door_debounce,
        retrigger_collapse_seconds=args.collapse,
        excursion_window_seconds=args.excursion_window,
        door_open_extended_seconds=args.open_extended,
        door_open_prolonged_seconds=args.open_prolonged,
    )
    activity, doors = PIPELINE.replay(events, config)
    summary = summarise(activity, doors, Counter(ev.entity_id for ev in events), roles)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_text(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
