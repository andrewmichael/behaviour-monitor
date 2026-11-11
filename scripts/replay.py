"""Replay a fixture through the core Engine and print the alert timeline.

Usage: python scripts/replay.py FIXTURE.jsonl [--poll-minutes 5] [--tz Europe/London]
       [--json]

Polls run on local wall time in ``--tz``, as Home Assistant's ``dt_util.now()``
gives, so a clock change mid-fixture doesn't leave them an hour out.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from custom_components.behaviour_monitor.core.alert_router import DeliveryAction
    from custom_components.behaviour_monitor.core.engine import (
        Engine,
        EngineConfig,
        EntitySpec,
    )
    from custom_components.behaviour_monitor.core.events import Category
except ModuleNotFoundError:
    # Home Assistant isn't installed in this environment (the usual case for a
    # dev venv; see README-DEV.md). custom_components.behaviour_monitor's own
    # __init__ needs it even though core/ does not, so fall back to the test
    # suite's lightweight stand-ins purely to make the pure core importable.
    import tests.conftest  # noqa: F401

    from custom_components.behaviour_monitor.core.alert_router import DeliveryAction
    from custom_components.behaviour_monitor.core.engine import (
        Engine,
        EngineConfig,
        EntitySpec,
    )
    from custom_components.behaviour_monitor.core.events import Category


DEFAULT_TZ = "Europe/London"


def load_fixture(
    path: Path,
) -> tuple[list[tuple[datetime, str, str]], list[EntitySpec], dict]:
    events = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        events.append((datetime.fromisoformat(row["t"]), row["e"], str(row["s"])))
    sidecar = json.loads(path.with_suffix("").with_suffix(".sidecar.json").read_text())
    specs = [
        EntitySpec(e["entity_id"], Category(e["category"]), e["room"])
        for e in sidecar["entities"]
    ]
    return sorted(events), specs, sidecar.get("options", {})


def run_fixture(
    path: Path, poll_minutes: int = 5, tz: str = DEFAULT_TZ
) -> list[tuple[datetime, DeliveryAction]]:
    return run_fixture_full(path, poll_minutes, tz)[0]


def run_fixture_full(
    path: Path, poll_minutes: int = 5, tz: str = DEFAULT_TZ
) -> tuple[list[tuple[datetime, DeliveryAction]], Engine, datetime | None]:
    """Replay and also return the engine and the last poll time, for snapshot assertions."""
    zone = ZoneInfo(tz)
    events, specs, options = load_fixture(path)
    engine = Engine(EngineConfig.from_options(options), specs)
    last_state: dict[str, str | None] = {s.entity_id: None for s in specs}
    timeline: list[tuple[datetime, DeliveryAction]] = []
    if not events:
        return timeline, engine, None
    next_poll = events[0][0].replace(second=0, microsecond=0)
    step = timedelta(minutes=poll_minutes)
    for ts, eid, state in events:
        while next_poll <= ts:
            now = next_poll.astimezone(zone)
            timeline.extend((now, a) for a in engine.poll(now))
            next_poll += step
        timeline.extend(
            (ts, a) for a in engine.handle_state(eid, last_state.get(eid), state, ts)
        )
        last_state[eid] = state
    end = events[-1][0] + timedelta(hours=6)
    while next_poll <= end:
        now = next_poll.astimezone(zone)
        timeline.extend((now, a) for a in engine.poll(now))
        next_poll += step
    return timeline, engine, (next_poll - step).astimezone(zone)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("fixture", type=Path)
    p.add_argument("--poll-minutes", type=int, default=5)
    p.add_argument("--tz", default=DEFAULT_TZ, help="local time zone for polls")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    for ts, a in run_fixture(args.fixture, args.poll_minutes, args.tz):
        if args.json:
            print(
                json.dumps(
                    {
                        "t": ts.isoformat(),
                        "action": a.event or a.action,
                        "reason": a.reason,
                        **a.alert.to_dict(),
                    }
                )
            )
        else:
            al = a.alert
            what = a.event or a.action
            why = f" [{a.reason}]" if a.reason else ""
            print(
                f"{ts:%Y-%m-%d %H:%M} {what:13} {al.cls.value:11} "
                f"{al.severity.value:8} {al.key}{why} :: {al.explanation}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
