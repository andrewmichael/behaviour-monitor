# Generic Welfare Core Implementation Plan (Part 1 of 2: pure core)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the stdlib-only learning and alerting core under `custom_components/behaviour_monitor/core/`, with fixtures and a replay CLI, so every model is testable without Home Assistant.

**Architecture:** Typed events flow from a `Normaliser` into three learning models (house, entity routine, chain), a CUSUM `DriftDetector`, and a `HealthTracker`. An `AlertRouter` turns model outputs into delivery actions. An `Engine` wires them with a simulated clock so the replay CLI and, in Part 2, the coordinator drive the same code.

**Tech Stack:** Python 3.12 stdlib only inside `core/`. pytest for tests. No Home Assistant imports anywhere in this plan.

**Spec:** `docs/superpowers/specs/2026-09-20-generic-welfare-core-design.md`

## Global Constraints

- Every file under `core/` imports only the Python standard library and sibling `core` modules. Never `homeassistant`, never `custom_components.behaviour_monitor.const`.
- Every model exposes `to_dict() -> dict` and `@classmethod from_dict(cls, data, config) -> Self`, and `from_dict` must tolerate a missing or malformed section by returning a fresh instance.
- All timestamps are timezone-aware `datetime` values passed as arguments. No module calls `datetime.now()`.
- Slot scheme everywhere: `weekday * 24 + hour`, 168 slots.
- Defaults are the spec's table: motion_debounce_s 90, plug_margin_w 5, learning_days 14, window_days 28, health_grace_s 900, push_repeat_s 1800, push_min_severity medium, house_low_ratio 3, chain_window_s 900, timing_promote_days 7, drift_sensitivity medium.
- Black, line length 88. Ruff clean. Type hints on every function.
- Commit after every task with a conventional commit message.
- Run tests with `venv/bin/python -m pytest` (the Makefile's `test` target). `tests/conftest.py` installs Home Assistant mocks at import time; core tests do not need them but are unaffected.

## Module map

| File | Responsibility |
|---|---|
| `core/__init__.py` | empty |
| `core/events.py` | `Category`, `EventKind`, `ActivityEvent`, `HealthEvent` |
| `core/alerts.py` | `AlertClass`, `Severity`, `Alert` |
| `core/slots.py` | `slot_index`, `slot_label`, `median_mad`, `is_weekend`, `confidence` |
| `core/normaliser.py` | `NormaliserConfig`, `Normaliser` |
| `core/house_model.py` | `HouseConfig`, `HouseAssessment`, `HouseModel` |
| `core/entity_routine.py` | `RoutineConfig`, `EntityRoutine`, `EntityRoutineModel` |
| `core/chain_model.py` | `ChainConfig`, `Chain`, `ChainModel` |
| `core/drift_detector.py` | `DriftConfig`, `DailySeries`, `CUSUMState`, `DriftDetector` |
| `core/health_tracker.py` | `HealthConfig`, `HealthTracker` |
| `core/alert_router.py` | `RouterConfig`, `DeliveryAction`, `AlertRouter` |
| `core/engine.py` | `EngineConfig`, `EntitySpec`, `Engine` |
| `tests/core/synth.py` | synthetic day generators |
| `tests/fixtures/*.jsonl`, `*.sidecar.json` | event fixtures |
| `scripts/replay.py` | fixture replay CLI |

Note for the spec: `core/engine.py` is an addition to the spec's module table. It holds the wiring the spec assigns to the coordinator, so the coordinator in Part 2 only translates Home Assistant calls into `Engine` calls.

---

### Task 1: Package scaffold and event types

**Files:**
- Create: `custom_components/behaviour_monitor/core/__init__.py`
- Create: `custom_components/behaviour_monitor/core/events.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_events.py`

**Interfaces:**
- Produces: `Category`, `EventKind`, `ACTIVITY_KINDS`, `UNAVAILABLE_STATES`, `ActivityEvent`, `HealthEvent`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_events.py
from datetime import datetime, timezone

from custom_components.behaviour_monitor.core.events import (
    ACTIVITY_KINDS,
    UNAVAILABLE_STATES,
    ActivityEvent,
    Category,
    EventKind,
    HealthEvent,
)

TS = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)


def test_activity_kinds_are_the_person_signals():
    assert ACTIVITY_KINDS == frozenset(
        {
            EventKind.PRESENCE,
            EventKind.OPEN,
            EventKind.APPLIANCE_ON,
            EventKind.LIGHT_ON,
            EventKind.GENERIC,
        }
    )


def test_activity_event_is_activity_property():
    ev = ActivityEvent("binary_sensor.k", Category.MOTION, EventKind.PRESENCE, "Kitchen", TS)
    assert ev.is_activity is True
    off = ActivityEvent("binary_sensor.d", Category.CONTACT, EventKind.CLOSE, "Hall", TS, duration_s=12.0)
    assert off.is_activity is False
    assert off.duration_s == 12.0


def test_panic_event_defaults_bypass_false_and_health_event_shape():
    ev = ActivityEvent("binary_sensor.p", Category.PANIC, EventKind.PANIC, "Hall", TS, bypass=True)
    assert ev.bypass is True
    he = HealthEvent("binary_sensor.p", Category.PANIC, "Hall", TS, available=False)
    assert he.available is False
    assert "unavailable" in UNAVAILABLE_STATES and "unknown" in UNAVAILABLE_STATES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.behaviour_monitor.core'`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/__init__.py
"""Pure Python core for Behaviour Monitor. No Home Assistant imports."""
```

```python
# tests/core/__init__.py
```

```python
# custom_components/behaviour_monitor/core/events.py
"""Typed events produced by the normaliser and consumed by every model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Category(str, Enum):
    """User-assigned entity category."""

    MOTION = "motion"
    CONTACT = "contact"
    PLUG = "plug"
    PANIC = "panic"
    LIGHT = "light"
    OTHER = "other"


class EventKind(str, Enum):
    """What a state change meant, per category rules."""

    PRESENCE = "presence"
    BURST_END = "burst_end"
    OPEN = "open"
    CLOSE = "close"
    APPLIANCE_ON = "appliance_on"
    APPLIANCE_OFF = "appliance_off"
    PANIC = "panic"
    PANIC_RELEASE = "panic_release"
    LIGHT_ON = "light_on"
    LIGHT_OFF = "light_off"
    GENERIC = "generic"


ACTIVITY_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.PRESENCE,
        EventKind.OPEN,
        EventKind.APPLIANCE_ON,
        EventKind.LIGHT_ON,
        EventKind.GENERIC,
    }
)
"""Kinds that count as the person doing something."""

UNAVAILABLE_STATES: frozenset[str] = frozenset({"unavailable", "unknown"})


@dataclass(frozen=True)
class ActivityEvent:
    """A category-aware event derived from one state change."""

    entity_id: str
    category: Category
    kind: EventKind
    room: str
    timestamp: datetime
    duration_s: float | None = None
    bypass: bool = False

    @property
    def is_activity(self) -> bool:
        """True when this event is evidence of the occupant acting."""
        return self.kind in ACTIVITY_KINDS


@dataclass(frozen=True)
class HealthEvent:
    """An availability transition for a monitored entity."""

    entity_id: str
    category: Category
    room: str
    timestamp: datetime
    available: bool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_events.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core tests/core
git commit -m "feat(core): event types and category enums"
```

---

### Task 2: Alert types

**Files:**
- Create: `custom_components/behaviour_monitor/core/alerts.py`
- Create: `tests/core/test_alerts.py`

**Interfaces:**
- Produces: `AlertClass`, `Severity`, `SEVERITY_ORDER`, `Severity.bump()`, `Severity.at_least()`, `Alert` with `key` property and `to_dict()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_alerts.py
from datetime import datetime, timezone

from custom_components.behaviour_monitor.core.alerts import Alert, AlertClass, Severity

TS = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)


def test_severity_ordering_and_bump():
    assert Severity.LOW < Severity.MEDIUM < Severity.HIGH < Severity.CRITICAL
    assert Severity.LOW.bump() is Severity.MEDIUM
    assert Severity.CRITICAL.bump() is Severity.CRITICAL
    assert Severity.HIGH.at_least(Severity.MEDIUM) is True
    assert Severity.LOW.at_least(Severity.MEDIUM) is False


def test_alert_key_and_to_dict():
    a = Alert(AlertClass.WELFARE, "house", "inactivity", Severity.MEDIUM, "No activity", TS, {"ratio": 6.2})
    assert a.key == "welfare:house:inactivity"
    d = a.to_dict()
    assert d["class"] == "welfare"
    assert d["severity"] == "medium"
    assert d["raised_at"] == TS.isoformat()
    assert d["details"] == {"ratio": 6.2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_alerts.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/alerts.py
"""Alert value types shared by every model and the router."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import total_ordering
from typing import Any


class AlertClass(str, Enum):
    WELFARE = "welfare"
    HEALTH = "health"
    STATISTICAL = "statistical"


@total_ordering
class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def _rank(self) -> int:
        return SEVERITY_ORDER.index(self)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._rank() < other._rank()

    def bump(self) -> "Severity":
        """One level higher, capped at CRITICAL."""
        return SEVERITY_ORDER[min(self._rank() + 1, len(SEVERITY_ORDER) - 1)]

    def at_least(self, floor: "Severity") -> bool:
        return self._rank() >= floor._rank()


SEVERITY_ORDER: list[Severity] = [
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
]


