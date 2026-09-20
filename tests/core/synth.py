"""Synthetic site and scenario generators for core tests and the replay CLI."""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.behaviour_monitor.core.engine import EntitySpec
from custom_components.behaviour_monitor.core.events import Category

TZ = timezone(timedelta(hours=1))
START = datetime(2026, 9, 7, 0, 0, tzinfo=TZ)  # a Monday

Site = list[EntitySpec]

SITE: Site = [
    EntitySpec("binary_sensor.bed_motion", Category.MOTION, "Back Bedroom"),
    EntitySpec("binary_sensor.bath_motion", Category.MOTION, "Bathroom"),
    EntitySpec("binary_sensor.kitchen_motion", Category.MOTION, "Kitchen"),
    EntitySpec("binary_sensor.lounge_motion", Category.MOTION, "Backroom"),
    EntitySpec("binary_sensor.side_door", Category.CONTACT, "Utilityroom"),
    EntitySpec("binary_sensor.front_door", Category.CONTACT, "Hall"),
    EntitySpec("sensor.kettle_power", Category.PLUG, "Kitchen"),
    EntitySpec("sensor.tv_power", Category.PLUG, "Backroom"),
    EntitySpec("binary_sensor.panic_hall", Category.PANIC, "Hall"),
]

Event = tuple[datetime, str, str]


def _pulse(out: list[Event], eid: str, t: datetime, hold: int = 60) -> None:
    out.append((t, eid, "on"))
    out.append((t + timedelta(seconds=hold), eid, "off"))


def _kettle(out: list[Event], t: datetime) -> None:
    out.append((t, "sensor.kettle_power", "2800"))
    out.append((t + timedelta(minutes=2), "sensor.kettle_power", "0"))


def normal_day(
    day: datetime, rng: random.Random, chain_minutes: float = 4.0
) -> list[Event]:
    """One plausible day for a single occupant."""
    out: list[Event] = []
    j = lambda m: timedelta(minutes=m + rng.uniform(-1.0, 1.0))  # noqa: E731
    # night: bathroom visit ~00:30 and ~05:00
    _pulse(out, "binary_sensor.bed_motion", day + j(25))
    _pulse(out, "binary_sensor.bath_motion", day + j(30))
    _pulse(out, "binary_sensor.bed_motion", day + j(36))
    _pulse(out, "binary_sensor.bath_motion", day + timedelta(hours=5) + j(0))
    _pulse(out, "binary_sensor.bed_motion", day + timedelta(hours=5) + j(6))
    # morning chain: bedroom -> bathroom -> kitchen (+kettle)
    t = day + timedelta(hours=7) + j(0)
    _pulse(out, "binary_sensor.bed_motion", t)
    t += timedelta(minutes=chain_minutes)
    _pulse(out, "binary_sensor.bath_motion", t)
    t += timedelta(minutes=chain_minutes)
    _pulse(out, "binary_sensor.kitchen_motion", t)
    _kettle(out, t + timedelta(minutes=1))
    # day: kitchen / backroom alternating every 20-40 min, side door once
    t = day + timedelta(hours=8)
    while t < day + timedelta(hours=21, minutes=30):
        room = (
            "binary_sensor.kitchen_motion"
            if rng.random() < 0.5
            else "binary_sensor.lounge_motion"
        )
        _pulse(out, room, t)
        if 12 <= t.hour < 13 and rng.random() < 0.3:
            _kettle(out, t + timedelta(minutes=3))
        t += timedelta(minutes=rng.uniform(20, 40))
    out.append((day + timedelta(hours=11), "binary_sensor.side_door", "on"))
    out.append(
        (day + timedelta(hours=11, seconds=40), "binary_sensor.side_door", "off")
    )
    # tv on backroom evenings
    out.append((day + timedelta(hours=18), "sensor.tv_power", "85"))
    out.append((day + timedelta(hours=22), "sensor.tv_power", "0"))
    # bed
    _pulse(out, "binary_sensor.bed_motion", day + timedelta(hours=22) + j(10))
    return out


