"""Export raw sensor history from InfluxDB 1.8 into the fixture format.

Reads the monitored entities from a fixture sidecar and writes their state
changes for a time range as fixture rows, in local time (the engine's daily
slots are local). Optionally merges into an existing fixture, so a site's
history keeps growing in one file, and writes everything else recorded
(batteries, sensor.uptime restarts, Behaviour Monitor's own outputs) to a
separate context file for scoring.

Usage:
  python scripts/export_influx.py \\
      --sidecar exports/fixture/biddulph_road.sidecar.json \\
      --start 2026-11-08T23:36:00+00:00 \\
      --merge exports/fixture/biddulph_road.jsonl \\
      --out exports/fixture/biddulph_road.jsonl \\
      --context exports/fixture/biddulph_road.context.jsonl

Credentials: ~/.influx_bm (or --creds), key=value lines with host, port,
database, username, password. InfluxDB is expected to store one measurement
per entity id (measurement_attr: entity_id) with fields "state" and "value".
"""

from __future__ import annotations

import argparse
import base64
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def parse_creds(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def build_query(measurement: str, start: str, end: str) -> str:
    return (
        f'SELECT "state","value" FROM "{measurement}" '
        f"WHERE time >= '{start}' AND time < '{end}' ORDER BY time ASC"
    )


def run_query(creds: dict[str, str], query: str) -> list[Any]:
    """Run one InfluxQL query and return the first series' values.

    SHOW MEASUREMENTS returns a flat list of names instead.
    """
    params = urllib.parse.urlencode(
        {"db": creds["database"], "q": query, "epoch": "ms"}
    )
    req = urllib.request.Request(
        f"http://{creds['host']}:{creds['port']}/query?{params}"
    )
    token = base64.b64encode(
        f"{creds['username']}:{creds['password']}".encode()
    ).decode()
    req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        body = json.load(resp)
    result = body["results"][0]
    if "error" in result:
        raise RuntimeError(result["error"])
    series = result.get("series") or []
    if not series:
        return []
    values = series[0]["values"]
    if query.startswith("SHOW MEASUREMENTS"):
        return [v[0] for v in values]
    return values


def rows_to_events(entity_id: str, rows: list[list[Any]], tz: ZoneInfo) -> list[dict]:
    """[[epoch_ms, state, value], ...] -> fixture rows; state wins over value."""
    events: list[dict] = []
    for ms, state, value in rows:
        if state is not None:
            s = str(state)
        elif value is not None:
            s = str(float(value))
        else:
            continue
        t = datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(tz)
        events.append({"t": t.isoformat(), "e": entity_id, "s": s})
    return events


def _instant(row: dict) -> datetime:
    return datetime.fromisoformat(row["t"])


def merge_events(*sets: list[dict]) -> list[dict]:
    """Merge fixture rows, dropping exact duplicates, ordered by instant."""
    seen: set[tuple[datetime, str, str]] = set()
    out: list[dict] = []
    for rows in sets:
        for r in rows:
            key = (_instant(r), r["e"], r["s"])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    out.sort(key=lambda r: (_instant(r), r["e"]))
    return out


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--creds", type=Path, default=Path.home() / ".influx_bm")
    p.add_argument("--sidecar", required=True, type=Path)
    p.add_argument("--start", required=True, help="ISO time, inclusive")
    p.add_argument("--end", help="ISO time, exclusive (default: now)")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--merge", type=Path, help="existing fixture to merge into")
    p.add_argument("--context", type=Path, help="write other measurements here")
    p.add_argument("--tz", default="Europe/London")
    a = p.parse_args(argv)

    creds = parse_creds(a.creds.read_text())
    tz = ZoneInfo(a.tz)
    end = a.end or datetime.now(timezone.utc).isoformat()
    monitored = [e["entity_id"] for e in json.loads(a.sidecar.read_text())["entities"]]

    events: list[dict] = []
    for eid in monitored:
        events += rows_to_events(
            eid, run_query(creds, build_query(eid, a.start, end)), tz
        )
    existing = _read_jsonl(a.merge) if a.merge and a.merge.exists() else []
    merged = merge_events(existing, events)
    _write_jsonl(a.out, merged)
    print(f"{len(events)} new rows; {len(merged)} rows in {a.out}")

    if a.context:
        others = [
            m for m in run_query(creds, "SHOW MEASUREMENTS") if m not in monitored
        ]
        ctx: list[dict] = []
        for m in others:
            ctx += rows_to_events(m, run_query(creds, build_query(m, a.start, end)), tz)
        old = _read_jsonl(a.context) if a.context.exists() else []
        ctx = merge_events(old, ctx)
        _write_jsonl(a.context, ctx)
        print(f"{len(ctx)} rows in {a.context} ({len(others)} measurements)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
