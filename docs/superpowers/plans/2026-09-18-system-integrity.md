# System Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Behaviour Monitor detect and report when it is blind: per-entity health with repair issues, `blind`/`degraded` welfare with contributing counts, a corrected status-summary counter, confidence that drops with input loss, panic device liveness with a test-press service, and a start-up grace / burst-discard event gate. Ships as v5.2.

**Architecture:** Three new HA-free units (`entity_health.py`, `event_gate.py`, device-liveness additions to `panic_monitor.py`) plus coordinator wiring. `RoutineModel.overall_confidence` learns an `expected_ids` denominator. Sensor descriptions read the corrected count shape. Config entry and storage version 13.

**Tech Stack:** Python 3.12, Home Assistant custom integration (mocked in tests via `tests/conftest.py`), pytest + pytest-asyncio, ruff, mypy, black.

**Spec:** `docs/superpowers/specs/2026-09-18-system-integrity-design.md`

## Global Constraints

- Branch `feat/entity-categories`; do not create branches or push.
- Config entry version, `STORAGE_VERSION` and `BehaviourMonitorConfigFlow.VERSION` become **13**.
- New config keys, exact: `startup_grace_seconds` (default 90, UI 0–300 step 10), `burst_discard_threshold` (default 3, UI 0–10 step 1), `panic_heartbeat_hours` (default 24, UI 0–168 step 1), `panic_test_reminder_days` (default 30, UI 0–365 step 1).
- New constants, exact: `WELFARE_BLIND = "blind"`, `WELFARE_DEGRADED = "degraded"`, `AlertType.DEVICE_HEALTH = "device_health"`, `SERVICE_PANIC_TEST = "panic_test"`, `PANIC_TEST_WINDOW_SECONDS = 120`, `PANIC_LOW_BATTERY_PERCENT = 20`, `HEALTH_PRESENT = "present"`, `HEALTH_UNAVAILABLE = "unavailable"`, `HEALTH_MISSING = "missing"`, `WELFARE_BLIND_RECOMMENDATION = "No monitored entities are reporting. Check sensors and the integration options."`, `WELFARE_DEGRADED_RECOMMENDATION = "Some monitored entities are not reporting."`.
- Welfare precedence: panic-driven `alert` > `blind` > (`alert`/`concern`/`check_recommended` from alerts) > `degraded` > `ok`. Correction from the spec: an ordinary alert still outranks `degraded`, but `blind` outranks ordinary alerts because their evidence is stale when nothing reports.
- `welfare["entity_count_by_status"]` shape becomes `{"ok": int, "attention": int, "unavailable": int, "missing": int}`; per-entity alert counts move to `welfare["alert_count_by_entity"]`.
- Panic entities bypass the event gate entirely. Device-health alerts use the ordinary notification path (severity gate + repeat interval) and are also sent during holiday/snooze; they are excluded from weighted welfare scoring and force `degraded` when the status would otherwise be `ok`.
- `entity_health.py` and `event_gate.py` must not import `homeassistant`.
- Every task: `source venv/bin/activate && python -m pytest tests/ -q` green before committing; `ruff check custom_components tests` and `mypy --no-incremental custom_components` must show no NEW findings vs. `git stash` baseline (the new `import-not-found` entries for `homeassistant.helpers.issue_registry` are expected, like the existing ones). `black` any new file.
- Conventional commits, `feat:`/`fix:`/`test:`/`docs:` (minor release).
- Commands run from `/Users/abourne/Documents/source/behaviour-monitor`.

---

## File Structure

| File | Responsibility |
|---|---|
| `const.py` | New CONF/DEFAULT/SERVICE/health/welfare constants, version 13 |
| `alert_result.py` | `AlertType.DEVICE_HEALTH` |
| `entity_health.py` (new) | `resolve_entity_health`, `qualify_welfare`, `count_by_status` |
| `event_gate.py` (new) | `EventGate` (grace + burst buffer) |
| `panic_monitor.py` | Device liveness fields, test window, device alerts, new serialisation shape |
| `routine_model.py` | `overall_confidence(now, expected_ids)` |
| `coordinator.py` | Health facts, repair issues, qualified welfare, counts, confidence, gate wiring, device wiring, blind notification |
| `sensor.py` | Summary value from new counts; welfare attrs |
| `button.py` | `devices` attribute |
| `__init__.py` | `panic_test` service, v13 migration |
| `services.yaml`, `translations/en.json` | Service, fields, repair issue |
| `config_flow.py` | Four fields, VERSION 13 |
| `tests/conftest.py` | `issue_registry` mock |
| `tests/test_entity_health.py`, `tests/test_event_gate.py` (new) | Unit tests |
| `tests/test_panic_monitor.py`, `tests/test_routine_model.py`, `tests/test_coordinator.py`, `tests/test_sensor.py`, `tests/test_button.py`, `tests/test_config_flow.py`, `tests/test_init.py` | Extended |
| `README.md`, `.planning/*` | Docs |

---

### Task 1: Constants, alert type, and `entity_health.py`

**Files:**
- Modify: `custom_components/behaviour_monitor/const.py`, `custom_components/behaviour_monitor/alert_result.py`
- Create: `custom_components/behaviour_monitor/entity_health.py`
- Test: `tests/test_entity_health.py` (new)

**Interfaces produced:**
```python
# const.py
CONF_STARTUP_GRACE_SECONDS = "startup_grace_seconds"; DEFAULT_STARTUP_GRACE_SECONDS = 90
CONF_BURST_DISCARD_THRESHOLD = "burst_discard_threshold"; DEFAULT_BURST_DISCARD_THRESHOLD = 3
CONF_PANIC_HEARTBEAT_HOURS = "panic_heartbeat_hours"; DEFAULT_PANIC_HEARTBEAT_HOURS = 24
CONF_PANIC_TEST_REMINDER_DAYS = "panic_test_reminder_days"; DEFAULT_PANIC_TEST_REMINDER_DAYS = 30
SERVICE_PANIC_TEST = "panic_test"; PANIC_TEST_WINDOW_SECONDS = 120; PANIC_LOW_BATTERY_PERCENT = 20
HEALTH_PRESENT = "present"; HEALTH_UNAVAILABLE = "unavailable"; HEALTH_MISSING = "missing"
WELFARE_BLIND = "blind"; WELFARE_DEGRADED = "degraded"
WELFARE_BLIND_RECOMMENDATION = "No monitored entities are reporting. Check sensors and the integration options."
WELFARE_DEGRADED_RECOMMENDATION = "Some monitored entities are not reporting."
# alert_result.py
AlertType.DEVICE_HEALTH = "device_health"
# entity_health.py
def resolve_entity_health(entity_ids, states: Mapping[str, str | None], in_registry: Collection[str]) -> dict[str, str]
def count_by_status(entity_ids, health: Mapping[str, str], contributing: Collection[str], alerting: Collection[str]) -> dict[str, int]
def qualify_welfare(welfare: dict, *, contributing: list[str], expected: list[str], missing: list[str], unavailable: list[str], panic_active: bool, device_alerts: bool) -> dict
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_entity_health.py`:

```python
"""Tests for entity_health: health classification and welfare qualification."""

from __future__ import annotations

import pytest

from custom_components.behaviour_monitor.alert_result import AlertType
from custom_components.behaviour_monitor.const import (
    CONF_BURST_DISCARD_THRESHOLD,
    CONF_PANIC_HEARTBEAT_HOURS,
    CONF_PANIC_TEST_REMINDER_DAYS,
    CONF_STARTUP_GRACE_SECONDS,
    DEFAULT_BURST_DISCARD_THRESHOLD,
    DEFAULT_PANIC_HEARTBEAT_HOURS,
    DEFAULT_PANIC_TEST_REMINDER_DAYS,
    DEFAULT_STARTUP_GRACE_SECONDS,
    HEALTH_MISSING,
    HEALTH_PRESENT,
    HEALTH_UNAVAILABLE,
    PANIC_LOW_BATTERY_PERCENT,
    PANIC_TEST_WINDOW_SECONDS,
    SERVICE_PANIC_TEST,
    WELFARE_BLIND,
    WELFARE_BLIND_RECOMMENDATION,
    WELFARE_DEGRADED,
    WELFARE_DEGRADED_RECOMMENDATION,
)
from custom_components.behaviour_monitor.entity_health import (
    count_by_status,
    qualify_welfare,
    resolve_entity_health,
)


class TestConstants:
    def test_values(self) -> None:
        assert CONF_STARTUP_GRACE_SECONDS == "startup_grace_seconds"
        assert DEFAULT_STARTUP_GRACE_SECONDS == 90
        assert CONF_BURST_DISCARD_THRESHOLD == "burst_discard_threshold"
        assert DEFAULT_BURST_DISCARD_THRESHOLD == 3
        assert CONF_PANIC_HEARTBEAT_HOURS == "panic_heartbeat_hours"
        assert DEFAULT_PANIC_HEARTBEAT_HOURS == 24
        assert CONF_PANIC_TEST_REMINDER_DAYS == "panic_test_reminder_days"
        assert DEFAULT_PANIC_TEST_REMINDER_DAYS == 30
        assert SERVICE_PANIC_TEST == "panic_test"
        assert PANIC_TEST_WINDOW_SECONDS == 120
        assert PANIC_LOW_BATTERY_PERCENT == 20
        assert (HEALTH_PRESENT, HEALTH_UNAVAILABLE, HEALTH_MISSING) == ("present", "unavailable", "missing")
        assert (WELFARE_BLIND, WELFARE_DEGRADED) == ("blind", "degraded")
        assert AlertType.DEVICE_HEALTH.value == "device_health"


class TestResolveEntityHealth:
    def test_present(self) -> None:
        assert resolve_entity_health(["a.b"], {"a.b": "on"}, set())["a.b"] == HEALTH_PRESENT

    def test_present_with_empty_state_string(self) -> None:
        # coordinator passes "" for "exists, non-string state" (test doubles)
        assert resolve_entity_health(["a.b"], {"a.b": ""}, set())["a.b"] == HEALTH_PRESENT

    @pytest.mark.parametrize("sv", ["unavailable", "unknown"])
    def test_unavailable_state(self, sv: str) -> None:
        assert resolve_entity_health(["a.b"], {"a.b": sv}, set())["a.b"] == HEALTH_UNAVAILABLE

    def test_no_state_but_in_registry_is_unavailable(self) -> None:
        assert resolve_entity_health(["a.b"], {"a.b": None}, {"a.b"})["a.b"] == HEALTH_UNAVAILABLE

    def test_no_state_not_in_registry_is_missing(self) -> None:
        assert resolve_entity_health(["a.b"], {"a.b": None}, set())["a.b"] == HEALTH_MISSING

    def test_absent_from_states_mapping_is_missing(self) -> None:
        assert resolve_entity_health(["a.b"], {}, set())["a.b"] == HEALTH_MISSING

    def test_returns_entry_for_every_entity(self) -> None:
        out = resolve_entity_health(["a.b", "c.d"], {"a.b": "on"}, set())
        assert out == {"a.b": HEALTH_PRESENT, "c.d": HEALTH_MISSING}


class TestCountByStatus:
    def test_counts(self) -> None:
        health = {"a": "present", "b": "present", "c": "unavailable", "d": "missing", "p": "present"}
        # p is a panic entity: present but not contributing
        counts = count_by_status(["a", "b", "c", "d", "p"], health, contributing=["a", "b"], alerting=["b"])
        assert counts == {"ok": 1, "attention": 1, "unavailable": 1, "missing": 1}

    def test_empty(self) -> None:
        assert count_by_status([], {}, [], []) == {"ok": 0, "attention": 0, "unavailable": 0, "missing": 0}


def _welfare(status: str) -> dict:
    return {"status": status, "reasons": ["r"], "summary": "s", "recommendation": "rec", "alert_count_by_entity": {}}


class TestQualifyWelfare:
    def test_ok_all_reporting_gets_suffix_and_counts(self) -> None:
        w = qualify_welfare(_welfare("ok"), contributing=["a", "b"], expected=["a", "b"], missing=[], unavailable=[], panic_active=False, device_alerts=False)
        assert w["status"] == "ok"
        assert w["summary"].endswith("(2 of 2 reporting)")
        assert w["contributing_entities"] == 2 and w["expected_entities"] == 2
        assert w["missing_entities"] == [] and w["unavailable_entities"] == []

    def test_blind_when_nothing_contributes(self) -> None:
        w = qualify_welfare(_welfare("ok"), contributing=[], expected=["a", "b"], missing=["a"], unavailable=["b"], panic_active=False, device_alerts=False)
        assert w["status"] == WELFARE_BLIND
        assert w["recommendation"] == WELFARE_BLIND_RECOMMENDATION
        assert w["summary"] == "blind: 0 of 2 entities reporting"
        assert w["reasons"] == ["r"]  # kept

    def test_blind_outranks_ordinary_alert(self) -> None:
        w = qualify_welfare(_welfare("alert"), contributing=[], expected=["a"], missing=["a"], unavailable=[], panic_active=False, device_alerts=False)
        assert w["status"] == WELFARE_BLIND

    def test_panic_outranks_blind(self) -> None:
        w = qualify_welfare(_welfare("alert"), contributing=[], expected=["a"], missing=["a"], unavailable=[], panic_active=True, device_alerts=False)
        assert w["status"] == "alert"
        assert w["recommendation"] == "rec"

    def test_degraded_on_partial_loss_when_ok(self) -> None:
        w = qualify_welfare(_welfare("ok"), contributing=["a"], expected=["a", "b"], missing=["b"], unavailable=[], panic_active=False, device_alerts=False)
        assert w["status"] == WELFARE_DEGRADED
        assert w["recommendation"] == WELFARE_DEGRADED_RECOMMENDATION
        assert w["summary"] == "degraded: 1 of 2 entities reporting"

    def test_ordinary_alert_outranks_degraded(self) -> None:
        w = qualify_welfare(_welfare("concern"), contributing=["a"], expected=["a", "b"], missing=["b"], unavailable=[], panic_active=False, device_alerts=False)
        assert w["status"] == "concern"
        assert w["summary"].endswith("(1 of 2 reporting)")

    def test_device_alert_degrades_ok(self) -> None:
        w = qualify_welfare(_welfare("ok"), contributing=["a"], expected=["a"], missing=[], unavailable=[], panic_active=False, device_alerts=True)
        assert w["status"] == WELFARE_DEGRADED

    def test_no_expected_entities_stays_ok(self) -> None:
        w = qualify_welfare(_welfare("ok"), contributing=[], expected=[], missing=[], unavailable=[], panic_active=False, device_alerts=False)
        assert w["status"] == "ok"
        assert w["summary"].endswith("(0 of 0 reporting)")

    def test_input_dict_not_mutated(self) -> None:
        src = _welfare("ok")
        qualify_welfare(src, contributing=[], expected=["a"], missing=["a"], unavailable=[], panic_active=False, device_alerts=False)
        assert src["status"] == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_health.py -q`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