@dataclass
class Alert:
    cls: AlertClass
    source: str
    kind: str
    severity: Severity
    explanation: str
    raised_at: datetime
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.cls.value}:{self.source}:{self.kind}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "class": self.cls.value,
            "source": self.source,
            "kind": self.kind,
            "severity": self.severity.value,
            "explanation": self.explanation,
            "raised_at": self.raised_at.isoformat(),
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Alert":
        return cls(
            cls=AlertClass(data["class"]),
            source=str(data["source"]),
            kind=str(data["kind"]),
            severity=Severity(data["severity"]),
            explanation=str(data.get("explanation", "")),
            raised_at=datetime.fromisoformat(data["raised_at"]),
            details=dict(data.get("details", {})),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_alerts.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/alerts.py tests/core/test_alerts.py
git commit -m "feat(core): Alert, AlertClass and ordered Severity"
```

---

### Task 3: Slot helpers

**Files:**
- Create: `custom_components/behaviour_monitor/core/slots.py`
- Create: `tests/core/test_slots.py`

**Interfaces:**
- Produces: `SLOTS = 168`, `slot_index(ts) -> int`, `slot_label(idx) -> str`, `median_mad(values) -> tuple[float, float]`, `is_weekend(d) -> bool`, `day_type(d) -> str`, `confidence(days_seen, learning_days) -> float`, `iso_day(d) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_slots.py
from datetime import date, datetime, timezone

from custom_components.behaviour_monitor.core.slots import (
    SLOTS,
    confidence,
    day_type,
    is_weekend,
    iso_day,
    median_mad,
    slot_index,
    slot_label,
)


def test_slot_index_is_weekday_times_24_plus_hour():
    mon_8 = datetime(2026, 9, 21, 8, 30, tzinfo=timezone.utc)  # Monday
    sun_23 = datetime(2026, 9, 27, 23, 0, tzinfo=timezone.utc)
    assert slot_index(mon_8) == 8
    assert slot_index(sun_23) == 167
    assert SLOTS == 168
    assert slot_label(8) == "Mon 08:00"
    assert slot_label(167) == "Sun 23:00"


def test_median_mad():
    assert median_mad([1, 2, 3, 4, 100]) == (3.0, 1.0)
    assert median_mad([]) == (0.0, 0.0)
    assert median_mad([5.0]) == (5.0, 0.0)


def test_weekend_and_confidence():
    assert is_weekend(date(2026, 9, 26)) is True
    assert day_type(date(2026, 9, 21)) == "weekday"
    assert day_type(date(2026, 9, 27)) == "weekend"
    assert confidence(7, 14) == 0.5
    assert confidence(20, 14) == 1.0
    assert confidence(0, 14) == 0.0
    assert iso_day(date(2026, 9, 21)) == "2026-09-21"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_slots.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/slots.py
"""Shared slot arithmetic and small statistics helpers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from statistics import median

SLOTS: int = 168
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def slot_index(ts: datetime) -> int:
    """Return weekday * 24 + hour for a local-time datetime."""
    return ts.weekday() * 24 + ts.hour


def slot_label(idx: int) -> str:
    return f"{_DAYS[idx // 24]} {idx % 24:02d}:00"


def median_mad(values: Iterable[float]) -> tuple[float, float]:
    """Median and median absolute deviation. (0.0, 0.0) for empty input."""
    vals = [float(v) for v in values]
    if not vals:
        return 0.0, 0.0
    med = float(median(vals))
    mad = float(median(abs(v - med) for v in vals))
    return med, mad


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def day_type(d: date) -> str:
    return "weekend" if is_weekend(d) else "weekday"


def confidence(days_seen: int, learning_days: int) -> float:
    if learning_days <= 0:
        return 1.0
    return max(0.0, min(1.0, days_seen / learning_days))


def iso_day(d: date) -> str:
    return d.isoformat()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_slots.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/slots.py tests/core/test_slots.py
git commit -m "feat(core): slot index and statistics helpers"
```

---

### Task 4: Normaliser for binary categories and health events

**Files:**
- Create: `custom_components/behaviour_monitor/core/normaliser.py`
- Create: `tests/core/test_normaliser.py`

**Interfaces:**
- Produces: `NormaliserConfig(motion_debounce_s=90.0, plug_margin_w=5.0, plug_min_samples=50, plug_reservoir=500)`, `Normaliser(config)` with `handle(entity_id, category, room, old_state, new_state, timestamp) -> list[ActivityEvent | HealthEvent]`, `flush(now) -> list[ActivityEvent]`, `forget(entity_id)`, `to_dict()`, `from_dict(data, config)`.
- This task covers motion, contact, panic, light, other and availability. Task 5 adds plugs.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_normaliser.py
from datetime import datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.events import (
    ActivityEvent,
    Category,
    EventKind,
    HealthEvent,
)
from custom_components.behaviour_monitor.core.normaliser import Normaliser, NormaliserConfig

T0 = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)


def _t(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _n() -> Normaliser:
    return Normaliser(NormaliserConfig())


def test_motion_rising_edge_is_presence_and_retrigger_is_merged():
    n = _n()
    ev = n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(0))
    assert [e.kind for e in ev] == [EventKind.PRESENCE]
    assert n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "off", _t(62)) == []
    # retrigger inside the 90 s window extends the burst
    assert n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(70)) == []
    assert n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "off", _t(132)) == []
    # next rise outside the window closes the old burst and opens a new one
    ev = n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(300))
    assert [e.kind for e in ev] == [EventKind.BURST_END, EventKind.PRESENCE]
    assert ev[0].duration_s == 132.0
    assert ev[0].timestamp == _t(132)


def test_flush_closes_a_burst_after_the_window():
    n = _n()
    n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(0))
    n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "off", _t(60))
    assert n.flush(_t(100)) == []
    out = n.flush(_t(151))
    assert [e.kind for e in out] == [EventKind.BURST_END]
    assert out[0].duration_s == 60.0
    assert n.flush(_t(200)) == []


def test_contact_open_close_with_duration():
    n = _n()
    ev = n.handle("binary_sensor.d", Category.CONTACT, "Hall", "off", "on", _t(0))
    assert ev[0].kind == EventKind.OPEN and ev[0].is_activity
    ev = n.handle("binary_sensor.d", Category.CONTACT, "Hall", "on", "off", _t(45))
    assert ev[0].kind == EventKind.CLOSE and ev[0].duration_s == 45.0 and not ev[0].is_activity


def test_panic_bypasses_and_release_is_recorded():
    n = _n()
    ev = n.handle("binary_sensor.p", Category.PANIC, "Hall", "off", "on", _t(0))
    assert ev[0].kind == EventKind.PANIC and ev[0].bypass is True
    ev = n.handle("binary_sensor.p", Category.PANIC, "Hall", "on", "off", _t(5))
    assert ev[0].kind == EventKind.PANIC_RELEASE and ev[0].bypass is False


def test_light_and_other():
    n = _n()
    assert n.handle("light.l", Category.LIGHT, "Lounge", "off", "on", _t(0))[0].kind == EventKind.LIGHT_ON
    assert n.handle("light.l", Category.LIGHT, "Lounge", "on", "off", _t(1))[0].kind == EventKind.LIGHT_OFF
    ev = n.handle("sensor.x", Category.OTHER, "Loft", "12", "13", _t(2))
    assert ev[0].kind == EventKind.GENERIC and ev[0].is_activity


def test_same_state_replay_emits_nothing():
    n = _n()
    assert n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "on", _t(0)) == []
    assert n.handle("sensor.x", Category.OTHER, "Loft", "12", "12", _t(0)) == []


def test_unavailable_transitions_are_health_not_activity():
    n = _n()
    ev = n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "unavailable", _t(0))
    assert ev == [HealthEvent("binary_sensor.k", Category.MOTION, "Kitchen", _t(0), available=False)]
    # coming back with state on is a restore, not the person
    ev = n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "unavailable", "on", _t(10))
    assert ev == [HealthEvent("binary_sensor.k", Category.MOTION, "Kitchen", _t(10), available=True)]
    # first ever state (old None) is also not activity
    ev = n.handle("binary_sensor.b", Category.MOTION, "Bath", None, "on", _t(20))
    assert ev == [HealthEvent("binary_sensor.b", Category.MOTION, "Bath", _t(20), available=True)]
    # repeated unavailable emits nothing
    n.handle("binary_sensor.b", Category.MOTION, "Bath", "on", "unavailable", _t(30))
    assert n.handle("binary_sensor.b", Category.MOTION, "Bath", "unavailable", "unknown", _t(31)) == []


def test_round_trip_serialisation_keeps_burst_state():
    n = _n()
    n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "off", "on", _t(0))
    n.handle("binary_sensor.k", Category.MOTION, "Kitchen", "on", "off", _t(60))
    n2 = Normaliser.from_dict(n.to_dict(), NormaliserConfig())
    out = n2.flush(_t(151))
    assert out and out[0].kind == EventKind.BURST_END
    assert Normaliser.from_dict({"garbage": 1}, NormaliserConfig()).flush(_t(0)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_normaliser.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/normaliser.py
"""Turn raw state changes into typed ActivityEvent / HealthEvent values."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Any

from .events import ActivityEvent, Category, EventKind, HealthEvent, UNAVAILABLE_STATES

_ON = "on"
_OFF = "off"


@dataclass(frozen=True)
class NormaliserConfig:
    motion_debounce_s: float = 90.0
    plug_margin_w: float = 5.0
    plug_min_samples: int = 50
    plug_reservoir: int = 500


@dataclass
class _Burst:
    entity_id: str
    room: str
    start: datetime
    last_rise: datetime
    last_fall: datetime | None = None


@dataclass
class _PlugState:
    reservoir: deque[float]
    on_since: datetime | None = None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class Normaliser:
    """Stateful per-entity normalisation. One instance per site."""

    def __init__(self, config: NormaliserConfig) -> None:
        self._cfg = config
        self._bursts: dict[str, _Burst] = {}
        self._open_since: dict[str, datetime] = {}
        self._plugs: dict[str, _PlugState] = {}
        self._available: dict[str, bool] = {}

    # ------------------------------------------------------------------ public

    def handle(
        self,
        entity_id: str,
        category: Category,
        room: str,
        old_state: str | None,
        new_state: str,
        timestamp: datetime,
    ) -> list[ActivityEvent | HealthEvent]:
        new_unavail = new_state in UNAVAILABLE_STATES
        old_unavail = old_state is None or old_state in UNAVAILABLE_STATES

        if new_unavail:
            if self._available.get(entity_id, True):
                self._available[entity_id] = False
                return [HealthEvent(entity_id, category, room, timestamp, available=False)]
            return []

        out: list[ActivityEvent | HealthEvent] = []
        if not self._available.get(entity_id, True) or old_state is None:
            self._available[entity_id] = True
            out.append(HealthEvent(entity_id, category, room, timestamp, available=True))
        if old_unavail:
            # restore of a real state is not the person acting
            return out
        if old_state == new_state:
            return out

        handler = {
            Category.MOTION: self._motion,
            Category.CONTACT: self._contact,
            Category.PLUG: self._plug,
            Category.PANIC: self._panic,
            Category.LIGHT: self._light,
            Category.OTHER: self._other,
        }[category]
        out.extend(handler(entity_id, room, old_state, new_state, timestamp))
        return out

    def flush(self, now: datetime) -> list[ActivityEvent]:
        """Close motion bursts whose last fall is older than the debounce window."""
        out: list[ActivityEvent] = []
        for eid in list(self._bursts):
            b = self._bursts[eid]
            if b.last_fall is None:
                continue
            if (now - b.last_fall).total_seconds() > self._cfg.motion_debounce_s:
                out.append(self._close_burst(b))
                del self._bursts[eid]
        return out

    def forget(self, entity_id: str) -> None:
        for store in (self._bursts, self._open_since, self._plugs, self._available):
            store.pop(entity_id, None)  # type: ignore[arg-type]

    # -------------------------------------------------------------- categories

    def _motion(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        out: list[ActivityEvent] = []
        burst = self._bursts.get(eid)
        if new == _ON:
            if burst is not None:
                if (ts - burst.last_rise).total_seconds() <= self._cfg.motion_debounce_s:
                    burst.last_rise = ts
                    burst.last_fall = None
                    return []
                out.append(self._close_burst(burst))
            self._bursts[eid] = _Burst(eid, room, ts, ts)
            out.append(ActivityEvent(eid, Category.MOTION, EventKind.PRESENCE, room, ts))
        elif new == _OFF and burst is not None:
            burst.last_fall = ts
        return out

    def _close_burst(self, b: _Burst) -> ActivityEvent:
        end = b.last_fall or b.last_rise
        return ActivityEvent(
            b.entity_id,
            Category.MOTION,
            EventKind.BURST_END,
            b.room,
            end,
            duration_s=(end - b.start).total_seconds(),
        )

    def _contact(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        if new == _ON:
            self._open_since[eid] = ts
            return [ActivityEvent(eid, Category.CONTACT, EventKind.OPEN, room, ts)]
        if new == _OFF:
            opened = self._open_since.pop(eid, None)
            dur = (ts - opened).total_seconds() if opened else None
            return [ActivityEvent(eid, Category.CONTACT, EventKind.CLOSE, room, ts, duration_s=dur)]
        return []

    def _panic(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        if new == _ON:
            return [ActivityEvent(eid, Category.PANIC, EventKind.PANIC, room, ts, bypass=True)]
        if new == _OFF:
            return [ActivityEvent(eid, Category.PANIC, EventKind.PANIC_RELEASE, room, ts)]
        return []

    def _light(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        if new == _ON:
            return [ActivityEvent(eid, Category.LIGHT, EventKind.LIGHT_ON, room, ts)]
        if new == _OFF:
            return [ActivityEvent(eid, Category.LIGHT, EventKind.LIGHT_OFF, room, ts)]
        return []

    def _other(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        return [ActivityEvent(eid, Category.OTHER, EventKind.GENERIC, room, ts)]

    def _plug(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        return []  # Task 5

    # ------------------------------------------------------------ persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "bursts": {
                eid: {
                    "room": b.room,
                    "start": b.start.isoformat(),
                    "last_rise": b.last_rise.isoformat(),
                    "last_fall": b.last_fall.isoformat() if b.last_fall else None,
                }
                for eid, b in self._bursts.items()
            },
            "open_since": {eid: ts.isoformat() for eid, ts in self._open_since.items()},
            "plugs": {
                eid: {
                    "reservoir": list(p.reservoir),
                    "on_since": p.on_since.isoformat() if p.on_since else None,
                }
                for eid, p in self._plugs.items()
            },
            "available": dict(self._available),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: NormaliserConfig) -> "Normaliser":
        n = cls(config)
        try:
            for eid, b in data.get("bursts", {}).items():
                start, rise = _parse_dt(b.get("start")), _parse_dt(b.get("last_rise"))
                if start and rise:
                    n._bursts[eid] = _Burst(eid, str(b.get("room", "")), start, rise, _parse_dt(b.get("last_fall")))
            for eid, ts in data.get("open_since", {}).items():
                if (dt := _parse_dt(ts)) is not None:
                    n._open_since[eid] = dt
            for eid, p in data.get("plugs", {}).items():
                res: deque[float] = deque(maxlen=config.plug_reservoir)
                res.extend(float(v) for v in p.get("reservoir", []))
                n._plugs[eid] = _PlugState(res, _parse_dt(p.get("on_since")))
            n._available = {k: bool(v) for k, v in data.get("available", {}).items()}
        except (AttributeError, TypeError, ValueError):
            return cls(config)
        return n
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_normaliser.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/normaliser.py tests/core/test_normaliser.py
git commit -m "feat(core): normaliser for motion, contact, panic, light, other and availability"
```

---

### Task 5: Normaliser plug rules with learned idle level

**Files:**
- Modify: `custom_components/behaviour_monitor/core/normaliser.py` (replace `_plug`)
- Modify: `tests/core/test_normaliser.py` (append)

**Interfaces:**
- Produces: `Normaliser.idle_level(entity_id) -> float | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_normaliser.py`:

```python
def test_numeric_plug_learns_idle_and_fires_on_rise():
    n = Normaliser(NormaliserConfig(plug_min_samples=10, plug_margin_w=5.0))
    # TV on standby at ~85 W: idle should settle near 85, not 0
    prev = "0"
    for i in range(20):
        val = f"{85 + (i % 3)}"
        assert n.handle("sensor.tv", Category.PLUG, "Backroom", prev, val, _t(i)) == []
        prev = val
    assert 84.5 <= n.idle_level("sensor.tv") <= 86.0
    ev = n.handle("sensor.tv", Category.PLUG, "Backroom", prev, "120", _t(30))
    assert [e.kind for e in ev] == [EventKind.APPLIANCE_ON]
    assert n.handle("sensor.tv", Category.PLUG, "Backroom", "120", "125", _t(31)) == []
    ev = n.handle("sensor.tv", Category.PLUG, "Backroom", "125", "86", _t(90))
    assert ev[0].kind == EventKind.APPLIANCE_OFF and ev[0].duration_s == 60.0


def test_numeric_plug_before_min_samples_uses_minimum_seen():
    n = Normaliser(NormaliserConfig(plug_min_samples=10, plug_margin_w=5.0))
    assert n.handle("sensor.kettle", Category.PLUG, "Kitchen", None, "0", _t(0))  # health only
    assert n.handle("sensor.kettle", Category.PLUG, "Kitchen", "0", "0.5", _t(1)) == []
    ev = n.handle("sensor.kettle", Category.PLUG, "Kitchen", "0.5", "2800", _t(2))
    assert ev[0].kind == EventKind.APPLIANCE_ON


def test_switch_plug_uses_on_off():
    n = _n()
    assert n.handle("switch.p", Category.PLUG, "Loft", "off", "on", _t(0))[0].kind == EventKind.APPLIANCE_ON
    ev = n.handle("switch.p", Category.PLUG, "Loft", "on", "off", _t(30))
    assert ev[0].kind == EventKind.APPLIANCE_OFF and ev[0].duration_s == 30.0


def test_non_numeric_non_switch_plug_state_is_ignored():
    n = _n()
    assert n.handle("sensor.p", Category.PLUG, "Loft", "abc", "def", _t(0)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_normaliser.py -v -k plug`
Expected: FAIL, `AttributeError: 'Normaliser' object has no attribute 'idle_level'` and empty event lists

- [ ] **Step 3: Write minimal implementation**

Replace the `_plug` stub in `normaliser.py` with:

```python
    def _plug(
        self, eid: str, room: str, old: str, new: str, ts: datetime
    ) -> list[ActivityEvent]:
        if new in (_ON, _OFF):
            return self._plug_switch(eid, room, new, ts)
        try:
            value = float(new)
        except (TypeError, ValueError):
            return []
        state = self._plugs.get(eid)
        if state is None:
            state = _PlugState(deque(maxlen=self._cfg.plug_reservoir))
            self._plugs[eid] = state
        state.reservoir.append(value)
        idle = self._idle(state)
        threshold = idle + self._cfg.plug_margin_w
        if state.on_since is None and value > threshold:
            state.on_since = ts
            return [ActivityEvent(eid, Category.PLUG, EventKind.APPLIANCE_ON, room, ts)]
        if state.on_since is not None and value <= threshold:
            dur = (ts - state.on_since).total_seconds()
            state.on_since = None
            return [ActivityEvent(eid, Category.PLUG, EventKind.APPLIANCE_OFF, room, ts, duration_s=dur)]
        return []

    def _plug_switch(self, eid: str, room: str, new: str, ts: datetime) -> list[ActivityEvent]:
        state = self._plugs.setdefault(eid, _PlugState(deque(maxlen=self._cfg.plug_reservoir)))
        if new == _ON and state.on_since is None:
            state.on_since = ts
            return [ActivityEvent(eid, Category.PLUG, EventKind.APPLIANCE_ON, room, ts)]
        if new == _OFF and state.on_since is not None:
            dur = (ts - state.on_since).total_seconds()
            state.on_since = None
            return [ActivityEvent(eid, Category.PLUG, EventKind.APPLIANCE_OFF, room, ts, duration_s=dur)]
        return []

    def _idle(self, state: _PlugState) -> float:
        vals = sorted(state.reservoir)
        if len(vals) < self._cfg.plug_min_samples:
            return vals[0] if vals else 0.0
        quintile = vals[: max(1, len(vals) // 5)]
        return float(median(quintile))

    def idle_level(self, entity_id: str) -> float | None:
        state = self._plugs.get(entity_id)
        return self._idle(state) if state and state.reservoir else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_normaliser.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/normaliser.py tests/core/test_normaliser.py
git commit -m "feat(core): plug normalisation with learned idle level"
```

---

### Task 6: House activity model

**Files:**
- Create: `custom_components/behaviour_monitor/core/house_model.py`
- Create: `tests/core/test_house_model.py`

**Interfaces:**
- Consumes: `ActivityEvent`, `slot_index`, `median_mad`, `confidence`, `iso_day`.
- Produces: `HouseConfig`, `HouseAssessment(gap_s, expected_s, ratio, severity, degraded, contributing)`, `HouseModel` with `record(event)`, `evaluate(now, live_fraction=1.0) -> HouseAssessment`, `expected_gap(now) -> float | None`, `last_activity`, `last_room`, `confidence(now)`, `rooms_visited(day) -> set[str]`, `prune(before: date)`, `to_dict`, `from_dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_house_model.py
from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import Severity
from custom_components.behaviour_monitor.core.events import ActivityEvent, Category, EventKind
from custom_components.behaviour_monitor.core.house_model import HouseConfig, HouseModel

MON = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def _ev(ts: datetime, room: str = "Kitchen", kind: EventKind = EventKind.PRESENCE) -> ActivityEvent:
    return ActivityEvent("binary_sensor.x", Category.MOTION, kind, room, ts)


def _train(model: HouseModel, days: int = 14, gap_min: int = 5) -> None:
    """Every day, events every gap_min minutes from 09:00 to 10:00."""
    for d in range(days):
        base = MON + timedelta(days=d)
        for m in range(0, 61, gap_min):
            model.record(_ev(base + timedelta(minutes=m)))


def test_non_activity_kinds_are_ignored():
    m = HouseModel(HouseConfig())
    m.record(_ev(MON, kind=EventKind.CLOSE))
    assert m.last_activity is None


def test_learns_expected_gap_for_slot():
    m = HouseModel(HouseConfig())
    _train(m)
    assert m.expected_gap(MON + timedelta(days=14, minutes=30)) == 300.0
    assert m.expected_gap(MON + timedelta(days=14, hours=5)) is None
    assert m.confidence(MON + timedelta(days=14)) == 1.0


def test_severity_ladder_and_sustain():
    m = HouseModel(HouseConfig(sustain_polls=2))
    _train(m)
    now = MON + timedelta(days=14)
    m.record(_ev(now))
    a = m.evaluate(now + timedelta(minutes=10))  # ratio 2
    assert a.severity is None and a.ratio == 2.0
    a = m.evaluate(now + timedelta(minutes=20))  # ratio 4 -> low, first poll
    assert a.severity is None
    a = m.evaluate(now + timedelta(minutes=21))  # second poll sustains
    assert a.severity is Severity.LOW
    a = m.evaluate(now + timedelta(minutes=35))  # ratio 7 -> medium after two polls
    a = m.evaluate(now + timedelta(minutes=36))
    assert a.severity is Severity.MEDIUM
    a = m.evaluate(now + timedelta(minutes=61))
    a = m.evaluate(now + timedelta(minutes=62))
    assert a.severity is Severity.HIGH
    # one poll below threshold drops one level
    m.record(_ev(now + timedelta(minutes=63)))
    a = m.evaluate(now + timedelta(minutes=64))
    assert a.severity is Severity.MEDIUM


def test_floor_prevents_tiny_median_blowing_up_ratio():
    m = HouseModel(HouseConfig(floor_s=300.0))
    _train(m, gap_min=1)
    now = MON + timedelta(days=14)
    m.record(_ev(now))
    a = m.evaluate(now + timedelta(minutes=5))
    assert a.expected_s == 60.0 and a.ratio == 1.0


def test_unknown_slot_reports_no_severity():
    m = HouseModel(HouseConfig())
    _train(m)
    now = MON + timedelta(days=14, hours=6)
    m.record(_ev(now))
    a = m.evaluate(now + timedelta(hours=3))
    assert a.severity is None and a.expected_s is None


def test_degraded_when_live_fraction_low():
    m = HouseModel(HouseConfig(min_live_fraction=0.5))
    _train(m)
    now = MON + timedelta(days=14)
    m.record(_ev(now))
    for _ in range(2):
        a = m.evaluate(now + timedelta(hours=2), live_fraction=0.4)
    assert a.degraded is True and a.severity is None


def test_rooms_visited_and_prune():
    m = HouseModel(HouseConfig(window_days=28))
    m.record(_ev(MON, room="Kitchen"))
    m.record(_ev(MON + timedelta(minutes=1), room="Bath"))
    assert m.rooms_visited(date(2026, 9, 21)) == {"Kitchen", "Bath"}
    m.prune(date(2026, 9, 22))
    assert m.rooms_visited(date(2026, 9, 21)) == set()


def test_round_trip():
    m = HouseModel(HouseConfig())
    _train(m)
    m2 = HouseModel.from_dict(m.to_dict(), HouseConfig())
    assert m2.expected_gap(MON + timedelta(days=14, minutes=30)) == 300.0
    assert m2.last_activity == m.last_activity
    assert HouseModel.from_dict({"bad": True}, HouseConfig()).last_activity is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_house_model.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/house_model.py
"""Whole-house activity gap model. The only sole source of welfare alerts."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .alerts import Severity
from .events import ActivityEvent
from .slots import SLOTS, confidence, iso_day, median_mad, slot_index

MIN_GAPS_PER_SLOT = 8
_GAPS_PER_SLOT = 400


@dataclass(frozen=True)
class HouseConfig:
    learning_days: int = 14
    window_days: int = 28
    low_ratio: float = 3.0
    medium_ratio: float = 6.0
    high_ratio: float = 12.0
    floor_s: float = 300.0
    min_live_fraction: float = 0.5
    sustain_polls: int = 2


@dataclass(frozen=True)
class HouseAssessment:
    gap_s: float | None
    expected_s: float | None
    ratio: float | None
    severity: Severity | None
    degraded: bool
    last_room: str | None


class HouseModel:
    def __init__(self, config: HouseConfig) -> None:
        self._cfg = config
        self._gaps: list[deque[tuple[str, float]]] = [
            deque(maxlen=_GAPS_PER_SLOT) for _ in range(SLOTS)
        ]
        self._last_activity: datetime | None = None
        self._last_room: str | None = None
        self._days_seen: set[str] = set()
        self._rooms_by_day: dict[str, set[str]] = {}
        self._current: Severity | None = None
        self._pending: Severity | None = None
        self._pending_count = 0
        self._below_count = 0

    # ------------------------------------------------------------ properties

    @property
    def last_activity(self) -> datetime | None:
        return self._last_activity

    @property
    def last_room(self) -> str | None:
        return self._last_room

    # ------------------------------------------------------------- recording

    def record(self, event: ActivityEvent) -> None:
        if not event.is_activity:
            return
        day = iso_day(event.timestamp.date())
        self._days_seen.add(day)
        self._rooms_by_day.setdefault(day, set()).add(event.room)
        if self._last_activity is not None and event.timestamp > self._last_activity:
            gap = (event.timestamp - self._last_activity).total_seconds()
            self._gaps[slot_index(event.timestamp)].append((day, gap))
        if self._last_activity is None or event.timestamp >= self._last_activity:
            self._last_activity = event.timestamp
            self._last_room = event.room

    # --------------------------------------------------------------- queries

    def expected_gap(self, now: datetime) -> float | None:
        gaps = self._gaps[slot_index(now)]
        if len(gaps) < MIN_GAPS_PER_SLOT:
            return None
        med, _ = median_mad(g for _, g in gaps)
        return med

    def confidence(self, now: datetime) -> float:
        return confidence(len(self._days_seen), self._cfg.learning_days)

    def rooms_visited(self, day: date) -> set[str]:
        return set(self._rooms_by_day.get(iso_day(day), set()))

    def evaluate(self, now: datetime, live_fraction: float = 1.0) -> HouseAssessment:
        degraded = live_fraction < self._cfg.min_live_fraction
        gap = (now - self._last_activity).total_seconds() if self._last_activity else None
        expected = self.expected_gap(now)
        ratio = None
        raw: Severity | None = None
        if gap is not None and expected is not None and not degraded:
            ratio = gap / max(expected, self._cfg.floor_s)
            if ratio >= self._cfg.high_ratio:
                raw = Severity.HIGH
            elif ratio >= self._cfg.medium_ratio:
                raw = Severity.MEDIUM
            elif ratio >= self._cfg.low_ratio:
                raw = Severity.LOW
        self._sustain(raw)
        return HouseAssessment(gap, expected, ratio, self._current, degraded, self._last_room)

    def _sustain(self, raw: Severity | None) -> None:
        if raw is not None and (self._current is None or raw > self._current):
            if raw == self._pending:
                self._pending_count += 1
            else:
                self._pending, self._pending_count = raw, 1
            self._below_count = 0
            if self._pending_count >= self._cfg.sustain_polls:
                self._current, self._pending, self._pending_count = raw, None, 0
        elif raw is not None and raw == self._current:
            self._pending, self._pending_count, self._below_count = None, 0, 0
        else:
            self._pending, self._pending_count = None, 0
            if self._current is not None:
                self._below_count += 1
                if self._below_count >= 1:
                    idx = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL].index(self._current)
                    self._current = None if idx == 0 else [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL][idx - 1]
                    if raw is not None and self._current is not None and raw < self._current:
                        self._current = raw
                    self._below_count = 0

    # --------------------------------------------------------------- window

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        for gaps in self._gaps:
            kept = [(d, g) for d, g in gaps if d >= cutoff]
            gaps.clear()
            gaps.extend(kept)
        self._days_seen = {d for d in self._days_seen if d >= cutoff}
        self._rooms_by_day = {d: r for d, r in self._rooms_by_day.items() if d >= cutoff}

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "gaps": [list(g) for g in self._gaps],
            "last_activity": self._last_activity.isoformat() if self._last_activity else None,
            "last_room": self._last_room,
            "days_seen": sorted(self._days_seen),
            "rooms_by_day": {d: sorted(r) for d, r in self._rooms_by_day.items()},
            "current": self._current.value if self._current else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: HouseConfig) -> "HouseModel":
        m = cls(config)
        try:
            gaps = data["gaps"]
            for i in range(min(SLOTS, len(gaps))):
                m._gaps[i].extend((str(d), float(g)) for d, g in gaps[i])
            la = data.get("last_activity")
            m._last_activity = datetime.fromisoformat(la) if la else None
            m._last_room = data.get("last_room")
            m._days_seen = set(data.get("days_seen", []))
            m._rooms_by_day = {d: set(r) for d, r in data.get("rooms_by_day", {}).items()}
            cur = data.get("current")
            m._current = Severity(cur) if cur else None
        except (KeyError, TypeError, ValueError):
            return cls(config)
        return m
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_house_model.py -v`
Expected: 8 passed. If `test_severity_ladder_and_sustain` fails on the drop step, check `_sustain`: a poll with `raw` below `_current` must lower `_current` by exactly one level, then adopt `raw` if `raw` is lower still.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/house_model.py tests/core/test_house_model.py
git commit -m "feat(core): house activity model with sustained severity ladder"
```

---

### Task 7: Entity routine model

**Files:**
- Create: `custom_components/behaviour_monitor/core/entity_routine.py`
- Create: `tests/core/test_entity_routine.py`

**Interfaces:**
- Produces: `RoutineConfig(learning_days=14, window_days=28, window_min_fraction=0.7, min_window_days=3)`, `EntityRoutine`, `EntityRoutineModel` with `add(entity_id, category, room)`, `remove(entity_id)`, `record(event)`, `evaluate(now) -> list[Alert]`, `expected_windows(entity_id, weekday) -> list[int]`, `longest_gap(entity_id) -> float | None`, `last_event(entity_id) -> datetime | None`, `daily_counts(day) -> dict[str, int]`, `daily_duration_medians(day) -> dict[str, float]`, `confidence(now)`, `prune(before)`, `to_dict`, `from_dict`, `entity_ids`.
- Routine notes are `Alert(STATISTICAL, entity_id, "routine_missed", LOW)` with `details={"hour": h, "room": room}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_entity_routine.py
from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import AlertClass, Severity
from custom_components.behaviour_monitor.core.entity_routine import (
    EntityRoutineModel,
    RoutineConfig,
)
from custom_components.behaviour_monitor.core.events import ActivityEvent, Category, EventKind

MON = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
KETTLE = "sensor.kettle"


def _model() -> EntityRoutineModel:
    m = EntityRoutineModel(RoutineConfig())
    m.add(KETTLE, Category.PLUG, "Kitchen")
    m.add("binary_sensor.front", Category.CONTACT, "Hall")
    return m


def _kettle(ts: datetime, kind: EventKind = EventKind.APPLIANCE_ON) -> ActivityEvent:
    return ActivityEvent(KETTLE, Category.PLUG, kind, "Kitchen", ts)


def _train(m: EntityRoutineModel, days: int = 14, hour: int = 8, skip: set[int] = frozenset()) -> None:
    for d in range(days):
        if d in skip:
            continue
        m.record(_kettle(MON + timedelta(days=d, hours=hour, minutes=5)))


def test_expected_window_learned_when_fired_on_most_days():
    m = _model()
    _train(m, days=14)
    assert m.expected_windows(KETTLE, weekday=0) == []  # only 2 Mondays seen; min is 3
    _train(m, days=21)  # now 3 Mondays
    assert m.expected_windows(KETTLE, weekday=0) == [8]
    assert m.expected_windows("binary_sensor.front", weekday=0) == []


def test_window_needs_fraction_of_days():
    m = _model()
    # Mondays only on 2 of 4 weeks -> 50% < 70%
    _train(m, days=28, skip={7, 21})
    assert m.expected_windows(KETTLE, weekday=0) == []
    assert m.expected_windows(KETTLE, weekday=1) == [8]


def test_missed_window_raises_routine_note_until_event_arrives():
    m = _model()
    _train(m, days=28)
    day = MON + timedelta(days=28)  # Monday
    assert m.evaluate(day + timedelta(hours=8, minutes=30)) == []  # window still open
    notes = m.evaluate(day + timedelta(hours=9, minutes=1))
    assert len(notes) == 1
    n = notes[0]
    assert n.cls is AlertClass.STATISTICAL and n.severity is Severity.LOW
    assert n.source == KETTLE and n.kind == "routine_missed" and n.details["hour"] == 8
    assert "Kitchen" in n.explanation
    m.record(_kettle(day + timedelta(hours=9, minutes=30)))
    assert m.evaluate(day + timedelta(hours=9, minutes=31)) == []


def test_longest_gap_last_event_and_daily_counts():
    m = _model()
    _train(m, days=3)
    assert m.longest_gap(KETTLE) == 86400.0
    assert m.longest_gap("binary_sensor.front") is None
    assert m.last_event(KETTLE) == MON + timedelta(days=2, hours=8, minutes=5)
    assert m.daily_counts(date(2026, 9, 22)) == {KETTLE: 1, "binary_sensor.front": 0}


def test_duration_medians_per_day():
    m = _model()
    for i, dur in enumerate((10.0, 30.0, 20.0)):
        m.record(ActivityEvent("binary_sensor.front", Category.CONTACT, EventKind.CLOSE, "Hall",
                               MON + timedelta(hours=i), duration_s=dur))
    assert m.daily_duration_medians(date(2026, 9, 21)) == {"binary_sensor.front": 20.0}


def test_prune_remove_and_round_trip():
    m = _model()
    _train(m, days=28)
    m.prune(date(2026, 10, 12))
    assert m.daily_counts(date(2026, 9, 21))[KETTLE] == 0
    m2 = EntityRoutineModel.from_dict(m.to_dict(), RoutineConfig())
    assert set(m2.entity_ids) == {KETTLE, "binary_sensor.front"}
    assert m2.last_event(KETTLE) == m.last_event(KETTLE)
    m2.remove(KETTLE)
    assert KETTLE not in m2.entity_ids
    assert EntityRoutineModel.from_dict({"x": 1}, RoutineConfig()).entity_ids == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_entity_routine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/entity_routine.py
"""Per-entity slot statistics, expected windows and routine notes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import median
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent, Category
from .slots import SLOTS, confidence, iso_day, slot_index


@dataclass(frozen=True)
class RoutineConfig:
    learning_days: int = 14
    window_days: int = 28
    window_min_fraction: float = 0.7
    min_window_days: int = 3


@dataclass
class EntityRoutine:
    entity_id: str
    category: Category
    room: str
    slot_days: list[dict[str, int]] = field(default_factory=lambda: [dict() for _ in range(SLOTS)])
    durations: dict[str, list[float]] = field(default_factory=dict)
    last_event: datetime | None = None
    longest_gap_s: float | None = None
    days_seen: set[str] = field(default_factory=set)
    first_observation: datetime | None = None

    def record(self, event: ActivityEvent) -> None:
        day = iso_day(event.timestamp.date())
        if event.duration_s is not None:
            self.durations.setdefault(day, []).append(float(event.duration_s))
        if not event.is_activity:
            return
        self.days_seen.add(day)
        slot = self.slot_days[slot_index(event.timestamp)]
        slot[day] = slot.get(day, 0) + 1
        if self.first_observation is None:
            self.first_observation = event.timestamp
        if self.last_event is not None:
            gap = (event.timestamp - self.last_event).total_seconds()
            if gap > 0 and (self.longest_gap_s is None or gap > self.longest_gap_s):
                self.longest_gap_s = gap
        if self.last_event is None or event.timestamp > self.last_event:
            self.last_event = event.timestamp

    def daily_count(self, day: date) -> int:
        d = iso_day(day)
        w = day.weekday()
        return sum(self.slot_days[w * 24 + h].get(d, 0) for h in range(24))

    def expected_windows(self, weekday: int, cfg: RoutineConfig) -> list[int]:
        days_for_weekday = {d for d in self.days_seen if date.fromisoformat(d).weekday() == weekday}
        if len(days_for_weekday) < cfg.min_window_days:
            return []
        out: list[int] = []
        for h in range(24):
            fired = sum(1 for d in days_for_weekday if self.slot_days[weekday * 24 + h].get(d, 0) > 0)
            if fired / len(days_for_weekday) >= cfg.window_min_fraction:
                out.append(h)
        return out

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        for slot in self.slot_days:
            for d in [d for d in slot if d < cutoff]:
                del slot[d]
        self.durations = {d: v for d, v in self.durations.items() if d >= cutoff}
        self.days_seen = {d for d in self.days_seen if d >= cutoff}

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "category": self.category.value,
            "room": self.room,
            "slot_days": self.slot_days,
            "durations": self.durations,
            "last_event": self.last_event.isoformat() if self.last_event else None,
            "longest_gap_s": self.longest_gap_s,
            "days_seen": sorted(self.days_seen),
            "first_observation": self.first_observation.isoformat() if self.first_observation else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityRoutine":
        r = cls(str(data["entity_id"]), Category(data["category"]), str(data.get("room", "")))
        slots = data.get("slot_days", [])
        for i in range(min(SLOTS, len(slots))):
            r.slot_days[i] = {str(d): int(c) for d, c in slots[i].items()}
        r.durations = {str(d): [float(x) for x in v] for d, v in data.get("durations", {}).items()}
        le = data.get("last_event")
        r.last_event = datetime.fromisoformat(le) if le else None
        lg = data.get("longest_gap_s")
        r.longest_gap_s = float(lg) if lg is not None else None
        r.days_seen = set(data.get("days_seen", []))
        fo = data.get("first_observation")
        r.first_observation = datetime.fromisoformat(fo) if fo else None
        return r


class EntityRoutineModel:
    def __init__(self, config: RoutineConfig) -> None:
        self._cfg = config
        self._entities: dict[str, EntityRoutine] = {}

    # ----------------------------------------------------------- membership

    def add(self, entity_id: str, category: Category, room: str) -> None:
        if entity_id in self._entities:
            self._entities[entity_id].room = room
            self._entities[entity_id].category = category
        else:
            self._entities[entity_id] = EntityRoutine(entity_id, category, room)

    def remove(self, entity_id: str) -> None:
        self._entities.pop(entity_id, None)

    @property
    def entity_ids(self) -> list[str]:
        return list(self._entities)

    def get(self, entity_id: str) -> EntityRoutine | None:
        return self._entities.get(entity_id)

    # ------------------------------------------------------------ recording

    def record(self, event: ActivityEvent) -> None:
        r = self._entities.get(event.entity_id)
        if r is not None:
            r.record(event)

    # -------------------------------------------------------------- queries

    def expected_windows(self, entity_id: str, weekday: int) -> list[int]:
        r = self._entities.get(entity_id)
        return r.expected_windows(weekday, self._cfg) if r else []

    def longest_gap(self, entity_id: str) -> float | None:
        r = self._entities.get(entity_id)
        return r.longest_gap_s if r else None

    def last_event(self, entity_id: str) -> datetime | None:
        r = self._entities.get(entity_id)
        return r.last_event if r else None

    def daily_counts(self, day: date) -> dict[str, int]:
        return {eid: r.daily_count(day) for eid, r in self._entities.items()}

    def daily_duration_medians(self, day: date) -> dict[str, float]:
        d = iso_day(day)
        return {
            eid: float(median(r.durations[d]))
            for eid, r in self._entities.items()
            if r.durations.get(d)
        }

    def confidence(self, now: datetime) -> float:
        if not self._entities:
            return 0.0
        return sum(confidence(len(r.days_seen), self._cfg.learning_days) for r in self._entities.values()) / len(self._entities)

    def evaluate(self, now: datetime) -> list[Alert]:
        """Routine notes for windows that closed today without an event."""
        out: list[Alert] = []
        today = now.date()
        for eid, r in self._entities.items():
            for hour in r.expected_windows(today.weekday(), self._cfg):
                if hour >= now.hour:
                    continue  # window not yet closed
                if r.slot_days[today.weekday() * 24 + hour].get(iso_day(today), 0) > 0:
                    continue
                if r.last_event is not None and r.last_event.date() == today and r.last_event.hour > hour:
                    continue  # fired later today; the miss is stale
                out.append(
                    Alert(
                        AlertClass.STATISTICAL,
                        eid,
                        "routine_missed",
                        Severity.LOW,
                        f"{r.room}: {eid} usually fires around {hour:02d}:00 on this weekday but has not today",
                        now,
                        {"hour": hour, "room": r.room},
                    )
                )
        return out

    def prune(self, before: date) -> None:
        for r in self._entities.values():
            r.prune(before)

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {"entities": {eid: r.to_dict() for eid, r in self._entities.items()}}

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: RoutineConfig) -> "EntityRoutineModel":
        m = cls(config)
        try:
            for eid, rd in data.get("entities", {}).items():
                m._entities[eid] = EntityRoutine.from_dict(rd)
        except (KeyError, TypeError, ValueError):
            return cls(config)
        return m
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_entity_routine.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/entity_routine.py tests/core/test_entity_routine.py
git commit -m "feat(core): entity routine model with expected windows and routine notes"
```

---

### Task 8: Chain model

**Files:**
- Create: `custom_components/behaviour_monitor/core/chain_model.py`
- Create: `tests/core/test_chain_model.py`

**Interfaces:**
- Produces: `ChainConfig(window_s=900.0, min_count=10, lift=2.0, learning_days=14, window_days=28, hop_tolerance_mads=3.0, max_chain_len=6, stall_ttl_s=3600.0)`, `Chain(rooms, hop_stats, completions)` with `name`, `ChainModel` with `record(event)`, `recompute()`, `evaluate(now) -> list[Alert]`, `chains -> list[Chain]`, `completions_for_day(day) -> dict[str, float]`, `rename_room(old, new)`, `remove_room(room)`, `prune(before)`, `confidence(now)`, `to_dict`, `from_dict`.
- Stall alerts are `Alert(STATISTICAL, chain.name, "chain_stall", LOW, details={"missing": room, "step": idx})`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_chain_model.py
from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import AlertClass
from custom_components.behaviour_monitor.core.chain_model import ChainConfig, ChainModel
from custom_components.behaviour_monitor.core.events import ActivityEvent, Category, EventKind

MON = datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc)
CFG = ChainConfig(min_count=5, lift=1.5)


def _ev(ts: datetime, room: str, eid: str = "x") -> ActivityEvent:
    return ActivityEvent(f"binary_sensor.{eid}", Category.MOTION, EventKind.PRESENCE, room, ts)


def _morning(m: ChainModel, day: datetime, hop_min: float = 4.0) -> None:
    """Bedroom -> Bathroom -> Kitchen with two kitchen sensors and a filler visit."""
    t = day
    m.record(_ev(t, "Bedroom"))
    t += timedelta(minutes=hop_min)
    m.record(_ev(t, "Bathroom"))
    t += timedelta(minutes=hop_min)
    m.record(_ev(t, "Kitchen", "kmotion"))
    m.record(_ev(t + timedelta(seconds=30), "Kitchen", "kettle"))  # same room: no new step
    # afternoon noise: kitchen <-> lounge back and forth, outside the window from the morning
    t += timedelta(hours=6)
    m.record(_ev(t, "Lounge"))
    m.record(_ev(t + timedelta(minutes=3), "Kitchen"))


def _trained(days: int = 14) -> ChainModel:
    m = ChainModel(CFG)
    for d in range(days):
        _morning(m, MON + timedelta(days=d))
    m.recompute()
    return m


def test_learns_bedroom_bathroom_kitchen_chain():
    m = _trained()
    names = [c.name for c in m.chains]
    assert "Bedroom → Bathroom → Kitchen" in names
    chain = next(c for c in m.chains if c.name.startswith("Bedroom"))
    assert chain.rooms == ["Bedroom", "Bathroom", "Kitchen"]
    assert chain.hop_stats[0][0] == 240.0  # median hop seconds
    assert len(chain.hop_stats) == 2


def test_same_room_events_do_not_create_pairs():
    m = _trained()
    assert all("Kitchen → Kitchen" not in c.name for c in m.chains)


def test_completed_run_records_duration_for_the_day():
    m = _trained()
    day = MON + timedelta(days=14)
    _morning(m, day)
    comps = m.completions_for_day(date(2026, 10, 5))
    assert comps["Bedroom → Bathroom → Kitchen"] == 480.0


def test_stall_raises_note_naming_missing_room():
    m = _trained()
    day = MON + timedelta(days=14)
    m.record(_ev(day, "Bedroom"))
    m.record(_ev(day + timedelta(minutes=4), "Bathroom"))
    assert m.evaluate(day + timedelta(minutes=6)) == []
    notes = m.evaluate(day + timedelta(minutes=20))  # 240s median, 0 mad -> tolerance falls back to window
    assert notes == [] or notes[0].kind == "chain_stall"
    notes = m.evaluate(day + timedelta(minutes=25))
    assert len(notes) == 1
    n = notes[0]
    assert n.cls is AlertClass.STATISTICAL and n.kind == "chain_stall"
    assert n.source == "Bedroom → Bathroom → Kitchen"
    assert n.details == {"missing": "Kitchen", "step": 2}
    # stall persists for its ttl then clears
    assert len(m.evaluate(day + timedelta(minutes=30))) == 1
    assert m.evaluate(day + timedelta(minutes=25 + 61)) == []


def test_rename_room_keeps_counts():
    m = _trained()
    m.rename_room("Bathroom", "Washroom")
    m.recompute()
    assert any(c.rooms == ["Bedroom", "Washroom", "Kitchen"] for c in m.chains)


def test_round_trip_and_prune():
    m = _trained()
    m2 = ChainModel.from_dict(m.to_dict(), CFG)
    assert [c.name for c in m2.chains] == [c.name for c in m.chains]
    m2.prune(date(2026, 12, 1))
    m2.recompute()
    assert m2.chains == []
    assert ChainModel.from_dict({"nope": 1}, CFG).chains == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_chain_model.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/chain_model.py
"""Ordered room chains: learning, live runs, stalls and completion timing."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent
from .slots import confidence, day_type, iso_day, median_mad

_HOPS_KEPT = 200
_COMPLETIONS_KEPT = 200
ARROW = " → "


@dataclass(frozen=True)
class ChainConfig:
    window_s: float = 900.0
    min_count: int = 10
    lift: float = 2.0
    learning_days: int = 14
    window_days: int = 28
    hop_tolerance_mads: float = 3.0
    max_chain_len: int = 6
    stall_ttl_s: float = 3600.0


@dataclass
class _Pair:
    count: int = 0
    hops: deque[tuple[str, float]] = field(default_factory=lambda: deque(maxlen=_HOPS_KEPT))


@dataclass
class Chain:
    rooms: list[str]
    hop_stats: list[tuple[float, float]]
    completions: dict[str, deque[tuple[str, float]]] = field(
        default_factory=lambda: {"weekday": deque(maxlen=_COMPLETIONS_KEPT), "weekend": deque(maxlen=_COMPLETIONS_KEPT)}
    )

    @property
    def name(self) -> str:
        return ARROW.join(self.rooms)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Chain) and other.rooms == self.rooms


@dataclass
class _Run:
    started: datetime
    step: int
    last_step_at: datetime


@dataclass
class _Stall:
    alert: Alert
    until: datetime


class ChainModel:
    def __init__(self, config: ChainConfig) -> None:
        self._cfg = config
        self._pairs: dict[tuple[str, str], _Pair] = {}
        self._steps_into: dict[str, int] = {}
        self._total_steps = 0
        self._recent: dict[str, datetime] = {}
        self._current_room: str | None = None
        self._days_seen: set[str] = set()
        self._chains: list[Chain] = []
        self._runs: dict[str, _Run] = {}
        self._stalls: dict[str, _Stall] = {}

    @property
    def chains(self) -> list[Chain]:
        return list(self._chains)

    # ------------------------------------------------------------ recording

    def record(self, event: ActivityEvent) -> None:
        if not event.is_activity:
            return
        ts, room = event.timestamp, event.room
        if room == self._current_room:
            return
        day = iso_day(ts.date())
        self._days_seen.add(day)
        for prev_room, prev_ts in list(self._recent.items()):
            age = (ts - prev_ts).total_seconds()
            if age > self._cfg.window_s:
                del self._recent[prev_room]
                continue
            if prev_room == room:
                continue
            pair = self._pairs.setdefault((prev_room, room), _Pair())
            pair.count += 1
            pair.hops.append((day, age))
        self._steps_into[room] = self._steps_into.get(room, 0) + 1
        self._total_steps += 1
        self._recent[room] = ts
        self._current_room = room
        self._advance_runs(room, ts)

    def _advance_runs(self, room: str, ts: datetime) -> None:
        for chain in self._chains:
            run = self._runs.get(chain.name)
            if run is None:
                if room == chain.rooms[0]:
                    self._runs[chain.name] = _Run(ts, 0, ts)
                continue
            nxt = run.step + 1
            if nxt < len(chain.rooms) and room == chain.rooms[nxt]:
                run.step, run.last_step_at = nxt, ts
                if nxt == len(chain.rooms) - 1:
                    dur = (ts - run.started).total_seconds()
                    chain.completions[day_type(ts.date())].append((iso_day(ts.date()), dur))
                    del self._runs[chain.name]
                    self._stalls.pop(chain.name, None)
            elif room == chain.rooms[0]:
                self._runs[chain.name] = _Run(ts, 0, ts)

    # ----------------------------------------------------------- learning

    def recompute(self) -> None:
        sig: dict[str, list[tuple[str, int]]] = {}
        preds: set[str] = set()
        total = max(1, self._total_steps)
        for (a, b), pair in self._pairs.items():
            if pair.count < self._cfg.min_count:
                continue
            steps_a = self._steps_into.get(a, 0)
            if steps_a == 0:
                continue
            p_b_given_a = pair.count / steps_a
            p_b = self._steps_into.get(b, 0) / total
            if p_b_given_a > self._cfg.lift * p_b:
                sig.setdefault(a, []).append((b, pair.count))
                preds.add(b)
        old = {c.name: c for c in self._chains}
        chains: list[Chain] = []
        for start in sorted(sig):
            if start in preds:
                continue
            rooms = [start]
            while rooms[-1] in sig and len(rooms) < self._cfg.max_chain_len:
                nxt = max(sig[rooms[-1]], key=lambda x: x[1])[0]
                if nxt in rooms:
                    break
                rooms.append(nxt)
            if len(rooms) < 2:
                continue
            stats = [median_mad(h for _, h in self._pairs[(rooms[i], rooms[i + 1])].hops) for i in range(len(rooms) - 1)]
            chain = Chain(rooms, stats)
            prev = old.get(chain.name)
            if prev is not None:
                chain.completions = prev.completions
            chains.append(chain)
        self._chains = chains
        self._runs = {k: v for k, v in self._runs.items() if k in {c.name for c in chains}}

    # ------------------------------------------------------------ queries

    def evaluate(self, now: datetime) -> list[Alert]:
        for chain in self._chains:
            run = self._runs.get(chain.name)
            if run is None:
                continue
            med, mad = chain.hop_stats[run.step]
            tolerance = med + self._cfg.hop_tolerance_mads * mad if mad > 0 else max(med * 2, self._cfg.window_s)
            if (now - run.last_step_at).total_seconds() > tolerance:
                missing = chain.rooms[run.step + 1]
                alert = Alert(
                    AlertClass.STATISTICAL,
                    chain.name,
                    "chain_stall",
                    Severity.LOW,
                    f"Routine {chain.name} started at {run.started:%H:%M} but {missing} was not reached",
                    now,
                    {"missing": missing, "step": run.step + 1},
                )
                self._stalls[chain.name] = _Stall(alert, now + timedelta(seconds=self._cfg.stall_ttl_s))
                del self._runs[chain.name]
        self._stalls = {k: s for k, s in self._stalls.items() if s.until > now}
        return [s.alert for s in self._stalls.values()]

    def completions_for_day(self, day: date) -> dict[str, float]:
        d = iso_day(day)
        out: dict[str, float] = {}
        for c in self._chains:
            vals = [v for dq in c.completions.values() for dd, v in dq if dd == d]
            if vals:
                out[c.name] = median_mad(vals)[0]
        return out

    def confidence(self, now: datetime) -> float:
        return confidence(len(self._days_seen), self._cfg.learning_days)

    # ------------------------------------------------------- maintenance

    def rename_room(self, old: str, new: str) -> None:
        self._pairs = {(new if a == old else a, new if b == old else b): p for (a, b), p in self._pairs.items()}
        if old in self._steps_into:
            self._steps_into[new] = self._steps_into.pop(old)
        if old in self._recent:
            self._recent[new] = self._recent.pop(old)
        if self._current_room == old:
            self._current_room = new
        for c in self._chains:
            c.rooms = [new if r == old else r for r in c.rooms]

    def remove_room(self, room: str) -> None:
        self._pairs = {k: p for k, p in self._pairs.items() if room not in k}
        self._steps_into.pop(room, None)
        self._recent.pop(room, None)
        self._chains = [c for c in self._chains if room not in c.rooms]
        self._runs = {k: v for k, v in self._runs.items() if k in {c.name for c in self._chains}}

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        for key in list(self._pairs):
            pair = self._pairs[key]
            kept = [(d, h) for d, h in pair.hops if d >= cutoff]
            removed = pair.count - len(kept) if pair.count > len(pair.hops) else len(pair.hops) - len(kept)
            pair.hops.clear()
            pair.hops.extend(kept)
            pair.count = max(0, pair.count - removed)
            if pair.count == 0:
                del self._pairs[key]
        self._days_seen = {d for d in self._days_seen if d >= cutoff}
        for c in self._chains:
            for dt_key, dq in c.completions.items():
                kept_c = [(d, v) for d, v in dq if d >= cutoff]
                dq.clear()
                dq.extend(kept_c)

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "pairs": [{"a": a, "b": b, "count": p.count, "hops": list(p.hops)} for (a, b), p in self._pairs.items()],
            "steps_into": dict(self._steps_into),
            "total_steps": self._total_steps,
            "current_room": self._current_room,
            "days_seen": sorted(self._days_seen),
            "chains": [
                {"rooms": c.rooms, "hop_stats": c.hop_stats, "completions": {k: list(v) for k, v in c.completions.items()}}
                for c in self._chains
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: ChainConfig) -> "ChainModel":
        m = cls(config)
        try:
            for p in data.get("pairs", []):
                pair = _Pair(int(p["count"]))
                pair.hops.extend((str(d), float(h)) for d, h in p.get("hops", []))
                m._pairs[(str(p["a"]), str(p["b"]))] = pair
            m._steps_into = {str(k): int(v) for k, v in data.get("steps_into", {}).items()}
            m._total_steps = int(data.get("total_steps", 0))
            m._current_room = data.get("current_room")
            m._days_seen = set(data.get("days_seen", []))
            for c in data.get("chains", []):
                chain = Chain([str(r) for r in c["rooms"]], [(float(a), float(b)) for a, b in c.get("hop_stats", [])])
                for k, v in c.get("completions", {}).items():
                    if k in chain.completions:
                        chain.completions[k].extend((str(d), float(x)) for d, x in v)
                m._chains.append(chain)
        except (KeyError, TypeError, ValueError):
            return cls(config)
        return m
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_chain_model.py -v`
Expected: 6 passed. `test_stall_raises_note_naming_missing_room` tolerates a stall at 20 minutes because with zero MAD the tolerance is `max(2 * median, window_s)` = 900 s; the stall must exist by 25 minutes.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/chain_model.py tests/core/test_chain_model.py
git commit -m "feat(core): room chain model with live runs, stalls and completion timing"
```

---

### Task 9: Drift detector on daily series

**Files:**
- Create: `custom_components/behaviour_monitor/core/drift_detector.py`
- Create: `tests/core/test_drift_detector.py`

**Interfaces:**
- Produces: `DriftConfig(sensitivity="medium", min_days=3, window_days=28, min_baseline_days=5)`, `CUSUM_PARAMS`, `DailySeries`, `CUSUMState`, `DriftDetector` with `record(key, day, value, split_day_type=False)`, `check(today, now) -> list[Alert]`, `reset(key=None)`, `remove_prefix(prefix)`, `prune(before)`, `to_dict`, `from_dict`.
- Drift alerts are `Alert(STATISTICAL, key, "drift", MEDIUM|HIGH, details={"direction", "days", "baseline", "today"})`.
- Series key convention used by Task 12: `count:<entity_id>`, `chain:<chain name>`, `rooms`, `open:<entity_id>`, `dwell:<entity_id>`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_drift_detector.py
from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import AlertClass, Severity
from custom_components.behaviour_monitor.core.drift_detector import DriftConfig, DriftDetector

D0 = date(2026, 9, 1)
NOW = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)


def _feed(det: DriftDetector, key: str, values: list[float], split: bool = False) -> list[list]:
    out = []
    for i, v in enumerate(values):
        day = D0 + timedelta(days=i)
        det.record(key, day, v, split_day_type=split)
        out.append(det.check(day, datetime.combine(day, NOW.timetz())))
    return out


def test_stable_series_never_alerts():
    det = DriftDetector(DriftConfig())
    results = _feed(det, "count:x", [10, 11, 9, 10, 12, 10, 9, 11, 10, 10, 11, 9, 10, 10])
    assert all(r == [] for r in results)


def test_step_change_alerts_after_min_days_with_direction_and_severity():
    det = DriftDetector(DriftConfig(min_days=3))
    values = [12.0] * 10 + [25.0] * 8
    results = _feed(det, "chain:Bedroom → Kitchen", values)
    first = next(i for i, r in enumerate(results) if r)
    assert first == 12  # 10 baseline days, alert on the third shifted day
    a = results[first][0]
    assert a.cls is AlertClass.STATISTICAL and a.kind == "drift" and a.severity is Severity.MEDIUM
    assert a.details["direction"] == "increase" and a.details["days"] == 3
    assert a.details["baseline"] < a.details["today"]
    assert results[-1][0].severity is Severity.HIGH  # 7+ days


def test_gradual_lengthening_is_caught():
    det = DriftDetector(DriftConfig(min_days=3))
    values = [12.0] * 10 + [12.0 + 2 * i for i in range(1, 15)]
    results = _feed(det, "chain:x", values)
    first = next(i for i, r in enumerate(results) if r)
    assert 13 <= first <= 20


def test_check_is_idempotent_per_day_and_needs_baseline():
    det = DriftDetector(DriftConfig(min_baseline_days=5))
    det.record("count:x", D0, 5.0)
    assert det.check(D0, NOW) == []
    for i in range(1, 6):
        det.record("count:x", D0 + timedelta(days=i), 5.0)
    day = D0 + timedelta(days=5)
    det.check(day, NOW)
    det.record("count:x", day, 50.0)
    assert det.check(day, NOW) == []  # already processed today


def test_reset_prune_remove_and_round_trip():
    det = DriftDetector(DriftConfig())
    _feed(det, "count:x", [12.0] * 10 + [30.0] * 3)
    det2 = DriftDetector.from_dict(det.to_dict(), DriftConfig())
    assert det2.to_dict() == det.to_dict()
    det2.reset("count:x")
    assert det2.to_dict()["cusum"]["count:x"]["days_above"] == 0
    det2.remove_prefix("count:")
    assert "count:x" not in det2.to_dict()["series"]
    det.prune(D0 + timedelta(days=12))
    assert len(det.to_dict()["series"]["count:x"]["values"]) == 1
    assert DriftDetector.from_dict({"x": 1}, DriftConfig()).to_dict()["series"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_drift_detector.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/drift_detector.py
"""Bidirectional CUSUM over named daily series."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .slots import day_type, iso_day

CUSUM_PARAMS: dict[str, tuple[float, float]] = {
    "high": (0.25, 2.0),
    "medium": (0.5, 4.0),
    "low": (1.0, 6.0),
}
_DECAY = 0.95


@dataclass(frozen=True)
class DriftConfig:
    sensitivity: str = "medium"
    min_days: int = 3
    window_days: int = 28
    min_baseline_days: int = 5


@dataclass
class DailySeries:
    values: dict[str, float] = field(default_factory=dict)
    split_day_type: bool = False

    def baseline(self, today: date) -> tuple[float, float, int]:
        """Decay-weighted mean, stdev and count of days before today, same day type if split."""
        rows: list[tuple[int, float]] = []
        want = day_type(today) if self.split_day_type else None
        for d, v in self.values.items():
            dd = date.fromisoformat(d)
            if dd >= today:
                continue
            if want is not None and day_type(dd) != want:
                continue
            rows.append(((today - dd).days, v))
        if self.split_day_type and len(rows) < 3:
            rows = [((today - date.fromisoformat(d)).days, v) for d, v in self.values.items() if date.fromisoformat(d) < today]
        if not rows:
            return 0.0, 0.0, 0
        weights = [_DECAY ** age for age, _ in rows]
        mean = sum(w * v for w, (_, v) in zip(weights, rows)) / sum(weights)
        vals = [v for _, v in rows]
        stdev = statistics.stdev(vals) if len(vals) >= 2 else 0.0
        return mean, stdev, len(rows)


@dataclass
class CUSUMState:
    s_pos: float = 0.0
    s_neg: float = 0.0
    days_above: int = 0
    last_day: str | None = None

    def reset(self) -> None:
        self.s_pos = self.s_neg = 0.0
        self.days_above = 0


class DriftDetector:
    def __init__(self, config: DriftConfig) -> None:
        self._cfg = config
        self._k, self._h = CUSUM_PARAMS.get(config.sensitivity, CUSUM_PARAMS["medium"])
        self._series: dict[str, DailySeries] = {}
        self._cusum: dict[str, CUSUMState] = {}

    def record(self, key: str, day: date, value: float, split_day_type: bool = False) -> None:
        s = self._series.setdefault(key, DailySeries(split_day_type=split_day_type))
        s.split_day_type = split_day_type
        s.values[iso_day(day)] = float(value)

    def check(self, today: date, now: datetime) -> list[Alert]:
        out: list[Alert] = []
        today_iso = iso_day(today)
        for key, series in self._series.items():
            if today_iso not in series.values:
                continue
            st = self._cusum.setdefault(key, CUSUMState())
            if st.last_day == today_iso:
                continue
            mean, stdev, n = series.baseline(today)
            if n < self._cfg.min_baseline_days:
                st.last_day = today_iso
                continue
            if stdev == 0.0:
                stdev = max(1.0, abs(mean) * 0.1)
            z = (series.values[today_iso] - mean) / stdev
            st.s_pos = max(0.0, st.s_pos + z - self._k)
            st.s_neg = max(0.0, st.s_neg - z - self._k)
            st.days_above = st.days_above + 1 if (st.s_pos > self._h or st.s_neg > self._h) else 0
            st.last_day = today_iso
            if st.days_above < self._cfg.min_days:
                continue
            direction = "increase" if st.s_pos >= st.s_neg else "decrease"
            sev = Severity.HIGH if st.days_above >= 7 else Severity.MEDIUM
            out.append(
                Alert(
                    AlertClass.STATISTICAL,
                    key,
                    "drift",
                    sev,
                    f"{key}: sustained {direction} for {st.days_above} days (baseline {mean:.1f}, today {series.values[today_iso]:.1f})",
                    now,
                    {"direction": direction, "days": st.days_above, "baseline": round(mean, 2), "today": series.values[today_iso]},
                )
            )
        return out

    def reset(self, key: str | None = None) -> None:
        for k, st in self._cusum.items():
            if key is None or k == key:
                st.reset()

    def remove_prefix(self, prefix: str) -> None:
        for k in [k for k in self._series if k.startswith(prefix)]:
            del self._series[k]
            self._cusum.pop(k, None)

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        for s in self._series.values():
            s.values = {d: v for d, v in s.values.items() if d >= cutoff}

    def to_dict(self) -> dict[str, Any]:
        return {
            "series": {k: {"values": s.values, "split": s.split_day_type} for k, s in self._series.items()},
            "cusum": {k: {"s_pos": c.s_pos, "s_neg": c.s_neg, "days_above": c.days_above, "last_day": c.last_day} for k, c in self._cusum.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: DriftConfig) -> "DriftDetector":
        d = cls(config)
        try:
            for k, s in data.get("series", {}).items():
                d._series[k] = DailySeries({str(dd): float(v) for dd, v in s["values"].items()}, bool(s.get("split", False)))
            for k, c in data.get("cusum", {}).items():
                d._cusum[k] = CUSUMState(float(c["s_pos"]), float(c["s_neg"]), int(c["days_above"]), c.get("last_day"))
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return d
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_drift_detector.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/drift_detector.py tests/core/test_drift_detector.py
git commit -m "feat(core): CUSUM drift detector over named daily series"
```

---

### Task 10: Health tracker

**Files:**
- Create: `custom_components/behaviour_monitor/core/health_tracker.py`
- Create: `tests/core/test_health_tracker.py`

**Interfaces:**
- Consumes: `HealthEvent`, `ActivityEvent`.
- Produces: `HealthConfig(grace_s=900.0, silent_multiplier=3.0, sitewide_fraction=0.5, sitewide_window_s=60.0)`, `HealthTracker` with `register(entity_id, category, room)`, `remove(entity_id)`, `record_health(event)`, `record_activity(event)`, `evaluate(now, longest_gap, house_last_activity) -> list[Alert]`, `down_entities(now) -> set[str]`, `live_fraction(now) -> float`, `sitewide_dropouts_today(day) -> int`, `entity_states(now) -> dict[str, str]`, `to_dict`, `from_dict`.
- Alert kinds: `unavailable` (source entity), `silent` (source entity), `dropout` (source `site`).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_health_tracker.py
from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import AlertClass, Severity
from custom_components.behaviour_monitor.core.events import ActivityEvent, Category, EventKind, HealthEvent
from custom_components.behaviour_monitor.core.health_tracker import HealthConfig, HealthTracker

T0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
ENTS = [("binary_sensor.k", Category.MOTION, "Kitchen"), ("binary_sensor.b", Category.MOTION, "Bath"),
        ("binary_sensor.p", Category.PANIC, "Hall"), ("sensor.kettle", Category.PLUG, "Kitchen")]


def _tracker() -> HealthTracker:
    t = HealthTracker(HealthConfig())
    for e in ENTS:
        t.register(*e)
    return t


def _down(t: HealthTracker, eid: str, ts: datetime, available: bool = False) -> None:
    cat, room = next((c, r) for e, c, r in ENTS if e == eid)
    t.record_health(HealthEvent(eid, cat, room, ts, available))


def test_short_dropout_inside_grace_is_ignored():
    t = _tracker()
    _down(t, "binary_sensor.k", T0)
    assert t.evaluate(T0 + timedelta(minutes=5), lambda e: None, None) == []
    _down(t, "binary_sensor.k", T0 + timedelta(seconds=10), available=True)
    assert t.evaluate(T0 + timedelta(minutes=20), lambda e: None, None) == []


def test_unavailable_beyond_grace_alerts_and_panic_is_high():
    t = _tracker()
    _down(t, "binary_sensor.k", T0)
    _down(t, "binary_sensor.p", T0)
    alerts = t.evaluate(T0 + timedelta(minutes=16), lambda e: None, None)
    by = {a.source: a for a in alerts}
    assert by["binary_sensor.k"].kind == "unavailable" and by["binary_sensor.k"].severity is Severity.MEDIUM
    assert by["binary_sensor.p"].severity is Severity.HIGH
    assert all(a.cls is AlertClass.HEALTH for a in alerts)
    assert t.down_entities(T0 + timedelta(minutes=16)) == {"binary_sensor.k", "binary_sensor.p"}
    assert t.live_fraction(T0 + timedelta(minutes=16)) == 0.5


def test_sitewide_dropout_is_one_alert_and_counted():
    t = _tracker()
    for eid, _, _ in ENTS[:3]:
        _down(t, eid, T0 + timedelta(seconds=5))
    alerts = t.evaluate(T0 + timedelta(seconds=30), lambda e: None, None)
    assert [a.kind for a in alerts] == ["dropout"]
    assert alerts[0].source == "site" and alerts[0].details["count"] == 3
    for eid, _, _ in ENTS[:3]:
        _down(t, eid, T0 + timedelta(seconds=40), available=True)
    assert t.evaluate(T0 + timedelta(seconds=60), lambda e: None, None) == []
    assert t.sitewide_dropouts_today(date(2026, 9, 21)) == 1


def test_silent_sensor_needs_house_activity_elsewhere():
    t = _tracker()
    t.record_activity(ActivityEvent("binary_sensor.k", Category.MOTION, EventKind.PRESENCE, "Kitchen", T0))
    longest = lambda e: 3600.0 if e == "binary_sensor.k" else None
    # house quiet too: not the sensor's fault
    assert t.evaluate(T0 + timedelta(hours=4), longest, T0) == []
    # house active after the sensor went quiet
    alerts = t.evaluate(T0 + timedelta(hours=4), longest, T0 + timedelta(hours=3))
    assert [a.kind for a in alerts] == ["silent"] and alerts[0].source == "binary_sensor.k"
    assert alerts[0].details["silent_s"] == 4 * 3600.0
    assert "binary_sensor.k" in t.down_entities(T0 + timedelta(hours=4))


def test_panic_is_never_silent_candidate_and_states_exposed():
    t = _tracker()
    t.record_activity(ActivityEvent("binary_sensor.p", Category.PANIC, EventKind.PANIC_RELEASE, "Hall", T0))
    assert t.evaluate(T0 + timedelta(days=30), lambda e: 60.0, T0 + timedelta(days=29)) == []
    states = t.entity_states(T0)
    assert states == {e: "ok" for e, _, _ in ENTS}


def test_remove_and_round_trip():
    t = _tracker()
    _down(t, "binary_sensor.k", T0)
    t2 = HealthTracker.from_dict(t.to_dict(), HealthConfig())
    assert t2.down_entities(T0 + timedelta(minutes=16)) == {"binary_sensor.k"}
    t2.remove("binary_sensor.k")
    assert t2.down_entities(T0 + timedelta(minutes=16)) == set()
    assert HealthTracker.from_dict({"bad": 1}, HealthConfig()).entity_states(T0) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_health_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/health_tracker.py
"""Device health: unavailable, site-wide dropout, silent sensor, panic liveness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent, Category, HealthEvent
from .slots import iso_day


@dataclass(frozen=True)
class HealthConfig:
    grace_s: float = 900.0
    silent_multiplier: float = 3.0
    sitewide_fraction: float = 0.5
    sitewide_window_s: float = 60.0


@dataclass
class _EntityHealth:
    category: Category
    room: str
    down_since: datetime | None = None
    last_event: datetime | None = None
    silent: bool = False


def _dt(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


class HealthTracker:
    def __init__(self, config: HealthConfig) -> None:
        self._cfg = config
        self._ent: dict[str, _EntityHealth] = {}
        self._recent_downs: list[tuple[str, datetime]] = []
        self._sitewide_open: datetime | None = None
        self._sitewide_by_day: dict[str, int] = {}

    # ----------------------------------------------------------- membership

    def register(self, entity_id: str, category: Category, room: str) -> None:
        cur = self._ent.get(entity_id)
        if cur is None:
            self._ent[entity_id] = _EntityHealth(category, room)
        else:
            cur.category, cur.room = category, room

    def remove(self, entity_id: str) -> None:
        self._ent.pop(entity_id, None)
        self._recent_downs = [(e, t) for e, t in self._recent_downs if e != entity_id]

    # ------------------------------------------------------------ recording

    def record_health(self, event: HealthEvent) -> None:
        e = self._ent.get(event.entity_id)
        if e is None:
            return
        if event.available:
            e.down_since = None
        elif e.down_since is None:
            e.down_since = event.timestamp
            self._recent_downs.append((event.entity_id, event.timestamp))
            self._maybe_open_sitewide(event.timestamp)

    def record_activity(self, event: ActivityEvent) -> None:
        e = self._ent.get(event.entity_id)
        if e is not None and (e.last_event is None or event.timestamp > e.last_event):
            e.last_event = event.timestamp

    def _maybe_open_sitewide(self, now: datetime) -> None:
        self._recent_downs = [(e, t) for e, t in self._recent_downs if (now - t).total_seconds() <= self._cfg.sitewide_window_s]
        if not self._ent:
            return
        if len({e for e, _ in self._recent_downs}) > self._cfg.sitewide_fraction * len(self._ent) and self._sitewide_open is None:
            self._sitewide_open = now
            day = iso_day(now.date())
            self._sitewide_by_day[day] = self._sitewide_by_day.get(day, 0) + 1

    # -------------------------------------------------------------- queries

    def _unavailable(self, now: datetime) -> set[str]:
        return {
            eid for eid, e in self._ent.items()
            if e.down_since is not None and (now - e.down_since).total_seconds() > self._cfg.grace_s
        }

    def _silent(self, now: datetime, longest_gap: Callable[[str], float | None], house_last: datetime | None) -> dict[str, float]:
        out: dict[str, float] = {}
        if house_last is None:
            return out
        for eid, e in self._ent.items():
            if e.category is Category.PANIC or e.last_event is None or e.down_since is not None:
                continue
            gap = longest_gap(eid)
            if gap is None or gap <= 0:
                continue
            silent = (now - e.last_event).total_seconds()
            if silent > self._cfg.silent_multiplier * gap and house_last > e.last_event:
                out[eid] = silent
        return out

    def down_entities(self, now: datetime) -> set[str]:
        return self._unavailable(now) | {eid for eid, e in self._ent.items() if e.silent}

    def live_fraction(self, now: datetime) -> float:
        if not self._ent:
            return 1.0
        return 1.0 - len(self.down_entities(now)) / len(self._ent)

    def sitewide_dropouts_today(self, day: date) -> int:
        return self._sitewide_by_day.get(iso_day(day), 0)

    def entity_states(self, now: datetime) -> dict[str, str]:
        unavail = self._unavailable(now)
        return {
            eid: "unavailable" if eid in unavail else ("silent" if e.silent else "ok")
            for eid, e in self._ent.items()
        }

    def evaluate(
        self,
        now: datetime,
        longest_gap: Callable[[str], float | None],
        house_last_activity: datetime | None,
    ) -> list[Alert]:
        out: list[Alert] = []
        down_now = {eid for eid, e in self._ent.items() if e.down_since is not None}
        if self._sitewide_open is not None:
            if len(down_now) <= self._cfg.sitewide_fraction * len(self._ent):
                self._sitewide_open = None
            else:
                out.append(Alert(AlertClass.HEALTH, "site", "dropout", Severity.MEDIUM,
                                 f"{len(down_now)} of {len(self._ent)} sensors went unavailable together",
                                 now, {"count": len(down_now)}))
        for eid in sorted(self._unavailable(now)):
            e = self._ent[eid]
            sev = Severity.HIGH if e.category is Category.PANIC else Severity.MEDIUM
            out.append(Alert(AlertClass.HEALTH, eid, "unavailable", sev,
                             f"{e.room}: {eid} has been unavailable since {e.down_since:%H:%M}", now,
                             {"since": e.down_since.isoformat() if e.down_since else None, "room": e.room}))
        silent = self._silent(now, longest_gap, house_last_activity)
        for eid, e in self._ent.items():
            e.silent = eid in silent
        for eid, secs in sorted(silent.items()):
            e = self._ent[eid]
            out.append(Alert(AlertClass.HEALTH, eid, "silent", Severity.MEDIUM,
                             f"{e.room}: {eid} has reported nothing for {secs / 3600:.1f} h while the house was active",
                             now, {"silent_s": secs, "room": e.room}))
        return out

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": {
                eid: {"category": e.category.value, "room": e.room,
                      "down_since": e.down_since.isoformat() if e.down_since else None,
                      "last_event": e.last_event.isoformat() if e.last_event else None}
                for eid, e in self._ent.items()
            },
            "sitewide_open": self._sitewide_open.isoformat() if self._sitewide_open else None,
            "sitewide_by_day": dict(self._sitewide_by_day),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: HealthConfig) -> "HealthTracker":
        t = cls(config)
        try:
            for eid, e in data.get("entities", {}).items():
                t._ent[eid] = _EntityHealth(Category(e["category"]), str(e.get("room", "")), _dt(e.get("down_since")), _dt(e.get("last_event")))
            t._sitewide_open = _dt(data.get("sitewide_open"))
            t._sitewide_by_day = {str(k): int(v) for k, v in data.get("sitewide_by_day", {}).items()}
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return t
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_health_tracker.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/health_tracker.py tests/core/test_health_tracker.py
git commit -m "feat(core): health tracker with grace, site-wide dropout and silent sensor"
```

---

### Task 11: Alert router

**Files:**
- Create: `custom_components/behaviour_monitor/core/alert_router.py`
- Create: `tests/core/test_alert_router.py`

**Interfaces:**
- Produces: `RouterConfig(push_min_severity=Severity.MEDIUM, push_repeat_s=1800.0, timing_promote_days=7)`, `DeliveryAction(action, alert)` where `action` is one of `"push"`, `"push_clear"`, `"repair_create"`, `"repair_delete"`, `"log"`, `"log_clear"`, and `AlertRouter` with `submit(alerts, now, snoozed=False, holiday=False) -> list[DeliveryAction]`, `submit_panic(event, now) -> list[DeliveryAction]`, `acknowledge(now)`, `open_alerts -> list[Alert]`, `welfare_severity -> Severity | None`, `to_dict`, `from_dict`.
- Escalation rules from spec 6.5 live here. Inputs: a house welfare alert has `source == "house"` and `kind == "inactivity"`; notes and stalls are STATISTICAL with kind `routine_missed` or `chain_stall`; timing drift is STATISTICAL kind `drift` with source starting `chain:`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_alert_router.py
from datetime import datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alert_router import AlertRouter, RouterConfig
from custom_components.behaviour_monitor.core.alerts import Alert, AlertClass, Severity
from custom_components.behaviour_monitor.core.events import ActivityEvent, Category, EventKind

T0 = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)


def _house(sev: Severity, ts: datetime = T0) -> Alert:
    return Alert(AlertClass.WELFARE, "house", "inactivity", sev, "No activity", ts)


def _note(src: str = "sensor.kettle", ts: datetime = T0) -> Alert:
    return Alert(AlertClass.STATISTICAL, src, "routine_missed", Severity.LOW, "missed", ts)


def _stall(ts: datetime = T0) -> Alert:
    return Alert(AlertClass.STATISTICAL, "Bed → Bath", "chain_stall", Severity.LOW, "stalled", ts)


def _health(src: str = "binary_sensor.k", ts: datetime = T0) -> Alert:
    return Alert(AlertClass.HEALTH, src, "unavailable", Severity.MEDIUM, "down", ts)


def _acts(actions, kind):
    return [a.alert.key for a in actions if a.action == kind]


def test_welfare_push_threshold_repeat_and_clear():
    r = AlertRouter(RouterConfig(push_repeat_s=600))
    assert _acts(r.submit([_house(Severity.LOW)], T0), "push") == []
    acts = r.submit([_house(Severity.MEDIUM)], T0 + timedelta(minutes=1))
    assert _acts(acts, "push") == ["welfare:house:inactivity"]
    assert r.submit([_house(Severity.MEDIUM)], T0 + timedelta(minutes=5)) == []
    acts = r.submit([_house(Severity.MEDIUM)], T0 + timedelta(minutes=12))
    assert _acts(acts, "push") == ["welfare:house:inactivity"]
    acts = r.submit([], T0 + timedelta(minutes=13))
    assert _acts(acts, "push_clear") == ["welfare:house:inactivity"]
    assert r.open_alerts == []


def test_severity_rise_pushes_immediately_and_ack_stops_repeats():
    r = AlertRouter(RouterConfig(push_repeat_s=600))
    r.submit([_house(Severity.MEDIUM)], T0)
    acts = r.submit([_house(Severity.HIGH)], T0 + timedelta(minutes=1))
    assert _acts(acts, "push") == ["welfare:house:inactivity"]
    r.acknowledge(T0 + timedelta(minutes=2))
    assert r.submit([_house(Severity.HIGH)], T0 + timedelta(minutes=30)) == []
    assert r.welfare_severity is Severity.HIGH


def test_health_becomes_repair_and_statistical_becomes_log():
    r = AlertRouter(RouterConfig())
    acts = r.submit([_health(), _note()], T0)
    assert _acts(acts, "repair_create") == ["health:binary_sensor.k:unavailable"]
    assert _acts(acts, "log") == ["statistical:sensor.kettle:routine_missed"]
    assert r.submit([_health(), _note()], T0 + timedelta(hours=2)) == []
    acts = r.submit([], T0 + timedelta(hours=3))
    assert _acts(acts, "repair_delete") == ["health:binary_sensor.k:unavailable"]
    assert _acts(acts, "log_clear") == ["statistical:sensor.kettle:routine_missed"]


def test_note_escalates_open_house_alert_by_one_level():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.LOW), _note()], T0)
    assert r.welfare_severity is Severity.MEDIUM


def test_two_notes_open_low_welfare_without_house_alert():
    r = AlertRouter(RouterConfig())
    acts = r.submit([_note("a"), _stall()], T0)
    keys = [a.alert.key for a in r.open_alerts]
    assert "welfare:house:routine_agreement" in keys
    assert r.welfare_severity is Severity.LOW
    assert _acts(acts, "push") == []  # low is below push threshold
    r.submit([_note("a")], T0 + timedelta(minutes=5))
    assert "welfare:house:routine_agreement" not in [a.key for a in r.open_alerts]


def test_chain_timing_drift_promotes_after_days():
    r = AlertRouter(RouterConfig(timing_promote_days=7))
    d6 = Alert(AlertClass.STATISTICAL, "chain:Bed → Kitchen", "drift", Severity.MEDIUM, "slower", T0, {"days": 6, "direction": "increase"})
    r.submit([d6], T0)
    assert [a.key for a in r.open_alerts] == ["statistical:chain:Bed → Kitchen:drift"]
    d7 = Alert(AlertClass.STATISTICAL, "chain:Bed → Kitchen", "drift", Severity.MEDIUM, "slower", T0, {"days": 7, "direction": "increase"})
    r.submit([d7], T0 + timedelta(days=1))
    assert "welfare:chain:Bed → Kitchen:timing_drift" in [a.key for a in r.open_alerts]
    dec = Alert(AlertClass.STATISTICAL, "chain:Other", "drift", Severity.MEDIUM, "faster", T0, {"days": 9, "direction": "decrease"})
    r.submit([d7, dec], T0 + timedelta(days=2))
    assert "welfare:chain:Other:timing_drift" not in [a.key for a in r.open_alerts]


def test_panic_is_immediate_critical_and_survives_submit_until_ack():
    r = AlertRouter(RouterConfig())
    ev = ActivityEvent("binary_sensor.p", Category.PANIC, EventKind.PANIC, "Hall", T0, bypass=True)
    acts = r.submit_panic(ev, T0)
    assert [(a.action, a.alert.severity) for a in acts] == [("push", Severity.CRITICAL)]
    assert r.submit([], T0 + timedelta(minutes=1), snoozed=True, holiday=True) == []
    assert "welfare:binary_sensor.p:panic" in [a.key for a in r.open_alerts]
    acts = r.submit([], T0 + timedelta(minutes=31))
    assert _acts(acts, "push") == ["welfare:binary_sensor.p:panic"]  # repeats until acknowledged
    r.acknowledge(T0 + timedelta(minutes=32))
    acts = r.submit([], T0 + timedelta(minutes=33))
    assert _acts(acts, "push_clear") == ["welfare:binary_sensor.p:panic"]


def test_snooze_suppresses_delivery_but_keeps_state_and_holiday_drops_alerts():
    r2 = AlertRouter(RouterConfig())
    acts = r2.submit([_house(Severity.HIGH), _health()], T0, snoozed=True)
    assert _acts(acts, "push") == [] and _acts(acts, "repair_create") == ["health:binary_sensor.k:unavailable"]
    assert r2.welfare_severity is Severity.HIGH
    r3 = AlertRouter(RouterConfig())
    acts = r3.submit([_house(Severity.HIGH), _note(), _health()], T0, holiday=True)
    assert [a.key for a in r3.open_alerts] == ["health:binary_sensor.k:unavailable"]


def test_round_trip():
    r = AlertRouter(RouterConfig())
    r.submit([_house(Severity.MEDIUM), _health()], T0)
    r2 = AlertRouter.from_dict(r.to_dict(), RouterConfig())
    assert sorted(a.key for a in r2.open_alerts) == sorted(a.key for a in r.open_alerts)
    assert AlertRouter.from_dict({"x": 1}, RouterConfig()).open_alerts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_alert_router.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/alert_router.py
"""Open alert set, escalation, promotion and class-based delivery actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent

_NOTE_KINDS = {"routine_missed", "chain_stall"}


@dataclass(frozen=True)
class RouterConfig:
    push_min_severity: Severity = Severity.MEDIUM
    push_repeat_s: float = 1800.0
    timing_promote_days: int = 7


@dataclass(frozen=True)
class DeliveryAction:
    action: str
    alert: Alert


@dataclass
class _Open:
    alert: Alert
    opened_at: datetime
    last_push: datetime | None = None
    acknowledged: bool = False
    panic: bool = False


class AlertRouter:
    def __init__(self, config: RouterConfig) -> None:
        self._cfg = config
        self._open: dict[str, _Open] = {}

    # ------------------------------------------------------------ properties

    @property
    def open_alerts(self) -> list[Alert]:
        return [o.alert for o in self._open.values()]

    @property
    def welfare_severity(self) -> Severity | None:
        sevs = [o.alert.severity for o in self._open.values() if o.alert.cls is AlertClass.WELFARE]
        return max(sevs) if sevs else None

    # --------------------------------------------------------------- submit

    def submit(self, alerts: list[Alert], now: datetime, snoozed: bool = False, holiday: bool = False) -> list[DeliveryAction]:
        incoming = self._combine([a for a in alerts if not (holiday and a.cls is not AlertClass.HEALTH)], now)
        actions: list[DeliveryAction] = []
        seen: set[str] = set()
        for alert in incoming:
            seen.add(alert.key)
            cur = self._open.get(alert.key)
            if cur is None:
                self._open[alert.key] = _Open(alert, now)
                actions.extend(self._on_open(alert, now, snoozed))
            else:
                rose = alert.severity > cur.alert.severity
                cur.alert = alert
                if rose and alert.cls is AlertClass.WELFARE:
                    cur.acknowledged = False
                    actions.extend(self._push(cur, now, snoozed))
        for key in list(self._open):
            o = self._open[key]
            if key in seen or (o.panic and not o.acknowledged):
                continue
            del self._open[key]
            actions.extend(self._on_clear(o, snoozed))
        for o in self._open.values():
            if o.alert.cls is AlertClass.WELFARE and not o.acknowledged and o.alert.severity.at_least(self._cfg.push_min_severity):
                if o.last_push is not None and (now - o.last_push).total_seconds() >= self._cfg.push_repeat_s:
                    actions.extend(self._push(o, now, snoozed))
        return actions

    def submit_panic(self, event: ActivityEvent, now: datetime) -> list[DeliveryAction]:
        alert = Alert(AlertClass.WELFARE, event.entity_id, "panic", Severity.CRITICAL,
                      f"{event.room}: panic button pressed", now, {"room": event.room})
        o = _Open(alert, now, panic=True)
        self._open[alert.key] = o
        return self._push(o, now, snoozed=False)

    def acknowledge(self, now: datetime) -> None:
        for o in self._open.values():
            if o.alert.cls is AlertClass.WELFARE:
                o.acknowledged = True

    # ------------------------------------------------------------ combining

    def _combine(self, alerts: list[Alert], now: datetime) -> list[Alert]:
        # Notes and stalls persist on their own (a note until the entity fires,
        # a stall for ChainConfig.stall_ttl_s), so counting the ones raised
        # right now is the agreement window.
        notes = sorted(a.key for a in alerts if a.cls is AlertClass.STATISTICAL and a.kind in _NOTE_KINDS)
        out = list(alerts)
        house = next((a for a in out if a.cls is AlertClass.WELFARE and a.source == "house" and a.kind == "inactivity"), None)
        if house is not None and notes:
            out.remove(house)
            out.append(Alert(house.cls, house.source, house.kind, house.severity.bump(),
                             house.explanation + f" and {len(notes)} routine sign(s) missed", house.raised_at,
                             {**house.details, "escalated_by": notes}))
        elif house is None and len(notes) >= 2:
            out.append(Alert(AlertClass.WELFARE, "house", "routine_agreement", Severity.LOW,
                             f"{len(notes)} routine signs missed at the same time", now,
                             {"notes": notes}))
        for a in alerts:
            if (a.cls is AlertClass.STATISTICAL and a.kind == "drift" and a.source.startswith("chain:")
                    and a.details.get("direction") == "increase"
                    and int(a.details.get("days", 0)) >= self._cfg.timing_promote_days):
                out.append(Alert(AlertClass.WELFARE, a.source, "timing_drift", Severity.LOW,
                                 f"Routine {a.source[6:]} has been taking longer for {a.details['days']} days",
                                 a.raised_at, dict(a.details)))
        return out

    # ------------------------------------------------------------- delivery

    def _on_open(self, alert: Alert, now: datetime, snoozed: bool) -> list[DeliveryAction]:
        if alert.cls is AlertClass.WELFARE:
            return self._push(self._open[alert.key], now, snoozed)
        if alert.cls is AlertClass.HEALTH:
            return [DeliveryAction("repair_create", alert)]
        return [] if snoozed else [DeliveryAction("log", alert)]

    def _on_clear(self, o: _Open, snoozed: bool) -> list[DeliveryAction]:
        alert = o.alert
        if alert.cls is AlertClass.WELFARE:
            return [] if snoozed or o.last_push is None else [DeliveryAction("push_clear", alert)]
        if alert.cls is AlertClass.HEALTH:
            return [DeliveryAction("repair_delete", alert)]
        return [DeliveryAction("log_clear", alert)]

    def _push(self, o: _Open, now: datetime, snoozed: bool) -> list[DeliveryAction]:
        if not o.alert.severity.at_least(self._cfg.push_min_severity):
            return []
        o.last_push = now
        return [] if snoozed and not o.panic else [DeliveryAction("push", o.alert)]

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "open": {
                k: {"alert": o.alert.to_dict(), "opened_at": o.opened_at.isoformat(),
                    "last_push": o.last_push.isoformat() if o.last_push else None,
                    "acknowledged": o.acknowledged, "panic": o.panic}
                for k, o in self._open.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: RouterConfig) -> "AlertRouter":
        r = cls(config)
        try:
            for k, o in data.get("open", {}).items():
                r._open[k] = _Open(Alert.from_dict(o["alert"]), datetime.fromisoformat(o["opened_at"]),
                                   datetime.fromisoformat(o["last_push"]) if o.get("last_push") else None,
                                   bool(o.get("acknowledged", False)), bool(o.get("panic", False)))
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return r
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_alert_router.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/alert_router.py tests/core/test_alert_router.py
git commit -m "feat(core): alert router with escalation, promotion and class-based delivery"
```

---

### Task 12: Engine wiring, midnight rollover and snapshot

**Files:**
- Create: `custom_components/behaviour_monitor/core/engine.py`
- Create: `tests/core/test_engine.py`

**Interfaces:**
- Produces: `EntitySpec(entity_id, category, room)`, `EngineConfig` (fields: `normaliser`, `house`, `routine`, `chain`, `drift`, `health`, `router`, plus `EngineConfig.from_options(options: dict) -> EngineConfig`), `Engine(config, entities)` with:
  - `set_entities(entities) -> tuple[set[str], set[str]]` (added, removed)
  - `handle_state(entity_id, old, new, ts, learn_only=False) -> list[DeliveryAction]`
  - `poll(now) -> list[DeliveryAction]`
  - `snapshot(now) -> dict`
  - `holiday: bool` property with setter, `snooze_until: datetime | None` with setter, `is_snoozed(now)`, `acknowledge(now)`, `reset(entity_id=None)`, `rename_room(old, new)`
  - `to_dict()`, `from_dict(data, config, entities)`
- The option keys read by `from_options` are the spec's option names: `motion_debounce_s`, `plug_margin_w`, `learning_days`, `window_days`, `health_grace_s`, `push_repeat_s`, `push_min_severity`, `house_low_ratio`, `chain_window_s`, `timing_promote_days`, `drift_sensitivity`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_engine.py
from datetime import datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import Severity
from custom_components.behaviour_monitor.core.engine import Engine, EngineConfig, EntitySpec
from custom_components.behaviour_monitor.core.events import Category

MON = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
ENTS = [
    EntitySpec("binary_sensor.bed", Category.MOTION, "Bedroom"),
    EntitySpec("binary_sensor.bath", Category.MOTION, "Bathroom"),
    EntitySpec("binary_sensor.kit", Category.MOTION, "Kitchen"),
    EntitySpec("sensor.kettle", Category.PLUG, "Kitchen"),
    EntitySpec("binary_sensor.panic", Category.PANIC, "Hall"),
]


def _engine(**opts) -> Engine:
    return Engine(EngineConfig.from_options(opts), ENTS)


def _pulse(e: Engine, eid: str, ts: datetime, learn_only: bool = True) -> list:
    out = e.handle_state(eid, "off", "on", ts, learn_only=learn_only)
    e.handle_state(eid, "on", "off", ts + timedelta(seconds=60), learn_only=learn_only)
    return out


def _day(e: Engine, day: datetime, learn_only: bool = True) -> None:
    """07:00 bed, 07:04 bath, 07:08 kitchen + kettle, then kitchen every 30 min until 21:00."""
    _pulse(e, "binary_sensor.bed", day + timedelta(hours=7), learn_only)
    _pulse(e, "binary_sensor.bath", day + timedelta(hours=7, minutes=4), learn_only)
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=7, minutes=8), learn_only)
    e.handle_state("sensor.kettle", "0", "2800", day + timedelta(hours=7, minutes=9), learn_only=learn_only)
    e.handle_state("sensor.kettle", "2800", "0", day + timedelta(hours=7, minutes=11), learn_only=learn_only)
    t = day + timedelta(hours=7, minutes=40)
    while t < day + timedelta(hours=21):
        _pulse(e, "binary_sensor.kit", t, learn_only)
        t += timedelta(minutes=30)
    e.poll(day + timedelta(hours=23, minutes=59))


def _train(e: Engine, days: int = 15) -> None:
    for d in range(days):
        _day(e, MON + timedelta(days=d))
    e.poll(MON + timedelta(days=days, minutes=1))  # rollover


def test_learn_only_produces_no_actions_and_snapshot_reports_learning():
    e = _engine()
    snap = e.snapshot(MON)
    assert snap["learning"]["confidence"] == 0.0 and snap["welfare"]["status"] == "learning"
    _train(e, days=3)
    assert e.snapshot(MON + timedelta(days=3))["learning"]["days_remaining"] == 11


def test_daytime_silence_raises_welfare_after_training():
    e = _engine(learning_days=14)
    _train(e, days=15)
    day = MON + timedelta(days=15)
    _pulse(e, "binary_sensor.kit", day + timedelta(hours=9), learn_only=False)
    quiet = day + timedelta(hours=9, minutes=1)
    assert all(a.action != "push" for a in e.poll(quiet))
    actions = []
    for m in range(5, 260, 5):
        actions += e.poll(quiet + timedelta(minutes=m))
    pushes = [a for a in actions if a.action == "push"]
    assert pushes and pushes[0].alert.kind == "inactivity"
    snap = e.snapshot(quiet + timedelta(minutes=260))
    assert snap["welfare"]["status"] in ("medium", "high")
    assert "Kitchen" in snap["house"]["last_room"]


def test_night_silence_is_normal():
    e = _engine()
    _train(e, days=15)
    night = MON + timedelta(days=15, hours=2)
    acts = []
    for m in range(0, 180, 10):
        acts += e.poll(night + timedelta(minutes=m))
    assert [a for a in acts if a.action == "push"] == []


def test_panic_pushes_immediately_even_while_learning():
    e = _engine()
    acts = e.handle_state("binary_sensor.panic", "off", "on", MON)
    assert [a.action for a in acts] == ["push"] and acts[0].alert.severity is Severity.CRITICAL
    e.acknowledge(MON + timedelta(minutes=1))
    assert [a.action for a in e.poll(MON + timedelta(minutes=2))] == ["push_clear"]


def test_rollover_feeds_drift_and_recomputes_chains():
    e = _engine(learning_days=14)
    _train(e, days=15)
    snap = e.snapshot(MON + timedelta(days=15))
    assert any("Bedroom" in c["name"] for c in snap["chains"])
    assert "rooms" in e._drift.to_dict()["series"]  # rooms visited series exists


def test_set_entities_add_remove_and_reset():
    e = _engine()
    _train(e, days=3)
    added, removed = e.set_entities(ENTS[:3] + [EntitySpec("light.hall", Category.LIGHT, "Hall")])
    assert added == {"light.hall"} and removed == {"sensor.kettle", "binary_sensor.panic"}
    assert "sensor.kettle" not in e.snapshot(MON)["entities"]
    e.reset()
    assert e.snapshot(MON)["learning"]["confidence"] == 0.0


def test_round_trip():
    e = _engine()
    _train(e, days=5)
    e2 = Engine.from_dict(e.to_dict(), EngineConfig.from_options({}), ENTS)
    assert e2.snapshot(MON + timedelta(days=5)) == e.snapshot(MON + timedelta(days=5))
    assert Engine.from_dict({"junk": 1}, EngineConfig.from_options({}), ENTS).snapshot(MON)["learning"]["confidence"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/core/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# custom_components/behaviour_monitor/core/engine.py
"""Wires normaliser, models, health, drift and router. Drives on a supplied clock."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .alert_router import AlertRouter, DeliveryAction, RouterConfig
from .alerts import Alert, AlertClass, Severity
from .chain_model import ChainConfig, ChainModel
from .drift_detector import DriftConfig, DriftDetector
from .entity_routine import EntityRoutineModel, RoutineConfig
from .events import ActivityEvent, Category, EventKind, HealthEvent
from .health_tracker import HealthConfig, HealthTracker
from .house_model import HouseConfig, HouseModel
from .normaliser import Normaliser, NormaliserConfig
from .slots import confidence, iso_day

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EntitySpec:
    entity_id: str
    category: Category
    room: str


@dataclass(frozen=True)
class EngineConfig:
    normaliser: NormaliserConfig = field(default_factory=NormaliserConfig)
    house: HouseConfig = field(default_factory=HouseConfig)
    routine: RoutineConfig = field(default_factory=RoutineConfig)
    chain: ChainConfig = field(default_factory=ChainConfig)
    drift: DriftConfig = field(default_factory=DriftConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    learning_days: int = 14
    window_days: int = 28

    @classmethod
    def from_options(cls, o: dict[str, Any]) -> "EngineConfig":
        ld = int(o.get("learning_days", 14))
        wd = int(o.get("window_days", 28))
        low = float(o.get("house_low_ratio", 3.0))
        return cls(
            normaliser=NormaliserConfig(motion_debounce_s=float(o.get("motion_debounce_s", 90)), plug_margin_w=float(o.get("plug_margin_w", 5))),
            house=HouseConfig(learning_days=ld, window_days=wd, low_ratio=low, medium_ratio=low * 2, high_ratio=low * 4),
            routine=RoutineConfig(learning_days=ld, window_days=wd),
            chain=ChainConfig(window_s=float(o.get("chain_window_s", 900)), learning_days=ld, window_days=wd),
            drift=DriftConfig(sensitivity=str(o.get("drift_sensitivity", "medium")), window_days=wd),
            health=HealthConfig(grace_s=float(o.get("health_grace_s", 900))),
            router=RouterConfig(push_min_severity=Severity(str(o.get("push_min_severity", "medium"))),
                                push_repeat_s=float(o.get("push_repeat_s", 1800)),
                                timing_promote_days=int(o.get("timing_promote_days", 7))),
            learning_days=ld,
            window_days=wd,
        )


class Engine:
    def __init__(self, config: EngineConfig, entities: list[EntitySpec]) -> None:
        self._cfg = config
        self._specs: dict[str, EntitySpec] = {}
        self._normaliser = Normaliser(config.normaliser)
        self._house = HouseModel(config.house)
        self._routines = EntityRoutineModel(config.routine)
        self._chains = ChainModel(config.chain)
        self._drift = DriftDetector(config.drift)
        self._health = HealthTracker(config.health)
        self._router = AlertRouter(config.router)
        self._holiday = False
        self._snooze_until: datetime | None = None
        self._last_poll_day: date | None = None
        self._first_observation: datetime | None = None
        self._today_count = 0
        self._today: date | None = None
        self._last_stat: list[Alert] = []
        self._degraded = False
        self.set_entities(entities)

    # ------------------------------------------------------------ entities

    def set_entities(self, entities: list[EntitySpec]) -> tuple[set[str], set[str]]:
        new = {s.entity_id: s for s in entities}
        added = set(new) - set(self._specs)
        removed = set(self._specs) - set(new)
        for eid in removed:
            self._routines.remove(eid)
            self._health.remove(eid)
            self._normaliser.forget(eid)
            self._drift.remove_prefix(f"count:{eid}")
            self._drift.remove_prefix(f"open:{eid}")
            self._drift.remove_prefix(f"dwell:{eid}")
        for eid, s in new.items():
            old = self._specs.get(eid)
            if old is not None and old.category != s.category:
                self._routines.remove(eid)
                self._health.remove(eid)
                self._normaliser.forget(eid)
                added.add(eid)
            self._routines.add(eid, s.category, s.room)
            self._health.register(eid, s.category, s.room)
        self._specs = new
        return added, removed

    def rename_room(self, old: str, new: str) -> None:
        self._chains.rename_room(old, new)
        self._specs = {k: EntitySpec(v.entity_id, v.category, new if v.room == old else v.room) for k, v in self._specs.items()}
        for s in self._specs.values():
            self._routines.add(s.entity_id, s.category, s.room)
            self._health.register(s.entity_id, s.category, s.room)

    # -------------------------------------------------------------- state

    @property
    def holiday(self) -> bool:
        return self._holiday

    @holiday.setter
    def holiday(self, value: bool) -> None:
        self._holiday = bool(value)

    @property
    def snooze_until(self) -> datetime | None:
        return self._snooze_until

    @snooze_until.setter
    def snooze_until(self, value: datetime | None) -> None:
        self._snooze_until = value

    def is_snoozed(self, now: datetime) -> bool:
        return self._snooze_until is not None and now < self._snooze_until

    def acknowledge(self, now: datetime) -> None:
        self._router.acknowledge(now)

    def reset(self, entity_id: str | None = None) -> None:
        if entity_id is None:
            specs = list(self._specs.values())
            self.__init__(self._cfg, specs)  # type: ignore[misc]
            return
        s = self._specs.get(entity_id)
        if s is None:
            return
        self._routines.remove(entity_id)
        self._routines.add(entity_id, s.category, s.room)
        self._normaliser.forget(entity_id)
        for p in ("count:", "open:", "dwell:"):
            self._drift.remove_prefix(f"{p}{entity_id}")

    # -------------------------------------------------------------- events

    def handle_state(self, entity_id: str, old: str | None, new: str, ts: datetime, learn_only: bool = False) -> list[DeliveryAction]:
        spec = self._specs.get(entity_id)
        if spec is None:
            return []
        actions: list[DeliveryAction] = []
        events = self._normaliser.handle(entity_id, spec.category, spec.room, old, new, ts)
        for ev in events:
            if isinstance(ev, HealthEvent):
                self._health.record_health(ev)
                continue
            if ev.bypass:
                if not learn_only:
                    actions.extend(self._router.submit_panic(ev, ts))
                continue
            self._learn(ev)
        return actions

    def _learn(self, ev: ActivityEvent) -> None:
        if self._holiday:
            return
        if self._first_observation is None and ev.is_activity:
            self._first_observation = ev.timestamp
        if ev.is_activity:
            if self._today != ev.timestamp.date():
                self._today, self._today_count = ev.timestamp.date(), 0
            self._today_count += 1
        self._house.record(ev)
        self._routines.record(ev)
        self._chains.record(ev)
        self._health.record_activity(ev)

    # ---------------------------------------------------------------- poll

    def poll(self, now: datetime) -> list[DeliveryAction]:
        for ev in self._normaliser.flush(now):
            self._learn(ev)
        if self._last_poll_day is not None and now.date() != self._last_poll_day:
            self._rollover(self._last_poll_day, now)
        self._last_poll_day = now.date()

        alerts: list[Alert] = []
        alerts.extend(self._health.evaluate(now, self._routines.longest_gap, self._house.last_activity))
        learned = confidence(self._days_seen(), self._cfg.learning_days) >= 1.0
        live = self._health.live_fraction(now)
        assessment = self._house.evaluate(now, live_fraction=live)
        if learned and not self._holiday:
            if assessment.severity is not None:
                hours = (assessment.gap_s or 0) / 3600
                alerts.append(Alert(AlertClass.WELFARE, "house", "inactivity", assessment.severity,
                                    f"No activity anywhere for {hours:.1f} h; last seen in {assessment.last_room} (usual gap {((assessment.expected_s or 0) / 60):.0f} min)",
                                    now, {"gap_s": assessment.gap_s, "expected_s": assessment.expected_s, "ratio": assessment.ratio, "last_room": assessment.last_room}))
            alerts.extend(self._routines.evaluate(now))
            alerts.extend(self._chains.evaluate(now))
            alerts.extend(self._last_stat)
        self._degraded = assessment.degraded
        return self._router.submit(alerts, now, snoozed=self.is_snoozed(now), holiday=self._holiday)

    def _rollover(self, finished: date, now: datetime) -> None:
        for eid, count in self._routines.daily_counts(finished).items():
            self._drift.record(f"count:{eid}", finished, float(count), split_day_type=True)
        for eid, med in self._routines.daily_duration_medians(finished).items():
            spec = self._specs.get(eid)
            key = "open" if spec and spec.category is Category.CONTACT else "dwell"
            self._drift.record(f"{key}:{eid}", finished, med)
        for name, secs in self._chains.completions_for_day(finished).items():
            self._drift.record(f"chain:{name}", finished, secs, split_day_type=True)
        self._drift.record("rooms", finished, float(len(self._house.rooms_visited(finished))), split_day_type=True)
        self._last_stat = self._drift.check(finished, now)
        self._chains.recompute()
        cutoff = now.date() - timedelta(days=self._cfg.window_days)
        self._house.prune(cutoff)
        self._routines.prune(cutoff)
        self._chains.prune(cutoff)
        self._drift.prune(cutoff)

    # ------------------------------------------------------------ snapshot

    def _days_seen(self) -> int:
        if self._first_observation is None:
            return 0
        last = self._last_poll_day or self._first_observation.date()
        return max(0, (last - self._first_observation.date()).days)

    def snapshot(self, now: datetime) -> dict[str, Any]:
        days = self._days_seen()
        conf = confidence(days, self._cfg.learning_days)
        sev = self._router.welfare_severity
        if conf < 1.0:
            status = "learning"
        elif self._degraded:
            status = "degraded"
        else:
            status = sev.value if sev else "ok"
        open_alerts = self._router.open_alerts
        assessment_gap = (now - self._house.last_activity).total_seconds() if self._house.last_activity else None
        return {
            "welfare": {
                "status": status,
                "reasons": [a.explanation for a in open_alerts if a.cls is AlertClass.WELFARE],
                "open_alerts": [a.to_dict() for a in open_alerts],
            },
            "house": {
                "last_activity": self._house.last_activity.isoformat() if self._house.last_activity else None,
                "last_room": self._house.last_room,
                "gap_s": assessment_gap,
                "expected_s": self._house.expected_gap(now),
                "rooms_today": sorted(self._house.rooms_visited(now.date())),
                "daily_count": self._today_count if self._today == now.date() else 0,
            },
            "anomalies": [a.to_dict() for a in open_alerts if a.cls is AlertClass.STATISTICAL],
            "health": {"states": self._health.entity_states(now),
                       "dropouts_today": self._health.sitewide_dropouts_today(now.date()),
                       "alerts": [a.to_dict() for a in open_alerts if a.cls is AlertClass.HEALTH]},
            "learning": {
                "confidence": round(conf * 100, 1),
                "days_seen": days,
                "days_remaining": max(0, self._cfg.learning_days - days),
                "first_observation": self._first_observation.isoformat() if self._first_observation else None,
                "models": {"house": round(self._house.confidence(now), 2), "routines": round(self._routines.confidence(now), 2), "chains": round(self._chains.confidence(now), 2)},
            },
            "entities": {
                eid: {"category": s.category.value, "room": s.room,
                      "last_seen": (le.isoformat() if (le := self._routines.last_event(eid)) else None),
                      "expected_hours": self._routines.expected_windows(eid, now.weekday()),
                      "health": self._health.entity_states(now).get(eid, "ok")}
                for eid, s in self._specs.items()
            },
            "chains": [{"name": c.name, "rooms": c.rooms, "hop_median_s": [h[0] for h in c.hop_stats]} for c in self._chains.chains],
            "holiday": self._holiday,
            "snooze_until": self._snooze_until.isoformat() if self._snooze_until else None,
        }

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "normaliser": self._normaliser.to_dict(),
            "house": self._house.to_dict(),
            "routines": self._routines.to_dict(),
            "chains": self._chains.to_dict(),
            "drift": self._drift.to_dict(),
            "health": self._health.to_dict(),
            "router": self._router.to_dict(),
            "meta": {
                "holiday": self._holiday,
                "snooze_until": self._snooze_until.isoformat() if self._snooze_until else None,
                "last_poll_day": iso_day(self._last_poll_day) if self._last_poll_day else None,
                "first_observation": self._first_observation.isoformat() if self._first_observation else None,
                "today": iso_day(self._today) if self._today else None,
                "today_count": self._today_count,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: EngineConfig, entities: list[EntitySpec]) -> "Engine":
        e = cls(config, entities)
        if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
            return e
        e._normaliser = Normaliser.from_dict(data.get("normaliser", {}), config.normaliser)
        e._house = HouseModel.from_dict(data.get("house", {}), config.house)
        e._routines = EntityRoutineModel.from_dict(data.get("routines", {}), config.routine)
        e._chains = ChainModel.from_dict(data.get("chains", {}), config.chain)
        e._drift = DriftDetector.from_dict(data.get("drift", {}), config.drift)
        e._health = HealthTracker.from_dict(data.get("health", {}), config.health)
        e._router = AlertRouter.from_dict(data.get("router", {}), config.router)
        try:
            m = data.get("meta", {})
            e._holiday = bool(m.get("holiday", False))
            e._snooze_until = datetime.fromisoformat(m["snooze_until"]) if m.get("snooze_until") else None
            e._last_poll_day = date.fromisoformat(m["last_poll_day"]) if m.get("last_poll_day") else None
            e._first_observation = datetime.fromisoformat(m["first_observation"]) if m.get("first_observation") else None
            e._today = date.fromisoformat(m["today"]) if m.get("today") else None
            e._today_count = int(m.get("today_count", 0))
        except (KeyError, TypeError, ValueError):
            pass
        e.set_entities(entities)
        return e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/core/test_engine.py -v`
Expected: 7 passed. If `test_daytime_silence_raises_welfare_after_training` yields no push, check that `_days_seen` counts full days between first observation and the last poll day (15 training days gives 15) and that the training loop's 30-minute kitchen pulses give every daytime slot at least 8 gaps.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/engine.py tests/core/test_engine.py
git commit -m "feat(core): engine wiring models, rollover, snapshot and persistence"
```

---

### Task 13: Synthetic fixtures, fixture format and replay CLI

**Files:**
- Create: `tests/core/synth.py`
- Create: `tests/fixtures/README.md`
- Create: `scripts/replay.py`
- Create: `tests/core/test_replay_scenarios.py`

**Interfaces:**
- Fixture format: a `.jsonl` file, one JSON object per line, sorted by time: `{"t": "<ISO 8601 with offset>", "e": "<entity_id>", "s": "<state string>"}`. A sidecar `<name>.sidecar.json`: `{"site": "<name>", "entities": [{"entity_id": ..., "category": ..., "room": ...}], "options": {...}}`.
- `synth.py` produces: `Site` (entity specs), `write_fixture(path, events, specs, options)`, `normal_days(start, days, chain_minutes=4.0, seed=1) -> list[tuple[datetime, str, str]]`, scenario builders `panic_press`, `silent_kitchen`, `sitewide_dropout`, `chain_stall_at_kettle`, `kettle_absent_days`, `chain_lengthening`, `chain_jump`.
- `scripts/replay.py`: `python scripts/replay.py <fixture.jsonl> [--poll-minutes 5] [--learn-days N] [--json]` prints one line per delivery action: `<timestamp> <action> <class> <severity> <key> :: <explanation>`. `run_fixture(path, poll_minutes=5) -> list[tuple[datetime, DeliveryAction]]` is importable by tests.

- [ ] **Step 1: Write the synthetic generator**

```python
# tests/core/synth.py
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


def normal_day(day: datetime, rng: random.Random, chain_minutes: float = 4.0) -> list[Event]:
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
        room = "binary_sensor.kitchen_motion" if rng.random() < 0.5 else "binary_sensor.lounge_motion"
        _pulse(out, room, t)
        if 12 <= t.hour < 13 and rng.random() < 0.3:
            _kettle(out, t + timedelta(minutes=3))
        t += timedelta(minutes=rng.uniform(20, 40))
    out.append((day + timedelta(hours=11), "binary_sensor.side_door", "on"))
    out.append((day + timedelta(hours=11, seconds=40), "binary_sensor.side_door", "off"))
    # tv on backroom evenings
    out.append((day + timedelta(hours=18), "sensor.tv_power", "85"))
    out.append((day + timedelta(hours=22), "sensor.tv_power", "0"))
    # bed
    _pulse(out, "binary_sensor.bed_motion", day + timedelta(hours=22) + j(10))
    return out


def normal_days(start: datetime = START, days: int = 21, chain_minutes: float = 4.0, seed: int = 1) -> list[Event]:
    rng = random.Random(seed)
    out: list[Event] = []
    for d in range(days):
        out.extend(normal_day(start + timedelta(days=d), rng, chain_minutes))
    return sorted(out)


# ----------------------------------------------------------------- scenarios


def panic_press(base_days: int = 21) -> list[Event]:
    ev = normal_days(days=base_days)
    t = START + timedelta(days=base_days, hours=14)
    ev += [(t, "binary_sensor.panic_hall", "on"), (t + timedelta(seconds=5), "binary_sensor.panic_hall", "off")]
    return sorted(ev)


def silent_kitchen(base_days: int = 21) -> list[Event]:
    """Kitchen PIR stops reporting for two days while everything else continues."""
    ev = normal_days(days=base_days + 2)
    cut = START + timedelta(days=base_days)
    return [e for e in ev if not (e[1] == "binary_sensor.kitchen_motion" and e[0] >= cut)]


def sitewide_dropout(base_days: int = 21) -> list[Event]:
    ev = normal_days(days=base_days + 1)
    t = START + timedelta(days=base_days, hours=10)
    for s in SITE:
        ev.append((t, s.entity_id, "unavailable"))
    for s in SITE:
        ev.append((t + timedelta(seconds=12), s.entity_id, "off" if s.category != Category.PLUG else "0"))
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


def chain_lengthening(base_days: int = 21, drift_days: int = 14, per_day_min: float = 2.0) -> list[Event]:
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


def write_fixture(path: Path, events: list[Event], specs: Site = SITE, options: dict | None = None, site: str = "Synthetic") -> None:
    path.write_text("".join(json.dumps({"t": t.isoformat(), "e": e, "s": s}) + "\n" for t, e, s in sorted(events)))
    sidecar = path.with_suffix("").with_suffix(".sidecar.json")
    sidecar.write_text(json.dumps({
        "site": site,
        "entities": [{"entity_id": s.entity_id, "category": s.category.value, "room": s.room} for s in specs],
        "options": options or {},
    }, indent=2))
```

- [ ] **Step 2: Write the fixture README**

```markdown
# Fixtures

`*.jsonl`: one state change per line, sorted by time.

    {"t": "2026-09-07T00:25:12+01:00", "e": "binary_sensor.bed_motion", "s": "on"}

`*.sidecar.json`: site name, entity categories and rooms, and engine options.

    {"site": "Synthetic",
     "entities": [{"entity_id": "binary_sensor.bed_motion", "category": "motion", "room": "Back Bedroom"}],
     "options": {"learning_days": 14}}

Synthetic fixtures are generated by `tests/core/synth.py`. A real export is
produced by `scripts/export_fixture.py` (Part 2 plan) with entity ids and
rooms replaced by generic names. Replay any fixture with
`python scripts/replay.py tests/fixtures/<name>.jsonl`.
```

- [ ] **Step 3: Write the replay CLI**

```python
# scripts/replay.py
"""Replay a fixture through the core Engine and print the alert timeline.

Usage: python scripts/replay.py FIXTURE.jsonl [--poll-minutes 5] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.behaviour_monitor.core.alert_router import DeliveryAction  # noqa: E402
from custom_components.behaviour_monitor.core.engine import Engine, EngineConfig, EntitySpec  # noqa: E402
from custom_components.behaviour_monitor.core.events import Category  # noqa: E402


def load_fixture(path: Path) -> tuple[list[tuple[datetime, str, str]], list[EntitySpec], dict]:
    events = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        events.append((datetime.fromisoformat(row["t"]), row["e"], str(row["s"])))
    sidecar = json.loads(path.with_suffix("").with_suffix(".sidecar.json").read_text())
    specs = [EntitySpec(e["entity_id"], Category(e["category"]), e["room"]) for e in sidecar["entities"]]
    return sorted(events), specs, sidecar.get("options", {})


def run_fixture(path: Path, poll_minutes: int = 5) -> list[tuple[datetime, DeliveryAction]]:
    events, specs, options = load_fixture(path)
    engine = Engine(EngineConfig.from_options(options), specs)
    last_state: dict[str, str | None] = {s.entity_id: None for s in specs}
    timeline: list[tuple[datetime, DeliveryAction]] = []
    if not events:
        return timeline
    next_poll = events[0][0].replace(second=0, microsecond=0)
    step = timedelta(minutes=poll_minutes)
    for ts, eid, state in events:
        while next_poll <= ts:
            timeline.extend((next_poll, a) for a in engine.poll(next_poll))
            next_poll += step
        timeline.extend((ts, a) for a in engine.handle_state(eid, last_state.get(eid), state, ts))
        last_state[eid] = state
    end = events[-1][0] + timedelta(hours=6)
    while next_poll <= end:
        timeline.extend((next_poll, a) for a in engine.poll(next_poll))
        next_poll += step
    return timeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("fixture", type=Path)
    p.add_argument("--poll-minutes", type=int, default=5)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    for ts, a in run_fixture(args.fixture, args.poll_minutes):
        if args.json:
            print(json.dumps({"t": ts.isoformat(), "action": a.action, **a.alert.to_dict()}))
        else:
            al = a.alert
            print(f"{ts:%Y-%m-%d %H:%M} {a.action:13} {al.cls.value:11} {al.severity.value:8} {al.key} :: {al.explanation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write the scenario tests**

```python
# tests/core/test_replay_scenarios.py
"""End-to-end expectations on synthetic fixtures via the replay runner."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from replay import run_fixture  # noqa: E402

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
    assert any(a.kind == "silent" and a.source == "binary_sensor.kitchen_motion" for a in repairs)
    assert [a for _, a in _pushes(tl) if a.kind == "inactivity"] == []


def test_sitewide_dropout_is_one_health_alert(tmp_path):
    tl = _run(tmp_path, synth.sitewide_dropout())
    created = [a.alert for _, a in tl if a.action == "repair_create"]
    assert [a.kind for a in created].count("dropout") == 1
    assert not any(a.kind == "unavailable" for a in created)


def test_chain_stall_logs_missing_kitchen_and_silence_escalates(tmp_path):
    tl = _run(tmp_path, synth.chain_stall_at_kettle())
    logs = [a.alert for _, a in tl if a.action == "log"]
    assert any(a.kind == "chain_stall" and a.details.get("missing") == "Kitchen" for a in logs)
    day = synth.START + timedelta(days=21)
    pushes = [(t, a) for t, a in _pushes(tl) if a.kind == "inactivity" and t.date() == day.date()]
    assert pushes, "daytime silence after the stall should raise welfare"
    assert pushes[0][0] < day + timedelta(hours=12)


def test_kettle_absent_three_days_becomes_routine_notes(tmp_path):
    tl = _run(tmp_path, synth.kettle_absent_days())
    logs = [(t, a.alert) for t, a in tl if a.action == "log" and a.alert.kind == "routine_missed"]
    assert {t.date() for t, _ in logs} >= {(synth.START + timedelta(days=21 + i)).date() for i in range(3)}
    assert all(a.source == "sensor.kettle_power" for _, a in logs)


def test_gradual_lengthening_reports_drift_within_two_weeks(tmp_path):
    tl = _run(tmp_path, synth.chain_lengthening())
    drifts = [(t, a.alert) for t, a in tl if a.action == "log" and a.alert.kind == "drift" and a.alert.source.startswith("chain:")]
    assert drifts
    first_day = (drifts[0][0].date() - synth.START.date()).days
    assert 24 <= first_day <= 35
    promoted = [a.alert for _, a in tl if a.alert.kind == "timing_drift"]
    assert promoted, "sustained lengthening should promote to welfare low"


def test_sudden_jump_is_reported_by_day_three_after_the_jump(tmp_path):
    tl = _run(tmp_path, synth.chain_jump(after=7, tail=10))
    drifts = [t for t, a in tl if a.action == "log" and a.alert.kind == "drift" and a.alert.source.startswith("chain:")]
    assert drifts
    jump_day = 21 + 7
    first = (drifts[0].date() - synth.START.date()).days
    assert jump_day + 2 <= first <= jump_day + 4


@pytest.mark.parametrize("builder", [synth.normal_days, synth.panic_press, synth.silent_kitchen])
def test_replay_cli_runs(tmp_path, builder, capsys):
    path = tmp_path / "cli.jsonl"
    synth.write_fixture(path, builder(), options=OPTS)
    from replay import main
    assert main([str(path)]) == 0
    assert capsys.readouterr().out.count("\n") >= 0
```

- [ ] **Step 5: Run the scenario tests**

Run: `venv/bin/python -m pytest tests/core/test_replay_scenarios.py -v`
Expected: 9 passed. These are the tests that exercise the whole pipeline on multi-week data. If one fails, the failure names the threshold to revisit:
- `normal_days` pushing welfare: `HouseConfig.low_ratio` or the 30-minute poll step in `normal_day` produce a daytime gap ratio above 3. Inspect with `python scripts/replay.py tmp.jsonl`.
- `silent_kitchen` not raising: `longest_gap` for the kitchen PIR must be under one third of two days, which holds because the synthetic day never leaves a kitchen gap above 12 hours.
- `chain_lengthening` late: CUSUM medium `(0.5, 4.0)` with 2 minutes per day against a 4 minute baseline should cross by day 4 to 6 of drift; if not, check that `completions_for_day` records the morning run each day, which requires the chain to be assembled by the first nightly `recompute` after 10 co-occurrences.

- [ ] **Step 6: Generate committed fixtures**

```bash
venv/bin/python - <<'PY'
from pathlib import Path
from tests.core import synth
out = Path("tests/fixtures")
out.mkdir(exist_ok=True)
synth.write_fixture(out / "synthetic_normal_28d.jsonl", synth.normal_days(days=28), options={"learning_days": 14})
synth.write_fixture(out / "synthetic_chain_jump.jsonl", synth.chain_jump(), options={"learning_days": 14})
PY
venv/bin/python scripts/replay.py tests/fixtures/synthetic_chain_jump.jsonl | tail -5
```

Expected: the tail shows `log statistical medium statistical:chain:Back Bedroom → Bathroom → Kitchen:drift` lines in the last days.

- [ ] **Step 7: Commit**

```bash
git add tests/core/synth.py tests/core/test_replay_scenarios.py tests/fixtures scripts/replay.py
git commit -m "feat(core): synthetic scenarios, fixture format and replay CLI"
```

---

### Task 14: Core lint, Makefile target and CLAUDE.md note

**Files:**
- Modify: `Makefile` (add `test-core` target after `test-init`)
- Modify: `custom_components/behaviour_monitor/CLAUDE.md` (add a "core/" paragraph)

- [ ] **Step 1: Add the Makefile target**

Insert after the `test-init` target:

```makefile
test-core: ## Run only pure-core tests (no Home Assistant)
	@echo "$(GREEN)Running core tests...$(NC)"
	$(PYTHON_VENV) -m pytest tests/core -v
```

- [ ] **Step 2: Run lint and format on the new code**

Run: `venv/bin/python -m black custom_components/behaviour_monitor/core tests/core scripts/replay.py && venv/bin/python -m ruff check custom_components/behaviour_monitor/core tests/core scripts/replay.py`
Expected: black reformats long lines; ruff reports nothing.

- [ ] **Step 3: Run the whole suite**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: all existing tests still pass (the old modules are untouched in Part 1) plus the new core tests.

- [ ] **Step 4: Document the core package**

Append to `custom_components/behaviour_monitor/CLAUDE.md`:

```markdown
## core/ package

Pure Python, stdlib only, no Home Assistant imports. `engine.Engine` wires
`normaliser`, `house_model`, `entity_routine`, `chain_model`,
`drift_detector`, `health_tracker` and `alert_router`. Every module takes
timestamps as arguments and never reads the clock. Replay any fixture with
`python scripts/replay.py tests/fixtures/<name>.jsonl`. Tests live in
`tests/core/` and run with `make test-core`.
```

- [ ] **Step 5: Commit**

```bash
git add Makefile custom_components/behaviour_monitor/CLAUDE.md custom_components/behaviour_monitor/core tests/core scripts/replay.py
git commit -m "chore(core): lint, test-core target and package notes"
```

---

## Self-review against the spec

| Spec section | Task |
|---|---|
| 5 categories and normalisation | 4, 5 |
| 5.1 rooms as event field, rename without reset | 1 (field), 8 (`rename_room`), 12 (`Engine.rename_room`); display-name stripping is coordinator work in Part 2 |
| 6.1 house model, ladder, sustain, floor, blind spots | 6, 12 (`live_fraction` passed in) |
| 6.2 entity routine, expected windows, longest gap | 7 |
| 6.3 chain model, rooms as nodes, stalls, completion timing | 8 |
| 6.4 drift on counts, chain timing, rooms visited, open/dwell | 9, 12 (`_rollover`) |
| 6.5 combining into welfare | 11 (`_combine`) |
| 7 alert classes, router table, panic, acknowledge, snooze, holiday | 2, 11 |
| 8 device health | 10 |
| 9 persistence, rolling window, bootstrap (learn_only), reset | 12; store file and recorder replay are Part 2 |
| 11 fixtures and replay | 13 |

Placeholder scan: none. Type consistency checks done: `Severity` ordering used by router and house; `Alert` fields identical across modules; `DeliveryAction.action` strings are `push`, `push_clear`, `repair_create`, `repair_delete`, `log`, `log_clear` everywhere; `EntitySpec` shared by engine, synth and replay.

Known simplification versus the spec: the spec's house ladder is expressed as three ratios; `EngineConfig.from_options` derives medium and high as 2x and 4x of `house_low_ratio` so one option controls the ladder.
