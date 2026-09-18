# Entity Categories, Motion Debounce and Weighted Welfare Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Categorise monitored entities as motion / contact / plug / light / other, debounce motion sensors at ingestion, and weight welfare status by category, shipping as Behaviour Monitor v5.0.

**Architecture:** A new pure-Python module `entity_category.py` owns the `EntityCategory` enum, category inference, a `MotionDebouncer`, and the weighted welfare function. The coordinator builds a category map at setup, routes every state-changed event and recorder replay through the debouncer, and calls the weighted welfare function in place of its max-severity branch. Config flow gains four override entity lists and a debounce window; a v10→v11 migration seeds defaults and triggers a one-shot re-bootstrap of motion entities.

**Tech Stack:** Python 3.12, Home Assistant custom integration (mocked in tests via `tests/conftest.py`), pytest + pytest-asyncio, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-18-entity-categories-design.md`

## Global Constraints

- Config entry version becomes **11**; `STORAGE_VERSION` becomes **11**; `BehaviourMonitorConfigFlow.VERSION` becomes **11**.
- New config keys and defaults, exact strings: `category_motion`, `category_contact`, `category_plug`, `category_light` (all default `[]`); `motion_debounce_seconds` default `120`, UI range 0–600 step 10; `rebootstrap_motion` (bool, set only by migration).
- Category weights: MOTION 1.0, CONTACT 0.8, OTHER 1.0, PLUG 0.5, LIGHT 0.5. Severity points LOW 1, MEDIUM 2, HIGH 3. Thresholds: alert ≥ 2.25, concern ≥ 1.25.
- `entity_category.py` must not import anything from `homeassistant`.
- Individual alert severity, notifications, min-notification-severity gate, reasons list, `entity_count_by_status`, and the `routine_reset` service are unchanged.
- Every task: run `source venv/bin/activate && python -m pytest tests/ -q` before committing; the suite must be green. Run `ruff check custom_components tests` on touched files.
- Commit messages use conventional commits. Only the final docs task uses `feat!:` to mark the major bump; intermediate tasks use `feat:` / `test:` / `docs:`.
- All work happens on branch `feat/entity-categories` (create it in Task 1 from `main`). Push with `git push -u https://github.com/andrewmichael/behaviour-monitor.git feat/entity-categories` (SSH agent has no key loaded).
- Commands are run from the repo root `/Users/abourne/Documents/source/behaviour-monitor`.

---

## File Structure

| File | Responsibility |
|---|---|
| `custom_components/behaviour_monitor/const.py` | New CONF keys, defaults, `EntityCategory` enum, weight/points/threshold constants, version bump |
| `custom_components/behaviour_monitor/entity_category.py` (new) | `infer_categories`, `MotionDebouncer`, `derive_weighted_status` — pure Python |
| `custom_components/behaviour_monitor/coordinator.py` | Category map, registry lookup helper, debounce wiring, weighted welfare call, bootstrap refactor, re-bootstrap |
| `custom_components/behaviour_monitor/config_flow.py` | Five new fields, overlap validation, normalisation, prefill, VERSION 11 |
| `custom_components/behaviour_monitor/__init__.py` | v10→v11 migration |
| `custom_components/behaviour_monitor/translations/en.json` | Labels, descriptions, `category_overlap` error |
| `tests/test_entity_category.py` (new) | Unit tests for the new module |
| `tests/test_coordinator.py` | Category map, debounce wiring, weighted welfare, bootstrap/re-bootstrap tests |
| `tests/test_config_flow.py` | New fields, overlap, normalisation, prefill, version |
| `tests/test_init.py` | Migration v11 tests and chain updates |
| `README.md`, `.planning/PROJECT.md`, `.planning/ROADMAP.md` | Docs |

---

### Task 1: Constants and `EntityCategory` enum

**Files:**
- Modify: `custom_components/behaviour_monitor/const.py`
- Test: `tests/test_entity_category.py` (new)

**Interfaces:**
- Produces: `EntityCategory` enum (`MOTION="motion"`, `CONTACT="contact"`, `PLUG="plug"`, `LIGHT="light"`, `OTHER="other"`); constants `CONF_CATEGORY_MOTION`, `CONF_CATEGORY_CONTACT`, `CONF_CATEGORY_PLUG`, `CONF_CATEGORY_LIGHT`, `CONF_MOTION_DEBOUNCE_SECONDS`, `CONF_REBOOTSTRAP_MOTION`, `DEFAULT_CATEGORY_MOTION`, `DEFAULT_CATEGORY_CONTACT`, `DEFAULT_CATEGORY_PLUG`, `DEFAULT_CATEGORY_LIGHT`, `DEFAULT_MOTION_DEBOUNCE_SECONDS`, `CATEGORY_WEIGHT`, `SEVERITY_POINTS`, `WELFARE_ALERT_SCORE`, `WELFARE_CONCERN_SCORE`, `MOTION_DEVICE_CLASSES`, `CONTACT_DEVICE_CLASSES`, `PLUG_DEVICE_CLASSES`.

- [ ] **Step 1: Create the branch**

```bash
git checkout main && git checkout -b feat/entity-categories
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_entity_category.py`:

```python
"""Tests for entity_category: inference, motion debounce, weighted welfare."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.behaviour_monitor.const import (
    CATEGORY_WEIGHT,
    CONF_CATEGORY_CONTACT,
    CONF_CATEGORY_LIGHT,
    CONF_CATEGORY_MOTION,
    CONF_CATEGORY_PLUG,
    CONF_MOTION_DEBOUNCE_SECONDS,
    CONF_REBOOTSTRAP_MOTION,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
    SEVERITY_POINTS,
    WELFARE_ALERT_SCORE,
    WELFARE_CONCERN_SCORE,
    EntityCategory,
)
from custom_components.behaviour_monitor.alert_result import AlertSeverity


class TestConstants:
    def test_enum_values(self) -> None:
        assert EntityCategory.MOTION.value == "motion"
        assert EntityCategory.CONTACT.value == "contact"
        assert EntityCategory.PLUG.value == "plug"
        assert EntityCategory.LIGHT.value == "light"
        assert EntityCategory.OTHER.value == "other"

    def test_config_keys(self) -> None:
        assert CONF_CATEGORY_MOTION == "category_motion"
        assert CONF_CATEGORY_CONTACT == "category_contact"
        assert CONF_CATEGORY_PLUG == "category_plug"
        assert CONF_CATEGORY_LIGHT == "category_light"
        assert CONF_MOTION_DEBOUNCE_SECONDS == "motion_debounce_seconds"
        assert CONF_REBOOTSTRAP_MOTION == "rebootstrap_motion"
        assert DEFAULT_MOTION_DEBOUNCE_SECONDS == 120

    def test_weights_and_thresholds(self) -> None:
        assert CATEGORY_WEIGHT[EntityCategory.MOTION] == 1.0
        assert CATEGORY_WEIGHT[EntityCategory.CONTACT] == 0.8
        assert CATEGORY_WEIGHT[EntityCategory.OTHER] == 1.0
        assert CATEGORY_WEIGHT[EntityCategory.PLUG] == 0.5
        assert CATEGORY_WEIGHT[EntityCategory.LIGHT] == 0.5
        assert SEVERITY_POINTS[AlertSeverity.LOW] == 1
        assert SEVERITY_POINTS[AlertSeverity.MEDIUM] == 2
        assert SEVERITY_POINTS[AlertSeverity.HIGH] == 3
        assert WELFARE_ALERT_SCORE == 2.25
        assert WELFARE_CONCERN_SCORE == 1.25
```

- [ ] **Step 3: Run test to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_category.py -q`
Expected: FAIL with `ImportError: cannot import name 'CATEGORY_WEIGHT'`

- [ ] **Step 4: Add the constants**

In `custom_components/behaviour_monitor/const.py`, after the `# New v4.1 defaults` block (after `DEFAULT_TRACK_ATTRIBUTES_EXCLUDE`), add:

```python
# New v5.0 config keys (entity categories + motion debounce)
CONF_CATEGORY_MOTION: Final = "category_motion"
CONF_CATEGORY_CONTACT: Final = "category_contact"
CONF_CATEGORY_PLUG: Final = "category_plug"
CONF_CATEGORY_LIGHT: Final = "category_light"
CONF_MOTION_DEBOUNCE_SECONDS: Final = "motion_debounce_seconds"
# One-shot flag written by the v11 migration; cleared by the coordinator
# after it re-bootstraps motion entities from recorder history.
CONF_REBOOTSTRAP_MOTION: Final = "rebootstrap_motion"

# New v5.0 defaults
DEFAULT_CATEGORY_MOTION: Final[list[str]] = []
DEFAULT_CATEGORY_CONTACT: Final[list[str]] = []
DEFAULT_CATEGORY_PLUG: Final[list[str]] = []
DEFAULT_CATEGORY_LIGHT: Final[list[str]] = []
DEFAULT_MOTION_DEBOUNCE_SECONDS: Final = 120  # seconds; 0 disables debounce
```

At the end of `const.py`, after `PMI_THRESHOLD`, add:

```python
# ---------------------------------------------------------------------------
# Entity categories, motion debounce and weighted welfare (v5.0)
# ---------------------------------------------------------------------------


class EntityCategory(Enum):
    """Kind of device an entity represents, for debounce and welfare weighting."""

    MOTION = "motion"
    CONTACT = "contact"
    PLUG = "plug"
    LIGHT = "light"
    OTHER = "other"


# Entity-registry device classes that map to each category
MOTION_DEVICE_CLASSES: Final = frozenset({"motion", "occupancy", "presence"})
CONTACT_DEVICE_CLASSES: Final = frozenset({"door", "window", "opening", "garage_door"})
PLUG_DEVICE_CLASSES: Final = frozenset({"outlet", "plug"})

# Welfare weight per category — how strongly an alert from this kind of
# device evidences something about the person, not the device.
CATEGORY_WEIGHT: Final = {
    EntityCategory.MOTION: 1.0,
    EntityCategory.CONTACT: 0.8,
    EntityCategory.OTHER: 1.0,
    EntityCategory.PLUG: 0.5,
    EntityCategory.LIGHT: 0.5,
}

# Severity points multiplied by CATEGORY_WEIGHT to score an alert.
# Imported lazily to avoid a const -> alert_result import cycle; see below.
WELFARE_ALERT_SCORE: Final[float] = 2.25
WELFARE_CONCERN_SCORE: Final[float] = 1.25
```

`SEVERITY_POINTS` needs `AlertSeverity`, which lives in `alert_result.py` and imports nothing from `const.py`, so a plain import is safe. Add at the very top of `const.py` after `from typing import Final`:

```python
from .alert_result import AlertSeverity
```

and directly below `CATEGORY_WEIGHT` add:

```python
SEVERITY_POINTS: Final = {
    AlertSeverity.LOW: 1,
    AlertSeverity.MEDIUM: 2,
    AlertSeverity.HIGH: 3,
}
```

Remove the sentence "Imported lazily … see below." from the comment above `WELFARE_ALERT_SCORE` (it no longer applies).

