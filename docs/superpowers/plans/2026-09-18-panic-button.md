# Panic Button Category Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `PANIC` entity category whose binary sensors raise an instant, unsuppressable notification on press, re-notify every N minutes until acknowledged, and clear on release, shipping as Behaviour Monitor v5.1.

**Architecture:** A pure-Python `panic_monitor.py` holds the per-entity panic state machine. The coordinator gets a dedicated panic branch in its state-changed handler, two poll additions (panic alerts and due re-notifications), an acknowledge method, and persistence of the monitor. A new `button.py` platform and an `acknowledge_panic` service expose acknowledgement. Config flow gains a `category_panic` list and a re-notify interval; config entry and storage version become 12.

**Tech Stack:** Python 3.12, Home Assistant custom integration (mocked in tests via `tests/conftest.py`), pytest + pytest-asyncio, ruff, mypy, black.

**Spec:** `docs/superpowers/specs/2026-09-18-panic-button-design.md`

## Global Constraints

- Work on the existing branch `feat/entity-categories` (v5.0 is already there, PR #2 open). Do not create branches or push; the controller integrates.
- Config entry version and `STORAGE_VERSION` become **12**; `BehaviourMonitorConfigFlow.VERSION` becomes **12**.
- New config keys, exact strings: `category_panic` (list, default `[]`), `panic_renotify_minutes` (int, default `5`, UI range 1–60 step 1).
- New enum values: `EntityCategory.PANIC = "panic"`, `AlertType.PANIC = "panic"`.
- Panic is override-list only: no device-class or domain inference may ever yield PANIC.
- Panic notifications bypass `_enable_notifications`, holiday mode, snooze, the severity gate and the repeat interval. Title `"Behaviour Monitor: PANIC"`, persistent notification id `"behaviour_monitor_panic"`.
- Welfare: any active panic forces `status="alert"`, `recommendation="Panic button pressed. Respond now."`.
- Service name `acknowledge_panic` (`SERVICE_ACKNOWLEDGE_PANIC`), optional `entity_id`. Button entity unique id `f"{entry.entry_id}_acknowledge_panic"`, name "Acknowledge Panic", icon `mdi:alarm-light-off`.
- Store key `"panic_state"`. Events fired: `behaviour_monitor_panic_pressed`, `behaviour_monitor_panic_released`, `behaviour_monitor_panic_acknowledged`.
- Panic entities never touch the routine model, correlation detector, daily count, last-seen, motion debounce, or recorder bootstrap.
- `panic_monitor.py` must not import anything from `homeassistant`.
- Every task: `source venv/bin/activate && python -m pytest tests/ -q` green before committing; `ruff check custom_components tests` and `mypy --no-incremental custom_components` must show no NEW findings vs. `git stash` baseline. Run `black` on any new file.
- Conventional commits, `feat:` / `test:` / `docs:` only (minor release, no `!`).
- Commands run from `/Users/abourne/Documents/source/behaviour-monitor`.

---

## File Structure

| File | Responsibility |
|---|---|
| `custom_components/behaviour_monitor/const.py` | New CONF/DEFAULT/SERVICE constants, `EntityCategory.PANIC`, version 12 |
| `custom_components/behaviour_monitor/alert_result.py` | `AlertType.PANIC` |
| `custom_components/behaviour_monitor/entity_category.py` | Skip PANIC in weighted scoring; tolerate unknown category weight |
| `custom_components/behaviour_monitor/panic_monitor.py` (new) | `PanicMonitor` state machine, pure Python |
| `custom_components/behaviour_monitor/coordinator.py` | Panic branch, notification, poll integration, welfare, acknowledge, persistence, sensor payload |
| `custom_components/behaviour_monitor/button.py` (new) | `AcknowledgePanicButton` platform |
| `custom_components/behaviour_monitor/__init__.py` | `Platform.BUTTON`, `acknowledge_panic` service, v12 migration |
| `custom_components/behaviour_monitor/services.yaml` | `acknowledge_panic` entry |
| `custom_components/behaviour_monitor/config_flow.py` | `category_panic`, `panic_renotify_minutes`, VERSION 12 |
| `custom_components/behaviour_monitor/translations/en.json` | Labels/descriptions |
| `tests/conftest.py` | `homeassistant.components.button` mock, `Platform.BUTTON` |
| `tests/test_panic_monitor.py` (new), `tests/test_button.py` (new) | Unit tests |
| `tests/test_entity_category.py`, `tests/test_coordinator.py`, `tests/test_config_flow.py`, `tests/test_init.py`, `tests/test_alert_result.py` | Extended |
| `README.md`, `.planning/PROJECT.md`, `.planning/ROADMAP.md`, `.planning/STATE.md` | Docs |

---

### Task 1: Constants, enum values, and weighted-scoring guard

**Files:**
- Modify: `custom_components/behaviour_monitor/const.py`, `custom_components/behaviour_monitor/alert_result.py`, `custom_components/behaviour_monitor/entity_category.py`
- Test: `tests/test_entity_category.py`, `tests/test_alert_result.py`

**Interfaces:**
- Produces: `CONF_CATEGORY_PANIC = "category_panic"`, `DEFAULT_CATEGORY_PANIC: list[str] = []`, `CONF_PANIC_RENOTIFY_MINUTES = "panic_renotify_minutes"`, `DEFAULT_PANIC_RENOTIFY_MINUTES = 5`, `SERVICE_ACKNOWLEDGE_PANIC = "acknowledge_panic"`, `EntityCategory.PANIC`, `AlertType.PANIC`, `WELFARE_PANIC_RECOMMENDATION = "Panic button pressed. Respond now."`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_entity_category.py`:

```python
class TestPanicCategory:
    def test_constants(self) -> None:
        from custom_components.behaviour_monitor.const import (
            CONF_CATEGORY_PANIC,
            CONF_PANIC_RENOTIFY_MINUTES,
            DEFAULT_CATEGORY_PANIC,
            DEFAULT_PANIC_RENOTIFY_MINUTES,
            SERVICE_ACKNOWLEDGE_PANIC,
            WELFARE_PANIC_RECOMMENDATION,
        )

        assert EntityCategory.PANIC.value == "panic"
        assert AlertType.PANIC.value == "panic"
        assert CONF_CATEGORY_PANIC == "category_panic"
        assert DEFAULT_CATEGORY_PANIC == []
        assert CONF_PANIC_RENOTIFY_MINUTES == "panic_renotify_minutes"
        assert DEFAULT_PANIC_RENOTIFY_MINUTES == 5
        assert SERVICE_ACKNOWLEDGE_PANIC == "acknowledge_panic"
        assert WELFARE_PANIC_RECOMMENDATION == "Panic button pressed. Respond now."

    def test_panic_only_from_override_list(self) -> None:
        eid = "binary_sensor.sos"
        assert infer_categories([eid], {EntityCategory.PANIC: [eid]}, {})[eid] is EntityCategory.PANIC

    @pytest.mark.parametrize("dc", ["safety", "problem", "motion", None])
    def test_panic_never_inferred_from_device_class(self, dc: str | None) -> None:
        eid = "binary_sensor.sos"
        assert infer_categories([eid], {}, {eid: dc})[eid] is not EntityCategory.PANIC

    def test_weighted_status_skips_panic_alerts(self) -> None:
        alerts = [_alert("binary_sensor.sos", AlertSeverity.HIGH, AlertType.PANIC), _alert("switch.p", AlertSeverity.LOW)]
        cats = {"binary_sensor.sos": EntityCategory.PANIC, "switch.p": EntityCategory.PLUG}
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "check_recommended"

    def test_unknown_category_weight_defaults_to_one(self) -> None:
        # a non-panic alert on a PANIC-category entity must not KeyError
        alerts = [_alert("binary_sensor.sos", AlertSeverity.HIGH)]
        status, _ = derive_weighted_status(alerts, {"binary_sensor.sos": EntityCategory.PANIC})
        assert status == "alert"
```

Append to `tests/test_alert_result.py` inside the existing `AlertType` test class (or as a new test function at module level if the class is not obvious):

```python
    def test_panic_type(self) -> None:
        assert AlertType.PANIC == "panic"
        assert AlertType.PANIC.value == "panic"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_category.py::TestPanicCategory tests/test_alert_result.py -q`
Expected: FAIL with `AttributeError: PANIC` / `ImportError`.

- [ ] **Step 3: Implement**

`alert_result.py`, in `AlertType`, add after `CORRELATION_BREAK`:
```python
    PANIC = "panic"
```

`const.py`:
- After `CONF_MOTION_DEBOUNCE_SECONDS` add:
```python
# New v5.1 config keys (panic button)
CONF_CATEGORY_PANIC: Final = "category_panic"
CONF_PANIC_RENOTIFY_MINUTES: Final = "panic_renotify_minutes"
```
- After `DEFAULT_MOTION_DEBOUNCE_SECONDS` add:
```python
# New v5.1 defaults
DEFAULT_CATEGORY_PANIC: Final[list[str]] = []  # override-list only; never inferred
DEFAULT_PANIC_RENOTIFY_MINUTES: Final = 5  # minutes between re-notifications until acknowledged
```
- After `SERVICE_ROUTINE_RESET` add:
```python
SERVICE_ACKNOWLEDGE_PANIC: Final = "acknowledge_panic"
```
- In `EntityCategory`, after `LIGHT = "light"` add:
```python
    PANIC = "panic"  # override-list only; instant alert, no learning
```
- After `WELFARE_CONCERN_SCORE` add:
```python
# Recommendation text when any panic button is active
WELFARE_PANIC_RECOMMENDATION: Final = "Panic button pressed. Respond now."
```

`entity_category.py`:
- In `_alert_score`, change `CATEGORY_WEIGHT[category]` to `CATEGORY_WEIGHT.get(category, 1.0)`.
- In `derive_weighted_status`, change the skip to:
```python
        if alert.alert_type in (AlertType.CORRELATION_BREAK, AlertType.PANIC):
            continue
```
- Update its docstring line "Correlation-break alerts are ignored." to "Correlation-break and panic alerts are ignored; panic is handled by the coordinator ahead of weighted scoring."

- [ ] **Step 4: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components/behaviour_monitor/entity_category.py tests/test_entity_category.py`
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/const.py custom_components/behaviour_monitor/alert_result.py custom_components/behaviour_monitor/entity_category.py tests/test_entity_category.py tests/test_alert_result.py
git commit -m "feat: add PANIC entity category and alert type constants"
```

---

### Task 2: `PanicMonitor`

**Files:**
- Create: `custom_components/behaviour_monitor/panic_monitor.py`
- Test: `tests/test_panic_monitor.py` (new)

**Interfaces:**
- Produces:
```python
class PanicMonitor:
    def press(self, entity_id: str, now: datetime) -> bool
    def release(self, entity_id: str) -> None
    def acknowledge(self, now: datetime, entity_id: str | None = None) -> list[str]
    def due(self, now: datetime, interval: timedelta) -> list[str]
    def active(self) -> list[tuple[str, datetime, bool]]      # (entity_id, active_since, acknowledged), ordered by active_since
    def is_active(self, entity_id: str) -> bool
    def active_since(self, entity_id: str) -> datetime | None
    def unacknowledged(self) -> list[str]
    def to_dict(self) -> dict[str, Any]
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PanicMonitor"
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_panic_monitor.py`:

```python
"""Tests for PanicMonitor — panic button state machine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.behaviour_monitor.panic_monitor import PanicMonitor

T0 = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
FIVE = timedelta(minutes=5)


class TestPress:
    def test_first_press_returns_true(self) -> None:
        m = PanicMonitor()
        assert m.press("binary_sensor.sos", T0) is True
        assert m.is_active("binary_sensor.sos") is True

    def test_repeat_press_returns_false_and_keeps_since(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.sos", T0)
        assert m.press("binary_sensor.sos", T0 + timedelta(seconds=30)) is False
        assert m.active_since("binary_sensor.sos") == T0

    def test_press_after_release_is_new(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.sos", T0)
        m.release("binary_sensor.sos")
        assert m.press("binary_sensor.sos", T0 + FIVE) is True
        assert m.active_since("binary_sensor.sos") == T0 + FIVE

    def test_active_since_none_when_inactive(self) -> None:
        assert PanicMonitor().active_since("binary_sensor.sos") is None


class TestRelease:
    def test_release_clears_entity(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.sos", T0)
        m.release("binary_sensor.sos")
        assert m.is_active("binary_sensor.sos") is False
        assert m.active() == []

    def test_release_clears_acknowledgement(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.sos", T0)
        m.acknowledge(T0)
        m.release("binary_sensor.sos")
        m.press("binary_sensor.sos", T0 + FIVE)
        assert m.unacknowledged() == ["binary_sensor.sos"]

    def test_release_unknown_is_noop(self) -> None:
        PanicMonitor().release("binary_sensor.nope")


class TestAcknowledge:
    def test_acknowledge_all(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.press("binary_sensor.b", T0)
        assert sorted(m.acknowledge(T0)) == ["binary_sensor.a", "binary_sensor.b"]
        assert m.unacknowledged() == []
        assert [acked for _, _, acked in m.active()] == [True, True]

    def test_acknowledge_one(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.press("binary_sensor.b", T0)
        assert m.acknowledge(T0, "binary_sensor.a") == ["binary_sensor.a"]
        assert m.unacknowledged() == ["binary_sensor.b"]

    def test_acknowledge_returns_only_newly_acked(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.acknowledge(T0)
        assert m.acknowledge(T0 + FIVE) == []

    def test_acknowledge_unknown_entity_returns_empty(self) -> None:
        m = PanicMonitor()
        assert m.acknowledge(T0, "binary_sensor.nope") == []

    def test_acknowledged_entity_stays_active(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.acknowledge(T0)
        assert m.is_active("binary_sensor.a") is True


class TestDue:
    def test_not_due_before_interval(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        assert m.due(T0 + timedelta(minutes=4, seconds=59), FIVE) == []

    def test_due_at_exact_interval(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        assert m.due(T0 + FIVE, FIVE) == ["binary_sensor.a"]

    def test_due_stamps_only_returned(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.press("binary_sensor.b", T0 + timedelta(minutes=3))
        assert m.due(T0 + FIVE, FIVE) == ["binary_sensor.a"]
        # a was stamped at T0+5, b still at T0+3
        assert m.due(T0 + timedelta(minutes=8), FIVE) == ["binary_sensor.b"]
        assert m.due(T0 + timedelta(minutes=10), FIVE) == ["binary_sensor.a"]

    def test_acknowledged_never_due(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.acknowledge(T0)
        assert m.due(T0 + timedelta(hours=1), FIVE) == []

    def test_released_never_due(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.release("binary_sensor.a")
        assert m.due(T0 + timedelta(hours=1), FIVE) == []


class TestActiveOrdering:
    def test_active_ordered_by_since(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.b", T0 + FIVE)
        m.press("binary_sensor.a", T0)
        assert [e for e, _, _ in m.active()] == ["binary_sensor.a", "binary_sensor.b"]


class TestSerialization:
    def test_round_trip(self) -> None:
        m = PanicMonitor()
        m.press("binary_sensor.a", T0)
        m.press("binary_sensor.b", T0 + FIVE)
        m.acknowledge(T0 + FIVE, "binary_sensor.a")
        m.due(T0 + timedelta(minutes=10), FIVE)  # stamps b
        restored = PanicMonitor.from_dict(m.to_dict())
        assert restored.active() == m.active()
        assert restored.unacknowledged() == ["binary_sensor.b"]
        assert restored.due(T0 + timedelta(minutes=14), FIVE) == []
        assert restored.due(T0 + timedelta(minutes=15), FIVE) == ["binary_sensor.b"]

    def test_from_dict_drops_malformed(self) -> None:
        data = {
            "binary_sensor.ok": {"active_since": T0.isoformat(), "last_notified": T0.isoformat(), "acknowledged": False},
            "binary_sensor.bad": {"active_since": "not-a-date", "last_notified": T0.isoformat(), "acknowledged": False},
            "binary_sensor.missing": {"acknowledged": True},
        }
        m = PanicMonitor.from_dict(data)
        assert [e for e, _, _ in m.active()] == ["binary_sensor.ok"]

    def test_from_dict_empty(self) -> None:
        assert PanicMonitor.from_dict({}).active() == []
        assert PanicMonitor.from_dict(None).active() == []  # type: ignore[arg-type]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_panic_monitor.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `custom_components/behaviour_monitor/panic_monitor.py`:

```python
"""Panic button state machine.

Pure Python stdlib only. Zero Home Assistant imports. The coordinator owns one
instance, feeds it press/release transitions and the current time, and asks it
which entities are active and which are due for re-notification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class _PanicState:
    active_since: datetime
    last_notified: datetime
    acknowledged: bool = False


class PanicMonitor:
    """Track pressed panic buttons, acknowledgement, and re-notification timing."""

    def __init__(self) -> None:
        self._states: dict[str, _PanicState] = {}

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def press(self, entity_id: str, now: datetime) -> bool:
        """Mark the entity active. Returns True only for a new activation."""
        if entity_id in self._states:
            return False
        self._states[entity_id] = _PanicState(active_since=now, last_notified=now)
        return True

    def release(self, entity_id: str) -> None:
        """Clear the entity entirely, including any acknowledgement."""
        self._states.pop(entity_id, None)

    def acknowledge(self, now: datetime, entity_id: str | None = None) -> list[str]:
        """Acknowledge one entity or all active ones. Returns ids newly acknowledged."""
        targets = [entity_id] if entity_id is not None else list(self._states)
        changed: list[str] = []
        for eid in targets:
            state = self._states.get(eid)
            if state is not None and not state.acknowledged:
                state.acknowledged = True
                changed.append(eid)
        return changed

    def due(self, now: datetime, interval: timedelta) -> list[str]:
        """Return unacknowledged entities due for re-notification and stamp them."""
        result: list[str] = []
        for eid, state in self._states.items():
            if state.acknowledged:
                continue
            if now - state.last_notified >= interval:
                state.last_notified = now
                result.append(eid)
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def active(self) -> list[tuple[str, datetime, bool]]:
        """(entity_id, active_since, acknowledged) for every active entity, oldest first."""
        return sorted(
            ((eid, s.active_since, s.acknowledged) for eid, s in self._states.items()),
            key=lambda item: item[1],
        )

    def is_active(self, entity_id: str) -> bool:
        return entity_id in self._states

    def active_since(self, entity_id: str) -> datetime | None:
        state = self._states.get(entity_id)
        return state.active_since if state is not None else None

    def unacknowledged(self) -> list[str]:
        return [eid for eid, _, acked in self.active() if not acked]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            eid: {
                "active_since": s.active_since.isoformat(),
                "last_notified": s.last_notified.isoformat(),
                "acknowledged": s.acknowledged,
            }
            for eid, s in self._states.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PanicMonitor:
        monitor = cls()
        for eid, raw in (data or {}).items():
            try:
                since = datetime.fromisoformat(raw["active_since"])
                notified = datetime.fromisoformat(raw["last_notified"])
            except (KeyError, TypeError, ValueError):
                continue
            monitor._states[eid] = _PanicState(
                active_since=since,
                last_notified=notified,
                acknowledged=bool(raw.get("acknowledged", False)),
            )
        return monitor
```

- [ ] **Step 4: Run tests, black, ruff**

Run: `source venv/bin/activate && black custom_components/behaviour_monitor/panic_monitor.py tests/test_panic_monitor.py && python -m pytest tests/test_panic_monitor.py -q && ruff check custom_components/behaviour_monitor/panic_monitor.py tests/test_panic_monitor.py`
Expected: 22 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/panic_monitor.py tests/test_panic_monitor.py
git commit -m "feat: add PanicMonitor state machine for panic buttons"
```

---

### Task 3: Coordinator press/release/acknowledge, notification, persistence

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `PanicMonitor` (Task 2), `EntityCategory.PANIC`, `CONF_CATEGORY_PANIC`, `CONF_PANIC_RENOTIFY_MINUTES`, `DEFAULT_PANIC_RENOTIFY_MINUTES`.
- Produces on the coordinator: `self._panic_monitor`, `self._panic_renotify_minutes`, `_handle_panic_event(eid, old_state, new_state)`, `async _async_panic_pressed(entity_ids, now)`, `async _send_panic_notification(entity_ids, now)`, `async async_acknowledge_panic(entity_id=None)`, properties `panic_active -> list[str]`, `panic_unacknowledged -> list[str]`, store key `"panic_state"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator.py`:

```python
# ---------------------------------------------------------------------------
# TestPanicPressRelease — instant notification, release, acknowledge, persistence
# ---------------------------------------------------------------------------


class TestPanicPressRelease:
    def _make(self, mock_hass: MagicMock, mock_config_entry: MagicMock, **extra: Any) -> BehaviourMonitorCoordinator:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_PANIC, CONF_MONITORED_ENTITIES, EntityCategory

        mock_config_entry.data = {
            **mock_config_entry.data,
            CONF_MONITORED_ENTITIES: ["binary_sensor.sos", "binary_sensor.door"],
            CONF_CATEGORY_PANIC: ["binary_sensor.sos"],
            **extra,
        }
        c = BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
        c._categories = {"binary_sensor.sos": EntityCategory.PANIC, "binary_sensor.door": EntityCategory.CONTACT}
        return c

    @staticmethod
    def _event(entity_id: str, old: str | None, new: str) -> MagicMock:
        event = MagicMock()
        event.data = {
            "entity_id": entity_id,
            "old_state": None if old is None else MagicMock(state=old),
            "new_state": MagicMock(state=new),
        }
        return event

    @staticmethod
    async def _drain(mock_hass: MagicMock) -> None:
        """Await every coroutine handed to hass.async_create_task."""
        for call in mock_hass.async_create_task.call_args_list:
            coro = call[0][0]
            if hasattr(coro, "__await__"):
                await coro
        mock_hass.async_create_task.reset_mock()

    def test_defaults(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        assert c._panic_renotify_minutes == 5
        assert c.panic_active == []
        assert c.panic_unacknowledged == []

    @pytest.mark.asyncio
    async def test_press_notifies_immediately_bypassing_everything(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import CONF_ENABLE_NOTIFICATIONS, CONF_NOTIFY_SERVICES

        c = self._make(mock_hass, mock_config_entry, **{CONF_ENABLE_NOTIFICATIONS: False, CONF_NOTIFY_SERVICES: ["notify.phone"]})
        c._holiday_mode = True
        c._snooze_until = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch.object(c._store, "async_save", new_callable=AsyncMock):
            c._handle_state_changed(self._event("binary_sensor.sos", "off", "on"))
            await self._drain(mock_hass)
        calls = mock_hass.services.async_call.call_args_list
        assert any(
            call[0][0] == "persistent_notification"
            and call[0][2]["notification_id"] == "behaviour_monitor_panic"
            and call[0][2]["title"] == "Behaviour Monitor: PANIC"
            and "binary_sensor.sos" in call[0][2]["message"]
            for call in calls
        )
        assert any(call[0][0] == "notify" and call[0][1] == "phone" for call in calls)
        assert c.panic_active == ["binary_sensor.sos"]
        assert c.panic_unacknowledged == ["binary_sensor.sos"]
        assert c._last_notification_info["type"] == "panic"
        mock_hass.bus.async_fire.assert_any_call("behaviour_monitor_panic_pressed", {"entity_ids": ["binary_sensor.sos"]})

    @pytest.mark.asyncio
    async def test_repeat_on_does_not_renotify(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        with patch.object(c._store, "async_save", new_callable=AsyncMock):
            c._handle_state_changed(self._event("binary_sensor.sos", "off", "on"))
            await self._drain(mock_hass)
            mock_hass.services.async_call.reset_mock()
            c._handle_state_changed(self._event("binary_sensor.sos", "on", "on"))
            c._handle_state_changed(self._event("binary_sensor.sos", None, "on"))
            await self._drain(mock_hass)
        mock_hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_off_releases(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        with patch.object(c._store, "async_save", new_callable=AsyncMock):
            c._handle_state_changed(self._event("binary_sensor.sos", "off", "on"))
            await self._drain(mock_hass)
            c._handle_state_changed(self._event("binary_sensor.sos", "on", "off"))
            await self._drain(mock_hass)
        assert c.panic_active == []
        mock_hass.bus.async_fire.assert_any_call("behaviour_monitor_panic_released", {"entity_id": "binary_sensor.sos"})

    def test_panic_entity_never_touches_learning(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._handle_state_changed(self._event("binary_sensor.sos", "off", "on"))
        c._handle_state_changed(self._event("binary_sensor.sos", "on", "off"))
        assert "binary_sensor.sos" not in c._routine_model._entities
        assert "binary_sensor.sos" not in c._last_seen
        assert c._today_count == 0
        assert "binary_sensor.sos" not in c._correlation_detector._entity_event_counts

    def test_other_transitions_ignored(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._handle_state_changed(self._event("binary_sensor.sos", "off", "unavailable"))
        c._handle_state_changed(self._event("binary_sensor.sos", "off", "off"))
        assert c.panic_active == []
        mock_hass.async_create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_acknowledge_all_and_one(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_PANIC, CONF_MONITORED_ENTITIES, EntityCategory

        c = self._make(
            mock_hass, mock_config_entry,
            **{CONF_MONITORED_ENTITIES: ["binary_sensor.a", "binary_sensor.b"], CONF_CATEGORY_PANIC: ["binary_sensor.a", "binary_sensor.b"]},
        )
        c._categories = {"binary_sensor.a": EntityCategory.PANIC, "binary_sensor.b": EntityCategory.PANIC}
        now = datetime.now(timezone.utc)
        c._panic_monitor.press("binary_sensor.a", now)
        c._panic_monitor.press("binary_sensor.b", now)
        with patch.object(c._store, "async_save", new_callable=AsyncMock) as save:
            await c.async_acknowledge_panic("binary_sensor.a")
            assert c.panic_unacknowledged == ["binary_sensor.b"]
            mock_hass.bus.async_fire.assert_any_call("behaviour_monitor_panic_acknowledged", {"entity_ids": ["binary_sensor.a"]})
            await c.async_acknowledge_panic()
            assert c.panic_unacknowledged == []
            assert c.panic_active == ["binary_sensor.a", "binary_sensor.b"]
            assert save.await_count == 2
            # nothing left to acknowledge: no save, no event
            await c.async_acknowledge_panic()
            assert save.await_count == 2

    @pytest.mark.asyncio
    async def test_panic_state_persists(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        now = datetime.now(timezone.utc)
        c._panic_monitor.press("binary_sensor.sos", now)
        c._panic_monitor.acknowledge(now)
        with patch.object(c._store, "async_save", new_callable=AsyncMock) as save:
            await c._save_data()
        stored = save.call_args[0][0]
        assert "binary_sensor.sos" in stored["panic_state"]
        assert stored["panic_state"]["binary_sensor.sos"]["acknowledged"] is True

        c2 = self._make(mock_hass, mock_config_entry)
        with patch.object(c2._store, "async_load", new_callable=AsyncMock, return_value=stored), \
             patch.object(c2, "_registry_device_classes", return_value={}):
            await c2.async_setup()
        assert c2.panic_active == ["binary_sensor.sos"]
        assert c2.panic_unacknowledged == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_coordinator.py::TestPanicPressRelease -q`
Expected: FAIL (`AttributeError: _panic_renotify_minutes` etc.)

- [ ] **Step 3: Implement**

In `coordinator.py`:

(a) Imports: add `CONF_CATEGORY_PANIC, CONF_PANIC_RENOTIFY_MINUTES, DEFAULT_PANIC_RENOTIFY_MINUTES` to the `.const` block; add
```python
from .panic_monitor import PanicMonitor
```
after the `.entity_category` import.

(b) In `__init__`: add `EntityCategory.PANIC: list(d.get(CONF_CATEGORY_PANIC) or []),` to the `_category_overrides` dict, and after `self._debouncer = ...` add:
```python
        self._panic_renotify_minutes: int = int(d.get(CONF_PANIC_RENOTIFY_MINUTES, DEFAULT_PANIC_RENOTIFY_MINUTES))
        self._panic_monitor = PanicMonitor()
```

(c) Properties, directly after `is_snoozed`:
```python
    @property
    def panic_active(self) -> list[str]:
        return [eid for eid, _, _ in self._panic_monitor.active()]

    @property
    def panic_unacknowledged(self) -> list[str]:
        return self._panic_monitor.unacknowledged()
```

(d) In `async_setup`, inside the `if stored:` restore block, after the correlation-state restore, add:
```python
            if "panic_state" in stored:
                self._panic_monitor = PanicMonitor.from_dict(stored["panic_state"])
```

(e) In `_save_data`, add after the `"correlation_state"` line:
```python
            "panic_state": self._panic_monitor.to_dict(),
```

(f) In `_handle_state_changed`, immediately after the `if ns is None: return` guard and before `old_state = event.data.get("old_state")`, add:
```python
        if self._categories.get(eid) is EntityCategory.PANIC:
            self._handle_panic_event(eid, event.data.get("old_state"), ns)
            return
```

(g) Add these methods directly after `_handle_state_changed`:
```python
    def _handle_panic_event(self, eid: str, old_state: Any, new_state: Any) -> None:
        """Panic entities bypass learning entirely: press notifies now, release clears."""
        sv = str(new_state.state).lower()
        old_sv = None if old_state is None else str(old_state.state).lower()
        now = dt_util.now()
        if sv == "on" and old_sv != "on":
            if self._panic_monitor.press(eid, now):
                self.hass.async_create_task(self._async_panic_pressed([eid], now))
        elif sv == "off" and self._panic_monitor.is_active(eid):
            self._panic_monitor.release(eid)
            self.hass.async_create_task(
                self._save_fire_refresh(f"{DOMAIN}_panic_released", {"entity_id": eid})
            )

    async def _async_panic_pressed(self, entity_ids: list[str], now: datetime) -> None:
        await self._send_panic_notification(entity_ids, now)
        await self._save_fire_refresh(f"{DOMAIN}_panic_pressed", {"entity_ids": entity_ids})

    async def _send_panic_notification(self, entity_ids: list[str], now: datetime) -> None:
        """Send a panic notification. Ignores every suppression on purpose."""
        lines = []
        for eid in entity_ids:
            since = self._panic_monitor.active_since(eid)
            elapsed = (now - since).total_seconds() if since is not None else 0.0
            when = "just now" if elapsed < 60 else f"{format_duration(elapsed)} ago"
            lines.append(f"- PANIC: {eid} pressed {when}")
        title, msg = "Behaviour Monitor: PANIC", "\n".join(lines)
        await self.hass.services.async_call(
            "persistent_notification", "create",
            {"title": title, "message": msg, "notification_id": "behaviour_monitor_panic"},
        )
        for svc in self._notify_services:
            parts = svc.split(".", 1)
            if len(parts) == 2:
                await self.hass.services.async_call(parts[0], parts[1], {"title": title, "message": msg})
        self._last_notification_info = {"timestamp": now.isoformat(), "type": "panic"}

    async def async_acknowledge_panic(self, entity_id: str | None = None) -> None:
        """Acknowledge one or all active panics; stops re-notification until release."""
        changed = self._panic_monitor.acknowledge(dt_util.now(), entity_id)
        if changed:
            await self._save_fire_refresh(f"{DOMAIN}_panic_acknowledged", {"entity_ids": changed})
```

(h) In `_bootstrap_from_recorder`, at the top of the `for eid in targets:` loop body add:
```python
                if self._categories.get(eid) is EntityCategory.PANIC:
                    continue
```

- [ ] **Step 4: Run the full suite and lint parity**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components/behaviour_monitor/coordinator.py | tail -1`
Expected: all pass; ruff summary unchanged vs. `git stash` baseline.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py tests/test_coordinator.py
git commit -m "feat: instant panic notification, release, acknowledge and persistence in coordinator"
```

---

### Task 4: Coordinator poll integration — panic alerts, re-notify, welfare, sensor payload

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: Task 3 members, `AlertType.PANIC`, `WELFARE_PANIC_RECOMMENDATION`.
- Produces: `_panic_alerts(now) -> list[AlertResult]`, `async _renotify_panic(now)`, `_panic_payload() -> dict`, sensor data keys `panic` and `entity_status[*]["panic_active"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator.py`:

```python
class TestPanicPoll:
    def _make(self, mock_hass: MagicMock, mock_config_entry: MagicMock, **extra: Any) -> BehaviourMonitorCoordinator:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_PANIC, CONF_MONITORED_ENTITIES, EntityCategory

        mock_config_entry.data = {
            **mock_config_entry.data,
            CONF_MONITORED_ENTITIES: ["binary_sensor.sos", "switch.kettle"],
            CONF_CATEGORY_PANIC: ["binary_sensor.sos"],
            **extra,
        }
        c = BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
        c._categories = {"binary_sensor.sos": EntityCategory.PANIC, "switch.kettle": EntityCategory.PLUG}
        return c

    def test_panic_alerts_built_per_active_entity(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        now = datetime.now(timezone.utc)
        c._panic_monitor.press("binary_sensor.sos", now - timedelta(minutes=3))
        alerts = c._panic_alerts(now)
        assert len(alerts) == 1
        a = alerts[0]
        assert a.alert_type == AlertType.PANIC
        assert a.severity == AlertSeverity.HIGH
        assert a.entity_id == "binary_sensor.sos"
        assert a.confidence == 1.0
        assert "PANIC" in a.explanation and "3m" in a.explanation
        assert a.details["acknowledged"] is False

    def test_welfare_forced_to_alert_by_panic(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        now = datetime.now(timezone.utc)
        c._panic_monitor.press("binary_sensor.sos", now)
        alerts = c._panic_alerts(now) + [_make_alert("switch.kettle", severity=AlertSeverity.LOW)]
        w = c._derive_welfare(alerts)
        assert w["status"] == "alert"
        assert w["recommendation"] == "Panic button pressed. Respond now."
        assert w["reasons"][0].startswith("binary_sensor.sos")
        assert w["entity_count_by_status"] == {"binary_sensor.sos": 1, "switch.kettle": 1}

    def test_welfare_unchanged_without_panic(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        w = c._derive_welfare([_make_alert("switch.kettle", severity=AlertSeverity.HIGH)])
        assert w["status"] == "concern"

    @pytest.mark.asyncio
    async def test_poll_renotifies_when_due_and_not_after_ack(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        t0 = datetime.now(timezone.utc)
        c._panic_monitor.press("binary_sensor.sos", t0 - timedelta(minutes=6))
        with patch.object(c._store, "async_save", new_callable=AsyncMock):
            await c._renotify_panic(t0)
            assert mock_hass.services.async_call.call_count >= 1
            mock_hass.services.async_call.reset_mock()
            await c._renotify_panic(t0 + timedelta(minutes=1))
            mock_hass.services.async_call.assert_not_called()
            c._panic_monitor.acknowledge(t0)
            await c._renotify_panic(t0 + timedelta(hours=1))
            mock_hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_data_includes_panic_and_forces_status(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        now = datetime.now(timezone.utc)
        c._panic_monitor.press("binary_sensor.sos", now)
        with patch.object(c._store, "async_save", new_callable=AsyncMock), \
             patch.object(c, "_send_notification", new_callable=AsyncMock) as ordinary:
            data = await c._async_update_data()
        assert data["welfare"]["status"] == "alert"
        assert any(a["alert_type"] == "panic" for a in data["anomalies"])
        assert data["panic"] == {"active": ["binary_sensor.sos"], "unacknowledged": ["binary_sensor.sos"]}
        by_id = {e["entity_id"]: e for e in data["entity_status"]}
        assert by_id["binary_sensor.sos"]["panic_active"] is True
        assert by_id["switch.kettle"]["panic_active"] is False
        assert c._current_welfare_status == "alert"
        ordinary.assert_not_called()  # panic never goes through the ordinary path
        assert not any(k.endswith("|panic") for k in c._alert_suppression)

    @pytest.mark.asyncio
    async def test_update_data_during_holiday_still_shows_panic(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        c._holiday_mode = True
        now = datetime.now(timezone.utc)
        c._panic_monitor.press("binary_sensor.sos", now)
        with patch.object(c._store, "async_save", new_callable=AsyncMock):
            data = await c._async_update_data()
        assert data["welfare"]["status"] == "alert"
        assert data["anomaly_detected"] is True
        assert data["panic"]["active"] == ["binary_sensor.sos"]
        assert data["routine"]["summary"] == "Suppressed"

    @pytest.mark.asyncio
    async def test_update_data_no_panic_payload_empty(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        with patch.object(c._store, "async_save", new_callable=AsyncMock):
            data = await c._async_update_data()
        assert data["panic"] == {"active": [], "unacknowledged": []}
        c._holiday_mode = True
        data = await c._async_update_data()
        assert data["panic"] == {"active": [], "unacknowledged": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_coordinator.py::TestPanicPoll -q`
Expected: FAIL (`AttributeError: _panic_alerts` etc.)

- [ ] **Step 3: Implement**

In `coordinator.py`:

(a) Add `WELFARE_PANIC_RECOMMENDATION` to the `.const` import block.

(b) Add after `async_acknowledge_panic`:
```python
    def _panic_alerts(self, now: datetime) -> list[AlertResult]:
        alerts: list[AlertResult] = []
        for eid, since, acked in self._panic_monitor.active():
            elapsed = max(0.0, (now - since).total_seconds())
            alerts.append(AlertResult(
                entity_id=eid, alert_type=AlertType.PANIC, severity=AlertSeverity.HIGH, confidence=1.0,
                explanation=f"{eid}: PANIC button pressed {format_duration(elapsed)} ago",
                timestamp=now.isoformat(),
                details={"acknowledged": acked, "active_since": since.isoformat()},
            ))
        return alerts

    async def _renotify_panic(self, now: datetime) -> None:
        due = self._panic_monitor.due(now, timedelta(minutes=self._panic_renotify_minutes))
        if due:
            await self._send_panic_notification(due, now)
            await self._save_data()

    def _panic_payload(self) -> dict[str, list[str]]:
        return {"active": self.panic_active, "unacknowledged": self.panic_unacknowledged}
```

(c) Replace the tail of `_async_update_data` (from `if self._holiday_mode or self.is_snoozed():` to the end of the method) with:
```python
        panic_alerts = self._panic_alerts(now)
        if panic_alerts:
            await self._renotify_panic(now)
            self._current_welfare_status = "alert"
        if self._holiday_mode or self.is_snoozed():
            data = self._build_safe_defaults()
            if panic_alerts:
                data["anomaly_detected"] = True
                data["anomalies"] = [a.to_dict() for a in panic_alerts]
                data["welfare"] = self._derive_welfare(panic_alerts)
            return data
        try:
            alerts = self._run_detection(now) + panic_alerts
            await self._handle_alerts(alerts, now)
            return self._build_sensor_data(alerts, now)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Coordinator update error — returning safe defaults")
            return self._build_safe_defaults()
```

(d) In `_handle_alerts`, change
```python
        notifiable = [a for a in alerts if _ok(a)]
```
to
```python
        notifiable = [a for a in alerts if a.alert_type != AlertType.PANIC and _ok(a)]
```
(The welfare-status computation a few lines below stays on the full `alerts` list, so panic keeps the status at alert.)

(e) In `_derive_welfare`, insert immediately after the `if not alerts:` early return:
```python
        panic = [a for a in alerts if a.alert_type == AlertType.PANIC]
        if panic:
            ordered = panic + [a for a in alerts if a.alert_type not in (AlertType.PANIC, AlertType.CORRELATION_BREAK)]
            cnt_p: dict[str, int] = {}
            for a in ordered:
                cnt_p[a.entity_id] = cnt_p.get(a.entity_id, 0) + 1
            return {"status": "alert", "reasons": [a.explanation for a in ordered],
                    "summary": f"{len(ordered)} active alert(s): alert",
                    "recommendation": WELFARE_PANIC_RECOMMENDATION, "entity_count_by_status": cnt_p}
```

(f) In `_build_sensor_data`: inside each `entity_status` entry add
```python
                    "panic_active": self._panic_monitor.is_active(e),
```
after the `"category"` line; and add a top-level key
```python
            "panic": self._panic_payload(),
```
after the `"learning_status"` entry (inside the returned dict).

(g) In `_build_safe_defaults`, add `"panic": self._panic_payload(),` after `"cross_sensor_patterns": [],`.

- [ ] **Step 4: Run the full suite and lint parity**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components/behaviour_monitor/coordinator.py | tail -1`
Expected: all pass; no new ruff findings.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py tests/test_coordinator.py
git commit -m "feat: panic alerts, re-notification and forced welfare on the coordinator poll"
```

---

### Task 5: Config flow fields and translations

**Files:**
- Modify: `custom_components/behaviour_monitor/config_flow.py`, `custom_components/behaviour_monitor/translations/en.json`
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config_flow.py`:

```python
class TestPanicFields:
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
    def _keys() -> tuple[str, str, str]:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_MOTION, CONF_CATEGORY_PANIC, CONF_PANIC_RENOTIFY_MINUTES

        return CONF_CATEGORY_MOTION, CONF_CATEGORY_PANIC, CONF_PANIC_RENOTIFY_MINUTES

    def _base_input(self, **extra: Any) -> dict[str, Any]:
        _, panic, renotify = self._keys()
        data = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_HISTORY_WINDOW_DAYS: DEFAULT_HISTORY_WINDOW_DAYS,
            CONF_INACTIVITY_MULTIPLIER: DEFAULT_INACTIVITY_MULTIPLIER,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: DEFAULT_ENABLE_NOTIFICATIONS,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
            CONF_TRACK_ATTRIBUTES: False,
            panic: [],
            renotify: 5,
        }
        data.update(extra)
        return data

    @pytest.mark.asyncio
    async def test_fields_in_both_flows(self, config_flow: BehaviourMonitorConfigFlow, options_flow: BehaviourMonitorOptionsFlow) -> None:
        _, panic, renotify = self._keys()
        for result in (await config_flow.async_step_user(user_input=None), await options_flow.async_step_init(user_input=None)):
            keys = {str(k) for k in result["data_schema"].keys()}
            assert any(panic in k for k in keys)
            assert any(renotify in k for k in keys)

    @pytest.mark.asyncio
    async def test_panic_overlap_with_motion_rejected(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        motion, panic, _ = self._keys()
        result = await config_flow.async_step_user(user_input=self._base_input(**{motion: ["sensor.test1"], panic: ["sensor.test1"]}))
        assert result["type"] == "form"
        assert result["errors"]["base"] == "category_overlap"

    @pytest.mark.asyncio
    async def test_options_normalises_cleared_panic_list(self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock) -> None:
        _, panic, _ = self._keys()
        mock_config_entry.data[panic] = ["binary_sensor.sos"]
        user_input = self._base_input()
        user_input.pop(panic)
        result = await options_flow.async_step_init(user_input=user_input)
        assert result["type"] == "create_entry"
        saved = options_flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert saved[panic] == []

    @pytest.mark.asyncio
    async def test_options_prefills(self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor import config_flow as cf_module

        _, panic, renotify = self._keys()
        mock_config_entry.data[panic] = ["binary_sensor.sos"]
        mock_config_entry.data[renotify] = 10
        with patch.object(cf_module, "_build_data_schema", wraps=cf_module._build_data_schema) as build:
            result = await options_flow.async_step_init(user_input=None)
        assert result["type"] == "form"
        assert build.call_args.kwargs["category_panic_default"] == ["binary_sensor.sos"]
        assert build.call_args.kwargs["panic_renotify_minutes_default"] == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_config_flow.py::TestPanicFields -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`config_flow.py`:
- Import `CONF_CATEGORY_PANIC, CONF_PANIC_RENOTIFY_MINUTES, DEFAULT_CATEGORY_PANIC, DEFAULT_PANIC_RENOTIFY_MINUTES`.
- Add `CONF_CATEGORY_PANIC,` as the last element of `_CATEGORY_LIST_KEYS`.
- Add `_build_data_schema` kwargs after `motion_debounce_seconds_default`:
```python
    category_panic_default: list[str] | None = None,
    panic_renotify_minutes_default: int = DEFAULT_PANIC_RENOTIFY_MINUTES,
```
- In `schema_dict`, after the `CONF_MOTION_DEBOUNCE_SECONDS` entry add:
```python
        vol.Optional(
            CONF_CATEGORY_PANIC,
            default=list(category_panic_default or DEFAULT_CATEGORY_PANIC),
        ): EntitySelector(EntitySelectorConfig(multiple=True, domain="binary_sensor")),
        vol.Required(
            CONF_PANIC_RENOTIFY_MINUTES, default=panic_renotify_minutes_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=1,
                max=60,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="minutes",
            )
        ),
```
- In `async_step_init`, after `current_motion_debounce_seconds = ...` add:
```python
        current_category_panic = self._config_entry.data.get(
            CONF_CATEGORY_PANIC, DEFAULT_CATEGORY_PANIC
        )
        current_panic_renotify_minutes = self._config_entry.data.get(
            CONF_PANIC_RENOTIFY_MINUTES, DEFAULT_PANIC_RENOTIFY_MINUTES
        )
```
and pass `category_panic_default=current_category_panic, panic_renotify_minutes_default=current_panic_renotify_minutes,` to `_build_data_schema`.
- The overlap validation and the normalisation loop already iterate `_CATEGORY_LIST_KEYS`, so they pick up the new key automatically.

`translations/en.json`, in BOTH `config.step.user` and `options.step.init`:
- `data`:
```json
          "category_panic": "Panic buttons",
          "panic_renotify_minutes": "Panic re-notify interval"
```
- `data_description`:
```json
          "category_panic": "Binary sensors that act as panic buttons. A press notifies immediately, even during snooze or holiday mode, and keeps re-notifying until acknowledged. Releasing the button clears the alert.",
          "panic_renotify_minutes": "Minutes between repeat panic notifications until the alert is acknowledged."
```
Validate: `python -c "import json; json.load(open('custom_components/behaviour_monitor/translations/en.json'))"`.

- [ ] **Step 4: Run the full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components/behaviour_monitor/config_flow.py tests/test_config_flow.py | tail -1`
Expected: all pass; no new findings.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/config_flow.py custom_components/behaviour_monitor/translations/en.json tests/test_config_flow.py
git commit -m "feat: config flow fields for panic buttons and re-notify interval"
```

---

### Task 6: Acknowledge service and button platform

**Files:**
- Create: `custom_components/behaviour_monitor/button.py`, `tests/test_button.py`
- Modify: `custom_components/behaviour_monitor/__init__.py`, `custom_components/behaviour_monitor/services.yaml`, `tests/conftest.py`, `tests/test_init.py`

- [ ] **Step 1: Add the button mock to conftest**

In `tests/conftest.py`:
- In `MockPlatform`, add `BUTTON = "button"` after `SELECT`.
- After the `mock_switch.SwitchEntity = MockSwitchEntity` line add:
```python
    # Mock button component
    mock_button = MagicMock()

    class MockButtonEntity:
        """Mock ButtonEntity base class."""
        def __init__(self):
            self._attr_unique_id = None
            self._attr_name = None
            self._attr_device_info = None

        @property
        def unique_id(self):
            """Return unique ID."""
            return self._attr_unique_id

        async def async_press(self):
            """Press the button."""
            raise NotImplementedError

    mock_button.ButtonEntity = MockButtonEntity
```
- Add `mock_components.button = mock_button` next to the other `mock_components.*` lines and `sys.modules['homeassistant.components.button'] = mock_button` next to the other component `sys.modules` lines.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_button.py`:

```python
"""Tests for the button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.behaviour_monitor.button import (
    AcknowledgePanicButton,
    async_setup_entry,
)
from custom_components.behaviour_monitor.const import DOMAIN
from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator


class TestAcknowledgePanicButton:
    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        coordinator.panic_active = ["binary_sensor.sos"]
        coordinator.panic_unacknowledged = ["binary_sensor.sos"]
        coordinator.async_acknowledge_panic = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_config_entry(self) -> MagicMock:
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        return entry

    def test_initialization(self, mock_coordinator: MagicMock, mock_config_entry: MagicMock) -> None:
        button = AcknowledgePanicButton(mock_coordinator, mock_config_entry)
        assert button._attr_unique_id == "test_entry_123_acknowledge_panic"
        assert button._attr_name == "Acknowledge Panic"
        assert button._attr_icon == "mdi:alarm-light-off"
        assert button._attr_has_entity_name is True
        assert (DOMAIN, "test_entry_123") in button._attr_device_info["identifiers"]

    def test_extra_state_attributes(self, mock_coordinator: MagicMock, mock_config_entry: MagicMock) -> None:
        button = AcknowledgePanicButton(mock_coordinator, mock_config_entry)
        attrs = button.extra_state_attributes
        assert attrs["active_panics"] == ["binary_sensor.sos"]
        assert attrs["unacknowledged"] == 1

    @pytest.mark.asyncio
    async def test_press_acknowledges_all(self, mock_coordinator: MagicMock, mock_config_entry: MagicMock) -> None:
        button = AcknowledgePanicButton(mock_coordinator, mock_config_entry)
        await button.async_press()
        mock_coordinator.async_acknowledge_panic.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_setup_entry_adds_button(self, mock_coordinator: MagicMock, mock_config_entry: MagicMock) -> None:
        hass = MagicMock()
        hass.data = {DOMAIN: {"test_entry_123": mock_coordinator}}
        add = MagicMock()
        await async_setup_entry(hass, mock_config_entry, add)
        entities = add.call_args[0][0]
        assert len(entities) == 1
        assert isinstance(entities[0], AcknowledgePanicButton)
```

In `tests/test_init.py`:
- Add `SERVICE_ACKNOWLEDGE_PANIC` to the `.const` import block that already imports `SERVICE_ROUTINE_RESET`.
- In `test_async_setup_entry_registers_all_services`, append `(DOMAIN, SERVICE_ACKNOWLEDGE_PANIC),` to `expected_services`.
- Append to the class that contains that test (`TestAsyncSetupEntry`, the class holding the `registers_all_services` test):
```python
    @pytest.mark.asyncio
    async def test_acknowledge_panic_service_calls_coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        with patch(
            "custom_components.behaviour_monitor.BehaviourMonitorCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
            mock_coordinator.async_setup = AsyncMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.async_acknowledge_panic = AsyncMock()
            mock_coordinator.monitored_entities = {"sensor.test1"}
            mock_coordinator_class.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            handler = next(
                call[0][2] for call in mock_hass.services.async_register.call_args_list
                if call[0][1] == SERVICE_ACKNOWLEDGE_PANIC
            )
            call = MagicMock()
            call.data = {"entity_id": "binary_sensor.sos"}
            await handler(call)
            mock_coordinator.async_acknowledge_panic.assert_awaited_with("binary_sensor.sos")
            call.data = {}
            await handler(call)
            mock_coordinator.async_acknowledge_panic.assert_awaited_with(None)

    def test_platforms_include_button(self) -> None:
        from custom_components.behaviour_monitor import PLATFORMS

        assert "button" in [str(getattr(p, "value", p)) for p in PLATFORMS]
```
- If a test asserts the exact set or count of services removed on unload, add `SERVICE_ACKNOWLEDGE_PANIC` to it.

- [ ] **Step 3: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_button.py tests/test_init.py -q 2>&1 | tail -3`
Expected: FAIL (`ModuleNotFoundError: button`, service not registered).

- [ ] **Step 4: Implement**

Create `custom_components/behaviour_monitor/button.py`:

```python
"""Button platform for Behaviour Monitor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BehaviourMonitorCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Behaviour Monitor buttons."""
    coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AcknowledgePanicButton(coordinator, entry)])


class AcknowledgePanicButton(CoordinatorEntity[BehaviourMonitorCoordinator], ButtonEntity):
    """Button that acknowledges every active panic alert."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:alarm-light-off"

    def __init__(self, coordinator: BehaviourMonitorCoordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_acknowledge_panic"
        self._attr_name = "Acknowledge Panic"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Behaviour Monitor",
            manufacturer="Custom Integration",
            model="Pattern Analyzer",
            sw_version="2.6.0",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose which panics are active and how many await acknowledgement."""
        return {
            "active_panics": list(self.coordinator.panic_active),
            "unacknowledged": len(self.coordinator.panic_unacknowledged),
        }

    async def async_press(self) -> None:
        """Acknowledge all active panic alerts."""
        await self.coordinator.async_acknowledge_panic()
```

`__init__.py`:
- `PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.SELECT, Platform.BUTTON]`
- Import `SERVICE_ACKNOWLEDGE_PANIC` from `.const`.
- After `handle_routine_reset` add:
```python
    async def handle_acknowledge_panic(call: ServiceCall) -> None:
        """Handle acknowledge panic service call."""
        await coordinator.async_acknowledge_panic(call.data.get("entity_id"))
```
- After the `SERVICE_ROUTINE_RESET` registration add:
```python
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACKNOWLEDGE_PANIC,
        handle_acknowledge_panic,
        schema=vol.Schema({vol.Optional("entity_id"): str}),
    )
```
- In `async_unload_entry`, after the `SERVICE_ROUTINE_RESET` removal add `hass.services.async_remove(DOMAIN, SERVICE_ACKNOWLEDGE_PANIC)`.

`services.yaml`, append:
```yaml

acknowledge_panic:
  name: Acknowledge Panic
  description: >
    Acknowledge active panic button alerts. Stops repeat notifications until the
    button is released. Omit entity_id to acknowledge every active panic.
  fields:
    entity_id:
      name: Entity
      description: The panic button to acknowledge (optional; all if omitted).
      required: false
      example: binary_sensor.sos_pendant
      selector:
        entity:
          domain: binary_sensor
```

- [ ] **Step 5: Run the full suite, black, lint parity**

Run: `source venv/bin/activate && black custom_components/behaviour_monitor/button.py tests/test_button.py && python -m pytest tests/ -q | tail -1 && ruff check custom_components tests | tail -1`
Expected: all pass; no new findings.

- [ ] **Step 6: Commit**

```bash
git add custom_components/behaviour_monitor/button.py custom_components/behaviour_monitor/__init__.py custom_components/behaviour_monitor/services.yaml tests/conftest.py tests/test_button.py tests/test_init.py
git commit -m "feat: acknowledge_panic service and Acknowledge Panic button entity"
```

---

### Task 7: Migration v11 → v12 and version bump

**Files:**
- Modify: `custom_components/behaviour_monitor/__init__.py`, `custom_components/behaviour_monitor/const.py`, `custom_components/behaviour_monitor/config_flow.py`
- Test: `tests/test_init.py`, `tests/test_config_flow.py`

- [ ] **Step 1: Update existing assertions and add the v12 tests**

Run from the repo root:

```bash
source venv/bin/activate && python3 - <<'EOF'
p = "tests/test_init.py"
s = open(p).read()

s = s.replace('assert last_call[1]["version"] == 11', 'assert last_call[1]["version"] == 12')
s = s.replace('assert last_call.kwargs.get("version") == 11 or last_call[1].get("version") == 11',
              'assert last_call.kwargs.get("version") == 12 or last_call[1].get("version") == 12')
s = s.replace('        version = last_call.kwargs.get("version") or last_call[1].get("version")\n        assert version == 11',
              '        version = last_call.kwargs.get("version") or last_call[1].get("version")\n        assert version == 12')

s = s.replace('''    def test_storage_version_is_11(self) -> None:
        """Test that STORAGE_VERSION equals 11 after entity categories bump."""
        assert STORAGE_VERSION == 11''',
'''    def test_storage_version_is_12(self) -> None:
        """Test that STORAGE_VERSION equals 12 after panic button bump."""
        assert STORAGE_VERSION == 12''')
s = s.replace('''    def test_config_flow_version_is_11(self) -> None:
        """BehaviourMonitorConfigFlow.VERSION should be 11 after entity categories bump."""
        from custom_components.behaviour_monitor.config_flow import BehaviourMonitorConfigFlow
        assert BehaviourMonitorConfigFlow.VERSION == 11''',
'''    def test_config_flow_version_is_12(self) -> None:
        """BehaviourMonitorConfigFlow.VERSION should be 12 after panic button bump."""
        from custom_components.behaviour_monitor.config_flow import BehaviourMonitorConfigFlow
        assert BehaviourMonitorConfigFlow.VERSION == 12''')
s = s.replace('async def test_migrate_v2_updates_version_to_11(self) -> None:\n        """Migration from v2 ends at version=11 (v2->...->v10->v11)."""',
              'async def test_migrate_v2_updates_version_to_12(self) -> None:\n        """Migration from v2 ends at version=12 (v2->...->v11->v12)."""')
s = s.replace('async def test_migrate_v4_updates_version_to_11(self) -> None:\n        """Migration from v4 ends at version=11 (v4->...->v10->v11)."""',
              'async def test_migrate_v4_updates_version_to_12(self) -> None:\n        """Migration from v4 ends at version=12 (v4->...->v11->v12)."""')

for old, new in ((9, 10), (8, 9), (7, 8), (6, 7), (5, 6), (4, 5), (3, 4), (2, 3)):
    s = s.replace(f"async_update_entry.call_count == {old}\n", f"async_update_entry.call_count == {new}\n")

# v10->v11 seeds test: last call is now v12
old_seed = '''        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_MOTION] == []'''
new_seed = '''        assert result is True
        assert hass.config_entries.async_update_entry.call_count == 2
        call_args = hass.config_entries.async_update_entry.call_args_list[0]
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_MOTION] == []'''
assert old_seed in s
s = s.replace(old_seed, new_seed, 1)
# its trailing version assertion refers to the v11 call (index 0) — keep == 11 there:
s = s.replace('''        assert updated_data[CONF_REBOOTSTRAP_MOTION] is True
        version = call_args.kwargs.get("version") or call_args[1].get("version")
        assert version == 12''', '''        assert updated_data[CONF_REBOOTSTRAP_MOTION] is True
        version = call_args.kwargs.get("version") or call_args[1].get("version")
        assert version == 11''')

# v10->v11 preserves test reads last call; v12 step copies data through so it still holds — leave it.

old_noop = '''    @pytest.mark.asyncio
    async def test_migrate_v11_is_noop(self) -> None:
        """A v11 config entry is not re-migrated — async_update_entry is not called."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=11,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_CATEGORY_MOTION: [],
                CONF_MOTION_DEBOUNCE_SECONDS: 120,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_not_called()
'''
new_block = '''    @pytest.mark.asyncio
    async def test_migrate_v11_preserves_category_lists(self) -> None:
        """A v11 entry continues to v12 without touching v11 keys."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=11,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_CATEGORY_MOTION: ["binary_sensor.pir"],
                CONF_MOTION_DEBOUNCE_SECONDS: 120,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_MOTION] == ["binary_sensor.pir"]


class TestMigrateEntryV11ToV12:
    """Tests for v11->v12 migration (panic buttons)."""

    def _make_config_entry(self, version: int, data: dict) -> MagicMock:
        """Create a mock config entry with given version and data."""
        entry = MagicMock()
        entry.version = version
        entry.data = data
        return entry

    @pytest.mark.asyncio
    async def test_migrate_v11_to_v12_seeds_defaults(self) -> None:
        """Migration from v11 adds empty panic list and re-notify default."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=11,
            data={"monitored_entities": ["sensor.test"]},
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_PANIC] == []
        assert updated_data[CONF_PANIC_RENOTIFY_MINUTES] == DEFAULT_PANIC_RENOTIFY_MINUTES
        assert CONF_REBOOTSTRAP_MOTION not in updated_data
        version = call_args.kwargs.get("version") or call_args[1].get("version")
        assert version == 12

    @pytest.mark.asyncio
    async def test_migrate_v11_to_v12_preserves_existing(self) -> None:
        """Migration from v11 keeps a panic list and interval already present."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=11,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_CATEGORY_PANIC: ["binary_sensor.sos"],
                CONF_PANIC_RENOTIFY_MINUTES: 10,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_PANIC] == ["binary_sensor.sos"]
        assert updated_data[CONF_PANIC_RENOTIFY_MINUTES] == 10

    @pytest.mark.asyncio
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
assert old_noop in s, "v11 noop test not found"
s = s.replace(old_noop, new_block, 1)

s = s.replace(
    "    CONF_CATEGORY_MOTION,\n    CONF_CATEGORY_PLUG,\n",
    "    CONF_CATEGORY_MOTION,\n    CONF_CATEGORY_PANIC,\n    CONF_CATEGORY_PLUG,\n",
    1,
)
s = s.replace(
    "    CONF_MOTION_DEBOUNCE_SECONDS,\n    CONF_REBOOTSTRAP_MOTION,\n",
    "    CONF_MOTION_DEBOUNCE_SECONDS,\n    CONF_PANIC_RENOTIFY_MINUTES,\n    CONF_REBOOTSTRAP_MOTION,\n",
    1,
)
s = s.replace(
    "    DEFAULT_MOTION_DEBOUNCE_SECONDS,\n    DEFAULT_TRACK_ATTRIBUTES,\n",
    "    DEFAULT_MOTION_DEBOUNCE_SECONDS,\n    DEFAULT_PANIC_RENOTIFY_MINUTES,\n    DEFAULT_TRACK_ATTRIBUTES,\n",
    1,
)
open(p, "w").write(s)

p = "tests/test_config_flow.py"
s = open(p).read()
old = '''    async def test_version_is_11(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        """Test VERSION is 11 after entity category additions."""
        assert config_flow.VERSION == 11'''
new = '''    async def test_version_is_12(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        """Test VERSION is 12 after panic button additions."""
        assert config_flow.VERSION == 12'''
assert old in s
open(p, "w").write(s.replace(old, new, 1))
print("ok")
EOF
grep -n "== 11$\|VERSION = 11\|is_11\|to_11" tests/test_init.py tests/test_config_flow.py
```

Expected grep output: only the intermediate `v10_call` / `call_args_list[0]` checks inside `TestMigrateEntryV9ToV10` and `TestMigrateEntryV10ToV11` that assert `== 11` on the v11 step. Nothing else.

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_init.py tests/test_config_flow.py -q 2>&1 | tail -2`
Expected: many FAIL.

- [ ] **Step 3: Implement**

`const.py`: `STORAGE_VERSION: Final = 12`.
`config_flow.py`: `VERSION = 12`.
`__init__.py`: import `CONF_CATEGORY_PANIC, CONF_PANIC_RENOTIFY_MINUTES, DEFAULT_CATEGORY_PANIC, DEFAULT_PANIC_RENOTIFY_MINUTES`; after the `< 11` block add:
```python
    if config_entry.version < 12:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_CATEGORY_PANIC, list(DEFAULT_CATEGORY_PANIC))
        new_data.setdefault(CONF_PANIC_RENOTIFY_MINUTES, DEFAULT_PANIC_RENOTIFY_MINUTES)
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=12)
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v12 — panic button category added"
        )
```

- [ ] **Step 4: Run the full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1`
Expected: all pass. If a chained test fails on a count, raise that one by one and report which.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/__init__.py custom_components/behaviour_monitor/const.py custom_components/behaviour_monitor/config_flow.py tests/test_init.py tests/test_config_flow.py
git commit -m "feat: migrate config entries to v12 with panic button defaults"
```

---

### Task 8: Docs, planning files, final verification

**Files:**
- Modify: `README.md`, `.planning/PROJECT.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`

- [ ] **Step 1: README**

(a) `### Configuration Options` table, append after the "Motion debounce window" row:
```markdown
| Panic buttons | Binary sensors that act as panic buttons; a press alerts instantly and bypasses every suppression | Empty |
| Panic re-notify interval | Minutes between repeat panic notifications until acknowledged (1–60) | 5 |
```

(b) Under `### Entity Categories`, append a subsection at its end (before `### Acute Detection`):
```markdown
#### Panic Button

Add a binary sensor to the **Panic buttons** list to treat it as a panic button. Panic is never inferred from a device class; it must be listed explicitly.

- **Instant alert.** The moment the sensor turns `on`, a notification titled "Behaviour Monitor: PANIC" is sent to the persistent notification area and every configured mobile service. This ignores the notification toggle, holiday mode, snooze, the minimum severity and the repeat interval.
- **Re-notification.** While the panic is active and unacknowledged, the notification repeats every *Panic re-notify interval* minutes (checked on the 60-second poll).
- **Acknowledge.** Press `button.behaviour_monitor_acknowledge_panic` or call `behaviour_monitor.acknowledge_panic` (optionally with an `entity_id`). Acknowledging stops the repeats; the welfare status stays at `alert` until the button is released.
- **Release.** When the sensor returns to `off` the panic clears, including its acknowledgement, so the next press alerts again.

Panic entities never contribute to routine learning, tier classification, correlation or motion debounce. The `entity_status_summary` sensor shows `category: panic` and `panic_active` per entity, and a top-level `panic` attribute lists active and unacknowledged buttons. Events `behaviour_monitor_panic_pressed`, `behaviour_monitor_panic_released` and `behaviour_monitor_panic_acknowledged` fire on the bus for automations.
```

(c) `## Services` table: add a row
```markdown
| `behaviour_monitor.acknowledge_panic` | Acknowledge active panic alerts; optional `entity_id` | Stops repeat notifications until the button is released |
```
(match the existing table's column layout; if the table has different columns, adapt the row to them).

(d) `### Control Entities`: add a row/bullet for `button.behaviour_monitor_acknowledge_panic` — "Acknowledges every active panic alert; attributes list active and unacknowledged panics."

(e) `### Upgrading`: change `(v2 through v11)` to `(v2 through v12)` and append:
```markdown
- **v12**: Added panic button category and re-notify interval
```

- [ ] **Step 2: Planning files**

`.planning/ROADMAP.md`: add after the v5.0 milestone line
```markdown
- ✅ **v5.1 Panic Button** — Phase 24 (shipped 2026-09-18)
```
a details block after the v5.0 block
```markdown
<details>
<summary>✅ v5.1 Panic Button (Phase 24) — SHIPPED 2026-09-18</summary>

- [x] Phase 24: Panic Category, Instant Alert and Acknowledgement (panic_monitor.py, coordinator, button platform, migration v12) — completed 2026-09-18

</details>
```
and a Progress row
```markdown
| 24. Panic Category, Instant Alert and Acknowledgement | v5.1 | 1/1 | Complete | 2026-09-18 |
```

`.planning/PROJECT.md`: add after the v5.0 validated bullets
```markdown

- ✓ Panic button category (override-list only): instant unsuppressable notification, re-notify every N minutes until acknowledged, cleared on release; acknowledge via service and button entity; config migration v11→v12 — v5.1
```
Update the context sentence to `Shipped v5.1`, the real test count from `pytest --co -q | tail -1`, real LOC rounded to the nearest hundred, `Config schema at v12`; add architecture lines
```markdown
- `panic_monitor.py` — pure-Python panic state machine (press/release/acknowledge/due) persisted under `panic_state`
- `button.py` — Acknowledge Panic button entity
```
update the migration chain to end `→v12`, and the footer to `*Last updated: 2026-09-18 after v5.1 milestone shipped*`.

`.planning/STATE.md`: `milestone: v5.1`, `milestone_name: Panic Button`, `total_phases: 1`, `completed_phases: 1`, `total_plans: 1`, `completed_plans: 1`, `percent: 100`, `last_updated` to the current UTC time; body `Phase: 24`, `Progress: [██████████] 100% (1/1 v5.1 phases)`; under `### Decisions` add
```markdown
- [v5.1]: Panic is override-list only; no device-class inference (safety/problem are too ambiguous)
- [v5.1]: Panic notifications bypass every suppression; re-notify rides the 60 s poll (≤60 s jitter accepted)
- [v5.1]: Release clears acknowledgement; acknowledge stops repeats but keeps welfare at alert
```

- [ ] **Step 3: Final verification**

```bash
source venv/bin/activate
python -m pytest tests/ -q | tail -1
ruff check custom_components tests | tail -1
mypy --no-incremental custom_components 2>&1 | grep -c error
git stash -q && ruff check custom_components tests | tail -1 && mypy --no-incremental custom_components 2>&1 | grep -c error; git stash pop -q
```
Expected: all pass; identical ruff summary and mypy count both ways.

- [ ] **Step 4: Commit**

```bash
git add README.md .planning/PROJECT.md .planning/ROADMAP.md .planning/STATE.md
git commit -m "docs: panic button category, acknowledge service and v5.1 milestone"
```

Do NOT push. The controller runs the final review and integration.

---

## Self-Review

**Spec coverage.** §1 category/config → Tasks 1, 5, 7. §2 PanicMonitor (incl. `active_since`, `unacknowledged` helpers the coordinator needs) → Task 2. §3 handler branch, poll, welfare, notification, acknowledge, persistence, sensor data, bootstrap exclusion → Tasks 3, 4. Acknowledge surfaces (service + button + PLATFORMS + services.yaml) → Task 6. §4 migration/docs/release → Tasks 7, 8. §5 every test group has a concrete test.

**Placeholder scan.** None. The one "adapt the row to the table's columns" note in Task 8 is a formatting instruction, not missing content.

**Type consistency.** `PanicMonitor` method names/signatures identical across Tasks 2, 3, 4, 6. `panic_active` / `panic_unacknowledged` properties used identically in Tasks 3, 4, 6. `async_acknowledge_panic(entity_id=None)` identical in Tasks 3, 6. `AlertType.PANIC` / `EntityCategory.PANIC` from Task 1 used in Tasks 3, 4. Config kwargs `category_panic_default` / `panic_renotify_minutes_default` match between Task 5 tests and implementation. Task 7's script assumes the Task 6 test additions did not alter the v10→v11 test text it rewrites (they don't; Task 6 only adds new tests).