`alert_result.py`: in `AlertType` add `DEVICE_HEALTH = "device_health"` after `PANIC`.

`const.py`: after `CONF_PANIC_RENOTIFY_MINUTES` add
```python
# New v5.2 config keys (system integrity)
CONF_STARTUP_GRACE_SECONDS: Final = "startup_grace_seconds"
CONF_BURST_DISCARD_THRESHOLD: Final = "burst_discard_threshold"
CONF_PANIC_HEARTBEAT_HOURS: Final = "panic_heartbeat_hours"
CONF_PANIC_TEST_REMINDER_DAYS: Final = "panic_test_reminder_days"
```
after `DEFAULT_PANIC_RENOTIFY_MINUTES` add
```python
# New v5.2 defaults
DEFAULT_STARTUP_GRACE_SECONDS: Final = 90  # seconds after setup during which events are ignored; 0 disables
DEFAULT_BURST_DISCARD_THRESHOLD: Final = 3  # distinct entities changing in one second = artifact; 0 disables
DEFAULT_PANIC_HEARTBEAT_HOURS: Final = 24  # hours without a report before a panic device alert; 0 disables
DEFAULT_PANIC_TEST_REMINDER_DAYS: Final = 30  # days without a test press before a reminder; 0 disables
PANIC_TEST_WINDOW_SECONDS: Final = 120
PANIC_LOW_BATTERY_PERCENT: Final = 20
```
after `SERVICE_ACKNOWLEDGE_PANIC` add `SERVICE_PANIC_TEST: Final = "panic_test"`.
after `WELFARE_ALERT: Final = "alert"` add
```python
WELFARE_BLIND: Final = "blind"  # no monitored entity is reporting
WELFARE_DEGRADED: Final = "degraded"  # some inputs lost or a device-health alert is active
```
after `WELFARE_PANIC_RECOMMENDATION` add
```python
WELFARE_BLIND_RECOMMENDATION: Final = "No monitored entities are reporting. Check sensors and the integration options."
WELFARE_DEGRADED_RECOMMENDATION: Final = "Some monitored entities are not reporting."

# Entity health classification (v5.2)
HEALTH_PRESENT: Final = "present"
HEALTH_UNAVAILABLE: Final = "unavailable"
HEALTH_MISSING: Final = "missing"
```

Create `custom_components/behaviour_monitor/entity_health.py`:
```python
"""Entity health classification and welfare qualification.

Pure Python stdlib only. Zero Home Assistant imports. The coordinator supplies
raw state strings and registry membership; this module decides health and
whether the welfare status may honestly say "ok".
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from typing import Any

from .const import (
    HEALTH_MISSING,
    HEALTH_PRESENT,
    HEALTH_UNAVAILABLE,
    WELFARE_BLIND,
    WELFARE_BLIND_RECOMMENDATION,
    WELFARE_DEGRADED,
    WELFARE_DEGRADED_RECOMMENDATION,
    WELFARE_OK,
)

_UNAVAILABLE_STATES = frozenset({"unavailable", "unknown"})


def resolve_entity_health(
    entity_ids: Iterable[str],
    states: Mapping[str, str | None],
    in_registry: Collection[str],
) -> dict[str, str]:
    """Classify each entity as present / unavailable / missing.

    ``states[eid]`` is the raw state string, ``""`` for an entity that exists
    but whose state is not a string (test doubles), or ``None`` when the entity
    has no state object at all.
    """
    out: dict[str, str] = {}
    for eid in entity_ids:
        sv = states.get(eid)
        if sv is None:
            out[eid] = HEALTH_UNAVAILABLE if eid in in_registry else HEALTH_MISSING
        elif sv in _UNAVAILABLE_STATES:
            out[eid] = HEALTH_UNAVAILABLE
        else:
            out[eid] = HEALTH_PRESENT
    return out


def count_by_status(
    entity_ids: Iterable[str],
    health: Mapping[str, str],
    contributing: Collection[str],
    alerting: Collection[str],
) -> dict[str, int]:
    """Counts the status-summary sensor renders: ok / attention / unavailable / missing."""
    counts = {"ok": 0, "attention": 0, "unavailable": 0, "missing": 0}
    for eid in entity_ids:
        h = health.get(eid, HEALTH_MISSING)
        if h == HEALTH_MISSING:
            counts["missing"] += 1
        elif h == HEALTH_UNAVAILABLE:
            counts["unavailable"] += 1
        elif eid in contributing:
            counts["attention" if eid in alerting else "ok"] += 1
    return counts


def qualify_welfare(
    welfare: dict[str, Any],
    *,
    contributing: list[str],
    expected: list[str],
    missing: list[str],
    unavailable: list[str],
    panic_active: bool,
    device_alerts: bool,
) -> dict[str, Any]:
    """Return a copy of ``welfare`` that never says "ok" from no data.

    Precedence: panic alert > blind > alert/concern/check from alerts >
    degraded > ok. Always adds contributing/expected counts and the missing
    and unavailable id lists.
    """
    out = dict(welfare)
    n_c, n_e = len(contributing), len(expected)
    out["contributing_entities"] = n_c
    out["expected_entities"] = n_e
    out["missing_entities"] = list(missing)
    out["unavailable_entities"] = list(unavailable)
    if panic_active:
        return out
    if n_e > 0 and n_c == 0:
        out["status"] = WELFARE_BLIND
        out["recommendation"] = WELFARE_BLIND_RECOMMENDATION
        out["summary"] = f"blind: 0 of {n_e} entities reporting"
        return out
    if out.get("status") == WELFARE_OK and (n_c < n_e or device_alerts):
        out["status"] = WELFARE_DEGRADED
        out["recommendation"] = WELFARE_DEGRADED_RECOMMENDATION
        out["summary"] = f"degraded: {n_c} of {n_e} entities reporting"
        return out
    out["summary"] = f"{out.get('summary', '')} ({n_c} of {n_e} reporting)"
    return out
```

- [ ] **Step 4: Run tests and lint**

Run: `source venv/bin/activate && black custom_components/behaviour_monitor/entity_health.py tests/test_entity_health.py && python -m pytest tests/ -q | tail -1 && ruff check custom_components/behaviour_monitor/entity_health.py tests/test_entity_health.py`
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/const.py custom_components/behaviour_monitor/alert_result.py custom_components/behaviour_monitor/entity_health.py tests/test_entity_health.py
git commit -m "feat: entity health classification and blind/degraded welfare qualification"
```

---

### Task 2: `EventGate`

**Files:**
- Create: `custom_components/behaviour_monitor/event_gate.py`
- Test: `tests/test_event_gate.py` (new)

**Interfaces produced:**
```python
@dataclass(frozen=True)
class GatedEvent: entity_id: str; old_state: str | None; new_state: str; timestamp: datetime
class EventGate:
    def __init__(self, grace_seconds: int, burst_threshold: int) -> None
    def arm(self, now: datetime) -> None
    def in_grace(self, now: datetime) -> bool
    def submit(self, entity_id, old_state, new_state, now) -> bool   # False when dropped by grace
    def flush(self, now: datetime, *, force: bool = False) -> list[GatedEvent]
    @property pending(self) -> int
    @property dropped_bursts(self) -> int
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_event_gate.py`:
```python
"""Tests for EventGate — start-up grace and same-second burst discard."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.behaviour_monitor.event_gate import EventGate, GatedEvent

T0 = datetime(2026, 9, 18, 12, 0, 0)


def _sub(g: EventGate, eid: str, t: datetime, old: str | None = "off", new: str = "on") -> bool:
    return g.submit(eid, old, new, t)


class TestGrace:
    def test_unarmed_has_no_grace(self) -> None:
        g = EventGate(90, 3)
        assert g.in_grace(T0) is False
        assert _sub(g, "a", T0) is True

    def test_events_dropped_during_grace(self) -> None:
        g = EventGate(90, 3)
        g.arm(T0)
        assert g.in_grace(T0 + timedelta(seconds=89)) is True
        assert _sub(g, "a", T0 + timedelta(seconds=10)) is False
        assert g.pending == 0

    def test_events_accepted_after_grace(self) -> None:
        g = EventGate(90, 3)
        g.arm(T0)
        assert _sub(g, "a", T0 + timedelta(seconds=90)) is True
        assert g.pending == 1

    def test_zero_grace_disables(self) -> None:
        g = EventGate(0, 3)
        g.arm(T0)
        assert _sub(g, "a", T0) is True


class TestBurst:
    def test_flush_returns_only_completed_seconds(self) -> None:
        g = EventGate(0, 3)
        _sub(g, "a", T0)
        _sub(g, "b", T0 + timedelta(seconds=1))
        out = g.flush(T0 + timedelta(seconds=1, milliseconds=500))
        assert [e.entity_id for e in out] == ["a"]
        assert g.pending == 1

    def test_force_flushes_current_second(self) -> None:
        g = EventGate(0, 3)
        _sub(g, "a", T0)
        out = g.flush(T0, force=True)
        assert [e.entity_id for e in out] == ["a"]
        assert g.pending == 0

    def test_burst_at_threshold_dropped(self) -> None:
        g = EventGate(0, 3)
        for eid in ("a", "b", "c"):
            _sub(g, eid, T0)
        assert g.flush(T0 + timedelta(seconds=2)) == []
        assert g.dropped_bursts == 1

    def test_below_threshold_kept(self) -> None:
        g = EventGate(0, 3)
        _sub(g, "a", T0)
        _sub(g, "b", T0 + timedelta(milliseconds=300))
        out = g.flush(T0 + timedelta(seconds=2))
        assert [e.entity_id for e in out] == ["a", "b"]
        assert g.dropped_bursts == 0

    def test_same_entity_repeated_is_one_distinct(self) -> None:
        g = EventGate(0, 3)
        for _ in range(5):
            _sub(g, "a", T0, "off", "on")
        assert len(g.flush(T0 + timedelta(seconds=2))) == 5

    def test_threshold_zero_disables(self) -> None:
        g = EventGate(0, 0)
        for eid in ("a", "b", "c", "d"):
            _sub(g, eid, T0)
        assert len(g.flush(T0 + timedelta(seconds=2))) == 4

    def test_events_preserve_order_and_fields(self) -> None:
        g = EventGate(0, 3)
        _sub(g, "a", T0, None, "on")
        _sub(g, "a", T0 + timedelta(milliseconds=10), "on", "off")
        out = g.flush(T0 + timedelta(seconds=2))
        assert out == [
            GatedEvent("a", None, "on", T0),
            GatedEvent("a", "on", "off", T0 + timedelta(milliseconds=10)),
        ]

    def test_buckets_independent(self) -> None:
        g = EventGate(0, 3)
        for eid in ("a", "b", "c"):
            _sub(g, eid, T0)  # burst second
        _sub(g, "d", T0 + timedelta(seconds=1))  # clean second
        out = g.flush(T0 + timedelta(seconds=3))
        assert [e.entity_id for e in out] == ["d"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_event_gate.py -q`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Implement**

Create `custom_components/behaviour_monitor/event_gate.py`:
```python
"""Start-up grace period and same-second burst discard for state events.