- [ ] **Step 5: Run test to verify it passes**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_category.py -q && python -m pytest tests/ -q | tail -1`
Expected: `3 passed` then `545 passed` (542 existing + 3 new)

- [ ] **Step 6: Commit**

```bash
git add custom_components/behaviour_monitor/const.py tests/test_entity_category.py
git commit -m "feat: add EntityCategory enum, v5.0 config keys and welfare weight constants"
```

---

### Task 2: Category inference

**Files:**
- Create: `custom_components/behaviour_monitor/entity_category.py`
- Test: `tests/test_entity_category.py`

**Interfaces:**
- Consumes: `EntityCategory`, `MOTION_DEVICE_CLASSES`, `CONTACT_DEVICE_CLASSES`, `PLUG_DEVICE_CLASSES` from Task 1.
- Produces:
  ```python
  def infer_categories(
      entity_ids: Iterable[str],
      overrides: Mapping[EntityCategory, Iterable[str]],
      device_classes: Mapping[str, str | None],
      numeric_entities: Collection[str] = (),
  ) -> dict[str, EntityCategory]
  ```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_entity_category.py`:

```python
from custom_components.behaviour_monitor.entity_category import infer_categories


class TestInferCategories:
    def _infer(self, entity_id: str, **kw) -> EntityCategory:
        overrides = kw.pop("overrides", {})
        device_classes = kw.pop("device_classes", {})
        numeric = kw.pop("numeric", ())
        return infer_categories([entity_id], overrides, device_classes, numeric)[entity_id]

    @pytest.mark.parametrize("dc", ["motion", "occupancy", "presence"])
    def test_motion_device_classes(self, dc: str) -> None:
        eid = "binary_sensor.hall"
        assert self._infer(eid, device_classes={eid: dc}) is EntityCategory.MOTION

    @pytest.mark.parametrize("dc", ["door", "window", "opening", "garage_door"])
    def test_contact_device_classes(self, dc: str) -> None:
        eid = "binary_sensor.front"
        assert self._infer(eid, device_classes={eid: dc}) is EntityCategory.CONTACT

    @pytest.mark.parametrize("dc", ["outlet", "plug"])
    def test_plug_device_classes(self, dc: str) -> None:
        eid = "switch.kettle"
        assert self._infer(eid, device_classes={eid: dc}) is EntityCategory.PLUG

    def test_switch_domain_fallback(self) -> None:
        eid = "switch.lamp_socket"
        assert self._infer(eid, device_classes={eid: None}) is EntityCategory.PLUG

    def test_light_domain_fallback(self) -> None:
        eid = "light.kitchen"
        assert self._infer(eid, device_classes={eid: None}) is EntityCategory.LIGHT

    def test_unknown_device_class_and_domain_is_other(self) -> None:
        eid = "binary_sensor.smoke"
        assert self._infer(eid, device_classes={eid: "smoke"}) is EntityCategory.OTHER

    def test_missing_from_registry_uses_domain(self) -> None:
        # entity not present in device_classes mapping at all
        assert self._infer("switch.yaml_defined") is EntityCategory.PLUG
        assert self._infer("sensor.yaml_defined") is EntityCategory.OTHER

    def test_override_beats_device_class(self) -> None:
        eid = "binary_sensor.hall"
        cat = self._infer(
            eid,
            overrides={EntityCategory.CONTACT: [eid]},
            device_classes={eid: "motion"},
        )
        assert cat is EntityCategory.CONTACT

    def test_light_override(self) -> None:
        eid = "switch.strip"
        cat = self._infer(eid, overrides={EntityCategory.LIGHT: [eid]})
        assert cat is EntityCategory.LIGHT

    def test_numeric_entity_forced_to_other(self) -> None:
        eid = "sensor.lux"
        cat = self._infer(
            eid,
            overrides={EntityCategory.MOTION: [eid]},
            device_classes={eid: "motion"},
            numeric=[eid],
        )
        assert cat is EntityCategory.OTHER

    def test_returns_entry_for_every_entity(self) -> None:
        result = infer_categories(
            ["binary_sensor.a", "light.b", "sensor.c"],
            {},
            {"binary_sensor.a": "motion"},
        )
        assert result == {
            "binary_sensor.a": EntityCategory.MOTION,
            "light.b": EntityCategory.LIGHT,
            "sensor.c": EntityCategory.OTHER,
        }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_category.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.behaviour_monitor.entity_category'`

- [ ] **Step 3: Create the module with `infer_categories`**

Create `custom_components/behaviour_monitor/entity_category.py`:

```python
"""Entity categorisation, motion debounce and weighted welfare scoring.

Pure Python stdlib only. Zero Home Assistant imports. The coordinator supplies
registry device classes and numeric-ness so this module stays testable in
isolation.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from datetime import datetime, timedelta

from .alert_result import AlertResult, AlertType
from .const import (
    CATEGORY_WEIGHT,
    CONTACT_DEVICE_CLASSES,
    MOTION_DEVICE_CLASSES,
    PLUG_DEVICE_CLASSES,
    SEVERITY_POINTS,
    WELFARE_ALERT,
    WELFARE_ALERT_SCORE,
    WELFARE_CHECK,
    WELFARE_CONCERN,
    WELFARE_CONCERN_SCORE,
    EntityCategory,
)

# ---------------------------------------------------------------------------
# Category inference
# ---------------------------------------------------------------------------

_DOMAIN_FALLBACK: dict[str, EntityCategory] = {
    "switch": EntityCategory.PLUG,
    "light": EntityCategory.LIGHT,
}


def _category_for_device_class(device_class: str | None) -> EntityCategory | None:
    if device_class is None:
        return None
    if device_class in MOTION_DEVICE_CLASSES:
        return EntityCategory.MOTION
    if device_class in CONTACT_DEVICE_CLASSES:
        return EntityCategory.CONTACT
    if device_class in PLUG_DEVICE_CLASSES:
        return EntityCategory.PLUG
    return None


def infer_categories(
    entity_ids: Iterable[str],
    overrides: Mapping[EntityCategory, Iterable[str]],
    device_classes: Mapping[str, str | None],
    numeric_entities: Collection[str] = (),
) -> dict[str, EntityCategory]:
    """Return a category for every entity id.

    Precedence: numeric entities are always OTHER; then override lists; then
    the entity-registry device class; then a domain fallback (switch -> PLUG,
    light -> LIGHT); otherwise OTHER.
    """
    override_lookup: dict[str, EntityCategory] = {}
    for category, ids in overrides.items():
        for eid in ids:
            override_lookup[eid] = category

    result: dict[str, EntityCategory] = {}
    for eid in entity_ids:
        if eid in numeric_entities:
            result[eid] = EntityCategory.OTHER
            continue
        if eid in override_lookup:
            result[eid] = override_lookup[eid]
            continue
        from_dc = _category_for_device_class(device_classes.get(eid))
        if from_dc is not None:
            result[eid] = from_dc
            continue
        domain = eid.split(".", 1)[0]
        result[eid] = _DOMAIN_FALLBACK.get(domain, EntityCategory.OTHER)
    return result
```

