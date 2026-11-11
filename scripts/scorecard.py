"""Score the current engine against a site's real data and a truth file.

Replays a fixture through the core Engine, lines the alerts up against a
hand-written truth file of what really happened, and injects simulated falls
(all activity stops) on ordinary days to measure time to alert.

Usage:
  python scripts/scorecard.py exports/fixture/biddulph_road.jsonl \\
      --truth exports/fixture/biddulph_road.truth.yaml [--json]

Truth file (YAML list). Each entry has `from`/`to` (or `at` for a moment),
`what`, and optionally `entity` and `note`; `to` defaults to the end of the
data. `what` is one of:
  out, away, visitor     the person was out / away / had company
  sensor_fault           a device stopped or misbehaved (give `entity`)
  maintenance            Home Assistant restarts, upgrades, rewiring
  concern                something genuinely wrong; welfare should alert
  gap                    no data (e.g. recorder purge); replayed as holiday
`away` and `gap` are replayed with holiday mode on, as a real site would be.

Restart storms in recorder CSV exports are mostly an export artefact: the
export can keep a sensor's "unavailable" row at a Home Assistant restart but
drop the "back to normal" row a second later, so the sensor looks offline
for hours. Live, the outage lasts under a second and the health grace period
absorbs it. InfluxDB exports keep both rows.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay import load_fixture  # noqa: E402

from custom_components.behaviour_monitor.core.engine import (  # noqa: E402
    Engine,
    EngineConfig,
)
from custom_components.behaviour_monitor.core.events import Category  # noqa: E402

HOLIDAY_KINDS = {"away", "gap"}
CARD_KINDS = ("not_yet_today", "trip_missed", "unusual_now")
NIGHT_KINDS = ("night_downstairs", "night_door")
EXPLAINS_WELFARE = {"out", "away", "visitor", "maintenance", "gap"}
PUSH_EVENTS = {"opened", "escalated", "reminder"}
STORM_MIN_SENSORS = 5
STORM_WINDOW = timedelta(minutes=2)
POLL = timedelta(minutes=5)
FALL_HORIZON = timedelta(hours=12)


@dataclass(frozen=True)
class Truth:
    start: datetime
    end: datetime
    what: str
    entity: str | None = None
    note: str | None = None

    def covers(self, t: datetime) -> bool:
        return self.start <= t <= self.end


# ------------------------------------------------------------------ truth


def _parse_time(value: Any, tz: Any) -> datetime:
    t = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return t if t.tzinfo else t.replace(tzinfo=tz)


def load_truth(path: Path, end_default: datetime) -> list[Truth]:
    tz = end_default.tzinfo
    out: list[Truth] = []
    for row in yaml.safe_load(path.read_text()) or []:
        if "at" in row:
            start = end = _parse_time(row["at"], tz)
        else:
            start = _parse_time(row["from"], tz)
            end = _parse_time(row["to"], tz) if row.get("to") else end_default
        out.append(
            Truth(start, end, str(row["what"]), row.get("entity"), row.get("note"))
        )
    return out


# ------------------------------------------------------------------ replay


def _row(t: datetime, a: Any) -> dict[str, Any]:
    al = a.alert
    return {
        "t": t,
        "action": a.action,
        "event": a.event,
        "reason": a.reason,
        "group": a.group,
        "id": a.alert_id,
        "kind": al.kind,
        "source": al.source,
        "severity": al.severity.value,
        "msg": al.explanation,
    }


def replay(
    events: list[tuple[datetime, str, str]],
    engine: Engine,
    holidays: list[Truth],
    checkpoints: list[datetime],
    tz: str = "Europe/London",
) -> tuple[list[dict[str, Any]], dict[datetime, dict[str, Any]]]:
    """Replay events, polling every 5 minutes, with holiday mode over the given
    windows. Returns the timeline and an engine snapshot at each checkpoint.

    Polls run on local wall time in ``tz``, as Home Assistant's
    ``dt_util.now()`` gives, so they stay right across a clock change."""
    zone = ZoneInfo(tz)
    timeline: list[dict[str, Any]] = []
    snaps: dict[datetime, dict[str, Any]] = {}
    pending = sorted(checkpoints)
    last: dict[str, str | None] = {}

    def on_holiday(t: datetime) -> bool:
        return any(h.covers(t) for h in holidays)

    def poll_until(limit: datetime) -> None:
        nonlocal next_poll
        while next_poll <= limit:
            now = next_poll.astimezone(zone)
            engine.holiday = on_holiday(now)
            timeline.extend(_row(now, a) for a in engine.poll(now))
            next_poll += POLL

    next_poll = events[0][0].replace(second=0, microsecond=0)
    for ts, eid, state in events:
        while pending and pending[0] <= ts:
            cp = pending.pop(0)
            poll_until(cp)
            snaps[cp] = engine.to_dict()
        poll_until(ts)
        engine.holiday = on_holiday(ts)
        timeline.extend(
            _row(ts, a) for a in engine.handle_state(eid, last.get(eid), state, ts)
        )
        last[eid] = state
    poll_until(events[-1][0] + timedelta(hours=1))
    return timeline, snaps


def _fall_points(
    events: list[tuple[datetime, str, str]],
    truth: list[Truth],
    learning_days: int,
    fall_times: list[str],
    fall_days: int,
) -> list[datetime]:
    """Evenly spaced ordinary days after learning, each at every given time.

    A day qualifies when no truth window comes near any of its fall times.
    """
    first_day = events[0][0].date()
    tz_by_day: dict[date, Any] = {}
    for ts, _, _ in events:
        tz_by_day.setdefault(ts.date(), ts.tzinfo)
    days = sorted(d for d in tz_by_day if (d - first_day).days >= learning_days)
    by_day: list[list[datetime]] = []
    for d in days[:-1]:  # the last day may be cut short
        points = []
        for hhmm in fall_times:
            h, m = (int(x) for x in hhmm.split(":"))
            points.append(datetime.combine(d, time(h, m), tz_by_day[d]))
        if any(
            tr.start <= t + FALL_HORIZON and tr.end >= t - timedelta(hours=1)
            for t in points
            for tr in truth
        ):
            continue
        by_day.append(points)
    if len(by_day) > fall_days:
        step = len(by_day) / fall_days
        by_day = [by_day[int(i * step)] for i in range(fall_days)]
    return [t for points in by_day for t in points]


def simulate_falls(
    snaps: dict[datetime, dict[str, Any]],
    config: EngineConfig,
    specs: list,
    tz: str = "Europe/London",
) -> list[dict[str, Any]]:
    """From each snapshot, stop all activity and poll until welfare alerts."""
    zone = ZoneInfo(tz)
    cases = []
    for start, snap in sorted(snaps.items()):
        e = Engine.from_dict(snap, config, specs)
        e.holiday = False
        t, latency = start, None
        while t < start + FALL_HORIZON and latency is None:
            t += POLL
            for a in e.poll(t.astimezone(zone)):
                if (
                    a.action == "event"
                    and a.group == "attention"
                    and a.event in PUSH_EVENTS
                ):
                    latency = int((t - start).total_seconds() // 60)
                    break
        cases.append({"start": start.isoformat(), "latency_min": latency})
    return cases


# ------------------------------------------------------------------ scoring


def _events(tl: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in tl if r["action"] == "event"]


def score_welfare(tl: list[dict[str, Any]], truth: list[Truth]) -> dict[str, Any]:
    first_push: dict[str, dict[str, Any]] = {}
    for r in _events(tl):
        if r["group"] == "attention" and r["event"] in PUSH_EVENTS:
            first_push.setdefault(r["id"], r)
    concerns = [t for t in truth if t.what == "concern"]
    explained: Counter[str] = Counter()
    unexplained: list[dict[str, Any]] = []
    caught: dict[int, int] = {}
    for r in first_push.values():
        hit = next(
            (
                i
                for i, c in enumerate(concerns)
                if c.start <= r["t"] <= c.end + timedelta(hours=12)
            ),
            None,
        )
        if hit is not None:
            mins = int((r["t"] - concerns[hit].start).total_seconds() // 60)
            caught[hit] = min(mins, caught.get(hit, mins))
            continue
        why = next(
            (t.what for t in truth if t.what in EXPLAINS_WELFARE and t.covers(r["t"])),
            None,
        )
        if why:
            explained[why] += 1
        else:
            unexplained.append(
                {
                    "id": r["id"],
                    "t": r["t"].isoformat(),
                    "kind": r["kind"],
                    "msg": r.get("msg"),
                }
            )
    return {
        "alerts": len(first_push),
        "night_pushes": sum(r["kind"] in NIGHT_KINDS for r in first_push.values()),
        "explained": dict(explained),
        "unexplained": unexplained,
        "concerns": len(concerns),
        "concerns_caught": len(caught),
        "concern_latency_min": [caught[i] for i in sorted(caught)],
    }


def score_health(tl: list[dict[str, Any]], truth: list[Truth]) -> dict[str, Any]:
    opened = [
        r for r in _events(tl) if r["group"] == "health" and r["event"] == "opened"
    ]
    faults = []
    for f in (t for t in truth if t.what == "sensor_fault"):
        hit = next(
            (
                r
                for r in opened
                if r["source"] == f.entity and f.start <= r["t"] <= f.end
            ),
            None,
        )
        faults.append(
            {
                "entity": f.entity,
                "caught": hit is not None,
                "latency_min": (
                    int((hit["t"] - f.start).total_seconds() // 60) if hit else None
                ),
            }
        )
    unavailable = sorted(
        (r for r in opened if r["kind"] == "unavailable"), key=lambda r: r["t"]
    )
    storms = storm_openings = 0
    i = 0
    while i < len(unavailable):
        j = i
        while (
            j + 1 < len(unavailable)
            and unavailable[j + 1]["t"] - unavailable[i]["t"] <= STORM_WINDOW
        ):
            j += 1
        if j - i + 1 >= STORM_MIN_SENSORS:
            storms += 1
            storm_openings += j - i + 1
        i = j + 1
    return {
        "opened": len(opened),
        "by_kind": dict(Counter(r["kind"] for r in opened)),
        "faults": faults,
        "restart_storms": storms,
        "storm_openings": storm_openings,
    }


def score_information(tl: list[dict[str, Any]], days: float) -> dict[str, Any]:
    opened = [
        r for r in _events(tl) if r["group"] == "information" and r["event"] == "opened"
    ]
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for r in opened:
        by_source[r["kind"]][r["source"]] += 1
    return {
        "opened": len(opened),
        "per_day": round(len(opened) / days, 1) if days else 0.0,
        "by_kind": dict(Counter(r["kind"] for r in opened)),
        "top_sources": {
            k: [[s, n] for s, n in c.most_common(5)] for k, c in by_source.items()
        },
    }


def score_panic(
    events: list[tuple[datetime, str, str]], specs: list, tl: list[dict[str, Any]]
) -> dict[str, Any]:
    panic_ids = {s.entity_id for s in specs if s.category is Category.PANIC}
    presses = 0
    last: dict[str, str] = {}
    for _, eid, state in events:
        if eid in panic_ids:
            if state == "on" and last.get(eid) != "on":
                presses += 1
            last[eid] = state
    ev = [r for r in _events(tl) if r["kind"] == "panic"]
    return {
        "presses": presses,
        "opened": sum(r["event"] == "opened" for r in ev),
        "pressed_again": sum(r["reason"] == "pressed_again" for r in ev),
    }


# ------------------------------------------------------------------ run


def run(
    fixture: Path,
    truth_path: Path | None = None,
    fall_times: list[str] | None = None,
    fall_days: int = 10,
    tz: str = "Europe/London",
) -> dict[str, Any]:
    events, specs, options = load_fixture(fixture)
    zone = ZoneInfo(tz)
    config = EngineConfig.from_options(options)
    end = events[-1][0]
    truth = load_truth(truth_path, end) if truth_path else []
    holidays = [t for t in truth if t.what in HOLIDAY_KINDS]
    points = _fall_points(
        events, truth, config.learning_days, fall_times or ["10:00", "15:00"], fall_days
    )
    tl, snaps = replay(events, Engine(config, specs), holidays, points, tz)
    for r in tl:  # event rows keep the fixture's offset; show local
        r["t"] = r["t"].astimezone(zone)
    data_days = len(
        {ts.date() for ts, _, _ in events if not any(h.covers(ts) for h in holidays)}
    )
    cases = simulate_falls(snaps, config, specs, tz)
    lat = [c["latency_min"] for c in cases if c["latency_min"] is not None]
    return {
        "span": {
            "first": events[0][0].isoformat(),
            "last": end.isoformat(),
            "days_with_data": data_days,
            "events": len(events),
        },
        "welfare": score_welfare(tl, truth),
        "health": score_health(tl, truth),
        "information": score_information(tl, float(data_days)),
        "panic": score_panic(events, specs, tl),
        "falls": {
            "injected": len(cases),
            "caught": len(lat),
            "latency_min": lat,
            "median_min": int(statistics.median(lat)) if lat else None,
            "worst_min": max(lat) if lat else None,
            "cases": cases,
        },
    }


def _hm(minutes: int | None) -> str:
    return "-" if minutes is None else f"{minutes // 60}h{minutes % 60:02d}m"


def render(r: dict[str, Any]) -> str:
    s, w, h, i, p, f = (
        r[k] for k in ("span", "welfare", "health", "information", "panic", "falls")
    )
    out = [
        f"{s['first'][:10]} to {s['last'][:10]}: {s['days_with_data']} days with data,"
        f" {s['events']} events",
        "",
        f"WELFARE (would push)          {w['alerts']}",
        f"  night pushes                {w['night_pushes']}",
        f"  explained by truth          {sum(w['explained'].values())}"
        + (f"  {w['explained']}" if w["explained"] else ""),
        f"  unexplained                 {len(w['unexplained'])}",
    ]
    out += [f"    {u['t'][:16]}  {u['kind']}: {u['msg']}" for u in w["unexplained"]]
    out.append(
        f"  concerns caught             {w['concerns_caught']} / {w['concerns']}"
        + (
            f"  (minutes: {w['concern_latency_min']})"
            if w["concern_latency_min"]
            else ""
        )
    )
    out += [
        "",
        f"DEVICE HEALTH opened          {h['opened']}  {h['by_kind']}",
        f"  restart storms              {h['restart_storms']}"
        f" ({h['storm_openings']} openings)",
    ]
    out += [
        f"  fault {x['entity']}: "
        + (f"caught after {_hm(x['latency_min'])}" if x["caught"] else "MISSED")
        for x in h["faults"]
    ]
    out += [
        "",
        f"INFORMATION opened            {i['opened']}  ({i['per_day']} a day)",
        f"  by kind                     {i['by_kind']}",
    ]
    out += [
        f"  top {k}: " + ", ".join(f"{src} {n}" for src, n in v)
        for k, v in i["top_sources"].items()
        if k in CARD_KINDS or k == "drift"
    ]
    out += [
        "",
        f"PANIC  presses {p['presses']}, alerts opened {p['opened']},"
        f" pressed-again reminders {p['pressed_again']}",
        "",
        f"INJECTED FALLS  {f['caught']} / {f['injected']} caught,"
        f" median {_hm(f['median_min'])}, worst {_hm(f['worst_min'])}",
    ]
    out += [
        f"  {c['start'][:16]}  "
        + (_hm(c["latency_min"]) if c["latency_min"] is not None else "MISSED")
        for c in f["cases"]
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("fixture", type=Path)
    p.add_argument("--truth", type=Path)
    p.add_argument(
        "--fall-times", default="10:00,15:00", help="local times, comma separated"
    )
    p.add_argument("--fall-days", type=int, default=10)
    p.add_argument("--tz", default="Europe/London")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    report = run(a.fixture, a.truth, a.fall_times.split(","), a.fall_days, a.tz)
    print(json.dumps(report, indent=1, default=str) if a.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