Pure Python stdlib only. Zero Home Assistant imports. Integration reloads and
Home Assistant restarts write synthetic states to every entity at once; this
gate drops events during a grace window after setup and drops any one-second
bucket in which too many distinct entities change together.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class GatedEvent:
    entity_id: str
    old_state: str | None
    new_state: str
    timestamp: datetime


class EventGate:
    """Buffer state events by wall-clock second and discard artifacts."""

    def __init__(self, grace_seconds: int, burst_threshold: int) -> None:
        self._grace = timedelta(seconds=max(0, int(grace_seconds)))
        self._threshold = max(0, int(burst_threshold))
        self._grace_until: datetime | None = None
        self._buckets: dict[int, list[GatedEvent]] = {}
        self._dropped_bursts = 0

    def arm(self, now: datetime) -> None:
        """Start the grace window at ``now`` (no-op when grace is 0)."""
        self._grace_until = now + self._grace if self._grace else None

    def in_grace(self, now: datetime) -> bool:
        return self._grace_until is not None and now < self._grace_until

    def submit(self, entity_id: str, old_state: str | None, new_state: str, now: datetime) -> bool:
        """Buffer an event. Returns False when it was dropped by the grace window."""
        if self.in_grace(now):
            return False
        key = int(now.timestamp())
        self._buckets.setdefault(key, []).append(GatedEvent(entity_id, old_state, new_state, now))
        return True

    def flush(self, now: datetime, *, force: bool = False) -> list[GatedEvent]:
        """Release buckets for seconds earlier than ``now`` (all when ``force``).

        A bucket in which at least ``burst_threshold`` distinct entities appear
        is dropped entirely and counted in ``dropped_bursts``.
        """
        current = int(now.timestamp())
        out: list[GatedEvent] = []
        for key in sorted(self._buckets):
            if not force and key >= current:
                continue
            events = self._buckets.pop(key)
            distinct = {e.entity_id for e in events}
            if self._threshold and len(distinct) >= self._threshold:
                self._dropped_bursts += 1
                continue
            out.extend(events)
        return out

    @property
    def pending(self) -> int:
        return sum(len(v) for v in self._buckets.values())

    @property
    def dropped_bursts(self) -> int:
        return self._dropped_bursts
```

- [ ] **Step 4: Run tests and lint**

Run: `source venv/bin/activate && black custom_components/behaviour_monitor/event_gate.py tests/test_event_gate.py && python -m pytest tests/test_event_gate.py -q && ruff check custom_components/behaviour_monitor/event_gate.py tests/test_event_gate.py`
Expected: 12 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/event_gate.py tests/test_event_gate.py
git commit -m "feat: EventGate with start-up grace and same-second burst discard"
```

---

### Task 3: Panic device liveness in `PanicMonitor`

**Files:**
- Modify: `custom_components/behaviour_monitor/panic_monitor.py`
- Test: `tests/test_panic_monitor.py`

**Interfaces produced (additions):**
```python
def update_device(self, entity_id, *, available: bool, last_reported: datetime | None, battery: float | None) -> None
def device_status(self, entity_id) -> dict[str, Any]   # {"available", "last_reported" iso|None, "battery", "last_test" iso|None}
def open_test_window(self, now, until: datetime, entity_id: str | None = None) -> list[str]
def in_test_window(self, entity_id, now) -> bool
def record_test(self, entity_id, now) -> None          # sets last_test, closes the window
def device_alerts(self, now, heartbeat: timedelta | None, reminder: timedelta | None, low_battery: float) -> list[tuple[str, str, str, str]]
    # (entity_id, kind in {"unavailable","heartbeat","battery","test_reminder"}, severity in {"low","medium","high"}, message)
def known_devices(self) -> list[str]
to_dict() -> {"active": {...}, "devices": {eid: {"last_test": iso|None, "battery": ..., "last_reported": iso|None, "available": bool}}}
from_dict(...) accepts the new shape AND the legacy flat shape
```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_panic_monitor.py`:
```python
from custom_components.behaviour_monitor.panic_monitor import PanicMonitor as _PM  # noqa: F811

H24 = timedelta(hours=24)
D30 = timedelta(days=30)


class TestDeviceLiveness:
    def test_update_and_status(self) -> None:
        m = PanicMonitor()
        m.update_device("binary_sensor.sos", available=True, last_reported=T0, battery=87.0)
        s = m.device_status("binary_sensor.sos")
        assert s == {"available": True, "last_reported": T0.isoformat(), "battery": 87.0, "last_test": None}
        assert m.known_devices() == ["binary_sensor.sos"]

    def test_status_unknown_device(self) -> None:
        assert PanicMonitor().device_status("binary_sensor.nope") == {"available": False, "last_reported": None, "battery": None, "last_test": None}

    def test_test_window_and_record(self) -> None:
        m = PanicMonitor()
        m.update_device("binary_sensor.sos", available=True, last_reported=T0, battery=None)
        assert m.open_test_window(T0, T0 + timedelta(seconds=120)) == ["binary_sensor.sos"]
        assert m.in_test_window("binary_sensor.sos", T0 + timedelta(seconds=119)) is True
        assert m.in_test_window("binary_sensor.sos", T0 + timedelta(seconds=120)) is False
        m.record_test("binary_sensor.sos", T0 + timedelta(seconds=30))
        assert m.device_status("binary_sensor.sos")["last_test"] == (T0 + timedelta(seconds=30)).isoformat()
        assert m.in_test_window("binary_sensor.sos", T0 + timedelta(seconds=31)) is False
        # a test press never activates the panic
        assert m.is_active("binary_sensor.sos") is False

    def test_open_window_for_one_or_unknown(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=T0, battery=None)
        m.update_device("b", available=True, last_reported=T0, battery=None)
        assert m.open_test_window(T0, T0 + FIVE, "a") == ["a"]
        assert m.in_test_window("b", T0) is False
        assert m.open_test_window(T0, T0 + FIVE, "zzz") == []

    def test_device_alerts_unavailable(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=False, last_reported=T0, battery=None)
        alerts = m.device_alerts(T0, None, None, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "unavailable", "high")]

    def test_device_alerts_heartbeat(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=T0, battery=None)
        assert m.device_alerts(T0 + H24 - timedelta(seconds=1), H24, None, 20) == []
        alerts = m.device_alerts(T0 + H24, H24, None, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "heartbeat", "high")]
        assert "24h" in alerts[0][3]

    def test_device_alerts_no_report_ever_with_heartbeat(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=None, battery=None)
        alerts = m.device_alerts(T0, H24, None, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "heartbeat", "high")]
        assert "never" in alerts[0][3]

    def test_device_alerts_battery(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=T0, battery=20)
        alerts = m.device_alerts(T0, None, None, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "battery", "medium")]
        m.update_device("a", available=True, last_reported=T0, battery=21)
        assert m.device_alerts(T0, None, None, 20) == []

    def test_device_alerts_test_reminder(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=T0, battery=None)
        alerts = m.device_alerts(T0, None, D30, 20)
        assert [(e, k, s) for e, k, s, _ in alerts] == [("a", "test_reminder", "low")]
        assert "never" in alerts[0][3]
        m.record_test("a", T0)
        assert m.device_alerts(T0 + D30 - timedelta(seconds=1), None, D30, 20) == []
        assert [k for _, k, _, _ in m.device_alerts(T0 + D30, None, D30, 20)] == ["test_reminder"]

    def test_disabled_checks(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=True, last_reported=None, battery=None)
        assert m.device_alerts(T0 + timedelta(days=400), None, None, 20) == []

    def test_multiple_conditions_ordered(self) -> None:
        m = PanicMonitor()
        m.update_device("a", available=False, last_reported=None, battery=5)
        kinds = [k for _, k, _, _ in m.device_alerts(T0, H24, D30, 20)]
        assert kinds == ["unavailable", "heartbeat", "battery", "test_reminder"]


class TestSerializationV2:
    def test_round_trip_with_devices(self) -> None:
        m = PanicMonitor()
        m.press("a", T0)
        m.update_device("a", available=True, last_reported=T0, battery=50)
        m.record_test("a", T0 - FIVE)
        m.update_device("b", available=False, last_reported=None, battery=None)
        d = m.to_dict()
        assert set(d) == {"active", "devices"}
        r = PanicMonitor.from_dict(d)
        assert r.active() == m.active()
        assert r.device_status("a") == m.device_status("a")
        assert r.device_status("b")["available"] is False
        # test window is not persisted
        assert r.in_test_window("a", T0) is False

    def test_legacy_flat_shape(self) -> None:
        legacy = {"a": {"active_since": T0.isoformat(), "last_notified": T0.isoformat(), "acknowledged": True}}
        r = PanicMonitor.from_dict(legacy)
        assert [e for e, _, acked in r.active()] == ["a"]
        assert r.active()[0][2] is True
        assert r.known_devices() == []

    def test_malformed_devices_dropped(self) -> None:
        r = PanicMonitor.from_dict({"active": {}, "devices": {"a": "bad", "b": {"last_test": "nope", "available": True}}})
        assert r.known_devices() == ["b"]
        assert r.device_status("b")["last_test"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_panic_monitor.py -q 2>&1 | tail -3`
Expected: FAIL (AttributeError update_device etc.). Existing `TestSerialization.test_round_trip` and `test_from_dict_*` will keep passing only after Step 3 makes `from_dict` accept both shapes.

- [ ] **Step 3: Implement**

In `panic_monitor.py`:

(a) Add a second dataclass after `_PanicState`:
```python
@dataclass
class _DeviceState:
    available: bool = False
    last_reported: datetime | None = None
    battery: float | None = None
    last_test: datetime | None = None
    test_window_until: datetime | None = None  # not persisted
```

(b) In `__init__` add `self._devices: dict[str, _DeviceState] = {}`.

(c) Add a section after the Queries section:
```python
    # ------------------------------------------------------------------
    # Device liveness
    # ------------------------------------------------------------------

    def update_device(
        self,
        entity_id: str,
        *,
        available: bool,
        last_reported: datetime | None,
        battery: float | None,
    ) -> None:
        d = self._devices.setdefault(entity_id, _DeviceState())
        d.available = available
        d.last_reported = last_reported
        d.battery = battery

    def known_devices(self) -> list[str]:
        return sorted(self._devices)

    def device_status(self, entity_id: str) -> dict[str, Any]:
        d = self._devices.get(entity_id, _DeviceState())
        return {
            "available": d.available,
            "last_reported": d.last_reported.isoformat() if d.last_reported else None,
            "battery": d.battery,
            "last_test": d.last_test.isoformat() if d.last_test else None,
        }

    def open_test_window(self, now: datetime, until: datetime, entity_id: str | None = None) -> list[str]:
        """Open a test-press window for one known device or all. Returns ids opened."""
        targets = [entity_id] if entity_id is not None else list(self._devices)
        opened: list[str] = []
        for eid in targets:
            d = self._devices.get(eid)
            if d is None:
                continue
            d.test_window_until = until
            opened.append(eid)
        return opened

    def in_test_window(self, entity_id: str, now: datetime) -> bool:
        d = self._devices.get(entity_id)
        return d is not None and d.test_window_until is not None and now < d.test_window_until

    def record_test(self, entity_id: str, now: datetime) -> None:
        d = self._devices.setdefault(entity_id, _DeviceState())
        d.last_test = now
        d.test_window_until = None

    def device_alerts(
        self,
        now: datetime,
        heartbeat: timedelta | None,
        reminder: timedelta | None,
        low_battery: float,
    ) -> list[tuple[str, str, str, str]]:
        """(entity_id, kind, severity, message) for every device-health condition.

        kind ∈ {unavailable, heartbeat, battery, test_reminder}; severity ∈ {low, medium, high}.
        ``heartbeat``/``reminder`` of None disable those checks.
        """
        out: list[tuple[str, str, str, str]] = []
        for eid in sorted(self._devices):
            d = self._devices[eid]
            if not d.available:
                out.append((eid, "unavailable", "high", f"panic button {eid} is unavailable"))
            if heartbeat is not None:
                if d.last_reported is None:
                    out.append((eid, "heartbeat", "high", f"panic button {eid} has never reported"))
                elif now - d.last_reported >= heartbeat:
                    out.append((eid, "heartbeat", "high", f"panic button {eid} has not reported for {_fmt(now - d.last_reported)}"))
            if d.battery is not None and d.battery <= low_battery:
                out.append((eid, "battery", "medium", f"panic button {eid} battery at {int(d.battery)}%"))
            if reminder is not None:
                if d.last_test is None:
                    out.append((eid, "test_reminder", "low", f"panic button {eid} has never been test-pressed"))
                elif now - d.last_test >= reminder:
                    out.append((eid, "test_reminder", "low", f"panic button {eid} has not been test-pressed for {_fmt(now - d.last_test)}"))
        return out
```
and a module-level helper above the class:
```python
def _fmt(delta: timedelta) -> str:
    """Short human duration: '3d', '24h', '45m'."""
    secs = int(delta.total_seconds())
    if secs >= 86400:
        return f"{secs // 86400}d"
    if secs >= 3600:
        return f"{secs // 3600}h"
    return f"{max(1, secs // 60)}m"
```

(d) Replace `to_dict` / `from_dict` with:
```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "active": {
                eid: {
                    "active_since": s.active_since.isoformat(),
                    "last_notified": s.last_notified.isoformat(),
                    "acknowledged": s.acknowledged,
                }
                for eid, s in self._states.items()
            },
            "devices": {
                eid: {
                    "available": d.available,
                    "last_reported": d.last_reported.isoformat() if d.last_reported else None,
                    "battery": d.battery,
                    "last_test": d.last_test.isoformat() if d.last_test else None,
                }
                for eid, d in self._devices.items()
            },
        }

    @staticmethod
    def _parse(value: Any) -> datetime | None:
        try:
            return datetime.fromisoformat(value) if isinstance(value, str) else None
        except ValueError:
            return None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PanicMonitor:
        monitor = cls()
        if not isinstance(data, dict):
            return monitor
        # Legacy (v5.1) flat shape: {eid: {active_since, ...}}
        legacy = "active" not in data and "devices" not in data
        active_raw = data if legacy else data.get("active", {})
        if isinstance(active_raw, dict):
            for eid, raw in active_raw.items():
                if not isinstance(raw, dict):
                    continue
                since = cls._parse(raw.get("active_since"))
                notified = cls._parse(raw.get("last_notified"))
                if since is None or notified is None:
                    continue
                monitor._states[eid] = _PanicState(
                    active_since=since, last_notified=notified, acknowledged=bool(raw.get("acknowledged", False))
                )
        devices_raw = {} if legacy else data.get("devices", {})
        if isinstance(devices_raw, dict):
            for eid, raw in devices_raw.items():
                if not isinstance(raw, dict):
                    continue
                battery = raw.get("battery")
                monitor._devices[eid] = _DeviceState(
                    available=bool(raw.get("available", False)),
                    last_reported=cls._parse(raw.get("last_reported")),
                    battery=float(battery) if isinstance(battery, (int, float)) else None,
                    last_test=cls._parse(raw.get("last_test")),
                )
        return monitor