(`MotionDebouncer` and `derive_weighted_status` are added in Tasks 3 and 4; the `AlertResult`, `AlertType`, `timedelta`, `SEVERITY_POINTS`, `CATEGORY_WEIGHT`, and `WELFARE_*` imports are used there. Ruff will flag them as unused until then — that is expected for this task only.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_category.py -q`
Expected: all pass (3 + 14 = 17)

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/entity_category.py tests/test_entity_category.py
git commit -m "feat: add category inference for monitored entities"
```

---

### Task 3: `MotionDebouncer`

**Files:**
- Modify: `custom_components/behaviour_monitor/entity_category.py`
- Test: `tests/test_entity_category.py`

**Interfaces:**
- Produces:
  ```python
  class MotionDebouncer:
      def __init__(self, window_seconds: int) -> None
      def should_count(self, entity_id: str, is_motion: bool,
                       old_state: str | None, new_state: str,
                       timestamp: datetime) -> bool
  ```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_entity_category.py`:

```python
from custom_components.behaviour_monitor.entity_category import MotionDebouncer

T0 = datetime(2026, 9, 18, 10, 0, 0)


class TestMotionDebouncer:
    def test_rising_edge_counts(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0) is True

    def test_off_transition_never_counts(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "on", "off", T0) is False
        # even when nothing has been counted yet
        assert d.should_count("binary_sensor.pir", True, None, "off", T0) is False

    def test_on_to_on_is_not_a_rising_edge(self) -> None:
        d = MotionDebouncer(0)
        assert d.should_count("binary_sensor.pir", True, "on", "on", T0) is False

    def test_second_edge_inside_window_dropped(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0) is True
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=119)) is False

    def test_edge_at_exactly_window_counts(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0) is True
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=120)) is True

    def test_dropped_edge_does_not_extend_window(self) -> None:
        d = MotionDebouncer(120)
        d.should_count("binary_sensor.pir", True, "off", "on", T0)
        d.should_count("binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=100))  # dropped
        # 120s after the *counted* edge, not the dropped one
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=120)) is True

    def test_zero_window_counts_every_rising_edge(self) -> None:
        d = MotionDebouncer(0)
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0) is True
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=1)) is True

    def test_none_old_state_counts_as_rising_edge(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, None, "on", T0) is True

    def test_non_motion_always_counts(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.door", False, "on", "off", T0) is True
        assert d.should_count("binary_sensor.door", False, "off", "off", T0) is True
        assert d.should_count("binary_sensor.door", False, "off", "on", T0 + timedelta(seconds=1)) is True

    def test_entities_are_independent(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.a", True, "off", "on", T0) is True
        assert d.should_count("binary_sensor.b", True, "off", "on", T0 + timedelta(seconds=1)) is True

    def test_state_is_case_insensitive(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "OFF", "On", T0) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_category.py::TestMotionDebouncer -q`
Expected: FAIL with `ImportError: cannot import name 'MotionDebouncer'`

- [ ] **Step 3: Implement the debouncer**

Append to `custom_components/behaviour_monitor/entity_category.py`:

```python
# ---------------------------------------------------------------------------
# Motion debounce
# ---------------------------------------------------------------------------


class MotionDebouncer:
    """Decide whether a motion-sensor event should count as activity.

    For motion entities only rising edges (not-on -> on) count, and only when
    at least ``window_seconds`` have elapsed since the last counted edge for
    that entity. Non-motion entities always count. State is in-memory only;
    after a restart the first rising edge always counts.
    """

    def __init__(self, window_seconds: int) -> None:
        self._window = timedelta(seconds=max(0, int(window_seconds)))
        self._last_counted: dict[str, datetime] = {}

    def should_count(
        self,
        entity_id: str,
        is_motion: bool,
        old_state: str | None,
        new_state: str,
        timestamp: datetime,
    ) -> bool:
        """Return True if this event should be recorded as activity."""
        if not is_motion:
            return True
        if new_state.lower() != "on":
            return False
        if old_state is not None and old_state.lower() == "on":
            return False
        last = self._last_counted.get(entity_id)
        if last is not None and timestamp - last < self._window:
            return False
        self._last_counted[entity_id] = timestamp
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_category.py -q`
Expected: all pass (17 + 11 = 28)

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/entity_category.py tests/test_entity_category.py
git commit -m "feat: add MotionDebouncer for rising-edge motion events"
```

---

### Task 4: `derive_weighted_status`

**Files:**
- Modify: `custom_components/behaviour_monitor/entity_category.py`
- Test: `tests/test_entity_category.py`

**Interfaces:**
- Produces:
  ```python
  def derive_weighted_status(
      alerts: Iterable[AlertResult],
      categories: Mapping[str, EntityCategory],
  ) -> tuple[str, str]   # (status, recommendation)
  ```
  Status is one of `WELFARE_ALERT` (`"alert"`), `WELFARE_CONCERN` (`"concern"`), `WELFARE_CHECK` (`"check_recommended"`). Never returns `"ok"`; the caller handles the no-alert case.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_entity_category.py`:

```python
from custom_components.behaviour_monitor.alert_result import AlertResult, AlertType
from custom_components.behaviour_monitor.entity_category import derive_weighted_status


def _alert(entity_id: str, severity: AlertSeverity, alert_type: AlertType = AlertType.INACTIVITY) -> AlertResult:
    return AlertResult(
        entity_id=entity_id,
        alert_type=alert_type,
        severity=severity,
        confidence=0.9,
        explanation=f"{entity_id} test",
        timestamp=T0.isoformat(),
    )


class TestDeriveWeightedStatus:
    @pytest.mark.parametrize(
        ("category", "severity", "expected"),
        [
            (EntityCategory.MOTION, AlertSeverity.HIGH, "alert"),
            (EntityCategory.MOTION, AlertSeverity.MEDIUM, "concern"),
            (EntityCategory.MOTION, AlertSeverity.LOW, "check_recommended"),
            (EntityCategory.OTHER, AlertSeverity.HIGH, "alert"),
            (EntityCategory.OTHER, AlertSeverity.MEDIUM, "concern"),
            (EntityCategory.OTHER, AlertSeverity.LOW, "check_recommended"),
            (EntityCategory.CONTACT, AlertSeverity.HIGH, "alert"),
            (EntityCategory.CONTACT, AlertSeverity.MEDIUM, "concern"),
            (EntityCategory.CONTACT, AlertSeverity.LOW, "check_recommended"),
            (EntityCategory.PLUG, AlertSeverity.HIGH, "concern"),
            (EntityCategory.PLUG, AlertSeverity.MEDIUM, "check_recommended"),
            (EntityCategory.PLUG, AlertSeverity.LOW, "check_recommended"),
            (EntityCategory.LIGHT, AlertSeverity.HIGH, "concern"),
            (EntityCategory.LIGHT, AlertSeverity.MEDIUM, "check_recommended"),
            (EntityCategory.LIGHT, AlertSeverity.LOW, "check_recommended"),
        ],
    )
    def test_single_alert_matrix(self, category: EntityCategory, severity: AlertSeverity, expected: str) -> None:
        status, _ = derive_weighted_status([_alert("x.y", severity)], {"x.y": category})
        assert status == expected

    def test_max_not_sum(self) -> None:
        alerts = [_alert(f"switch.p{i}", AlertSeverity.HIGH) for i in range(5)]
        cats = {a.entity_id: EntityCategory.PLUG for a in alerts}
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "concern"

    def test_strongest_alert_wins(self) -> None:
        alerts = [_alert("switch.p", AlertSeverity.HIGH), _alert("binary_sensor.m", AlertSeverity.MEDIUM)]
        cats = {"switch.p": EntityCategory.PLUG, "binary_sensor.m": EntityCategory.MOTION}
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "concern"
        alerts.append(_alert("binary_sensor.m2", AlertSeverity.HIGH))
        cats["binary_sensor.m2"] = EntityCategory.MOTION
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "alert"

    def test_unknown_entity_defaults_to_other_weight(self) -> None:
        status, _ = derive_weighted_status([_alert("sensor.unknown", AlertSeverity.HIGH)], {})
        assert status == "alert"

    def test_correlation_breaks_ignored(self) -> None:
        alerts = [
            _alert("binary_sensor.m", AlertSeverity.HIGH, AlertType.CORRELATION_BREAK),
            _alert("switch.p", AlertSeverity.LOW),
        ]
        cats = {"binary_sensor.m": EntityCategory.MOTION, "switch.p": EntityCategory.PLUG}
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "check_recommended"

    def test_recommendations(self) -> None:
        _, rec = derive_weighted_status([_alert("x.y", AlertSeverity.HIGH)], {})
        assert rec == "Immediate welfare check recommended."
        _, rec = derive_weighted_status([_alert("x.y", AlertSeverity.MEDIUM)], {})
        assert rec == "Schedule a welfare check soon."
        _, rec = derive_weighted_status([_alert("x.y", AlertSeverity.LOW)], {})
        assert rec == "Monitor closely."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_category.py::TestDeriveWeightedStatus -q`
Expected: FAIL with `ImportError: cannot import name 'derive_weighted_status'`

- [ ] **Step 3: Implement the function**

Append to `custom_components/behaviour_monitor/entity_category.py`:

```python
# ---------------------------------------------------------------------------
# Weighted welfare
# ---------------------------------------------------------------------------

_RECOMMENDATION = {
    WELFARE_ALERT: "Immediate welfare check recommended.",
    WELFARE_CONCERN: "Schedule a welfare check soon.",
    WELFARE_CHECK: "Monitor closely.",
}


def alert_score(alert: AlertResult, categories: Mapping[str, EntityCategory]) -> float:
    """Severity points times the category weight of the alert's entity."""
    category = categories.get(alert.entity_id, EntityCategory.OTHER)
    return SEVERITY_POINTS[alert.severity] * CATEGORY_WEIGHT[category]


def derive_weighted_status(
    alerts: Iterable[AlertResult],
    categories: Mapping[str, EntityCategory],
) -> tuple[str, str]:
    """Return (welfare status, recommendation) from the highest-scoring alert.

    Correlation-break alerts are ignored. The maximum score is used, not the
    sum, so several weak alerts from automated devices cannot compound.
    Callers must handle the no-alert case themselves; with no scoring alerts
    this returns the check_recommended tier.
    """
    top = 0.0
    for alert in alerts:
        if alert.alert_type == AlertType.CORRELATION_BREAK:
            continue
        top = max(top, alert_score(alert, categories))
    if top >= WELFARE_ALERT_SCORE:
        status = WELFARE_ALERT
    elif top >= WELFARE_CONCERN_SCORE:
        status = WELFARE_CONCERN
    else:
        status = WELFARE_CHECK
    return status, _RECOMMENDATION[status]
```

- [ ] **Step 4: Run tests and lint**

Run: `source venv/bin/activate && python -m pytest tests/test_entity_category.py -q && ruff check custom_components/behaviour_monitor/entity_category.py`
Expected: all pass (28 + 20 = 48); ruff `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/entity_category.py tests/test_entity_category.py
git commit -m "feat: add category-weighted welfare status derivation"
```

---

### Task 5: Coordinator category map, debounce wiring and sensor attribute

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `infer_categories`, `MotionDebouncer`, `EntityCategory`, new CONF/DEFAULT constants.
- Produces on `BehaviourMonitorCoordinator`:
  - `self._categories: dict[str, EntityCategory]` (empty until `_refresh_categories()` runs)
  - `self._motion_debounce_seconds: int`
  - `self._debouncer: MotionDebouncer` (live)
  - `def _registry_device_classes(self) -> dict[str, str | None]`
  - `def _refresh_categories(self) -> None`
  - `entity_status[*]["category"]` in sensor data

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator.py`:

```python
# ---------------------------------------------------------------------------
# TestEntityCategories — category map, debounce wiring, sensor attribute
# ---------------------------------------------------------------------------


class TestEntityCategories:
    """Category inference on the coordinator and motion debounce at ingestion."""

    def _make(
        self,
        mock_hass: MagicMock,
        mock_config_entry: MagicMock,
        entities: list[str],
        **extra: Any,
    ) -> BehaviourMonitorCoordinator:
        from custom_components.behaviour_monitor.const import CONF_MONITORED_ENTITIES

        mock_config_entry.data = {**mock_config_entry.data, CONF_MONITORED_ENTITIES: entities, **extra}
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    @staticmethod
    def _event(entity_id: str, old: str | None, new: str) -> MagicMock:
        event = MagicMock()
        event.data = {
            "entity_id": entity_id,
            "old_state": None if old is None else MagicMock(state=old),
            "new_state": MagicMock(state=new),
        }
        return event

    def test_defaults(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import DEFAULT_MOTION_DEBOUNCE_SECONDS

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"])
        assert c._motion_debounce_seconds == DEFAULT_MOTION_DEBOUNCE_SECONDS
        assert c._categories == {}

    def test_refresh_categories_uses_registry_and_overrides(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_CONTACT, EntityCategory

        c = self._make(
            mock_hass,
            mock_config_entry,
            ["binary_sensor.pir", "binary_sensor.door", "switch.kettle", "light.hall", "sensor.temp"],
            **{CONF_CATEGORY_CONTACT: ["sensor.temp"]},
        )
        with patch.object(
            c,
            "_registry_device_classes",
            return_value={"binary_sensor.pir": "motion", "binary_sensor.door": "door"},
        ):
            c._refresh_categories()
        assert c._categories == {
            "binary_sensor.pir": EntityCategory.MOTION,
            "binary_sensor.door": EntityCategory.CONTACT,
            "switch.kettle": EntityCategory.PLUG,
            "light.hall": EntityCategory.LIGHT,
            "sensor.temp": EntityCategory.CONTACT,
        }

    def test_refresh_categories_forces_numeric_to_other(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_MOTION, EntityCategory

        c = self._make(mock_hass, mock_config_entry, ["sensor.lux"], **{CONF_CATEGORY_MOTION: ["sensor.lux"]})
        c._routine_model.get_or_create("sensor.lux", is_binary=False)
        with patch.object(c, "_registry_device_classes", return_value={}):
            c._refresh_categories()
        assert c._categories["sensor.lux"] is EntityCategory.OTHER

    def test_registry_device_classes_handles_missing_entries(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor import coordinator as coord_module

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir", "switch.x"])
        registry = MagicMock()
        entry = MagicMock()
        entry.device_class = None
        entry.original_device_class = "motion"
        registry.async_get = lambda eid: entry if eid == "binary_sensor.pir" else None
        with patch.object(coord_module.er, "async_get", return_value=registry):
            result = c._registry_device_classes()
        assert result == {"binary_sensor.pir": "motion", "switch.x": None}

    def test_motion_off_transition_updates_last_seen_but_not_model(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import EntityCategory

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"])
        c._categories = {"binary_sensor.pir": EntityCategory.MOTION}
        c._handle_state_changed(self._event("binary_sensor.pir", "on", "off"))
        assert "binary_sensor.pir" in c._last_seen
        assert "binary_sensor.pir" not in c._routine_model._entities
        assert c._today_count == 0

    def test_motion_rising_edge_records(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import EntityCategory

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"])
        c._categories = {"binary_sensor.pir": EntityCategory.MOTION}
        c._handle_state_changed(self._event("binary_sensor.pir", "off", "on"))
        assert "binary_sensor.pir" in c._routine_model._entities
        assert c._today_count == 1

    def test_motion_burst_counts_once(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import EntityCategory

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"])
        c._categories = {"binary_sensor.pir": EntityCategory.MOTION}
        for _ in range(3):
            c._handle_state_changed(self._event("binary_sensor.pir", "off", "on"))
            c._handle_state_changed(self._event("binary_sensor.pir", "on", "off"))
        assert c._today_count == 1

    def test_zero_window_counts_every_edge(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import CONF_MOTION_DEBOUNCE_SECONDS, EntityCategory

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"], **{CONF_MOTION_DEBOUNCE_SECONDS: 0})
        c._categories = {"binary_sensor.pir": EntityCategory.MOTION}
        for _ in range(3):
            c._handle_state_changed(self._event("binary_sensor.pir", "off", "on"))
            c._handle_state_changed(self._event("binary_sensor.pir", "on", "off"))
        assert c._today_count == 3

    def test_non_motion_unchanged(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import EntityCategory

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.door"])
        c._categories = {"binary_sensor.door": EntityCategory.CONTACT}
        c._handle_state_changed(self._event("binary_sensor.door", "off", "on"))
        c._handle_state_changed(self._event("binary_sensor.door", "on", "off"))
        assert c._today_count == 2

    def test_sensor_data_includes_category(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import EntityCategory

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir", "sensor.other"])
        c._categories = {"binary_sensor.pir": EntityCategory.MOTION}
        data = c._build_sensor_data([], datetime.now())
        by_id = {e["entity_id"]: e for e in data["entity_status"]}
        assert by_id["binary_sensor.pir"]["category"] == "motion"
        assert by_id["sensor.other"]["category"] == "other"

    @pytest.mark.asyncio
    async def test_async_setup_refreshes_categories(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        c = self._make(mock_hass, mock_config_entry, ["switch.kettle"])
        with patch.object(c._store, "async_load", new_callable=AsyncMock, return_value=None), \
             patch.object(c, "_bootstrap_from_recorder", new_callable=AsyncMock), \
             patch.object(c._store, "async_save", new_callable=AsyncMock), \
             patch.object(c, "_registry_device_classes", return_value={}):
            await c.async_setup()
        assert c._categories["switch.kettle"].value == "plug"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_coordinator.py::TestEntityCategories -q`
Expected: FAIL (AttributeError on `_motion_debounce_seconds` / `_categories` / `_refresh_categories`)

- [ ] **Step 3: Wire the coordinator**

In `custom_components/behaviour_monitor/coordinator.py`:

(a) Add the entity registry import after `from homeassistant.core import ...`:

```python
from homeassistant.helpers import entity_registry as er
```

(b) Extend the `.const` import block: add `CONF_CATEGORY_CONTACT, CONF_CATEGORY_LIGHT, CONF_CATEGORY_MOTION, CONF_CATEGORY_PLUG, CONF_MOTION_DEBOUNCE_SECONDS, DEFAULT_MOTION_DEBOUNCE_SECONDS, EntityCategory` (keep the existing alphabetical-ish grouping; exact placement does not matter).

(c) After `from .drift_detector import ...` add:

```python
from .entity_category import MotionDebouncer, infer_categories
```

(d) In `__init__`, after the two `_track_attributes_*` lines add:

```python
        self._category_overrides: dict[EntityCategory, list[str]] = {
            EntityCategory.MOTION: list(d.get(CONF_CATEGORY_MOTION) or []),
            EntityCategory.CONTACT: list(d.get(CONF_CATEGORY_CONTACT) or []),
            EntityCategory.PLUG: list(d.get(CONF_CATEGORY_PLUG) or []),
            EntityCategory.LIGHT: list(d.get(CONF_CATEGORY_LIGHT) or []),
        }
        self._motion_debounce_seconds: int = int(d.get(CONF_MOTION_DEBOUNCE_SECONDS, DEFAULT_MOTION_DEBOUNCE_SECONDS))
        self._categories: dict[str, EntityCategory] = {}
        self._debouncer = MotionDebouncer(self._motion_debounce_seconds)
```

(e) Add two methods directly above `_tracks_attributes`:

```python
    def _registry_device_classes(self) -> dict[str, str | None]:
        """Return entity-registry device class per monitored entity (None if unknown)."""
        out: dict[str, str | None] = {}
        try:
            registry = er.async_get(self.hass)
        except Exception:  # noqa: BLE001
            return {eid: None for eid in self._monitored_entities}
        for eid in self._monitored_entities:
            entry = registry.async_get(eid)
            dc: Any = None
            if entry is not None:
                dc = entry.device_class or entry.original_device_class
            out[eid] = dc if isinstance(dc, str) else None
        return out

    def _refresh_categories(self) -> None:
        """Rebuild the entity -> category map from overrides, registry and model."""
        numeric = {eid for eid, r in self._routine_model._entities.items() if not r.is_binary}
        self._categories = infer_categories(
            self._monitored_entities,
            self._category_overrides,
            self._registry_device_classes(),
            numeric,
        )
```

(f) In `async_setup`, insert `self._refresh_categories()` as the first line after `stored = await self._store.async_load()` **and before** the `if stored:` block. (Task 7 reorganises the rest of this block; for now just add the call.)

(g) Replace the body of `_handle_state_changed` from `now, sv = ...` onward with:

```python
        now, sv = dt_util.now(), str(ns.state)
        self._last_seen[eid] = now
        old_state = event.data.get("old_state")
        old_sv = None if old_state is None else str(old_state.state)
        is_motion = self._categories.get(eid) is EntityCategory.MOTION
        if not self._debouncer.should_count(eid, is_motion, old_sv, sv, now):
            return
        self._routine_model.record(entity_id=eid, timestamp=now, state_value=sv, is_binary=is_binary_state(sv))
        self._correlation_detector.record_event(eid, now, self._last_seen)
        if self._today_date != now.date():
            self._today_count, self._today_date = 0, now.date()
        self._today_count += 1
        self.hass.async_create_task(self.async_request_refresh())
```

Note `_last_seen` is now set **before** the debounce decision (it was previously set after `record`). That is the intended behaviour change.

(h) In `_build_sensor_data`, inside the `entity_status` list comprehension, add after the `"activity_tier"` line:

```python
                    "category": self._categories.get(e, EntityCategory.OTHER).value,
```

- [ ] **Step 4: Run the full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1`
Expected: all pass. If `test_registry_device_classes_handles_missing_entries` fails because `coord_module.er` is a `MagicMock` attribute that `patch.object` cannot find, ensure the import in (a) is `from homeassistant.helpers import entity_registry as er` (module-level name `er`).

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py tests/test_coordinator.py
git commit -m "feat: infer entity categories and debounce motion events in coordinator"
```

---

### Task 6: Coordinator uses weighted welfare

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py` (`_derive_welfare`)
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `derive_weighted_status` from Task 4, `self._categories` from Task 5.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator.py`:

```python
class TestWeightedWelfare:
    """_derive_welfare uses category-weighted scoring."""

    @pytest.fixture
    def coordinator(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> BehaviourMonitorCoordinator:
        from custom_components.behaviour_monitor.const import CONF_MONITORED_ENTITIES

        mock_config_entry.data = {
            **mock_config_entry.data,
            CONF_MONITORED_ENTITIES: ["binary_sensor.pir", "switch.kettle"],
        }
        c = BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
        from custom_components.behaviour_monitor.const import EntityCategory

        c._categories = {
            "binary_sensor.pir": EntityCategory.MOTION,
            "switch.kettle": EntityCategory.PLUG,
        }
        return c

    def test_plug_high_is_concern_not_alert(self, coordinator: BehaviourMonitorCoordinator) -> None:
        welfare = coordinator._derive_welfare([_make_alert("switch.kettle", severity=AlertSeverity.HIGH)])
        assert welfare["status"] == "concern"
        assert welfare["recommendation"] == "Schedule a welfare check soon."

    def test_motion_high_is_alert(self, coordinator: BehaviourMonitorCoordinator) -> None:
        welfare = coordinator._derive_welfare([_make_alert("binary_sensor.pir", severity=AlertSeverity.HIGH)])
        assert welfare["status"] == "alert"

    def test_reasons_and_counts_still_include_plug_alert(self, coordinator: BehaviourMonitorCoordinator) -> None:
        alerts = [
            _make_alert("switch.kettle", severity=AlertSeverity.LOW),
            _make_alert("binary_sensor.pir", severity=AlertSeverity.LOW),
        ]
        welfare = coordinator._derive_welfare(alerts)
        assert welfare["status"] == "check_recommended"
        assert len(welfare["reasons"]) == 2
        assert welfare["entity_count_by_status"] == {"switch.kettle": 1, "binary_sensor.pir": 1}
        assert welfare["summary"] == "2 active alert(s): check_recommended"

    def test_no_alerts_is_ok(self, coordinator: BehaviourMonitorCoordinator) -> None:
        assert coordinator._derive_welfare([])["status"] == "ok"

    def test_only_correlation_breaks_is_ok(self, coordinator: BehaviourMonitorCoordinator) -> None:
        alerts = [_make_alert("binary_sensor.pir", alert_type=AlertType.CORRELATION_BREAK, severity=AlertSeverity.HIGH)]
        assert coordinator._derive_welfare(alerts)["status"] == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_coordinator.py::TestWeightedWelfare -q`
Expected: `test_plug_high_is_concern_not_alert` FAILS (status is `"alert"`); the others may already pass.

- [ ] **Step 3: Replace the severity branch in `_derive_welfare`**

In `coordinator.py`, change the `.entity_category` import to:

```python
from .entity_category import MotionDebouncer, derive_weighted_status, infer_categories
```

Then replace these lines in `_derive_welfare`:

```python
        sevs = [a.severity for a in welfare_alerts]
        if AlertSeverity.HIGH in sevs:
            st, rec = "alert", "Immediate welfare check recommended."
        elif AlertSeverity.MEDIUM in sevs:
            st, rec = "concern", "Schedule a welfare check soon."
        else:
            st, rec = "check_recommended", "Monitor closely."
```

with:

```python
        st, rec = derive_weighted_status(welfare_alerts, self._categories)
```

Leave the rest of the method (counts, reasons, summary) untouched.

- [ ] **Step 4: Run the full suite and lint**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components/behaviour_monitor/coordinator.py`
Expected: all pass. Any pre-existing ruff findings in `coordinator.py` are acceptable if they were present before this task (compare with `git stash; ruff check ...; git stash pop`); no new ones.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py tests/test_coordinator.py
git commit -m "feat: weight welfare status by entity category"
```

---

### Task 7: Bootstrap debounce and one-shot motion re-bootstrap

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py` (`async_setup`, `_bootstrap_from_recorder`, new `_rebootstrap_motion_entities`)
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `CONF_REBOOTSTRAP_MOTION`, `MotionDebouncer`, `EntityCategory`, `CorrelationDetector.remove_entity(entity_id)`.
- Produces:
  ```python
  async def _bootstrap_from_recorder(self, entity_ids: list[str] | None = None) -> None
  async def _rebootstrap_motion_entities(self) -> None
  ```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator.py`:

```python
class TestBootstrapDebounceAndRebootstrap:
    """Recorder replay goes through the debouncer; v11 flag triggers motion re-bootstrap."""

    def _make(self, mock_hass: MagicMock, mock_config_entry: MagicMock, **extra: Any) -> BehaviourMonitorCoordinator:
        from custom_components.behaviour_monitor.const import CONF_MONITORED_ENTITIES, EntityCategory

        mock_config_entry.data = {
            **mock_config_entry.data,
            CONF_MONITORED_ENTITIES: ["binary_sensor.pir", "binary_sensor.door"],
            **extra,
        }
        c = BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
        c._categories = {
            "binary_sensor.pir": EntityCategory.MOTION,
            "binary_sensor.door": EntityCategory.CONTACT,
        }
        return c

    @staticmethod
    def _states(entity_id: str, seq: list[tuple[str, int]]) -> list[MagicMock]:
        base = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
        out = []
        for state, offset in seq:
            s = MagicMock()
            s.state = state
            s.last_changed = base + timedelta(seconds=offset)
            out.append(s)
        return out

    def _patch_recorder(self, history: dict[str, list[MagicMock]]):
        instance = MagicMock()

        async def _job(_fn, _hass, _start, _end, ids, _sig):
            return {eid: history.get(eid, []) for eid in ids}

        instance.async_add_executor_job = _job
        return (
            patch("custom_components.behaviour_monitor.coordinator.recorder_get_instance", return_value=instance),
            patch("custom_components.behaviour_monitor.coordinator.recorder_state_changes_during_period", MagicMock()),
        )

    @pytest.mark.asyncio
    async def test_bootstrap_debounces_motion_history(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        history = {
            # three on/off cycles inside 120s -> one counted edge
            "binary_sensor.pir": self._states("binary_sensor.pir", [("on", 0), ("off", 10), ("on", 20), ("off", 30), ("on", 40), ("off", 50)]),
            # contact: every transition counts
            "binary_sensor.door": self._states("binary_sensor.door", [("on", 0), ("off", 10)]),
        }
        p1, p2 = self._patch_recorder(history)
        with p1, p2:
            await c._bootstrap_from_recorder()
        pir = c._routine_model._entities["binary_sensor.pir"]
        door = c._routine_model._entities["binary_sensor.door"]
        assert sum(len(s.event_times) for s in pir.slots) == 1
        assert sum(len(s.event_times) for s in door.slots) == 2

    @pytest.mark.asyncio
    async def test_bootstrap_respects_entity_subset(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        c = self._make(mock_hass, mock_config_entry)
        history = {
            "binary_sensor.pir": self._states("binary_sensor.pir", [("on", 0)]),
            "binary_sensor.door": self._states("binary_sensor.door", [("on", 0)]),
        }
        p1, p2 = self._patch_recorder(history)
        with p1, p2:
            await c._bootstrap_from_recorder(entity_ids=["binary_sensor.pir"])
        assert "binary_sensor.pir" in c._routine_model._entities
        assert "binary_sensor.door" not in c._routine_model._entities

    @pytest.mark.asyncio
    async def test_rebootstrap_clears_only_motion_and_clears_flag(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import CONF_REBOOTSTRAP_MOTION
        from custom_components.behaviour_monitor.drift_detector import CUSUMState

        c = self._make(mock_hass, mock_config_entry, **{CONF_REBOOTSTRAP_MOTION: True})
        # seed noisy state
        c._routine_model.get_or_create("binary_sensor.pir", is_binary=True)
        c._routine_model.get_or_create("binary_sensor.door", is_binary=True)
        c._correlation_detector._entity_event_counts["binary_sensor.pir"] = 5
        c._drift_detector._states["binary_sensor.pir"] = CUSUMState()
        c._last_seen["binary_sensor.pir"] = datetime.now(timezone.utc)
        door_before = c._routine_model._entities["binary_sensor.door"]

        history = {"binary_sensor.pir": self._states("binary_sensor.pir", [("on", 0)])}
        p1, p2 = self._patch_recorder(history)
        with p1, p2, patch.object(c._store, "async_save", new_callable=AsyncMock) as save:
            await c._rebootstrap_motion_entities()

        # motion routine rebuilt from history (1 event), contact untouched
        pir = c._routine_model._entities["binary_sensor.pir"]
        assert sum(len(s.event_times) for s in pir.slots) == 1
        assert c._routine_model._entities["binary_sensor.door"] is door_before
        # correlation counts purged for motion entity
        assert "binary_sensor.pir" not in c._correlation_detector._entity_event_counts
        # CUSUM and last_seen kept
        assert "binary_sensor.pir" in c._drift_detector._states
        assert "binary_sensor.pir" in c._last_seen
        save.assert_awaited_once()
        # flag cleared via async_update_entry
        call = mock_hass.config_entries.async_update_entry.call_args
        assert CONF_REBOOTSTRAP_MOTION not in call.kwargs["data"]

    @pytest.mark.asyncio
    async def test_rebootstrap_clears_flag_when_recorder_unavailable(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import CONF_REBOOTSTRAP_MOTION

        c = self._make(mock_hass, mock_config_entry, **{CONF_REBOOTSTRAP_MOTION: True})
        c._routine_model.get_or_create("binary_sensor.pir", is_binary=True)
        with patch("custom_components.behaviour_monitor.coordinator.recorder_get_instance", None), \
             patch.object(c._store, "async_save", new_callable=AsyncMock):
            await c._rebootstrap_motion_entities()
        assert "binary_sensor.pir" not in c._routine_model._entities
        call = mock_hass.config_entries.async_update_entry.call_args
        assert CONF_REBOOTSTRAP_MOTION not in call.kwargs["data"]

    @pytest.mark.asyncio
    async def test_async_setup_runs_rebootstrap_when_flag_set(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import CONF_REBOOTSTRAP_MOTION

        c = self._make(mock_hass, mock_config_entry, **{CONF_REBOOTSTRAP_MOTION: True})
        stored = {"routine_model": c._routine_model.to_dict(), "coordinator": {}}
        with patch.object(c._store, "async_load", new_callable=AsyncMock, return_value=stored), \
             patch.object(c, "_registry_device_classes", return_value={}), \
             patch.object(c, "_rebootstrap_motion_entities", new_callable=AsyncMock) as reboot, \
             patch.object(c, "_bootstrap_from_recorder", new_callable=AsyncMock) as boot:
            await c.async_setup()
        reboot.assert_awaited_once()
        boot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_async_setup_skips_rebootstrap_without_flag(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        c = self._make(mock_hass, mock_config_entry)
        stored = {"routine_model": c._routine_model.to_dict(), "coordinator": {}}
        with patch.object(c._store, "async_load", new_callable=AsyncMock, return_value=stored), \
             patch.object(c, "_registry_device_classes", return_value={}), \
             patch.object(c, "_rebootstrap_motion_entities", new_callable=AsyncMock) as reboot:
            await c.async_setup()
        reboot.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_coordinator.py::TestBootstrapDebounceAndRebootstrap -q`
Expected: FAIL (`TypeError: _bootstrap_from_recorder() got an unexpected keyword argument 'entity_ids'`, `AttributeError: _rebootstrap_motion_entities`, debounce assertion `3 == 1`)

- [ ] **Step 3: Implement**

In `coordinator.py`:

(a) Add `CONF_REBOOTSTRAP_MOTION` to the `.const` import block.

(b) Replace `_bootstrap_from_recorder` with:

```python
    async def _bootstrap_from_recorder(self, entity_ids: list[str] | None = None) -> None:
        """Replay recorder history into the routine model, debouncing motion entities.

        Uses a private MotionDebouncer so replay never disturbs live debounce state.
        """
        if recorder_get_instance is None or recorder_state_changes_during_period is None:
            _LOGGER.warning("Behaviour Monitor: recorder unavailable, skipping bootstrap")
            return
        targets = list(entity_ids) if entity_ids is not None else list(self._monitored_entities)
        debouncer = MotionDebouncer(self._motion_debounce_seconds)
        try:
            instance = recorder_get_instance(self.hass)
            if instance is None:
                return
            end, start = dt_util.now(), dt_util.now() - timedelta(days=self._history_window_days)
            for eid in targets:
                is_motion = self._categories.get(eid) is EntityCategory.MOTION
                prev: str | None = None
                try:
                    for sl in (await instance.async_add_executor_job(
                        recorder_state_changes_during_period, self.hass, start, end, [eid], False,
                    )).values():
                        for s in sl:
                            if s.state in ("unavailable", "unknown"):
                                continue
                            sv = str(s.state)
                            if debouncer.should_count(eid, is_motion, prev, sv, s.last_changed):
                                self._routine_model.record(eid, s.last_changed, sv, is_binary_state(sv))
                            prev = sv
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Could not load recorder history for %s", eid)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Behaviour Monitor: recorder bootstrap failed", exc_info=True)
```

(c) Add after `_bootstrap_from_recorder`:

```python
    async def _rebootstrap_motion_entities(self) -> None:
        """One-shot after the v11 migration: rebuild motion routines with debounce.

        Drops the learned routine and correlation counts for every motion-category
        entity, replays recorder history for those entities, saves, then clears
        the rebootstrap_motion flag on the config entry. CUSUM drift state and
        last_seen are kept.
        """
        motion = [e for e in self._monitored_entities if self._categories.get(e) is EntityCategory.MOTION]
        for eid in motion:
            self._routine_model._entities.pop(eid, None)
            self._correlation_detector.remove_entity(eid)
        if motion:
            await self._bootstrap_from_recorder(entity_ids=motion)
            _LOGGER.info("Behaviour Monitor: re-bootstrapped %d motion entities with debounce", len(motion))
        await self._save_data()
        new_data = {k: v for k, v in self._entry.data.items() if k != CONF_REBOOTSTRAP_MOTION}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
```

(d) In `async_setup`, restructure the store-loading tail so it reads:

```python
        stored = await self._store.async_load()
        if stored:
            ... (existing restore block, unchanged) ...
        self._refresh_categories()
        if stored:
            if self._entry.data.get(CONF_REBOOTSTRAP_MOTION, False):
                await self._rebootstrap_motion_entities()
        elif not self._routine_model._entities:
            await self._bootstrap_from_recorder()
            await self._save_data()
        self._unsub_state_changed = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed)
```

That is: move the `self._refresh_categories()` call added in Task 5 to sit **after** the restore block (so numeric-ness comes from the loaded model), and convert the old `elif not self._routine_model._entities:` into the `if stored: … elif …` shape above.

- [ ] **Step 4: Run the full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1`
Expected: all pass. The existing `TestRecorderBootstrap` tests still pass because a coordinator with empty `_categories` treats every entity as non-motion.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py tests/test_coordinator.py
git commit -m "feat: debounce motion history on bootstrap and re-bootstrap motion entities after migration"
```

---

### Task 8: Config flow fields, validation, prefill and translations

**Files:**
- Modify: `custom_components/behaviour_monitor/config_flow.py`
- Modify: `custom_components/behaviour_monitor/translations/en.json`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Produces: `_validate_category_overrides(user_input) -> str | None` returning `"category_overlap"` on conflict; `_build_data_schema` keyword args `category_motion_default`, `category_contact_default`, `category_plug_default`, `category_light_default`, `motion_debounce_seconds_default`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config_flow.py`:

```python
class TestCategoryFields:
    """v5.0 category override lists and motion debounce window in both flows."""

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
    def _keys() -> tuple[str, str, str, str, str]:
        from custom_components.behaviour_monitor.const import (
            CONF_CATEGORY_CONTACT,
            CONF_CATEGORY_LIGHT,
            CONF_CATEGORY_MOTION,
            CONF_CATEGORY_PLUG,
            CONF_MOTION_DEBOUNCE_SECONDS,
        )

        return (
            CONF_CATEGORY_MOTION,
            CONF_CATEGORY_CONTACT,
            CONF_CATEGORY_PLUG,
            CONF_CATEGORY_LIGHT,
            CONF_MOTION_DEBOUNCE_SECONDS,
        )

    def _base_input(self, **extra: Any) -> dict[str, Any]:
        motion, contact, plug, light, debounce = self._keys()
        data = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_HISTORY_WINDOW_DAYS: DEFAULT_HISTORY_WINDOW_DAYS,
            CONF_INACTIVITY_MULTIPLIER: DEFAULT_INACTIVITY_MULTIPLIER,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: DEFAULT_ENABLE_NOTIFICATIONS,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
            CONF_TRACK_ATTRIBUTES: False,
            motion: [],
            contact: [],
            plug: [],
            light: [],
            debounce: 120,
        }
        data.update(extra)
        return data

    @pytest.mark.asyncio
    async def test_user_schema_includes_category_fields(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        result = await config_flow.async_step_user(user_input=None)
        keys = {str(k) for k in result["data_schema"].keys()}
        for key in self._keys():
            assert any(key in k for k in keys), key

    @pytest.mark.asyncio
    async def test_options_schema_includes_category_fields(self, options_flow: BehaviourMonitorOptionsFlow) -> None:
        result = await options_flow.async_step_init(user_input=None)
        keys = {str(k) for k in result["data_schema"].keys()}
        for key in self._keys():
            assert any(key in k for k in keys), key

    @pytest.mark.asyncio
    @pytest.mark.parametrize("pair", [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)])
    async def test_user_rejects_entity_in_two_lists(
        self, config_flow: BehaviourMonitorConfigFlow, pair: tuple[int, int]
    ) -> None:
        keys = self._keys()
        result = await config_flow.async_step_user(
            user_input=self._base_input(**{keys[pair[0]]: ["sensor.test1"], keys[pair[1]]: ["sensor.test1"]})
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "category_overlap"

    @pytest.mark.asyncio
    async def test_options_rejects_entity_in_two_lists(self, options_flow: BehaviourMonitorOptionsFlow) -> None:
        motion, contact, *_ = self._keys()
        result = await options_flow.async_step_init(
            user_input=self._base_input(**{motion: ["sensor.test1"], contact: ["sensor.test1"]})
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "category_overlap"

    @pytest.mark.asyncio
    async def test_user_accepts_disjoint_lists(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        motion, contact, plug, light, debounce = self._keys()
        result = await config_flow.async_step_user(
            user_input=self._base_input(**{motion: ["sensor.test1"], plug: ["sensor.test2"], debounce: 60})
        )
        assert result["type"] == "create_entry"
        assert result["data"][motion] == ["sensor.test1"]
        assert result["data"][plug] == ["sensor.test2"]
        assert result["data"][debounce] == 60

    @pytest.mark.asyncio
    async def test_options_normalises_cleared_lists(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        motion, contact, plug, light, _ = self._keys()
        mock_config_entry.data[motion] = ["sensor.test1"]
        mock_config_entry.data[light] = ["sensor.test2"]
        user_input = self._base_input()
        for key in (motion, contact, plug, light):
            user_input.pop(key)  # cleared selectors are absent from user_input
        result = await options_flow.async_step_init(user_input=user_input)
        assert result["type"] == "create_entry"
        saved = options_flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        for key in (motion, contact, plug, light):
            assert saved[key] == []

    @pytest.mark.asyncio
    async def test_options_prefills_existing_values(
        self, options_flow: BehaviourMonitorOptionsFlow, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor import config_flow as cf_module

        motion, contact, plug, light, debounce = self._keys()
        mock_config_entry.data[motion] = ["binary_sensor.pir"]
        mock_config_entry.data[contact] = ["binary_sensor.door"]
        mock_config_entry.data[plug] = ["switch.kettle"]
        mock_config_entry.data[light] = ["light.hall"]
        mock_config_entry.data[debounce] = 45
        with patch.object(cf_module, "_build_data_schema", wraps=cf_module._build_data_schema) as build:
            result = await options_flow.async_step_init(user_input=None)
        assert result["type"] == "form"
        kwargs = build.call_args.kwargs
        assert kwargs["category_motion_default"] == ["binary_sensor.pir"]
        assert kwargs["category_contact_default"] == ["binary_sensor.door"]
        assert kwargs["category_plug_default"] == ["switch.kettle"]
        assert kwargs["category_light_default"] == ["light.hall"]
        assert kwargs["motion_debounce_seconds_default"] == 45
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_config_flow.py::TestCategoryFields -q`
Expected: FAIL (schema keys missing; overlap not rejected; prefill kwargs missing)

- [ ] **Step 3: Implement config flow changes**

In `config_flow.py`:

(a) Extend the `.const` import block with:

```python
    CONF_CATEGORY_CONTACT,
    CONF_CATEGORY_LIGHT,
    CONF_CATEGORY_MOTION,
    CONF_CATEGORY_PLUG,
    CONF_MOTION_DEBOUNCE_SECONDS,
    DEFAULT_CATEGORY_CONTACT,
    DEFAULT_CATEGORY_LIGHT,
    DEFAULT_CATEGORY_MOTION,
    DEFAULT_CATEGORY_PLUG,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
```

(b) Add below `_validate_track_attribute_overrides`:

```python
_CATEGORY_LIST_KEYS: tuple[str, ...] = (
    CONF_CATEGORY_MOTION,
    CONF_CATEGORY_CONTACT,
    CONF_CATEGORY_PLUG,
    CONF_CATEGORY_LIGHT,
)


def _validate_category_overrides(user_input: dict[str, Any]) -> str | None:
    """Return an error key if an entity appears in more than one category list."""
    seen: set[str] = set()
    for key in _CATEGORY_LIST_KEYS:
        current = set(user_input.get(key) or [])
        if current & seen:
            return "category_overlap"
        seen |= current
    return None
```

(c) Add keyword parameters to `_build_data_schema` after `track_attributes_exclude_default`:

```python
    category_motion_default: list[str] | None = None,
    category_contact_default: list[str] | None = None,
    category_plug_default: list[str] | None = None,
    category_light_default: list[str] | None = None,
    motion_debounce_seconds_default: int = DEFAULT_MOTION_DEBOUNCE_SECONDS,
```

(d) In the `schema_dict` literal, directly after the `CONF_TRACK_ATTRIBUTES_EXCLUDE` entry, add:

```python
        vol.Optional(
            CONF_CATEGORY_MOTION,
            default=list(category_motion_default or DEFAULT_CATEGORY_MOTION),
        ): EntitySelector(EntitySelectorConfig(multiple=True)),
        vol.Optional(
            CONF_CATEGORY_CONTACT,
            default=list(category_contact_default or DEFAULT_CATEGORY_CONTACT),
        ): EntitySelector(EntitySelectorConfig(multiple=True)),
        vol.Optional(
            CONF_CATEGORY_PLUG,
            default=list(category_plug_default or DEFAULT_CATEGORY_PLUG),
        ): EntitySelector(EntitySelectorConfig(multiple=True)),
        vol.Optional(
            CONF_CATEGORY_LIGHT,
            default=list(category_light_default or DEFAULT_CATEGORY_LIGHT),
        ): EntitySelector(EntitySelectorConfig(multiple=True)),
        vol.Required(
            CONF_MOTION_DEBOUNCE_SECONDS, default=motion_debounce_seconds_default
        ): NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=600,
                step=10,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="seconds",
            )
        ),
```

(e) In **both** `async_step_user` and `async_step_init`, extend the validation chain. After the line

```python
            elif (override_error := _validate_track_attribute_overrides(user_input)):
                errors["base"] = override_error
```

add:

```python
            elif (category_error := _validate_category_overrides(user_input)):
                errors["base"] = category_error
```

(f) In `async_step_init`, change the normalisation loop to cover the category lists:

```python
                for key in (
                    CONF_TRACK_ATTRIBUTES_INCLUDE,
                    CONF_TRACK_ATTRIBUTES_EXCLUDE,
                    *_CATEGORY_LIST_KEYS,
                ):
                    if not user_input.get(key):
                        updated_data[key] = []
```

(g) In `async_step_init`, after `current_correlation_window = ...` add:

```python
        current_category_motion = self._config_entry.data.get(
            CONF_CATEGORY_MOTION, DEFAULT_CATEGORY_MOTION
        )
        current_category_contact = self._config_entry.data.get(
            CONF_CATEGORY_CONTACT, DEFAULT_CATEGORY_CONTACT
        )
        current_category_plug = self._config_entry.data.get(
            CONF_CATEGORY_PLUG, DEFAULT_CATEGORY_PLUG
        )
        current_category_light = self._config_entry.data.get(
            CONF_CATEGORY_LIGHT, DEFAULT_CATEGORY_LIGHT
        )
        current_motion_debounce_seconds = self._config_entry.data.get(
            CONF_MOTION_DEBOUNCE_SECONDS, DEFAULT_MOTION_DEBOUNCE_SECONDS
        )
```

and pass them into `_build_data_schema(...)`:

```python
            category_motion_default=current_category_motion,
            category_contact_default=current_category_contact,
            category_plug_default=current_category_plug,
            category_light_default=current_category_light,
            motion_debounce_seconds_default=current_motion_debounce_seconds,
```

- [ ] **Step 4: Update translations**

In `custom_components/behaviour_monitor/translations/en.json`, in **both** `config.step.user` and `options.step.init`:

Add to `data`:

```json
          "category_motion": "Motion sensors",
          "category_contact": "Contact sensors",
          "category_plug": "Plugs and switches",
          "category_light": "Lights",
          "motion_debounce_seconds": "Motion debounce window"
```

Add to `data_description`:

```json
          "category_motion": "Force these entities into the motion category. Motion is inferred automatically from the motion, occupancy and presence device classes; use this list to correct it.",
          "category_contact": "Force these entities into the contact category. Contact is inferred from door, window, opening and garage door device classes.",
          "category_plug": "Force these entities into the plug category. Plugs are inferred from the outlet and plug device classes and the switch domain. Plug alerts carry half weight in the welfare status.",
          "category_light": "Force these entities into the light category. Lights are inferred from the light domain. Light alerts carry half weight in the welfare status.",
          "motion_debounce_seconds": "Motion sensors only count when they turn on, and repeated triggers within this many seconds are merged into one activity. 0 disables merging."
```

Add to both `error` objects:

```json
      "category_overlap": "An entity cannot be in more than one category list."
```

Validate: `python -c "import json; json.load(open('custom_components/behaviour_monitor/translations/en.json'))"`.

- [ ] **Step 5: Run the full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1 && ruff check custom_components/behaviour_monitor/config_flow.py`
Expected: all pass, no new ruff findings.

- [ ] **Step 6: Commit**

```bash
git add custom_components/behaviour_monitor/config_flow.py custom_components/behaviour_monitor/translations/en.json tests/test_config_flow.py
git commit -m "feat: config flow fields for entity categories and motion debounce"
```

---

### Task 9: Migration v10 → v11 and version bump

**Files:**
- Modify: `custom_components/behaviour_monitor/__init__.py`
- Modify: `custom_components/behaviour_monitor/const.py` (`STORAGE_VERSION = 11`)
- Modify: `custom_components/behaviour_monitor/config_flow.py` (`VERSION = 11`)
- Test: `tests/test_init.py`, `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `CONF_CATEGORY_*`, `CONF_MOTION_DEBOUNCE_SECONDS`, `CONF_REBOOTSTRAP_MOTION`, `DEFAULT_*`.

- [ ] **Step 1: Update existing version assertions and write the new migration tests**

Run this script from the repo root to update existing assertions (it bumps every "final version" check from 10 to 11, renames the `_10` tests, bumps chained call counts by one, and rewrites the v10 no-op test):

```bash
source venv/bin/activate && python3 - <<'EOF'
import re
p = "tests/test_init.py"
s = open(p).read()

# final-version assertions
s = s.replace('assert last_call[1]["version"] == 10', 'assert last_call[1]["version"] == 11')
s = s.replace('assert last_call.kwargs.get("version") == 10 or last_call[1].get("version") == 10',
              'assert last_call.kwargs.get("version") == 11 or last_call[1].get("version") == 11')
s = s.replace('        version = last_call.kwargs.get("version") or last_call[1].get("version")\n        assert version == 10',
              '        version = last_call.kwargs.get("version") or last_call[1].get("version")\n        assert version == 11')

# constants tests
s = s.replace('''    def test_storage_version_is_10(self) -> None:
        """Test that STORAGE_VERSION equals 10 after per-entity track_attributes bump."""
        assert STORAGE_VERSION == 10''',
'''    def test_storage_version_is_11(self) -> None:
        """Test that STORAGE_VERSION equals 11 after entity categories bump."""
        assert STORAGE_VERSION == 11''')
s = s.replace('''    def test_config_flow_version_is_10(self) -> None:
        """BehaviourMonitorConfigFlow.VERSION should be 10 after per-entity track_attributes bump."""
        from custom_components.behaviour_monitor.config_flow import BehaviourMonitorConfigFlow
        assert BehaviourMonitorConfigFlow.VERSION == 10''',
'''    def test_config_flow_version_is_11(self) -> None:
        """BehaviourMonitorConfigFlow.VERSION should be 11 after entity categories bump."""
        from custom_components.behaviour_monitor.config_flow import BehaviourMonitorConfigFlow
        assert BehaviourMonitorConfigFlow.VERSION == 11''')

# chained test names
s = s.replace('async def test_migrate_v2_updates_version_to_10(self) -> None:\n        """Migration from v2 ends at version=10 (v2->v3->v4->v5->v6->v7->v8->v9->v10)."""',
              'async def test_migrate_v2_updates_version_to_11(self) -> None:\n        """Migration from v2 ends at version=11 (v2->...->v10->v11)."""')
s = s.replace('async def test_migrate_v4_updates_version_to_10(self) -> None:\n        """Migration from v4 ends at version=10 (v4->v5->v6->v7->v8->v9->v10)."""',
              'async def test_migrate_v4_updates_version_to_11(self) -> None:\n        """Migration from v4 ends at version=11 (v4->...->v10->v11)."""')

# chained call counts: each +1 (there is one more migration step)
for old, new in ((8, 9), (7, 8), (6, 7), (5, 6), (4, 5), (3, 4), (2, 3)):
    s = s.replace(f"async_update_entry.call_count == {old}\n", f"async_update_entry.call_count == {new}\n")

# v9->v10 bump test: last call is now v11
s = s.replace('''        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        version = call_args.kwargs.get("version") or call_args[1].get("version")
        assert version == 10
''', '''        assert result is True
        assert hass.config_entries.async_update_entry.call_count == 2
        v10_call = hass.config_entries.async_update_entry.call_args_list[0]
        version = v10_call.kwargs.get("version") or v10_call[1].get("version")
        assert version == 10
        last_call = hass.config_entries.async_update_entry.call_args
        version = last_call.kwargs.get("version") or last_call[1].get("version")
        assert version == 11
''')

# v9->v10 "adds override lists" and "preserves lists" read the last call; point them at index 0
s = s.replace('''        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_TRACK_ATTRIBUTES_INCLUDE] == []
        assert updated_data[CONF_TRACK_ATTRIBUTES_EXCLUDE] == []''',
'''        assert result is True
        v10_call = hass.config_entries.async_update_entry.call_args_list[0]
        updated_data = v10_call.kwargs.get("data") or v10_call[1].get("data")
        assert updated_data[CONF_TRACK_ATTRIBUTES_INCLUDE] == []
        assert updated_data[CONF_TRACK_ATTRIBUTES_EXCLUDE] == []''')
s = s.replace('''        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_TRACK_ATTRIBUTES_INCLUDE] == ["binary_sensor.door"]
        assert updated_data[CONF_TRACK_ATTRIBUTES_EXCLUDE] == ["binary_sensor.pir"]''',
'''        assert result is True
        v10_call = hass.config_entries.async_update_entry.call_args_list[0]
        updated_data = v10_call.kwargs.get("data") or v10_call[1].get("data")
        assert updated_data[CONF_TRACK_ATTRIBUTES_INCLUDE] == ["binary_sensor.door"]
        assert updated_data[CONF_TRACK_ATTRIBUTES_EXCLUDE] == ["binary_sensor.pir"]''')

# v10 no-op becomes "v10 continues to v11"; new V10ToV11 class appended after it
old_noop = '''    @pytest.mark.asyncio
    async def test_migrate_v10_is_noop(self) -> None:
        """A v10 config entry is not re-migrated — async_update_entry is not called."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=10,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_TRACK_ATTRIBUTES_INCLUDE: [],
                CONF_TRACK_ATTRIBUTES_EXCLUDE: [],
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_not_called()
'''
new_block = '''    @pytest.mark.asyncio
    async def test_migrate_v10_preserves_track_attribute_lists(self) -> None:
        """A v10 entry continues to v11 without touching the track_attributes lists."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=10,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_TRACK_ATTRIBUTES_INCLUDE: ["a.b"],
                CONF_TRACK_ATTRIBUTES_EXCLUDE: [],
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_TRACK_ATTRIBUTES_INCLUDE] == ["a.b"]


class TestMigrateEntryV10ToV11:
    """Tests for v10->v11 migration (entity categories + motion debounce)."""

    def _make_config_entry(self, version: int, data: dict) -> MagicMock:
        """Create a mock config entry with given version and data."""
        entry = MagicMock()
        entry.version = version
        entry.data = data
        return entry

    @pytest.mark.asyncio
    async def test_migrate_v10_to_v11_seeds_defaults_and_flag(self) -> None:
        """Migration from v10 adds empty category lists, debounce default and rebootstrap flag."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=10,
            data={"monitored_entities": ["sensor.test"]},
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_MOTION] == []
        assert updated_data[CONF_CATEGORY_CONTACT] == []
        assert updated_data[CONF_CATEGORY_PLUG] == []
        assert updated_data[CONF_CATEGORY_LIGHT] == []
        assert updated_data[CONF_MOTION_DEBOUNCE_SECONDS] == DEFAULT_MOTION_DEBOUNCE_SECONDS
        assert updated_data[CONF_REBOOTSTRAP_MOTION] is True
        version = call_args.kwargs.get("version") or call_args[1].get("version")
        assert version == 11

    @pytest.mark.asyncio
    async def test_migrate_v10_to_v11_preserves_existing_values(self) -> None:
        """Migration from v10 keeps category lists and debounce already present."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(
            version=10,
            data={
                "monitored_entities": ["sensor.test"],
                CONF_CATEGORY_MOTION: ["binary_sensor.pir"],
                CONF_MOTION_DEBOUNCE_SECONDS: 30,
            },
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        updated_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert updated_data[CONF_CATEGORY_MOTION] == ["binary_sensor.pir"]
        assert updated_data[CONF_MOTION_DEBOUNCE_SECONDS] == 30

    @pytest.mark.asyncio
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
assert old_noop in s, "v10 noop test not found"
s = s.replace(old_noop, new_block, 1)

# imports
s = s.replace(
    "    CONF_ACTIVITY_TIER_OVERRIDE,\n    CONF_ALERT_REPEAT_INTERVAL,\n",
    "    CONF_ACTIVITY_TIER_OVERRIDE,\n    CONF_ALERT_REPEAT_INTERVAL,\n    CONF_CATEGORY_CONTACT,\n    CONF_CATEGORY_LIGHT,\n    CONF_CATEGORY_MOTION,\n    CONF_CATEGORY_PLUG,\n",
    1,
)
s = s.replace(
    "    CONF_MIN_INACTIVITY_MULTIPLIER,\n    CONF_TRACK_ATTRIBUTES,\n",
    "    CONF_MIN_INACTIVITY_MULTIPLIER,\n    CONF_MOTION_DEBOUNCE_SECONDS,\n    CONF_REBOOTSTRAP_MOTION,\n    CONF_TRACK_ATTRIBUTES,\n",
    1,
)
s = s.replace(
    "    DEFAULT_MIN_INACTIVITY_MULTIPLIER,\n    DEFAULT_TRACK_ATTRIBUTES,\n)",
    "    DEFAULT_MIN_INACTIVITY_MULTIPLIER,\n    DEFAULT_MOTION_DEBOUNCE_SECONDS,\n    DEFAULT_TRACK_ATTRIBUTES,\n)",
    1,
)
open(p, "w").write(s)

p = "tests/test_config_flow.py"
s = open(p).read()
old = '''    async def test_version_is_10(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        """Test VERSION is 10 after per-entity track_attributes override additions."""
        assert config_flow.VERSION == 10'''
new = '''    async def test_version_is_11(self, config_flow: BehaviourMonitorConfigFlow) -> None:
        """Test VERSION is 11 after entity category additions."""
        assert config_flow.VERSION == 11'''
assert old in s
open(p, "w").write(s.replace(old, new, 1))
print("ok")
EOF
```

Then verify no stragglers:

```bash
grep -n "== 10$\|VERSION = 10\|is_10\|to_10\b" tests/test_init.py tests/test_config_flow.py
```

Expected: only lines inside `TestMigrateEntryV9ToV10` that assert the *intermediate* v10 call (`assert version == 10` on `v10_call`). Nothing else.

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_init.py tests/test_config_flow.py -q 2>&1 | tail -3`
Expected: many FAIL (version still 10, no v11 step).

- [ ] **Step 3: Implement the migration and bump versions**

`const.py`: change `STORAGE_VERSION: Final = 10` to `STORAGE_VERSION: Final = 11`.

`config_flow.py`: change `VERSION = 10` to `VERSION = 11`.

`__init__.py`: extend the `.const` import block with

```python
    CONF_CATEGORY_CONTACT,
    CONF_CATEGORY_LIGHT,
    CONF_CATEGORY_MOTION,
    CONF_CATEGORY_PLUG,
    CONF_MOTION_DEBOUNCE_SECONDS,
    CONF_REBOOTSTRAP_MOTION,
    DEFAULT_CATEGORY_CONTACT,
    DEFAULT_CATEGORY_LIGHT,
    DEFAULT_CATEGORY_MOTION,
    DEFAULT_CATEGORY_PLUG,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
```

and add after the `if config_entry.version < 10:` block, before `return True`:

```python
    if config_entry.version < 11:
        new_data = dict(config_entry.data)
        new_data.setdefault(CONF_CATEGORY_MOTION, list(DEFAULT_CATEGORY_MOTION))
        new_data.setdefault(CONF_CATEGORY_CONTACT, list(DEFAULT_CATEGORY_CONTACT))
        new_data.setdefault(CONF_CATEGORY_PLUG, list(DEFAULT_CATEGORY_PLUG))
        new_data.setdefault(CONF_CATEGORY_LIGHT, list(DEFAULT_CATEGORY_LIGHT))
        new_data.setdefault(CONF_MOTION_DEBOUNCE_SECONDS, DEFAULT_MOTION_DEBOUNCE_SECONDS)
        # One-shot: the coordinator rebuilds motion routines with debounce
        # from recorder history on its next setup, then clears this flag.
        new_data[CONF_REBOOTSTRAP_MOTION] = True
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=11)
        _LOGGER.info(
            "Behaviour Monitor: Config entry migrated to v11 — "
            "entity categories and motion debounce added"
        )
```

- [ ] **Step 4: Run the full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q | tail -1`
Expected: all pass. If a chained test still fails on `call_count`, inspect that one test and add one to its expected count (a new migration step ran).

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/__init__.py custom_components/behaviour_monitor/const.py custom_components/behaviour_monitor/config_flow.py tests/test_init.py tests/test_config_flow.py
git commit -m "feat: migrate config entries to v11 with category defaults and motion re-bootstrap flag"
```

---

### Task 10: Docs, planning files, final verification and PR

**Files:**
- Modify: `README.md`, `.planning/PROJECT.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`

- [ ] **Step 1: README configuration table**

In `README.md` under `### Configuration Options`, append these rows to the table after the "Never track attribute changes for" row:

```markdown
| Motion sensors | Force these entities into the motion category (auto-inferred from motion/occupancy/presence device class) | Empty |
| Contact sensors | Force these entities into the contact category (auto-inferred from door/window/opening/garage door device class) | Empty |
| Plugs and switches | Force these entities into the plug category (auto-inferred from outlet/plug device class or the switch domain) | Empty |
| Lights | Force these entities into the light category (auto-inferred from the light domain) | Empty |
| Motion debounce window | Merge repeated motion triggers within this many seconds into one activity; 0 disables (0–600) | 120 seconds |
```

- [ ] **Step 2: README "Entity Categories" section**

Insert a new `### Entity Categories` subsection under `## How It Works`, directly before `### Acute Detection`:

```markdown
### Entity Categories

Each monitored entity is assigned a category at startup so that noisy devices and automated devices are treated appropriately.

**Inference order** (first match wins):

1. The entity is in one of the four category override lists.
2. Its entity-registry device class: `motion`, `occupancy`, `presence` → motion; `door`, `window`, `opening`, `garage_door` → contact; `outlet`, `plug` → plug.
3. Its domain: `switch` → plug; `light` → light; anything else → other.

Numeric entities are always "other". The inferred category is shown as the `category` attribute on each entry of the `entity_status_summary` sensor.

**Motion debounce.** Motion entities only count when they turn *on*, and repeated triggers within the debounce window (default 2 minutes) are merged into a single activity. The learned routine, correlation detection and daily count all see the debounced stream; the entity's last-seen time still updates on every raw transition so inactivity detection is not delayed. Recorder history is debounced the same way on first install, and existing installs rebuild their motion baselines from recorder history when upgrading to v5.0.

**Weighted welfare.** The welfare status is derived from the highest-scoring active alert, where score = severity points × category weight:

| Category | Weight | Rationale |
|---|---|---|
| motion | 1.0 | Direct evidence of presence |
| other | 1.0 | Unchanged from previous versions |
| contact | 0.8 | Strong but sparser evidence |
| plug | 0.5 | Often driven by automations |
| light | 0.5 | Often driven by automations |

Severity points are LOW 1, MEDIUM 2, HIGH 3. A score of 2.25 or more gives `alert`, 1.25 or more gives `concern`, anything else gives `check_recommended`. In practice motion, contact and other behave as before; a plug or light alert alone tops out at `concern`. Individual alert severities and notifications are not affected.
```

- [ ] **Step 3: README upgrade note and troubleshooting**

Under `### Upgrading`, change `(v2 through v9)` to `(v2 through v11)` and append to the notable migrations list:

```markdown
- **v10**: Added per-entity track_attributes override lists
- **v11**: Added entity category override lists and motion debounce window; motion baselines are rebuilt from recorder history once after upgrade
```

Under `## Troubleshooting`, add a new subsection after `### Activity Not Being Tracked`:

```markdown
### Motion Sensor Generates Too Many or Too Few Activities

- Check the `category` attribute on `entity_status_summary` shows `motion`. If not, add the entity to the "Motion sensors" list.
- Increase the "Motion debounce window" if a single walk through a room still produces several activities; decrease it (or set 0) if genuinely separate visits are being merged.
- After changing the window, the learned routine adapts as the history window rolls over.
```

- [ ] **Step 4: Planning files**

`.planning/ROADMAP.md`: add a milestone line after the v4.0 line in the `## Milestones` list:

```markdown
- ✅ **v5.0 Entity Categories** — Phases 21-23 (shipped 2026-09-18)
```

and a details block after the v4.0 block:

```markdown
<details>
<summary>✅ v5.0 Entity Categories (Phases 21-23) — SHIPPED 2026-09-18</summary>

- [x] Phase 21: Category Inference and Motion Debounce (entity_category.py, coordinator wiring) — completed 2026-09-18
- [x] Phase 22: Weighted Welfare (category-weighted status derivation) — completed 2026-09-18
- [x] Phase 23: Config, Migration v11 and Motion Re-bootstrap — completed 2026-09-18

</details>
```

and three rows at the end of the `## Progress` table:

```markdown
| 21. Category Inference and Motion Debounce | v5.0 | 1/1 | Complete | 2026-09-18 |
| 22. Weighted Welfare | v5.0 | 1/1 | Complete | 2026-09-18 |
| 23. Config, Migration v11 and Motion Re-bootstrap | v5.0 | 1/1 | Complete | 2026-09-18 |
```

`.planning/PROJECT.md`:
- In the validated list, after the v4.2 line, add:

```markdown

- ✓ Entity categories (motion/contact/plug/light/other) inferred from device class and domain with per-category override lists — v5.0
- ✓ Motion debounce at ingestion: rising edges only, configurable merge window (default 120s), applied to recorder bootstrap and one-shot re-bootstrap on upgrade — v5.0
- ✓ Category-weighted welfare status (max score, plugs and lights at half weight) with config migration v10→v11 — v5.0
```

- Replace `Shipped v4.2 with ~13,400 LOC` with `Shipped v5.0 with ~14,000 LOC`, `542 tests passing` with the actual count from `pytest --co -q | tail -1`, `Config schema at v10` with `Config schema at v11`.
- In the architecture list, add a line after `acute_detector.py`:

```markdown
- `entity_category.py` — pure-Python entity categorisation, `MotionDebouncer` (rising-edge + merge window), and `derive_weighted_status()` for category-weighted welfare
```

- Update the `config_flow.py` line to start `v11 config with category override lists, motion debounce window, per-entity track_attributes …` and the migration chain to end `→v10→v11`.
- Change the last-updated footer to `*Last updated: 2026-09-18 after v5.0 milestone shipped*`.

`.planning/STATE.md`: set `milestone: v5.0`, `milestone_name: Entity Categories`, `status: shipped`, `stopped_at: v5.0 shipped`, `last_activity: 2026-09-18`; under `## Current Position` set `Phase: 23`, `Status: Shipped`, `Progress: [██████████] 100% (3/3 v5.0 phases)`; under `### Decisions` add:

```markdown
- [v5.0]: Category lives in entity_category.py (pure Python); coordinator supplies registry device classes and numeric-ness
- [v5.0]: Welfare uses max weighted score, not sum; plugs/lights 0.5, contact 0.8, motion/other 1.0
- [v5.0]: Motion debounce default 120s, on by default; last_seen updates on raw events, model/correlation/daily count on debounced events
- [v5.0]: Upgrade re-bootstraps motion routines from recorder via one-shot rebootstrap_motion entry flag
```

- [ ] **Step 5: Final verification**

```bash
source venv/bin/activate
python -m pytest tests/ -q | tail -1
ruff check custom_components tests | tail -1
mypy --no-incremental custom_components 2>&1 | grep -c error
git stash -q && ruff check custom_components tests | tail -1 && mypy --no-incremental custom_components 2>&1 | grep -c error; git stash pop -q
```

Expected: all tests pass; ruff summary and mypy error count are identical with and without the working-tree changes (i.e. no new findings). Fix any new findings before committing.

- [ ] **Step 6: Commit with the major-bump marker**

```bash
git add README.md .planning/PROJECT.md .planning/ROADMAP.md .planning/STATE.md
git commit -m "feat!: entity categories, motion debounce and weighted welfare (v5.0)

BREAKING CHANGE: welfare status is now derived from category-weighted alert
scores. Alerts from plugs and lights alone can no longer raise the status to
'alert'. Motion sensors are debounced at ingestion by default (120s) and
existing motion baselines are rebuilt from recorder history on upgrade.
Config entry version 11."
```

- [ ] **Step 7: Push and open the PR**

```bash
git push -u https://github.com/andrewmichael/behaviour-monitor.git feat/entity-categories
git update-ref refs/remotes/origin/feat/entity-categories HEAD
git branch --set-upstream-to=origin/feat/entity-categories
gh pr create --base main --head feat/entity-categories \
  --title "feat!: entity categories, motion debounce and weighted welfare (v5.0)" \
  --body "$(cat <<'EOF'
## Summary
- New `entity_category.py`: categorise monitored entities as motion / contact / plug / light / other from device class and domain, with four override lists in the config flow.
- Motion sensors are debounced at ingestion: rising edges only, merged within a configurable window (default 120 s). Recorder bootstrap applies the same debounce; upgrading installs re-bootstrap motion routines once.
- Welfare status is now derived from category-weighted alert scores (max, not sum). Plugs and lights carry half weight; motion, contact and other are unchanged in practice.
- Config entry version 11 with migration. Category exposed as `category` attribute on `entity_status_summary`.

Spec: `docs/superpowers/specs/2026-09-18-entity-categories-design.md`
Plan: `docs/superpowers/plans/2026-09-18-entity-categories.md`

## Test plan
- [x] `make test` green (see plan Task 10 for count)
- [x] ruff and mypy identical to `main`
- [ ] Manual: upgrade a v10 entry in a live HA instance, confirm the four category lists and debounce window appear, `category` attribute is populated, and the log shows the motion re-bootstrap message once

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage.**
- §1 inference order, override lists, numeric→OTHER, config keys, VERSION 11, `category` attribute → Tasks 1, 2, 5, 8, 9. ✓
- §2 debounce rule, `MotionDebouncer` shape, placement (last_seen before decision), non-motion passthrough → Tasks 3, 5. ✓
- §3 scoring table, thresholds, max-not-sum, constants in `const.py`, unchanged fields → Tasks 1, 4, 6. ✓
- §4 migration seeds + flag, re-bootstrap clears motion routines and correlation counts but keeps CUSUM and last_seen, recorder-unavailable path still clears flag, bootstrap accepts entity subset and uses a private debouncer → Tasks 7, 9. ✓
- §5 README, translations, PROJECT/ROADMAP → Tasks 8, 10. ✓
- §6 every listed test group has a concrete test in Tasks 1–9. ✓

**Placeholder scan.** No TBD/TODO. Every code step has code. The only "may already pass" note is in Task 6 Step 2, which is a factual statement about pre-existing behaviour, not a placeholder.

**Type consistency.**
- `MotionDebouncer.should_count(entity_id, is_motion, old_state, new_state, timestamp)` used identically in Tasks 3, 5, 7. ✓
- `infer_categories(entity_ids, overrides, device_classes, numeric_entities)` used identically in Tasks 2, 5. ✓
- `derive_weighted_status(alerts, categories) -> (status, recommendation)` used identically in Tasks 4, 6. ✓
- `_bootstrap_from_recorder(entity_ids=None)` used identically in Tasks 7 tests and implementation. ✓
- `_build_data_schema` kwargs `category_*_default`, `motion_debounce_seconds_default` match between Task 8 tests and implementation. ✓
- `const.py` now imports `AlertSeverity` from `alert_result.py`; `alert_result.py` has no `const` import, so no cycle. `entity_category.py` imports from both; `coordinator.py` imports `entity_category`. ✓