def normal_days(
    start: datetime = START, days: int = 21, chain_minutes: float = 4.0, seed: int = 1
) -> list[Event]:
    rng = random.Random(seed)
    out: list[Event] = []
    for d in range(days):
        out.extend(normal_day(start + timedelta(days=d), rng, chain_minutes))
    return sorted(out)


# ----------------------------------------------------------------- scenarios


def panic_press(base_days: int = 21) -> list[Event]:
    ev = normal_days(days=base_days)
    t = START + timedelta(days=base_days, hours=14)
    ev += [
        (t, "binary_sensor.panic_hall", "on"),
        (t + timedelta(seconds=5), "binary_sensor.panic_hall", "off"),
    ]
    return sorted(ev)


def silent_kitchen(base_days: int = 21) -> list[Event]:
    """Kitchen PIR stops reporting for two days while everything else continues."""
    ev = normal_days(days=base_days + 2)
    cut = START + timedelta(days=base_days)
    return [
        e for e in ev if not (e[1] == "binary_sensor.kitchen_motion" and e[0] >= cut)
    ]


def sitewide_dropout(base_days: int = 21) -> list[Event]:
    ev = normal_days(days=base_days + 1)
    t = START + timedelta(days=base_days, hours=10)
    for s in SITE:
        ev.append((t, s.entity_id, "unavailable"))
    for s in SITE:
        ev.append(
            (
                t + timedelta(seconds=12),
                s.entity_id,
                "off" if s.category != Category.PLUG else "0",
            )
        )
    return sorted(ev)


def chain_stall_at_kettle(base_days: int = 21) -> list[Event]:
    """Morning chain reaches the bathroom and stops; nothing else all day."""
    ev = normal_days(days=base_days)
    day = START + timedelta(days=base_days)
    t = day + timedelta(hours=7)
    _pulse(ev, "binary_sensor.bed_motion", t)
    _pulse(ev, "binary_sensor.bath_motion", t + timedelta(minutes=4))
    return sorted(ev)


def kettle_absent_days(base_days: int = 21, absent: int = 3) -> list[Event]:
    ev = normal_days(days=base_days + absent)
    cut = START + timedelta(days=base_days)
    return [e for e in ev if not (e[1] == "sensor.kettle_power" and e[0] >= cut)]


def chain_lengthening(
    base_days: int = 21, drift_days: int = 14, per_day_min: float = 2.0
) -> list[Event]:
    ev = normal_days(days=base_days)
    rng = random.Random(7)
    for i in range(drift_days):
        day = START + timedelta(days=base_days + i)
        ev.extend(normal_day(day, rng, chain_minutes=4.0 + per_day_min * (i + 1)))
    return sorted(ev)


def chain_jump(base_days: int = 21, after: int = 7, tail: int = 10) -> list[Event]:
    ev = normal_days(days=base_days)
    rng = random.Random(9)
    for i in range(after + tail):
        day = START + timedelta(days=base_days + i)
        ev.extend(normal_day(day, rng, chain_minutes=4.0 if i < after else 12.5))
    return sorted(ev)


# ------------------------------------------------------------------- output


def write_fixture(
    path: Path,
    events: list[Event],
    specs: Site = SITE,
    options: dict | None = None,
    site: str = "Synthetic",
) -> None:
    path.write_text(
        "".join(
            json.dumps({"t": t.isoformat(), "e": e, "s": s}) + "\n"
            for t, e, s in sorted(events)
        )
    )
    sidecar = path.with_suffix("").with_suffix(".sidecar.json")
    sidecar.write_text(
        json.dumps(
            {
                "site": site,
                "entities": [
                    {
                        "entity_id": s.entity_id,
                        "category": s.category.value,
                        "room": s.room,
                    }
                    for s in specs
                ],
                "options": options or {},
            },
            indent=2,
        )
    )