```

- [ ] **Step 4: Run tests and lint**

Run: `source venv/bin/activate && black custom_components/behaviour_monitor/panic_monitor.py tests/test_panic_monitor.py && python -m pytest tests/ -q | tail -1 && ruff check custom_components/behaviour_monitor/panic_monitor.py tests/test_panic_monitor.py`
Expected: all pass (the coordinator test `test_panic_state_persists` still passes: it reads `stored["panic_state"]["binary_sensor.sos"]` — update that assertion to `stored["panic_state"]["active"]["binary_sensor.sos"]`); ruff clean. Remove the `# noqa: F811` import line from the test file if ruff flags it as unused; it was only a placeholder.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/panic_monitor.py tests/test_panic_monitor.py tests/test_coordinator.py
git commit -m "feat: panic device liveness, test window and device-health alerts in PanicMonitor"
```

---

### Task 4: `RoutineModel.overall_confidence(expected_ids=...)`

**Files:**
- Modify: `custom_components/behaviour_monitor/routine_model.py`
- Test: `tests/test_routine_model.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_routine_model.py` (it already imports `RoutineModel` and `datetime`; add `timezone` if missing):
```python
class TestOverallConfidenceExpected:
    def test_expected_ids_count_absent_as_zero(self) -> None:
        from datetime import datetime, timezone

        model = RoutineModel(history_window_days=7)
        now = datetime(2026, 9, 18, tzinfo=timezone.utc)
        er = model.get_or_create("a", is_binary=True)
        # a fully learned entity: confidence 1.0
        er.first_observation = (now - timedelta(days=30)).isoformat()
        conf_a = er.confidence(now)
        assert conf_a > 0
        assert model.overall_confidence(now) == conf_a
        assert model.overall_confidence(now, expected_ids=["a", "b"]) == conf_a / 2
        assert model.overall_confidence(now, expected_ids=["b"]) == 0.0
        assert model.overall_confidence(now, expected_ids=[]) == 0.0

    def test_learning_status_uses_expected(self) -> None:
        from datetime import datetime, timezone

        model = RoutineModel(history_window_days=7)
        now = datetime(2026, 9, 18, tzinfo=timezone.utc)
        er = model.get_or_create("a", is_binary=True)
        er.first_observation = (now - timedelta(days=30)).isoformat()
        assert model.learning_status(now) == "ready"
        assert model.learning_status(now, expected_ids=["a", "b", "c", "d"]) != "ready"
```
If `timedelta` is not imported in the test module, add it to the existing `from datetime import ...` line. If `EntityRoutine.confidence` derives from `first_observation` differently than assumed (read `confidence()` first), adjust only the way the fixture reaches a non-zero confidence, not the assertions on the ratio.

- [ ] **Step 2: Run to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_routine_model.py::TestOverallConfidenceExpected -q`
Expected: FAIL (`TypeError: unexpected keyword argument 'expected_ids'`).

- [ ] **Step 3: Implement**

Replace `overall_confidence` and `learning_status` in `routine_model.py`:
```python
    def overall_confidence(
        self, now: datetime | None = None, expected_ids: Iterable[str] | None = None
    ) -> float:
        """Mean confidence across entities.

        With ``expected_ids`` the mean is taken over that set, and any expected
        entity absent from the model counts as 0.0 — input loss lowers the
        score instead of being renormalised away. Without it, the mean is over
        tracked entities (0.0 when none).
        """
        if now is None:
            now = datetime.now(tz=timezone.utc)
        if expected_ids is None:
            if not self._entities:
                return 0.0
            return sum(er.confidence(now) for er in self._entities.values()) / len(self._entities)
        ids = list(expected_ids)
        if not ids:
            return 0.0
        total = sum(er.confidence(now) for eid in ids if (er := self._entities.get(eid)) is not None)
        return total / len(ids)

    def learning_status(
        self, now: datetime | None = None, expected_ids: Iterable[str] | None = None
    ) -> str:
        """inactive (< 0.1) / learning (< 0.8) / ready."""
        conf = self.overall_confidence(now=now, expected_ids=expected_ids)
        if conf < 0.1:
            return "inactive"
        if conf < 0.8:
            return "learning"
        return "ready"
```
Add `Iterable` to the module's `collections.abc`/`typing` imports.

- [ ] **Step 4: Run the full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components/behaviour_monitor/routine_model.py tests/test_routine_model.py | tail -1`

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/routine_model.py tests/test_routine_model.py
git commit -m "feat: overall_confidence over expected entities counts absent inputs as zero"
```

---

### Task 5: Coordinator health, repair issues, qualified welfare, counts, confidence; sensor

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py`, `custom_components/behaviour_monitor/sensor.py`, `tests/conftest.py`
- Test: `tests/test_coordinator.py`, `tests/test_sensor.py`

**Interfaces produced (coordinator):**
```python
self._entity_health: dict[str, str]; self._open_issues: set[str]; self._blind_notified: bool
def _entity_facts(self) -> tuple[dict[str, str | None], set[str]]      # patchable in tests
def _refresh_health(self) -> None                                     # classifies + manages repair issues
def _expected_entities(self) -> list[str]                             # monitored minus panic
def _contributing_entities(self) -> list[str]
def _finalize_welfare(self, welfare, alerts) -> dict                  # counts + qualify_welfare
```

- [ ] **Step 1: conftest — issue registry mock**

In `tests/conftest.py`, next to `mock_ha_helpers.entity_registry = MagicMock()` add:
```python
    mock_ha_helpers.issue_registry = MagicMock()

    class MockIssueSeverity:
        CRITICAL = "critical"
        ERROR = "error"
        WARNING = "warning"

    mock_ha_helpers.issue_registry.IssueSeverity = MockIssueSeverity
```
and next to the `sys.modules['homeassistant.helpers.entity_registry']` line add
`sys.modules['homeassistant.helpers.issue_registry'] = mock_ha_helpers.issue_registry`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_coordinator.py`:
```python
# ---------------------------------------------------------------------------
# TestEntityHealthIntegration — health facts, repair issues, blind/degraded welfare, counts, confidence
# ---------------------------------------------------------------------------


class TestEntityHealthIntegration:
    def _make(self, mock_hass: MagicMock, mock_config_entry: MagicMock, entities: list[str], **extra: Any) -> BehaviourMonitorCoordinator:
        from custom_components.behaviour_monitor.const import CONF_MONITORED_ENTITIES

        mock_config_entry.data = {**mock_config_entry.data, CONF_MONITORED_ENTITIES: entities, **extra}
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    def test_entity_facts_from_states_and_registry(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor import coordinator as coord_module

        c = self._make(mock_hass, mock_config_entry, ["a.on", "a.unavail", "a.gone", "a.reg_only"])
        states = {"a.on": MagicMock(state="on"), "a.unavail": MagicMock(state="unavailable")}
        mock_hass.states.get = lambda eid: states.get(eid)
        registry = MagicMock()
        registry.async_get = lambda eid: MagicMock() if eid in ("a.on", "a.unavail", "a.reg_only") else None
        with patch.object(coord_module.er, "async_get", return_value=registry):
            st, reg = c._entity_facts()
        assert st == {"a.on": "on", "a.unavail": "unavailable", "a.gone": None, "a.reg_only": None}
        assert reg == {"a.on", "a.unavail", "a.reg_only"}

    def test_entity_facts_non_string_state_is_present(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry, ["a.b"])
        st, _ = c._entity_facts()  # default MagicMock state
        assert st["a.b"] == ""

    def test_refresh_health_creates_and_clears_repair_issue_once(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor import coordinator as coord_module

        c = self._make(mock_hass, mock_config_entry, ["a.b", "c.d"])
        with patch.object(c, "_entity_facts", return_value=({"a.b": "on", "c.d": None}, set())), \
             patch.object(coord_module.ir, "async_create_issue") as create, \
             patch.object(coord_module.ir, "async_delete_issue") as delete:
            c._refresh_health()
            c._refresh_health()
        assert c._entity_health == {"a.b": "present", "c.d": "missing"}
        create.assert_called_once()
        kwargs = create.call_args.kwargs
        assert create.call_args.args[1] == "behaviour_monitor" or kwargs.get("domain") == "behaviour_monitor"
        assert "missing_entity_c.d" in create.call_args.args or kwargs.get("issue_id") == "missing_entity_c.d"
        assert kwargs.get("translation_placeholders") == {"entity_id": "c.d"}
        delete.assert_not_called()
        with patch.object(c, "_entity_facts", return_value=({"a.b": "on", "c.d": "off"}, set())), \
             patch.object(coord_module.ir, "async_delete_issue") as delete2:
            c._refresh_health()
        delete2.assert_called_once()
        assert c._open_issues == set()

    def test_expected_and_contributing(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_PANIC, EntityCategory

        c = self._make(mock_hass, mock_config_entry, ["a.b", "c.d", "binary_sensor.sos"], **{CONF_CATEGORY_PANIC: ["binary_sensor.sos"]})
        c._categories = {"a.b": EntityCategory.OTHER, "c.d": EntityCategory.OTHER, "binary_sensor.sos": EntityCategory.PANIC}
        c._entity_health = {"a.b": "present", "c.d": "missing", "binary_sensor.sos": "present"}
        assert c._expected_entities() == ["a.b", "c.d"]
        assert c._contributing_entities() == ["a.b"]

    @pytest.mark.asyncio
    async def test_blind_when_nothing_reports(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry, ["a.b", "c.d"])
        with patch.object(c, "_entity_facts", return_value=({"a.b": None, "c.d": None}, set())), \
             patch.object(c._store, "async_save", new_callable=AsyncMock), \
             patch.object(c, "_deliver_notification", new_callable=AsyncMock) as deliver:
            data = await c._async_update_data()
            data2 = await c._async_update_data()
        assert data["welfare"]["status"] == "blind"
        assert data["welfare"]["contributing_entities"] == 0
        assert data["welfare"]["expected_entities"] == 2
        assert sorted(data["welfare"]["missing_entities"]) == ["a.b", "c.d"]
        assert data["welfare"]["entity_count_by_status"] == {"ok": 0, "attention": 0, "unavailable": 0, "missing": 2}
        assert data["baseline_confidence"] == 0.0
        by_id = {e["entity_id"]: e for e in data["entity_status"]}
        assert by_id["a.b"]["health"] == "missing" and by_id["a.b"]["status"] == "missing"
        assert by_id["a.b"]["contributing"] is False
        # blind notification sent once on transition, not every poll
        assert deliver.await_count == 1
        assert deliver.call_args.args[2] == "behaviour_monitor_health"
        assert data2["welfare"]["status"] == "blind"

    @pytest.mark.asyncio
    async def test_blind_during_holiday(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry, ["a.b"])
        c._holiday_mode = True
        with patch.object(c, "_entity_facts", return_value=({"a.b": None}, set())), \
             patch.object(c._store, "async_save", new_callable=AsyncMock), \
             patch.object(c, "_deliver_notification", new_callable=AsyncMock):
            data = await c._async_update_data()
        assert data["welfare"]["status"] == "blind"
        assert data["routine"]["summary"] == "Suppressed"

    @pytest.mark.asyncio
    async def test_degraded_on_partial_loss(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry, ["a.b", "c.d"])
        with patch.object(c, "_entity_facts", return_value=({"a.b": "on", "c.d": "unavailable"}, set())), \
             patch.object(c._store, "async_save", new_callable=AsyncMock):
            data = await c._async_update_data()
        assert data["welfare"]["status"] == "degraded"
        assert data["welfare"]["unavailable_entities"] == ["c.d"]
        assert data["welfare"]["entity_count_by_status"] == {"ok": 1, "attention": 0, "unavailable": 1, "missing": 0}

    @pytest.mark.asyncio
    async def test_all_present_ok_with_suffix(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry, ["a.b", "c.d"])
        with patch.object(c, "_entity_facts", return_value=({"a.b": "on", "c.d": "off"}, set())), \
             patch.object(c._store, "async_save", new_callable=AsyncMock):
            data = await c._async_update_data()
        assert data["welfare"]["status"] == "ok"
        assert data["welfare"]["summary"].endswith("(2 of 2 reporting)")
        assert data["welfare"]["alert_count_by_entity"] == {}

    def test_alert_counts_and_attention(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry, ["a.b", "c.d"])
        c._entity_health = {"a.b": "present", "c.d": "present"}
        w = c._finalize_welfare(c._derive_welfare([_make_alert("a.b", severity=AlertSeverity.LOW)]), [_make_alert("a.b", severity=AlertSeverity.LOW)])
        assert w["alert_count_by_entity"] == {"a.b": 1}
        assert w["entity_count_by_status"] == {"ok": 1, "attention": 1, "unavailable": 0, "missing": 0}
        assert w["status"] == "check_recommended"

    @pytest.mark.asyncio
    async def test_confidence_uses_expected_denominator(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry, ["a.b", "c.d"])
        er = c._routine_model.get_or_create("a.b", is_binary=True)
        er.first_observation = (datetime.now() - timedelta(days=60)).isoformat()
        with patch.object(c, "_entity_facts", return_value=({"a.b": "on", "c.d": "on"}, set())), \
             patch.object(c._store, "async_save", new_callable=AsyncMock):
            data = await c._async_update_data()
        full = c._routine_model.overall_confidence(datetime.now()) * 100.0
        assert 0 < data["baseline_confidence"] <= round(full / 2, 1) + 0.1

    @pytest.mark.asyncio
    async def test_setup_refreshes_health(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry, ["a.b"])
        with patch.object(c._store, "async_load", new_callable=AsyncMock, return_value=None), \
             patch.object(c, "_bootstrap_from_recorder", new_callable=AsyncMock), \
             patch.object(c._store, "async_save", new_callable=AsyncMock), \
             patch.object(c, "_registry_device_classes", return_value={}), \
             patch.object(c, "_entity_facts", return_value=({"a.b": "on"}, set())):
            await c.async_setup()
        assert c._entity_health == {"a.b": "present"}
```

