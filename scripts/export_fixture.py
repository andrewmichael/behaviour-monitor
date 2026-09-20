"""Export recorder history for a site into the fixture format, anonymised.

Usage:
  python scripts/export_fixture.py --url http://homeassistant.local:8123 \
      --token "$HA_TOKEN" --entities site_entities.json --days 10 \
      --out tests/fixtures/site_real_10d.jsonl --site "Real site"

site_entities.json: [{"entity_id": "...", "category": "motion", "room": "Kitchen"}, ...]
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


def anonymise(specs: list[dict]) -> tuple[list[dict], dict[str, str], dict[str, str]]:
    id_map: dict[str, str] = {}
    room_map: dict[str, str] = {}
    counters: dict[str, int] = {}
    out: list[dict] = []
    for s in specs:
        cat = s["category"]
        counters[cat] = counters.get(cat, 0) + 1
        domain = s["entity_id"].split(".", 1)[0]
        new_id = f"{domain}.{cat}_{counters[cat]}"
        id_map[s["entity_id"]] = new_id
        room = s.get("room") or s["entity_id"]
        if room not in room_map:
            room_map[room] = f"Room {len(room_map) + 1}"
        out.append({"entity_id": new_id, "category": cat, "room": room_map[room]})
    return out, id_map, room_map


def rows_to_events(
    rows_by_entity: list[list[dict]], id_map: dict[str, str]
) -> list[dict]:
    events: list[dict] = []
    for rows in rows_by_entity:
        for r in rows:
            eid = id_map.get(r["entity_id"])
            if eid is None:
                continue
            events.append({"t": r["last_changed"], "e": eid, "s": str(r["state"])})
    events.sort(key=lambda e: e["t"])
    return events


def fetch_history(
    url: str, token: str, entity_ids: list[str], days: int
) -> list[list[dict]]:
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = urllib.parse.urlencode(
        {
            "filter_entity_id": ",".join(entity_ids),
            "minimal_response": "",
            "no_attributes": "",
        }
    )
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/history/period/{start}?{q}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        rows = json.load(resp)
    # minimal_response omits entity_id on all but the first row per entity; restore it
    for series in rows:
        if series:
            eid = series[0]["entity_id"]
            for r in series:
                r.setdefault("entity_id", eid)
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--url", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--entities", required=True, type=Path)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--site", default="Real site")
    args = p.parse_args(argv)
    specs = json.loads(args.entities.read_text())
    anon, id_map, room_map = anonymise(specs)
    rows = fetch_history(args.url, args.token, list(id_map), args.days)
    events = rows_to_events(rows, id_map)
    args.out.write_text("".join(json.dumps(e) + "\n" for e in events))
    sidecar = args.out.with_suffix("").with_suffix(".sidecar.json")
    sidecar.write_text(
        json.dumps(
            {"site": args.site, "entities": anon, "options": {"learning_days": 14}},
            indent=2,
        )
    )
    print(f"wrote {len(events)} events to {args.out}")
    print("entity map (not stored):", json.dumps(id_map, indent=2))
    print("room map (not stored):", json.dumps(room_map, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