Update `tests/test_sensor.py`:
- `test_entity_status_summary_sensor`: data becomes `{"welfare": {"entity_count_by_status": {"ok": 5, "attention": 2, "unavailable": 0, "missing": 0}}}`, expected `"5 OK, 2 Need Attention"`; add:
```python
    def test_entity_status_summary_sensor_with_missing(self) -> None:
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "entity_status_summary")
        data = {"welfare": {"entity_count_by_status": {"ok": 3, "attention": 0, "unavailable": 1, "missing": 2}}}
        assert sensor.value_fn(data) == "3 OK, 0 Need Attention, 2 Missing, 1 Unavailable"

    def test_entity_status_summary_sensor_empty(self) -> None:
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "entity_status_summary")
        assert sensor.value_fn({}) == "0 OK, 0 Need Attention"
```
- `test_welfare_status_extra_attrs`: keep, and add assertions that `result["contributing_entities"] == 0`, `result["expected_entities"] == 0`, `result["missing_entities"] == []`, `result["unavailable_entities"] == []`, `result["alert_count_by_entity"] == {}` when absent from data.

- [ ] **Step 3: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_coordinator.py::TestEntityHealthIntegration tests/test_sensor.py -q 2>&1 | tail -3`

- [ ] **Step 4: Implement**

`coordinator.py`:

(a) Imports: `from homeassistant.helpers import entity_registry as er, issue_registry as ir` (replace the existing entity_registry import line). Add to `.const` import: `HEALTH_MISSING, HEALTH_PRESENT, HEALTH_UNAVAILABLE, WELFARE_BLIND`. Add `from .entity_health import count_by_status, qualify_welfare, resolve_entity_health`.

(b) `__init__` additions after `self._panic_monitor = PanicMonitor()`:
```python
        self._entity_health: dict[str, str] = {}
        self._open_issues: set[str] = set()
        self._blind_notified = False
```

(c) New methods, directly after `_refresh_categories`:
```python
    def _entity_facts(self) -> tuple[dict[str, str | None], set[str]]:
        """Raw state string per monitored entity (None = no state object; "" = non-string state) and registry membership."""
        states: dict[str, str | None] = {}
        in_registry: set[str] = set()
        try:
            registry = er.async_get(self.hass)
        except Exception:  # noqa: BLE001
            registry = None
        for eid in self._monitored_entities:
            st = self.hass.states.get(eid)
            if st is None:
                states[eid] = None
            else:
                sv = getattr(st, "state", None)
                states[eid] = sv if isinstance(sv, str) else ""
            if registry is not None and registry.async_get(eid) is not None:
                in_registry.add(eid)
        return states, in_registry

    def _refresh_health(self) -> None:
        """Classify entity health and raise/clear repair issues on transitions only."""
        states, in_registry = self._entity_facts()
        self._entity_health = resolve_entity_health(self._monitored_entities, states, in_registry)
        wanted = {f"missing_entity_{eid}" for eid, h in self._entity_health.items() if h == HEALTH_MISSING}
        for issue_id in wanted - self._open_issues:
            ir.async_create_issue(
                self.hass, DOMAIN, issue_id,
                is_fixable=False, severity=ir.IssueSeverity.ERROR,
                translation_key="missing_entity",
                translation_placeholders={"entity_id": issue_id[len("missing_entity_"):]},
            )
        for issue_id in self._open_issues - wanted:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._open_issues = wanted

    def _expected_entities(self) -> list[str]:
        return [e for e in self._monitored_entities if self._categories.get(e) is not EntityCategory.PANIC]

    def _contributing_entities(self) -> list[str]:
        return [e for e in self._expected_entities() if self._entity_health.get(e) == HEALTH_PRESENT]

    def _finalize_welfare(self, welfare: dict[str, Any], alerts: list[AlertResult]) -> dict[str, Any]:
        expected = self._expected_entities()
        contributing = self._contributing_entities()
        alerting = {a.entity_id for a in alerts if a.alert_type not in (AlertType.CORRELATION_BREAK, AlertType.DEVICE_HEALTH)}
        out = qualify_welfare(
            welfare,
            contributing=contributing, expected=expected,
            missing=[e for e in expected if self._entity_health.get(e) == HEALTH_MISSING],
            unavailable=[e for e in expected if self._entity_health.get(e) == HEALTH_UNAVAILABLE],
            panic_active=any(a.alert_type == AlertType.PANIC for a in alerts),
            device_alerts=any(a.alert_type == AlertType.DEVICE_HEALTH for a in alerts),
        )
        out["entity_count_by_status"] = count_by_status(self._monitored_entities, self._entity_health, contributing, alerting)
        return out
```

(d) `_derive_welfare`: rename every `"entity_count_by_status"` key in this method to `"alert_count_by_entity"` (three return dicts plus the two empty returns), and exclude `AlertType.DEVICE_HEALTH` alongside `CORRELATION_BREAK` in both the panic `ordered` comprehension and the `welfare_alerts` filter.

(e) `_build_sensor_data`:
- `conf = self._routine_model.overall_confidence(now, expected_ids=self._expected_entities()) * 100.0` and `ls = self._routine_model.learning_status(now, expected_ids=self._expected_entities())`.
- `"welfare": self._finalize_welfare(self._derive_welfare(alerts), alerts),`
- In each `entity_status` entry, replace the `"status"` line with:
```python
                    "status": ("active" if e in self._last_seen else "unknown") if self._entity_health.get(e, HEALTH_PRESENT) == HEALTH_PRESENT else self._entity_health[e],
                    "health": self._entity_health.get(e, HEALTH_PRESENT),
                    "contributing": self._entity_health.get(e) == HEALTH_PRESENT and self._categories.get(e) is not EntityCategory.PANIC,
```

(f) `_build_safe_defaults`: `"welfare": self._finalize_welfare({"status": "ok", "reasons": [], "summary": "No active alerts", "recommendation": "", "alert_count_by_entity": {}}, []),` and `"entity_status"` stays `[]`.

(g) `_with_panic`: the welfare line becomes `data["welfare"] = self._finalize_welfare(self._derive_welfare(panic_alerts), panic_alerts)`.

(h) `_handle_alerts`: `new_status = self._finalize_welfare(self._derive_welfare(alerts), alerts)["status"]`.

(i) `_async_update_data`: as the first statement after `now = dt_util.now()`, add `self._refresh_health()`. After the payload is built on every return path, notify once on the blind transition. Restructure the tail so all three return paths go through one helper:
```python
        if self._holiday_mode or self.is_snoozed():
            return await self._finish_update(self._with_panic(self._build_safe_defaults(), panic_alerts), now)
        try:
            alerts = self._run_detection(now) + panic_alerts
            await self._handle_alerts(alerts, now)
            return await self._finish_update(self._build_sensor_data(alerts, now), now)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Coordinator update error — returning safe defaults")
            return await self._finish_update(self._with_panic(self._build_safe_defaults(), panic_alerts), now)
```
with
```python
    async def _finish_update(self, data: dict[str, Any], now: datetime) -> dict[str, Any]:
        """Send the blind notification once per transition into blindness."""
        blind = data.get("welfare", {}).get("status") == WELFARE_BLIND
        if blind and not self._blind_notified:
            w = data["welfare"]
            await self._deliver_notification(
                "Behaviour Monitor: no data",
                f"0 of {w.get('expected_entities', 0)} monitored entities are reporting. {w.get('recommendation', '')}",
                "behaviour_monitor_health",
            )
            self._last_notification_info = {"timestamp": now.isoformat(), "type": "blind"}
        self._blind_notified = blind
        return data
```

(j) `async_setup`: call `self._refresh_health()` immediately after `self._refresh_categories()`.

`sensor.py`:
- Add a module-level helper:
```python
def _summary_text(counts: dict) -> str:
    text = f"{counts.get('ok', 0)} OK, {counts.get('attention', 0)} Need Attention"
    if counts.get("missing", 0):
        text += f", {counts['missing']} Missing"
    if counts.get("unavailable", 0):
        text += f", {counts['unavailable']} Unavailable"
    return text
```
- `entity_status_summary.value_fn = lambda data: _summary_text(data.get("welfare", {}).get("entity_count_by_status", {}))`.
- `welfare_status.extra_attrs_fn` adds: `"contributing_entities": w.get("contributing_entities", 0)`, `"expected_entities": w.get("expected_entities", 0)`, `"missing_entities": w.get("missing_entities", [])`, `"unavailable_entities": w.get("unavailable_entities", [])`, `"alert_count_by_entity": w.get("alert_count_by_entity", {})` where `w = data.get("welfare", {})` (inline as repeated `data.get("welfare", {})` if the lambda style must be kept).

Existing tests that assert `welfare["entity_count_by_status"] == {"switch.kettle": 1, ...}` (e.g. `TestWeightedWelfare.test_reasons_and_counts_still_include_plug_alert`, `TestPanicPoll.test_welfare_forced_to_alert_by_panic`) must change that key to `alert_count_by_entity`. Existing tests asserting a bare `"ok"` status from `_async_update_data` with default MagicMock states remain valid because a MagicMock state maps to `""` → present.

- [ ] **Step 5: Run the full suite and parity**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components tests | tail -1`
Expected: all pass; no new ruff findings.

- [ ] **Step 6: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py custom_components/behaviour_monitor/sensor.py tests/conftest.py tests/test_coordinator.py tests/test_sensor.py
git commit -m "feat: entity health with repair issues, blind/degraded welfare, corrected status counts"
```

---

### Task 6: Event gate wiring in the coordinator

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces produced:** `self._gate: EventGate`, `self._gate_flush_pending: bool`, `_flush_gate(force: bool = False) -> None`, `_process_activity(eid, old_sv, sv, ts) -> None`.

- [ ] **Step 1: Update existing tests for the buffered path**

Every existing test that calls `_handle_state_changed(...)` on a NON-panic entity and then asserts on `_last_seen`, `_today_count`, `_routine_model._entities` or the correlation detector must flush the gate first. Add this helper near the top of `tests/test_coordinator.py` (after `_make_alert`):
```python
def _fire(coordinator: BehaviourMonitorCoordinator, event: MagicMock) -> None:
    """Deliver a state_changed event and flush the one-second gate immediately."""
    coordinator._handle_state_changed(event)
    coordinator._flush_gate(force=True)
```
Then run: `grep -n "_handle_state_changed(" tests/test_coordinator.py` and, for each call site OUTSIDE `TestPanicPressRelease` / `TestPanicPoll` (panic bypasses the gate; those tests must stay as they are), replace `X._handle_state_changed(EVT)` with `_fire(X, EVT)` where `X` is the coordinator variable. `test_handle_state_changed_ignores_unmonitored` and `..._ignores_none_new_state` may also use `_fire` (flush of nothing is harmless).

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_coordinator.py`:
```python
class TestEventGateWiring:
    def _make(self, mock_hass: MagicMock, mock_config_entry: MagicMock, **extra: Any) -> BehaviourMonitorCoordinator:
        from custom_components.behaviour_monitor.const import CONF_MONITORED_ENTITIES

        mock_config_entry.data = {**mock_config_entry.data, CONF_MONITORED_ENTITIES: ["s.a", "s.b", "s.c", "s.d"], **extra}
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    @staticmethod
    def _event(eid: str, old: str | None, new: str) -> MagicMock:
        e = MagicMock()
        e.data = {"entity_id": eid, "old_state": None if old is None else MagicMock(state=old), "new_state": MagicMock(state=new)}
        return e

    def test_defaults(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        assert c._gate._grace.total_seconds() == 90
        assert c._gate._threshold == 3

    def test_event_is_buffered_then_processed_on_flush(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._handle_state_changed(self._event("s.a", "off", "on"))
        assert "s.a" not in c._last_seen
        assert c._gate.pending == 1
        mock_hass.loop.call_later.assert_called_once()
        assert mock_hass.loop.call_later.call_args.args[0] == 1.0
        c._flush_gate(force=True)
        assert "s.a" in c._last_seen
        assert c._today_count == 1
        assert c._gate.pending == 0

    def test_single_timer_per_batch(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._handle_state_changed(self._event("s.a", "off", "on"))
        c._handle_state_changed(self._event("s.b", "off", "on"))
        assert mock_hass.loop.call_later.call_count == 1
        c._flush_gate(force=True)
        c._handle_state_changed(self._event("s.a", "on", "off"))
        assert mock_hass.loop.call_later.call_count == 2

    def test_burst_dropped(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        for eid in ("s.a", "s.b", "s.c"):
            c._handle_state_changed(self._event(eid, "off", "on"))
        c._flush_gate(force=True)
        assert c._last_seen == {}
        assert c._today_count == 0
        assert c._gate.dropped_bursts == 1

    def test_threshold_zero_keeps_burst(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import CONF_BURST_DISCARD_THRESHOLD

        c = self._make(mock_hass, mock_config_entry, **{CONF_BURST_DISCARD_THRESHOLD: 0})
        for eid in ("s.a", "s.b", "s.c"):
            c._handle_state_changed(self._event(eid, "off", "on"))
        c._flush_gate(force=True)
        assert c._today_count == 3

    @pytest.mark.asyncio
    async def test_grace_armed_at_setup_drops_events(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        with patch.object(c._store, "async_load", new_callable=AsyncMock, return_value=None), \
             patch.object(c, "_bootstrap_from_recorder", new_callable=AsyncMock), \
             patch.object(c._store, "async_save", new_callable=AsyncMock), \
             patch.object(c, "_registry_device_classes", return_value={}):
            await c.async_setup()
        c._handle_state_changed(self._event("s.a", "off", "on"))
        c._flush_gate(force=True)
        assert "s.a" not in c._last_seen
        mock_hass.loop.call_later.assert_not_called()

    def test_panic_bypasses_gate(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_PANIC, EntityCategory

        c = self._make(mock_hass, mock_config_entry, **{CONF_CATEGORY_PANIC: ["binary_sensor.sos"]})
        c._categories["binary_sensor.sos"] = EntityCategory.PANIC
        c._gate.arm(datetime.now())  # even during grace
        c._handle_state_changed(self._event("binary_sensor.sos", "off", "on"))
        assert c.panic_active == ["binary_sensor.sos"]
        assert c._gate.pending == 0

    def test_flush_uses_original_timestamp(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._handle_state_changed(self._event("s.a", "off", "on"))
        ts = c._gate._buckets[next(iter(c._gate._buckets))][0].timestamp
        c._flush_gate(force=True)
        assert c._last_seen["s.a"] == ts
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_coordinator.py::TestEventGateWiring -q 2>&1 | tail -3`

- [ ] **Step 4: Implement**

`coordinator.py`:

(a) Imports: `CONF_STARTUP_GRACE_SECONDS, DEFAULT_STARTUP_GRACE_SECONDS, CONF_BURST_DISCARD_THRESHOLD, DEFAULT_BURST_DISCARD_THRESHOLD` from `.const`; `from .event_gate import EventGate`.

(b) `__init__`, after `self._blind_notified = False`:
```python
        self._gate = EventGate(
            int(d.get(CONF_STARTUP_GRACE_SECONDS, DEFAULT_STARTUP_GRACE_SECONDS)),
            int(d.get(CONF_BURST_DISCARD_THRESHOLD, DEFAULT_BURST_DISCARD_THRESHOLD)),
        )
        self._gate_flush_pending = False
```

(c) `async_setup`: immediately before the `async_listen` subscription add `self._gate.arm(dt_util.now())`.

(d) Replace the tail of `_handle_state_changed` (from `now, sv = dt_util.now(), str(ns.state)` to the end) with:
```python
        now, sv = dt_util.now(), str(ns.state)
        old_sv = None if old_state is None else str(old_state.state)
        if not self._gate.submit(eid, old_sv, sv, now):
            return
        if not self._gate_flush_pending:
            self._gate_flush_pending = True
            self.hass.loop.call_later(1.0, self._flush_gate)

    @callback
    def _flush_gate(self, force: bool = False) -> None:
        """Release completed one-second buckets from the gate and process them."""
        self._gate_flush_pending = False
        events = self._gate.flush(dt_util.now(), force=force)
        for ev in events:
            self._process_activity(ev.entity_id, ev.old_state, ev.new_state, ev.timestamp)
        if self._gate.pending and not force:
            self._gate_flush_pending = True
            self.hass.loop.call_later(1.0, self._flush_gate)
        if events:
            self.hass.async_create_task(self.async_request_refresh())

    def _process_activity(self, eid: str, old_sv: str | None, sv: str, now: datetime) -> None:
        """The pre-gate activity path: last-seen, debounce, record, correlate, count."""
        self._last_seen[eid] = now
        is_motion = self._categories.get(eid) is EntityCategory.MOTION
        if not self._debouncer.should_count(eid, is_motion, old_sv, sv, now):
            return
        self._routine_model.record(entity_id=eid, timestamp=now, state_value=sv, is_binary=is_binary_state(sv))
        self._correlation_detector.record_event(eid, now, self._last_seen)
        if self._today_date != now.date():
            self._today_count, self._today_date = 0, now.date()
        self._today_count += 1
```
`callback` is already imported from `homeassistant.core`. Note the `async_request_refresh` task is now created once per flush rather than per event.

(e) `async_shutdown`: before unsubscribing, `self._flush_gate(force=True)` so buffered events are not lost on unload.

- [ ] **Step 5: Run the full suite and parity**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components tests | tail -1`
Expected: all pass. Tests that break because they asserted on state immediately after `_handle_state_changed` without `_fire` are the ones Step 1 missed — convert them.

- [ ] **Step 6: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py tests/test_coordinator.py
git commit -m "feat: route activity events through the start-up grace and burst-discard gate"
```

---

### Task 7: Panic device liveness wiring, `panic_test` service, button attributes

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py`, `custom_components/behaviour_monitor/__init__.py`, `custom_components/behaviour_monitor/services.yaml`, `custom_components/behaviour_monitor/button.py`
- Test: `tests/test_coordinator.py`, `tests/test_init.py`, `tests/test_button.py`

**Interfaces produced:** coordinator `_refresh_panic_devices()`, `_device_alerts(now) -> list[AlertResult]`, `async_panic_test(entity_id=None) -> list[str]`, `panic_devices -> dict[str, dict]`; `self._panic_heartbeat_hours`, `self._panic_test_reminder_days`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator.py`:
```python
class TestPanicDeviceLiveness:
    def _make(self, mock_hass: MagicMock, mock_config_entry: MagicMock, **extra: Any) -> BehaviourMonitorCoordinator:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_PANIC, CONF_MONITORED_ENTITIES, EntityCategory

        mock_config_entry.data = {**mock_config_entry.data, CONF_MONITORED_ENTITIES: ["s.a"], CONF_CATEGORY_PANIC: ["binary_sensor.sos"], **extra}
        c = BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
        c._categories = {"s.a": EntityCategory.OTHER, "binary_sensor.sos": EntityCategory.PANIC}
        return c

    @staticmethod
    def _state(state: str, battery: float | None = None, reported: datetime | None = None) -> MagicMock:
        s = MagicMock()
        s.state = state
        s.attributes = {} if battery is None else {"battery_level": battery}
        s.last_reported = reported
        s.last_updated = reported
        return s

    def test_defaults(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        assert c._panic_heartbeat_hours == 24 and c._panic_test_reminder_days == 30

    def test_refresh_devices_reads_state(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        reported = datetime.now() - timedelta(hours=2)
        mock_hass.states.get = lambda eid: self._state("off", 55, reported) if eid == "binary_sensor.sos" else self._state("on")
        with patch.object(c, "_entity_facts", return_value=({"s.a": "on", "binary_sensor.sos": "off"}, set())):
            c._refresh_health()
        d = c.panic_devices["binary_sensor.sos"]
        assert d["available"] is True and d["battery"] == 55 and d["last_reported"] == reported.isoformat()

    def test_device_alerts_built(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._panic_monitor.update_device("binary_sensor.sos", available=False, last_reported=None, battery=10)
        alerts = c._device_alerts(datetime.now())
        assert [a.alert_type for a in alerts] == [AlertType.DEVICE_HEALTH] * 4
        assert [a.severity for a in alerts] == [AlertSeverity.HIGH, AlertSeverity.HIGH, AlertSeverity.MEDIUM, AlertSeverity.LOW]
        assert all(a.entity_id == "binary_sensor.sos" for a in alerts)
        assert alerts[0].details["kind"] == "unavailable"

    def test_heartbeat_zero_disables(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import CONF_PANIC_HEARTBEAT_HOURS, CONF_PANIC_TEST_REMINDER_DAYS

        c = self._make(mock_hass, mock_config_entry, **{CONF_PANIC_HEARTBEAT_HOURS: 0, CONF_PANIC_TEST_REMINDER_DAYS: 0})
        c._panic_monitor.update_device("binary_sensor.sos", available=True, last_reported=None, battery=None)
        assert c._device_alerts(datetime.now()) == []

    @pytest.mark.asyncio
    async def test_device_alert_degrades_welfare_and_notifies_even_on_holiday(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._holiday_mode = True
        c._panic_monitor.update_device("binary_sensor.sos", available=False, last_reported=datetime.now(), battery=None)
        with patch.object(c, "_entity_facts", return_value=({"s.a": "on", "binary_sensor.sos": "unavailable"}, set())), \
             patch.object(c._store, "async_save", new_callable=AsyncMock), \
             patch.object(c, "_send_notification", new_callable=AsyncMock) as send, \
             patch.object(c, "_refresh_panic_devices"):
            data = await c._async_update_data()
        assert data["welfare"]["status"] == "degraded"
        assert any(a["alert_type"] == "device_health" for a in data["anomalies"])
        send.assert_awaited_once()
        sent = send.call_args.args[0]
        assert all(a.alert_type == AlertType.DEVICE_HEALTH for a in sent)

    @pytest.mark.asyncio
    async def test_device_alert_excluded_from_weighted_scoring(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._entity_health = {"s.a": "present", "binary_sensor.sos": "present"}
        alerts = [_make_alert("binary_sensor.sos", alert_type=AlertType.DEVICE_HEALTH, severity=AlertSeverity.HIGH)]
        w = c._finalize_welfare(c._derive_welfare(alerts), alerts)
        assert w["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_panic_test_window_and_test_press(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._panic_monitor.update_device("binary_sensor.sos", available=True, last_reported=datetime.now(), battery=None)
        with patch.object(c._store, "async_save", new_callable=AsyncMock) as save:
            opened = await c.async_panic_test()
            assert opened == ["binary_sensor.sos"]
            ev = MagicMock()
            ev.data = {"entity_id": "binary_sensor.sos", "old_state": MagicMock(state="off"), "new_state": MagicMock(state="on")}
            c._handle_state_changed(ev)
            for call in mock_hass.async_create_task.call_args_list:
                coro = call[0][0]
                if hasattr(coro, "__await__"):
                    await coro
        assert c.panic_active == []
        assert c.panic_devices["binary_sensor.sos"]["last_test"] is not None
        mock_hass.bus.async_fire.assert_any_call("behaviour_monitor_panic_tested", {"entity_id": "binary_sensor.sos"})
        assert not any(call[0][0] == "persistent_notification" and call[0][2].get("notification_id") == "behaviour_monitor_panic" for call in mock_hass.services.async_call.call_args_list)
        save.assert_awaited()

    @pytest.mark.asyncio
    async def test_press_outside_window_is_real(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._panic_monitor.update_device("binary_sensor.sos", available=True, last_reported=datetime.now(), battery=None)
        with patch.object(c._store, "async_save", new_callable=AsyncMock):
            ev = MagicMock()
            ev.data = {"entity_id": "binary_sensor.sos", "old_state": MagicMock(state="off"), "new_state": MagicMock(state="on")}
            c._handle_state_changed(ev)
        assert c.panic_active == ["binary_sensor.sos"]
```

`tests/test_init.py`: add `SERVICE_PANIC_TEST` to the `.const` import, append `(DOMAIN, SERVICE_PANIC_TEST),` to `expected_services` in `test_async_setup_entry_registers_all_services`, and add to that class:
```python
    @pytest.mark.asyncio
    async def test_panic_test_service_calls_coordinator(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        with patch("custom_components.behaviour_monitor.BehaviourMonitorCoordinator") as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.async_panic_test = AsyncMock(return_value=[])
            mock_coordinator.monitored_entities = {"sensor.test1"}
            mock_coordinator_class.return_value = mock_coordinator
            await async_setup_entry(mock_hass, mock_config_entry)
            handler = next(call[0][2] for call in mock_hass.services.async_register.call_args_list if call[0][1] == SERVICE_PANIC_TEST)
            call = MagicMock()
            call.data = {"entity_id": "binary_sensor.sos"}
            await handler(call)
            mock_coordinator.async_panic_test.assert_awaited_with("binary_sensor.sos")
```
If a test asserts the exact set of services removed on unload, add the new one.

`tests/test_button.py`: in the `mock_coordinator` fixture add `coordinator.panic_devices = {"binary_sensor.sos": {"available": True, "battery": 50, "last_reported": None, "last_test": None}}`, and in `test_extra_state_attributes` assert `attrs["devices"] == coordinator.panic_devices`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_coordinator.py::TestPanicDeviceLiveness tests/test_init.py tests/test_button.py -q 2>&1 | tail -3`

- [ ] **Step 3: Implement**

`coordinator.py`:

(a) Imports from `.const`: `CONF_PANIC_HEARTBEAT_HOURS, DEFAULT_PANIC_HEARTBEAT_HOURS, CONF_PANIC_TEST_REMINDER_DAYS, DEFAULT_PANIC_TEST_REMINDER_DAYS, PANIC_LOW_BATTERY_PERCENT, PANIC_TEST_WINDOW_SECONDS`. Also `from collections.abc import Mapping` if not already imported.

(b) `__init__` after the gate:
```python
        self._panic_heartbeat_hours: int = int(d.get(CONF_PANIC_HEARTBEAT_HOURS, DEFAULT_PANIC_HEARTBEAT_HOURS))
        self._panic_test_reminder_days: int = int(d.get(CONF_PANIC_TEST_REMINDER_DAYS, DEFAULT_PANIC_TEST_REMINDER_DAYS))
```

(c) Property after `panic_unacknowledged`:
```python
    @property
    def panic_devices(self) -> dict[str, dict[str, Any]]:
        return {eid: self._panic_monitor.device_status(eid) for eid in self._panic_monitor.known_devices()}
```

(d) At the end of `_refresh_health` add `self._refresh_panic_devices()` and define:
```python
    def _refresh_panic_devices(self) -> None:
        """Feed availability, last-report time and battery of each panic entity to the monitor."""
        for eid in self._monitored_entities:
            if self._categories.get(eid) is not EntityCategory.PANIC:
                continue
            st = self.hass.states.get(eid)
            reported = None
            battery: float | None = None
            if st is not None:
                for attr in ("last_reported", "last_updated"):
                    val = getattr(st, attr, None)
                    if isinstance(val, datetime):
                        reported = val
                        break
                attrs = getattr(st, "attributes", None)
                if isinstance(attrs, Mapping):
                    raw = attrs.get("battery_level", attrs.get("battery"))
                    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                        battery = float(raw)
            self._panic_monitor.update_device(
                eid,
                available=self._entity_health.get(eid) == HEALTH_PRESENT,
                last_reported=reported,
                battery=battery,
            )

    def _device_alerts(self, now: datetime) -> list[AlertResult]:
        heartbeat = timedelta(hours=self._panic_heartbeat_hours) if self._panic_heartbeat_hours > 0 else None
        reminder = timedelta(days=self._panic_test_reminder_days) if self._panic_test_reminder_days > 0 else None
        sev = {"low": AlertSeverity.LOW, "medium": AlertSeverity.MEDIUM, "high": AlertSeverity.HIGH}
        return [
            AlertResult(
                entity_id=eid, alert_type=AlertType.DEVICE_HEALTH, severity=sev[severity], confidence=1.0,
                explanation=message, timestamp=now.isoformat(), details={"kind": kind},
            )
            for eid, kind, severity, message in self._panic_monitor.device_alerts(now, heartbeat, reminder, PANIC_LOW_BATTERY_PERCENT)
        ]

    async def async_panic_test(self, entity_id: str | None = None) -> list[str]:
        """Open a test-press window; a press inside it is recorded, not alerted."""
        now = dt_util.now()
        opened = self._panic_monitor.open_test_window(now, now + timedelta(seconds=PANIC_TEST_WINDOW_SECONDS), entity_id)
        if opened:
            self.hass.bus.async_fire(f"{DOMAIN}_panic_test_window", {"entity_ids": opened})
        return opened
```

(e) `_handle_panic_event`: in the rising-edge branch, before `press`:
```python
        if sv == "on" and old_sv != "on":
            if self._panic_monitor.in_test_window(eid, now):
                self._panic_monitor.record_test(eid, now)
                self.hass.async_create_task(self._save_fire_refresh(f"{DOMAIN}_panic_tested", {"entity_id": eid}))
                return
            if self._panic_monitor.press(eid, now):
                ...
```

(f) `_async_update_data`: after `panic_alerts = self._panic_alerts(now)` add `device_alerts = self._device_alerts(now)`. Holiday/snooze branch becomes:
```python
        if self._holiday_mode or self.is_snoozed():
            if device_alerts:
                await self._handle_alerts(device_alerts, now)
            data = self._with_panic(self._build_safe_defaults(), panic_alerts)
            if device_alerts:
                data["anomaly_detected"] = True
                data["anomalies"] = data.get("anomalies", []) + [a.to_dict() for a in device_alerts]
                data["welfare"] = self._finalize_welfare(self._derive_welfare(panic_alerts + device_alerts), panic_alerts + device_alerts)
            return await self._finish_update(data, now)
```
and the normal path uses `alerts = self._run_detection(now) + panic_alerts + device_alerts`.

(g) `_handle_alerts`: the early `if not self._enable_notifications or not alerts: return` stays; nothing else changes (device alerts pass the severity gate / repeat like any alert and are not PANIC, so they are notifiable).

`__init__.py`: import `SERVICE_PANIC_TEST`; add handler
```python
    async def handle_panic_test(call: ServiceCall) -> None:
        """Handle panic test service call."""
        await coordinator.async_panic_test(call.data.get("entity_id"))
```
register with `schema=vol.Schema({vol.Optional("entity_id"): str})` after the acknowledge registration, and remove it in `async_unload_entry`.

`services.yaml`: append
```yaml

panic_test:
  name: Panic Test
  description: >
    Open a two-minute test window. A panic button pressed inside the window is
    recorded as a test and does not raise an alert. Omit entity_id to open the
    window for every panic button.
  fields:
    entity_id:
      name: Entity
      description: The panic button to test (optional; all if omitted).
      required: false
      example: binary_sensor.sos_pendant
      selector:
        entity:
          domain: binary_sensor
```

`button.py`: `extra_state_attributes` adds `"devices": dict(self.coordinator.panic_devices)`.

- [ ] **Step 4: Run the full suite and parity**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components tests | tail -1`

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py custom_components/behaviour_monitor/__init__.py custom_components/behaviour_monitor/services.yaml custom_components/behaviour_monitor/button.py tests/test_coordinator.py tests/test_init.py tests/test_button.py
git commit -m "feat: panic device liveness alerts, panic_test service and device attributes"
```

---

### Task 8: Config flow, translations (incl. repair issue), migration v13

**Files:**
- Modify: `config_flow.py`, `translations/en.json`, `__init__.py`, `const.py`
- Test: `tests/test_config_flow.py`, `tests/test_init.py`

- [ ] **Step 1: Write the failing config-flow tests**

Append to `tests/test_config_flow.py`:
```python
class TestIntegrityFields:
    @pytest.fixture
    def config_flow(self) -> BehaviourMonitorConfigFlow:
        flow = BehaviourMonitorConfigFlow()
        flow.hass = MagicMock()
        return flow

    @pytest.fixture
    def options_flow(self, mock_config_entry: MagicMock) -> BehaviourMonitorOptionsFlow:
        flow = BehaviourMonitorOptionsFlow(mock_config_entry)
        flow.hass = MagicMock()
        flow.hass.config_entries = MagicMock()
        flow.hass.config_entries.async_update_entry = MagicMock()
        return flow

    @staticmethod
    def _keys() -> tuple[str, str, str, str]:
        from custom_components.behaviour_monitor.const import (
            CONF_BURST_DISCARD_THRESHOLD,
            CONF_PANIC_HEARTBEAT_HOURS,
            CONF_PANIC_TEST_REMINDER_DAYS,
            CONF_STARTUP_GRACE_SECONDS,
        )

        return CONF_STARTUP_GRACE_SECONDS, CONF_BURST_DISCARD_THRESHOLD, CONF_PANIC_HEARTBEAT_HOURS, CONF_PANIC_TEST_REMINDER_DAYS

    @pytest.mark.asyncio
    async def test_fields_in_both_flows(self, config_flow: BehaviourMonitorConfigFlow, options_flow: BehaviourMonitorOptionsFlow) -> None:
        for result in (await config_flow.async_step_user(user_input=None), await options_flow.async_step_init(user_input=None)):
            keys = {str(k) for k in result["data_schema"].keys()}
            for key in self._keys():
                assert any(key in k for k in keys), key

    @pytest.mark.asyncio
    async def test_options_prefills(self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor import config_flow as cf_module

        grace, burst, hb, rem = self._keys()
        mock_config_entry.data.update({grace: 120, burst: 5, hb: 48, rem: 7})
        with patch.object(cf_module, "_build_data_schema", wraps=cf_module._build_data_schema) as build:
            result = await options_flow.async_step_init(user_input=None)
        assert result["type"] == "form"
        kw = build.call_args.kwargs
        assert kw["startup_grace_seconds_default"] == 120
        assert kw["burst_discard_threshold_default"] == 5
        assert kw["panic_heartbeat_hours_default"] == 48
        assert kw["panic_test_reminder_days_default"] == 7
```

- [ ] **Step 2: Update migration tests and add v13 tests**

Run from the repo root:
```bash
source venv/bin/activate && python3 - <<'EOF'
p = "tests/test_init.py"
s = open(p).read()
s = s.replace('assert last_call[1]["version"] == 12', 'assert last_call[1]["version"] == 13')
s = s.replace('assert last_call.kwargs.get("version") == 12 or last_call[1].get("version") == 12',
              'assert last_call.kwargs.get("version") == 13 or last_call[1].get("version") == 13')
s = s.replace('        version = last_call.kwargs.get("version") or last_call[1].get("version")\n        assert version == 12',
              '        version = last_call.kwargs.get("version") or last_call[1].get("version")\n        assert version == 13')
s = s.replace('''    def test_storage_version_is_12(self) -> None:
        """Test that STORAGE_VERSION equals 12 after panic button bump."""
        assert STORAGE_VERSION == 12''', '''    def test_storage_version_is_13(self) -> None:
        """Test that STORAGE_VERSION equals 13 after system integrity bump."""
        assert STORAGE_VERSION == 13''')
s = s.replace('''    def test_config_flow_version_is_12(self) -> None:
        """BehaviourMonitorConfigFlow.VERSION should be 12 after panic button bump."""
        from custom_components.behaviour_monitor.config_flow import BehaviourMonitorConfigFlow
        assert BehaviourMonitorConfigFlow.VERSION == 12''', '''    def test_config_flow_version_is_13(self) -> None:
        """BehaviourMonitorConfigFlow.VERSION should be 13 after system integrity bump."""
        from custom_components.behaviour_monitor.config_flow import BehaviourMonitorConfigFlow
        assert BehaviourMonitorConfigFlow.VERSION == 13''')
s = s.replace('async def test_migrate_v2_updates_version_to_12(self) -> None:\n        """Migration from v2 ends at version=12 (v2->...->v11->v12)."""',
              'async def test_migrate_v2_updates_version_to_13(self) -> None:\n        """Migration from v2 ends at version=13 (v2->...->v12->v13)."""')
s = s.replace('async def test_migrate_v4_updates_version_to_12(self) -> None:\n        """Migration from v4 ends at version=12 (v4->...->v11->v12)."""',
              'async def test_migrate_v4_updates_version_to_13(self) -> None:\n        """Migration from v4 ends at version=13 (v4->...->v12->v13)."""')
for old, new in ((10, 11), (9, 10), (8, 9), (7, 8), (6, 7), (5, 6), (4, 5), (3, 4), (2, 3)):
    s = s.replace(f"async_update_entry.call_count == {old}\n", f"async_update_entry.call_count == {new}\n")
# v11->v12 seeds: two calls now, inspect index 0, version 12 on that call
old_seed = '''        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_PANIC] == []'''
new_seed = '''        assert result is True
        assert hass.config_entries.async_update_entry.call_count == 2
        call_args = hass.config_entries.async_update_entry.call_args_list[0]
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_PANIC] == []'''
assert old_seed in s
s = s.replace(old_seed, new_seed, 1)
s = s.replace('''        assert CONF_REBOOTSTRAP_MOTION not in updated_data
        version = call_args.kwargs.get("version") or call_args[1].get("version")
        assert version == 13''', '''        assert CONF_REBOOTSTRAP_MOTION not in updated_data
        version = call_args.kwargs.get("version") or call_args[1].get("version")
        assert version == 12''')
old_noop = '''    @pytest.mark.asyncio
    async def test_migrate_v12_is_noop(self) -> None:
        """A v12 config entry is not re-migrated — async_update_entry is not called."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=12,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_CATEGORY_PANIC: [],
                CONF_PANIC_RENOTIFY_MINUTES: 5,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_not_called()
'''
new_block = '''    @pytest.mark.asyncio
    async def test_migrate_v12_preserves_panic_keys(self) -> None:
        """A v12 entry continues to v13 without touching v12 keys."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=12,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_CATEGORY_PANIC: ["binary_sensor.sos"],
                CONF_PANIC_RENOTIFY_MINUTES: 5,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_PANIC] == ["binary_sensor.sos"]


class TestMigrateEntryV12ToV13:
    """Tests for v12->v13 migration (system integrity)."""

    def _make_config_entry(self, version: int, data: dict) -> MagicMock:
        entry = MagicMock()
        entry.version = version
        entry.data = data
        return entry

    @pytest.mark.asyncio
    async def test_migrate_v12_to_v13_seeds_defaults(self) -> None:
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(version=12, data={"monitored_entities": ["sensor.test"]})

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_STARTUP_GRACE_SECONDS] == DEFAULT_STARTUP_GRACE_SECONDS
        assert updated_data[CONF_BURST_DISCARD_THRESHOLD] == DEFAULT_BURST_DISCARD_THRESHOLD
        assert updated_data[CONF_PANIC_HEARTBEAT_HOURS] == DEFAULT_PANIC_HEARTBEAT_HOURS
        assert updated_data[CONF_PANIC_TEST_REMINDER_DAYS] == DEFAULT_PANIC_TEST_REMINDER_DAYS
        version = call_args.kwargs.get("version") or call_args[1].get("version")
        assert version == 13

    @pytest.mark.asyncio
    async def test_migrate_v12_to_v13_preserves_existing(self) -> None:
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(version=12, data={"monitored_entities": ["sensor.test"], CONF_STARTUP_GRACE_SECONDS: 0, CONF_PANIC_HEARTBEAT_HOURS: 6})

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_STARTUP_GRACE_SECONDS] == 0
        assert updated_data[CONF_PANIC_HEARTBEAT_HOURS] == 6

    @pytest.mark.asyncio
    async def test_migrate_v13_is_noop(self) -> None:
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(version=13, data={"monitored_entities": ["sensor.test"], CONF_STARTUP_GRACE_SECONDS: 90})

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_not_called()
'''
assert old_noop in s, "v12 noop test not found"
s = s.replace(old_noop, new_block, 1)
s = s.replace("    CONF_ACTIVITY_TIER_OVERRIDE,\n    CONF_ALERT_REPEAT_INTERVAL,\n",
              "    CONF_ACTIVITY_TIER_OVERRIDE,\n    CONF_ALERT_REPEAT_INTERVAL,\n    CONF_BURST_DISCARD_THRESHOLD,\n", 1)
s = s.replace("    CONF_MOTION_DEBOUNCE_SECONDS,\n    CONF_PANIC_RENOTIFY_MINUTES,\n",
              "    CONF_MOTION_DEBOUNCE_SECONDS,\n    CONF_PANIC_HEARTBEAT_HOURS,\n    CONF_PANIC_RENOTIFY_MINUTES,\n    CONF_PANIC_TEST_REMINDER_DAYS,\n    CONF_STARTUP_GRACE_SECONDS,\n", 1)
s = s.replace("    DEFAULT_ACTIVITY_TIER_OVERRIDE,\n",
              "    DEFAULT_ACTIVITY_TIER_OVERRIDE,\n    DEFAULT_BURST_DISCARD_THRESHOLD,\n    DEFAULT_PANIC_HEARTBEAT_HOURS,\n    DEFAULT_PANIC_TEST_REMINDER_DAYS,\n    DEFAULT_STARTUP_GRACE_SECONDS,\n", 1)
open(p, "w").write(s)

p = "tests/test_config_flow.py"
s = open(p).read()
old = '''    async def test_version_is_12(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        """Test VERSION is 12 after panic button additions."""
        assert config_flow.VERSION == 12'''
new = '''    async def test_version_is_13(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        """Test VERSION is 13 after system integrity additions."""
        assert config_flow.VERSION == 13'''
assert old in s
open(p, "w").write(s.replace(old, new, 1))
print("ok")
EOF
grep -n "== 12$\|VERSION = 12\|is_12\|to_12" tests/test_init.py tests/test_config_flow.py
```
Expected grep: only intermediate-call assertions inside `TestMigrateEntryV11ToV12` (index-0 version 12).

- [ ] **Step 3: Run to verify failures**, then **Step 4: Implement**

`const.py`: `STORAGE_VERSION: Final = 13`. `config_flow.py`: `VERSION = 13`; import the four CONF/DEFAULT pairs; add kwargs `startup_grace_seconds_default: int = DEFAULT_STARTUP_GRACE_SECONDS`, `burst_discard_threshold_default: int = DEFAULT_BURST_DISCARD_THRESHOLD`, `panic_heartbeat_hours_default: int = DEFAULT_PANIC_HEARTBEAT_HOURS`, `panic_test_reminder_days_default: int = DEFAULT_PANIC_TEST_REMINDER_DAYS`; after the `CONF_PANIC_RENOTIFY_MINUTES` field add four `vol.Required(...)` NumberSelectors: grace (min 0, max 300, step 10, seconds), burst (0–10 step 1), heartbeat (0–168 step 1, hours), reminder (0–365 step 1, days), all `NumberSelectorMode.BOX`; add the four `current_*` reads in `async_step_init` and pass them through.

`__init__.py`: import the four CONF/DEFAULT pairs; after the `< 12` block:
```python
    if config_entry.version < 13:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_STARTUP_GRACE_SECONDS, DEFAULT_STARTUP_GRACE_SECONDS)
        new_data.setdefault(CONF_BURST_DISCARD_THRESHOLD, DEFAULT_BURST_DISCARD_THRESHOLD)
        new_data.setdefault(CONF_PANIC_HEARTBEAT_HOURS, DEFAULT_PANIC_HEARTBEAT_HOURS)
        new_data.setdefault(CONF_PANIC_TEST_REMINDER_DAYS, DEFAULT_PANIC_TEST_REMINDER_DAYS)
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=13)
        _LOGGER.info("Behaviour Monitor: Config entry migrated to v13 — system integrity settings added")
```

`translations/en.json`, both flows, `data`:
```json
          "startup_grace_seconds": "Start-up grace period",
          "burst_discard_threshold": "Burst discard threshold",
          "panic_heartbeat_hours": "Panic device heartbeat",
          "panic_test_reminder_days": "Panic test reminder"
```
`data_description`:
```json
          "startup_grace_seconds": "Seconds after Home Assistant starts or the integration reloads during which state changes are ignored, because restarts write synthetic states to every entity. 0 disables.",
          "burst_discard_threshold": "If at least this many different entities change within the same second, the whole second is discarded as a reload artifact. 0 disables.",
          "panic_heartbeat_hours": "Raise a device-health alert when a panic button has not reported for this many hours. 0 disables.",
          "panic_test_reminder_days": "Raise a reminder when a panic button has not been test-pressed for this many days. 0 disables."
```
and a top-level `"issues"` object as in the spec.

- [ ] **Step 5: Run the full suite and parity, then commit**

```bash
git add custom_components/behaviour_monitor/config_flow.py custom_components/behaviour_monitor/translations/en.json custom_components/behaviour_monitor/__init__.py custom_components/behaviour_monitor/const.py tests/test_config_flow.py tests/test_init.py
git commit -m "feat: integrity settings in config flow, repair-issue translations, migration v13"
```

---

### Task 9: Docs, planning files, final verification

**Files:** `README.md`, `.planning/PROJECT.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`

- [ ] **Step 1: README**
- Configuration table: four rows (Start-up grace period 90 seconds; Burst discard threshold 3; Panic device heartbeat 24 hours; Panic test reminder 30 days) with one-line descriptions matching the translations.
- New `## System Integrity` section before `## Troubleshooting`:
  - **Entity health** — present / unavailable / missing; missing raises a repair issue; `health` and `contributing` on each entity status entry.
  - **Blind and degraded** — welfare `blind` when nothing reports (with a one-off "Behaviour Monitor: no data" notification), `degraded` on partial loss or a device-health alert; `contributing_entities`, `expected_entities`, `missing_entities`, `unavailable_entities` on the welfare sensor; confidence counts lost inputs as zero.
  - **Status summary** — "X OK, Y Need Attention[, Z Missing][, W Unavailable]".
  - **Panic device liveness** — availability, last report, battery; device-health alerts (unavailable, heartbeat, low battery, test reminder); the `panic_test` service and two-minute window; `devices` attribute on the Acknowledge Panic button.
  - **Start-up grace and burst discard** — what they do and the two settings.
- Services table row for `panic_test`. Upgrading: "(v2 through v13)" and a v13 bullet.

- [ ] **Step 2: Planning files** — ROADMAP v5.2 milestone line, details block (Phase 25: System Integrity), Progress row; PROJECT validated bullets (health/repair issues, blind/degraded, counts, panic liveness, event gate), context to v5.2 with real test count and LOC, schema v13, architecture lines for `entity_health.py` and `event_gate.py`, migration chain →v13, footer; STATE milestone v5.2 / Phase 25 / 100%, three decision bullets (blind precedence, gate armed at setup, device alerts on the ordinary path).

- [ ] **Step 3: Final verification**
```bash
source venv/bin/activate
python -m pytest tests/ -q | tail -1
ruff check custom_components tests | tail -1
mypy --no-incremental custom_components 2>&1 | grep -c error
git stash -q && ruff check custom_components tests | tail -1 && mypy --no-incremental custom_components 2>&1 | grep -c error; git stash pop -q
```

- [ ] **Step 4: Commit**
```bash
git add README.md .planning/PROJECT.md .planning/ROADMAP.md .planning/STATE.md
git commit -m "docs: system integrity — entity health, blind/degraded welfare, panic device liveness, event gate (v5.2)"
```
Do NOT push.

---

## Self-Review

**Spec coverage.** §1 health + repair issues → T1, T5. §2 qualified welfare + confidence → T1, T4, T5. §3 counter → T1, T5. §4 panic liveness + test press + device alerts → T3, T7. §5 gate → T2, T6. §6 config/migration → T8. §7 docs → T9. §8 tests: each bullet has a concrete test in T1–T8.

**Placeholder scan.** None. T9 describes doc text by content because it is prose, not code.

**Type consistency.** `resolve_entity_health/count_by_status/qualify_welfare` signatures identical in T1 and T5. `EventGate.submit/flush/arm/pending/dropped_bursts` identical in T2 and T6. `PanicMonitor.update_device/device_status/open_test_window/in_test_window/record_test/device_alerts/known_devices` identical in T3 and T7; `to_dict` new shape referenced by T3's coordinator-test fix. `overall_confidence(now, expected_ids)` identical in T4 and T5. `_finalize_welfare` produced in T5, used in T7. `_entity_facts` produced in T5, patched in T7 tests. Welfare precedence corrected vs. the spec (ordinary alert > degraded, blind > ordinary alert) and stated in Global Constraints.
