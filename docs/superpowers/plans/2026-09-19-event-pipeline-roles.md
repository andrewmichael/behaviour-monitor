# Event Pipeline and Roles (v5.3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace entity categories with semantic roles inferred from Home Assistant areas, and replace the motion debouncer with a pure, replayable activity pipeline (retrigger collapse, per-kind debounce, door open-duration classes, exterior-door excursions).

**Architecture:** `entity_role.py` (pure) infers an `EntityRole` per entity from panic list, override map, exterior-door list, device class and area name. `pipeline.py` (pure) turns gated state events into `ActivityEvent`s. The coordinator feeds the pipeline from the existing `EventGate`, consumes activity events uniformly, and uses `replay()` for recorder bootstrap. Config entry v14 migrates the four category lists into an override map and re-bootstraps door and appliance baselines once.

**Tech Stack:** Python 3.9 (venv), Home Assistant custom integration, pytest with mocked HA (`tests/conftest.py`), black (88), ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-19-event-pipeline-roles-design.md`

## Global Constraints

- Python 3.9 compatible: `from __future__ import annotations` in every module; no `match`; no runtime `X | Y` in `isinstance`.
- `entity_role.py`, `pipeline.py` and `scripts/replay.py` import nothing from Home Assistant.
- Roles replace categories entirely; `EntityCategory`, `CATEGORY_WEIGHT`, `MotionDebouncer` and `entity_category.py` are deleted in Task 6.
- Every threshold is a config key with a default in `const.py`; zero disables the stage it names.
- Config entry `VERSION = 14`; `STORAGE_VERSION = 14`; `_async_migrate_func` still passes data through.
- Keep `CONF_CATEGORY_PANIC` and `CONF_MOTION_DEBOUNCE_SECONDS` keys unchanged.
- `last_seen` is set by the coordinator before the pipeline sees an event; nothing in the pipeline may suppress it.
- Tests run with `venv/bin/python -m pytest tests/ -q`; lint with `venv/bin/python -m ruff check custom_components/ tests/` and `venv/bin/python -m black --check custom_components/ tests/` must show no *new* failures versus `main` (the repo has pre-existing long lines that black would reflow; run black only on files you create).
- Commit after every task with a conventional-commit message ending in the attribution line `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
|---|---|
| `custom_components/behaviour_monitor/const.py` | `EntityRole`, `ROLE_KINDS`, `KIND_WEIGHT`, `AREA_ROLE_KEYWORDS`, door-open class names, new config keys and defaults, `CONF_REBOOTSTRAP_ROLES`, version bumps |
| `custom_components/behaviour_monitor/entity_role.py` (new, replaces `entity_category.py`) | `role_for_area`, `parse_role_overrides`, `infer_roles`, `derive_weighted_status` |
| `custom_components/behaviour_monitor/pipeline.py` (new) | `PipelineConfig`, `PipelineEvent`, `ActivityEvent`, `ActivityPipeline`, `classify_open_duration`, `replay` |
| `custom_components/behaviour_monitor/coordinator.py` | roles map, area names, pipeline wiring, activity consumption, bootstrap via `replay`, role re-bootstrap, role repair issue, status attributes |
| `custom_components/behaviour_monitor/config_flow.py` | new fields, `_validate_roles`, `VERSION = 14` |
| `custom_components/behaviour_monitor/__init__.py` | v13 → v14 migration, `exterior_doors_unconfirmed` issue |
| `custom_components/behaviour_monitor/translations/en.json` | field labels, errors, issue texts |
| `scripts/replay.py` (new) | CLI over `replay()` |
| `tests/test_entity_role.py` (new, replaces `tests/test_entity_category.py`) | role inference and parsing |
| `tests/test_pipeline.py` (new) | pipeline stages and `replay` |
| `tests/fixtures/replay_week.csv` (new) + `tests/test_replay_fixture.py` (new) | synthetic seven-day trace, CLI smoke test |
| `tests/test_coordinator.py`, `tests/test_config_flow.py`, `tests/test_init.py` | updated for roles, pipeline, migration |
| `README.md`, `CLAUDE.md`, `docs/design/2026-09-18-detection-gap-analysis.md` | docs |

---

### Task 1: Role constants and config keys

**Files:**
- Modify: `custom_components/behaviour_monitor/const.py:66-90` (config keys), `:269-297` (category block)
- Create: `tests/test_entity_role.py`

**Interfaces:**
- Produces: `EntityRole` enum (values in spec §1.1) with `.kind` property and `EntityRole.from_string(value)`; `ROLE_KINDS: frozenset[str]`; `KIND_WEIGHT: dict[str, float]`; `AREA_ROLE_KEYWORDS: tuple[tuple[EntityRole, tuple[str, ...]], ...]`; `DOOR_OPEN_BRIEF/EXTENDED/PROLONGED: str`; `CONF_EXTERIOR_DOORS`, `CONF_ROLE_OVERRIDES`, `CONF_DOOR_DEBOUNCE_SECONDS`, `CONF_RETRIGGER_COLLAPSE_SECONDS`, `CONF_EXCURSION_WINDOW_SECONDS`, `CONF_DOOR_OPEN_EXTENDED_SECONDS`, `CONF_DOOR_OPEN_PROLONGED_SECONDS`, `CONF_REBOOTSTRAP_ROLES` and matching `DEFAULT_*`.
- `EntityCategory` and `CATEGORY_WEIGHT` stay in place until Task 6.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_entity_role.py`:

```python
"""Tests for entity roles: constants, area lookup, override parsing, inference."""

from __future__ import annotations

import pytest

from custom_components.behaviour_monitor.const import (
    AREA_ROLE_KEYWORDS,
    CONF_DOOR_DEBOUNCE_SECONDS,
    CONF_DOOR_OPEN_EXTENDED_SECONDS,
    CONF_DOOR_OPEN_PROLONGED_SECONDS,
    CONF_EXCURSION_WINDOW_SECONDS,
    CONF_EXTERIOR_DOORS,
    CONF_REBOOTSTRAP_ROLES,
    CONF_RETRIGGER_COLLAPSE_SECONDS,
    CONF_ROLE_OVERRIDES,
    DEFAULT_DOOR_DEBOUNCE_SECONDS,
    DEFAULT_DOOR_OPEN_EXTENDED_SECONDS,
    DEFAULT_DOOR_OPEN_PROLONGED_SECONDS,
    DEFAULT_EXCURSION_WINDOW_SECONDS,
    DEFAULT_EXTERIOR_DOORS,
    DEFAULT_RETRIGGER_COLLAPSE_SECONDS,
    DEFAULT_ROLE_OVERRIDES,
    DOOR_OPEN_BRIEF,
    DOOR_OPEN_EXTENDED,
    DOOR_OPEN_PROLONGED,
    KIND_WEIGHT,
    ROLE_KINDS,
    EntityRole,
)


class TestRoleConstants:
    def test_role_values(self) -> None:
        assert {r.value for r in EntityRole} == {
            "motion.bathroom", "motion.bedroom", "motion.living", "motion.kitchen",
            "motion.transit", "motion.unassigned", "door.exterior", "door.interior",
            "appliance", "panic", "other",
        }

    @pytest.mark.parametrize(
        ("role", "kind"),
        [
            (EntityRole.MOTION_BATHROOM, "motion"),
            (EntityRole.MOTION_UNASSIGNED, "motion"),
            (EntityRole.DOOR_EXTERIOR, "door"),
            (EntityRole.DOOR_INTERIOR, "door"),
            (EntityRole.APPLIANCE, "appliance"),
            (EntityRole.PANIC, "panic"),
            (EntityRole.OTHER, "other"),
        ],
    )
    def test_kind(self, role: EntityRole, kind: str) -> None:
        assert role.kind == kind

    def test_from_string(self) -> None:
        assert EntityRole.from_string("door.exterior") is EntityRole.DOOR_EXTERIOR
        with pytest.raises(ValueError):
            EntityRole.from_string("door.side")

    def test_kinds_and_weights(self) -> None:
        assert ROLE_KINDS == frozenset({"motion", "door", "appliance", "panic", "other"})
        assert KIND_WEIGHT == {"motion": 1.0, "door": 0.8, "appliance": 0.5, "other": 1.0}

    def test_area_keywords_cover_every_room_role(self) -> None:
        roles = [role for role, _ in AREA_ROLE_KEYWORDS]
        assert roles == [
            EntityRole.MOTION_BATHROOM, EntityRole.MOTION_BEDROOM, EntityRole.MOTION_LIVING,
            EntityRole.MOTION_KITCHEN, EntityRole.MOTION_TRANSIT,
        ]
        for _, keywords in AREA_ROLE_KEYWORDS:
            assert keywords and all(k == k.lower() for k in keywords)

    def test_open_classes(self) -> None:
        assert (DOOR_OPEN_BRIEF, DOOR_OPEN_EXTENDED, DOOR_OPEN_PROLONGED) == ("brief", "extended", "prolonged")

    def test_config_keys_and_defaults(self) -> None:
        assert CONF_EXTERIOR_DOORS == "exterior_doors"
        assert CONF_ROLE_OVERRIDES == "role_overrides"
        assert CONF_DOOR_DEBOUNCE_SECONDS == "door_debounce_seconds"
        assert CONF_RETRIGGER_COLLAPSE_SECONDS == "retrigger_collapse_seconds"
        assert CONF_EXCURSION_WINDOW_SECONDS == "excursion_window_seconds"
        assert CONF_DOOR_OPEN_EXTENDED_SECONDS == "door_open_extended_seconds"
        assert CONF_DOOR_OPEN_PROLONGED_SECONDS == "door_open_prolonged_seconds"
        assert CONF_REBOOTSTRAP_ROLES == "rebootstrap_roles"
        assert DEFAULT_EXTERIOR_DOORS == []
        assert DEFAULT_ROLE_OVERRIDES == ""
        assert DEFAULT_DOOR_DEBOUNCE_SECONDS == 60
        assert DEFAULT_RETRIGGER_COLLAPSE_SECONDS == 5
        assert DEFAULT_EXCURSION_WINDOW_SECONDS == 60
        assert DEFAULT_DOOR_OPEN_EXTENDED_SECONDS == 15
        assert DEFAULT_DOOR_OPEN_PROLONGED_SECONDS == 120
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_entity_role.py -q`
Expected: FAIL with `ImportError: cannot import name 'AREA_ROLE_KEYWORDS'`.

- [ ] **Step 3: Add the constants**

In `const.py`, after the v5.2 defaults block (after `PANIC_LOW_BATTERY_PERCENT`), add:

```python
# New v5.3 config keys (roles + event pipeline)
CONF_EXTERIOR_DOORS: Final = "exterior_doors"
CONF_ROLE_OVERRIDES: Final = "role_overrides"
CONF_DOOR_DEBOUNCE_SECONDS: Final = "door_debounce_seconds"
CONF_RETRIGGER_COLLAPSE_SECONDS: Final = "retrigger_collapse_seconds"
CONF_EXCURSION_WINDOW_SECONDS: Final = "excursion_window_seconds"
CONF_DOOR_OPEN_EXTENDED_SECONDS: Final = "door_open_extended_seconds"
CONF_DOOR_OPEN_PROLONGED_SECONDS: Final = "door_open_prolonged_seconds"
# One-shot flag written by the v14 migration; cleared by the coordinator
# after it re-bootstraps door and appliance entities from recorder history.
CONF_REBOOTSTRAP_ROLES: Final = "rebootstrap_roles"

# New v5.3 defaults
DEFAULT_EXTERIOR_DOORS: Final[list[str]] = []  # door.exterior is never inferred
DEFAULT_ROLE_OVERRIDES: Final = ""  # multiline "entity_id: role-or-kind"
DEFAULT_DOOR_DEBOUNCE_SECONDS: Final = 60  # seconds; 0 disables
DEFAULT_RETRIGGER_COLLAPSE_SECONDS: Final = 5  # seconds; off/on pairs closer than this are noise; 0 disables
DEFAULT_EXCURSION_WINDOW_SECONDS: Final = 60  # seconds; exterior-door events inside this window are one excursion; 0 disables
DEFAULT_DOOR_OPEN_EXTENDED_SECONDS: Final = 15  # open at least this long = "extended"
DEFAULT_DOOR_OPEN_PROLONGED_SECONDS: Final = 120  # open at least this long = "prolonged"
```

Then, in the "Entity categories" block (keep `EntityCategory` and `CATEGORY_WEIGHT` for now; Task 6 removes them), add after `PLUG_DEVICE_CLASSES`:

```python
# ---------------------------------------------------------------------------
# Entity roles and event pipeline (v5.3)
# ---------------------------------------------------------------------------


class EntityRole(Enum):
    """Semantic role of a monitored entity. The part before the dot is its kind."""

    MOTION_BATHROOM = "motion.bathroom"
    MOTION_BEDROOM = "motion.bedroom"
    MOTION_LIVING = "motion.living"
    MOTION_KITCHEN = "motion.kitchen"
    MOTION_TRANSIT = "motion.transit"
    MOTION_UNASSIGNED = "motion.unassigned"  # motion sensor with no recognised area
    DOOR_EXTERIOR = "door.exterior"  # exterior-door list only; never inferred
    DOOR_INTERIOR = "door.interior"  # default for every contact class, windows included
    APPLIANCE = "appliance"
    PANIC = "panic"  # panic list only; instant alert, no learning
    OTHER = "other"

    @property
    def kind(self) -> str:
        return self.value.split(".", 1)[0]

    @classmethod
    def from_string(cls, value: str) -> "EntityRole":
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"unknown role: {value!r}") from None


ROLE_KINDS: Final = frozenset({"motion", "door", "appliance", "panic", "other"})

# Interim welfare weight per kind until v5.4 entropy weighting.
KIND_WEIGHT: Final[dict[str, float]] = {
    "motion": 1.0,
    "door": 0.8,
    "appliance": 0.5,
    "other": 1.0,
}

# Lower-case substrings of a Home Assistant area name that place a motion
# sensor in a room role. First hit in table order wins. English only; other
# languages use the role override map.
AREA_ROLE_KEYWORDS: Final[tuple[tuple[EntityRole, tuple[str, ...]], ...]] = (
    (EntityRole.MOTION_BATHROOM, ("bathroom", "toilet", "ensuite", "en-suite", "shower", "wc", "loo", "cloakroom")),
    (EntityRole.MOTION_BEDROOM, ("bedroom", "bed")),
    (EntityRole.MOTION_LIVING, ("living", "lounge", "sitting", "dining", "study", "office", "conservatory", "snug")),
    (EntityRole.MOTION_KITCHEN, ("kitchen", "utility", "pantry")),
    (EntityRole.MOTION_TRANSIT, ("hall", "landing", "stairs", "stairway", "corridor", "porch", "entrance", "passage")),
)

# Door open-duration classes (pipeline stage 3)
DOOR_OPEN_BRIEF: Final = "brief"
DOOR_OPEN_EXTENDED: Final = "extended"
DOOR_OPEN_PROLONGED: Final = "prolonged"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_entity_role.py -q`
Expected: all pass. Then `venv/bin/python -m pytest tests/ -q` still passes (nothing else changed).

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/const.py tests/test_entity_role.py
git commit -m "feat: entity role constants and v5.3 pipeline config keys

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `entity_role.py` — area lookup, override parsing, inference, kind-weighted welfare

**Files:**
- Create: `custom_components/behaviour_monitor/entity_role.py`
- Modify: `tests/test_entity_role.py`

**Interfaces:**
- Consumes: Task 1 constants; `AlertResult`, `AlertType` from `alert_result.py`; `SEVERITY_POINTS`, `WELFARE_*` from `const.py`.
- Produces:
  - `role_for_area(area_name: str | None) -> EntityRole` (a motion room role or `MOTION_UNASSIGNED`)
  - `parse_role_overrides(text: str) -> dict[str, str]` (entity id → role value or bare kind; raises `ValueError` naming the line; `panic` is rejected in both forms; duplicate entity ids are rejected)
  - `infer_roles(entity_ids, panic, exterior_doors, overrides, device_classes, area_names, numeric_entities=()) -> dict[str, EntityRole]`
  - `derive_weighted_status(alerts, roles: Mapping[str, EntityRole]) -> tuple[str, str]` (same contract as the old category version, weight by `role.kind`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_entity_role.py`:

```python
from datetime import datetime, timezone

from custom_components.behaviour_monitor.alert_result import AlertResult, AlertSeverity, AlertType
from custom_components.behaviour_monitor.const import WELFARE_ALERT, WELFARE_CHECK, WELFARE_CONCERN
from custom_components.behaviour_monitor.entity_role import (
    derive_weighted_status,
    infer_roles,
    parse_role_overrides,
    role_for_area,
)


class TestRoleForArea:
    @pytest.mark.parametrize(
        ("name", "role"),
        [
            ("Bathroom", EntityRole.MOTION_BATHROOM),
            ("Downstairs WC", EntityRole.MOTION_BATHROOM),
            ("Master Bedroom", EntityRole.MOTION_BEDROOM),
            ("Living Room", EntityRole.MOTION_LIVING),
            ("Kitchen", EntityRole.MOTION_KITCHEN),
            ("Upstairs Landing", EntityRole.MOTION_TRANSIT),
            ("Garage", EntityRole.MOTION_UNASSIGNED),
            ("", EntityRole.MOTION_UNASSIGNED),
            (None, EntityRole.MOTION_UNASSIGNED),
        ],
    )
    def test_lookup(self, name: str | None, role: EntityRole) -> None:
        assert role_for_area(name) is role

    def test_table_order_wins_on_double_match(self) -> None:
        # "bed" (bedroom) and "bathroom" both match; bathroom is earlier in the table
        assert role_for_area("Bedroom Bathroom") is EntityRole.MOTION_BATHROOM


class TestParseRoleOverrides:
    def test_parses_roles_kinds_comments_and_blanks(self) -> None:
        text = "\n".join([
            "# exterior doors are listed separately",
            "",
            "binary_sensor.pir_hall: motion.transit",
            "  Binary_Sensor.Study : motion  ",
            "switch.lamp: appliance",
        ])
        assert parse_role_overrides(text) == {
            "binary_sensor.pir_hall": "motion.transit",
            "binary_sensor.study": "motion",
            "switch.lamp": "appliance",
        }

    def test_empty(self) -> None:
        assert parse_role_overrides("") == {}
        assert parse_role_overrides("\n  \n") == {}

    @pytest.mark.parametrize(
        "line",
        [
            "binary_sensor.pir",                 # no colon
            "binary_sensor.pir: motion.garage",  # unknown role
            "binary_sensor.pir: contact",        # old category name is not a kind
            "pir: motion",                       # entity id needs a domain
            "binary_sensor.sos: panic",          # panic only via the panic list
            "binary_sensor.pir: ",               # empty value
        ],
    )
    def test_rejects_bad_lines(self, line: str) -> None:
        with pytest.raises(ValueError) as exc:
            parse_role_overrides("ok.entity: appliance\n" + line)
        assert "line 2" in str(exc.value)

    def test_rejects_duplicate_entity(self) -> None:
        with pytest.raises(ValueError) as exc:
            parse_role_overrides("a.b: motion\na.b: appliance")
        assert "line 2" in str(exc.value)


class TestInferRoles:
    def _infer(self, entity_ids, **kw):
        base = dict(panic=(), exterior_doors=(), overrides={}, device_classes={}, area_names={}, numeric_entities=())
        base.update(kw)
        return infer_roles(entity_ids, **base)

    def test_numeric_is_other_even_when_overridden(self) -> None:
        r = self._infer(["sensor.lux"], overrides={"sensor.lux": "motion.kitchen"}, numeric_entities={"sensor.lux"})
        assert r["sensor.lux"] is EntityRole.OTHER

    def test_panic_list_beats_override(self) -> None:
        r = self._infer(["binary_sensor.sos"], panic=["binary_sensor.sos"], overrides={"binary_sensor.sos": "appliance"})
        assert r["binary_sensor.sos"] is EntityRole.PANIC

    def test_full_role_override_beats_everything_below(self) -> None:
        r = self._infer(
            ["binary_sensor.x"],
            overrides={"binary_sensor.x": "motion.kitchen"},
            device_classes={"binary_sensor.x": "door"},
            area_names={"binary_sensor.x": "Bathroom"},
        )
        assert r["binary_sensor.x"] is EntityRole.MOTION_KITCHEN

    def test_exterior_list(self) -> None:
        r = self._infer(["binary_sensor.front"], exterior_doors=["binary_sensor.front"], device_classes={"binary_sensor.front": "door"})
        assert r["binary_sensor.front"] is EntityRole.DOOR_EXTERIOR

    def test_kind_override_lets_area_fill_room(self) -> None:
        r = self._infer(["sensor.presence"], overrides={"sensor.presence": "motion"}, area_names={"sensor.presence": "Kitchen"})
        assert r["sensor.presence"] is EntityRole.MOTION_KITCHEN

    def test_kind_override_door_is_interior(self) -> None:
        r = self._infer(["sensor.x"], overrides={"sensor.x": "door"})
        assert r["sensor.x"] is EntityRole.DOOR_INTERIOR

    @pytest.mark.parametrize(
        ("eid", "dc", "area", "role"),
        [
            ("binary_sensor.a", "motion", "Bathroom", EntityRole.MOTION_BATHROOM),
            ("binary_sensor.b", "occupancy", "Bedroom", EntityRole.MOTION_BEDROOM),
            ("binary_sensor.c", "presence", None, EntityRole.MOTION_UNASSIGNED),
            ("binary_sensor.d", "door", "Kitchen", EntityRole.DOOR_INTERIOR),
            ("binary_sensor.e", "window", None, EntityRole.DOOR_INTERIOR),
            ("binary_sensor.f", "garage_door", None, EntityRole.DOOR_INTERIOR),
            ("switch.g", "outlet", None, EntityRole.APPLIANCE),
            ("switch.h", None, None, EntityRole.APPLIANCE),
            ("light.i", None, "Kitchen", EntityRole.APPLIANCE),
            ("sensor.j", None, "Kitchen", EntityRole.OTHER),
            ("binary_sensor.k", "smoke", None, EntityRole.OTHER),
        ],
    )
    def test_device_class_and_domain(self, eid, dc, area, role) -> None:
        r = self._infer([eid], device_classes={eid: dc}, area_names={eid: area})
        assert r[eid] is role

    def test_every_entity_gets_a_role(self) -> None:
        r = self._infer(["a.b", "c.d"])
        assert set(r) == {"a.b", "c.d"}


def _alert(entity_id: str, severity: AlertSeverity, alert_type: AlertType = AlertType.INACTIVITY) -> AlertResult:
    return AlertResult(
        entity_id=entity_id, alert_type=alert_type, severity=severity, confidence=1.0,
        explanation="x", timestamp=datetime.now(timezone.utc).isoformat(), details={},
    )


class TestDeriveWeightedStatus:
    roles = {
        "binary_sensor.pir": EntityRole.MOTION_LIVING,
        "binary_sensor.door": EntityRole.DOOR_INTERIOR,
        "switch.kettle": EntityRole.APPLIANCE,
    }

    def test_motion_high_is_alert(self) -> None:
        assert derive_weighted_status([_alert("binary_sensor.pir", AlertSeverity.HIGH)], self.roles)[0] == WELFARE_ALERT

    def test_door_high_is_alert(self) -> None:
        assert derive_weighted_status([_alert("binary_sensor.door", AlertSeverity.HIGH)], self.roles)[0] == WELFARE_ALERT

    def test_appliance_high_is_concern(self) -> None:
        assert derive_weighted_status([_alert("switch.kettle", AlertSeverity.HIGH)], self.roles)[0] == WELFARE_CONCERN

    def test_unknown_entity_weighs_as_other(self) -> None:
        assert derive_weighted_status([_alert("sensor.x", AlertSeverity.MEDIUM)], self.roles)[0] == WELFARE_CONCERN

    def test_max_not_sum(self) -> None:
        alerts = [_alert("switch.kettle", AlertSeverity.HIGH), _alert("switch.kettle", AlertSeverity.HIGH)]
        assert derive_weighted_status(alerts, self.roles)[0] == WELFARE_CONCERN

    def test_panic_and_correlation_ignored(self) -> None:
        alerts = [
            _alert("binary_sensor.pir", AlertSeverity.HIGH, AlertType.PANIC),
            _alert("binary_sensor.pir", AlertSeverity.HIGH, AlertType.CORRELATION_BREAK),
        ]
        assert derive_weighted_status(alerts, self.roles)[0] == WELFARE_CHECK
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_entity_role.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.behaviour_monitor.entity_role'`.

- [ ] **Step 3: Create the module**

Create `custom_components/behaviour_monitor/entity_role.py`:

```python
"""Entity roles: inference from areas, device classes and overrides; weighted welfare.

Pure Python stdlib only. Zero Home Assistant imports. The coordinator supplies
registry device classes, area names and numeric-ness so this module stays
testable in isolation.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping

from .alert_result import AlertResult, AlertType
from .const import (
    AREA_ROLE_KEYWORDS,
    CONTACT_DEVICE_CLASSES,
    KIND_WEIGHT,
    MOTION_DEVICE_CLASSES,
    PLUG_DEVICE_CLASSES,
    ROLE_KINDS,
    SEVERITY_POINTS,
    WELFARE_ALERT,
    WELFARE_ALERT_SCORE,
    WELFARE_CHECK,
    WELFARE_CONCERN,
    WELFARE_CONCERN_SCORE,
    EntityRole,
)

_DOMAIN_KIND: dict[str, str] = {"switch": "appliance", "light": "appliance"}
_OVERRIDE_VALUES: frozenset[str] = frozenset(
    {r.value for r in EntityRole if r is not EntityRole.PANIC} | (ROLE_KINDS - {"panic"})
)


# ---------------------------------------------------------------------------
# Area lookup
# ---------------------------------------------------------------------------


def role_for_area(area_name: str | None) -> EntityRole:
    """Map a Home Assistant area name to a motion room role, or MOTION_UNASSIGNED."""
    if not area_name:
        return EntityRole.MOTION_UNASSIGNED
    name = area_name.lower()
    for role, keywords in AREA_ROLE_KEYWORDS:
        if any(k in name for k in keywords):
            return role
    return EntityRole.MOTION_UNASSIGNED


# ---------------------------------------------------------------------------
# Override map
# ---------------------------------------------------------------------------


def parse_role_overrides(text: str) -> dict[str, str]:
    """Parse ``entity_id: role-or-kind`` lines. Blank lines and ``#`` comments are ignored.

    Raises ``ValueError`` naming the 1-based offending line. ``panic`` is not
    accepted (use the panic list); an entity may appear only once.
    """
    out: dict[str, str] = {}
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"line {n}: expected 'entity_id: role'")
        eid, value = (part.strip().lower() for part in line.split(":", 1))
        if "." not in eid or not eid.split(".", 1)[1]:
            raise ValueError(f"line {n}: {eid!r} is not an entity id")
        if value not in _OVERRIDE_VALUES:
            raise ValueError(f"line {n}: {value!r} is not a role or kind")
        if eid in out:
            raise ValueError(f"line {n}: {eid} appears more than once")
        out[eid] = value
    return out


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def _kind_for_device_class(device_class: str | None) -> str | None:
    if device_class is None:
        return None
    if device_class in MOTION_DEVICE_CLASSES:
        return "motion"
    if device_class in CONTACT_DEVICE_CLASSES:
        return "door"
    if device_class in PLUG_DEVICE_CLASSES:
        return "appliance"
    return None


def infer_roles(
    entity_ids: Iterable[str],
    panic: Iterable[str],
    exterior_doors: Iterable[str],
    overrides: Mapping[str, str],
    device_classes: Mapping[str, str | None],
    area_names: Mapping[str, str | None],
    numeric_entities: Collection[str] = (),
) -> dict[str, EntityRole]:
    """Return a role for every entity id (spec §1.2 precedence)."""
    panic_set = set(panic)
    exterior = set(exterior_doors)
    result: dict[str, EntityRole] = {}
    for eid in entity_ids:
        if eid in numeric_entities:
            result[eid] = EntityRole.OTHER
            continue
        if eid in panic_set:
            result[eid] = EntityRole.PANIC
            continue
        override = overrides.get(eid)
        if override is not None and override not in ROLE_KINDS:
            result[eid] = EntityRole.from_string(override)
            continue
        if eid in exterior:
            result[eid] = EntityRole.DOOR_EXTERIOR
            continue
        kind = override
        if kind is None:
            kind = _kind_for_device_class(device_classes.get(eid))
        if kind is None:
            kind = _DOMAIN_KIND.get(eid.split(".", 1)[0])
        if kind == "motion":
            result[eid] = role_for_area(area_names.get(eid))
        elif kind == "door":
            result[eid] = EntityRole.DOOR_INTERIOR
        elif kind == "appliance":
            result[eid] = EntityRole.APPLIANCE
        else:
            result[eid] = EntityRole.OTHER
    return result


# ---------------------------------------------------------------------------
# Weighted welfare
# ---------------------------------------------------------------------------

_RECOMMENDATION = {
    WELFARE_ALERT: "Immediate welfare check recommended.",
    WELFARE_CONCERN: "Schedule a welfare check soon.",
    WELFARE_CHECK: "Monitor closely.",
}


def _alert_score(alert: AlertResult, roles: Mapping[str, EntityRole]) -> float:
    """Severity points times the kind weight of the alert's entity."""
    kind = roles.get(alert.entity_id, EntityRole.OTHER).kind
    return SEVERITY_POINTS[alert.severity] * KIND_WEIGHT.get(kind, 1.0)


def derive_weighted_status(
    alerts: Iterable[AlertResult],
    roles: Mapping[str, EntityRole],
) -> tuple[str, str]:
    """Return (welfare status, recommendation) from the highest-scoring alert.

    Correlation-break and panic alerts are ignored; panic is handled by the
    coordinator ahead of weighted scoring. The maximum score is used, not the
    sum, so several weak alerts from automated devices cannot compound.
    With no scoring alerts this returns the check_recommended tier.
    """
    top = 0.0
    for alert in alerts:
        if alert.alert_type in (AlertType.CORRELATION_BREAK, AlertType.PANIC):
            continue
        top = max(top, _alert_score(alert, roles))
    if top >= WELFARE_ALERT_SCORE:
        status = WELFARE_ALERT
    elif top >= WELFARE_CONCERN_SCORE:
        status = WELFARE_CONCERN
    else:
        status = WELFARE_CHECK
    return status, _RECOMMENDATION[status]
```

- [ ] **Step 4: Run the tests to verify they pass, then lint**

Run: `venv/bin/python -m pytest tests/test_entity_role.py -q` → all pass.
Run: `venv/bin/python -m ruff check custom_components/behaviour_monitor/entity_role.py tests/test_entity_role.py && venv/bin/python -m black custom_components/behaviour_monitor/entity_role.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/entity_role.py tests/test_entity_role.py
git commit -m "feat: entity_role module — area lookup, override parsing, role inference, kind-weighted welfare

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `pipeline.py` — types, pass-through, rising-edge debounce

**Files:**
- Create: `custom_components/behaviour_monitor/pipeline.py`
- Create: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `EntityRole`, `DEFAULT_*` and `DOOR_OPEN_*` from `const.py`; `is_binary_state` from `routine_model.py`.
- Produces (used by Tasks 4–9):
  - `PipelineConfig(motion_debounce_seconds=120, door_debounce_seconds=60, retrigger_collapse_seconds=5, excursion_window_seconds=60, door_open_extended_seconds=15, door_open_prolonged_seconds=120)` frozen dataclass
  - `PipelineEvent(entity_id, role, old_state, new_state, timestamp)` frozen dataclass
  - `ActivityEvent(entity_id, role, timestamp, kind="activation", state="on", entities=(), duration_seconds=None)` frozen dataclass; `ACTIVATION = "activation"`, `EXCURSION = "excursion"`
  - `ActivityPipeline(config).submit(event) -> list[ActivityEvent]` and `.flush(now, *, force=False) -> list[ActivityEvent]`
  - Tasks 4 and 5 add `_confirm_off`, `door_status`, `seed_door_status`, excursions, `classify_open_duration`, `replay`.

Behaviour in this task: `unavailable`/`unknown` resets edge tracking; numeric, `appliance` and `other` pass through as one activation per submit carrying the raw state; motion and door roles count rising edges only, debounced per entity by kind. Off edges are recorded (`is_on = False`) but nothing else happens yet (Task 4 adds collapse and open duration). `flush` returns `[]` for now.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
"""Tests for the activity pipeline: pass-through, debounce, collapse, open duration, excursions, replay."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.behaviour_monitor.const import EntityRole
from custom_components.behaviour_monitor.pipeline import (
    ACTIVATION,
    ActivityEvent,
    ActivityPipeline,
    PipelineConfig,
    PipelineEvent,
)

T0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _ev(eid: str, role: EntityRole, old: str | None, new: str, seconds: float) -> PipelineEvent:
    return PipelineEvent(eid, role, old, new, _at(seconds))


def _run(pipeline: ActivityPipeline, events: list[PipelineEvent]) -> list[ActivityEvent]:
    out: list[ActivityEvent] = []
    for ev in events:
        out.extend(pipeline.submit(ev))
    return out


@pytest.fixture
def cfg() -> PipelineConfig:
    return PipelineConfig()


class TestDefaults:
    def test_config_defaults(self, cfg: PipelineConfig) -> None:
        assert (cfg.motion_debounce_seconds, cfg.door_debounce_seconds, cfg.retrigger_collapse_seconds) == (120, 60, 5)
        assert (cfg.excursion_window_seconds, cfg.door_open_extended_seconds, cfg.door_open_prolonged_seconds) == (60, 15, 120)

    def test_activity_event_defaults(self) -> None:
        ev = ActivityEvent("a.b", EntityRole.OTHER, T0)
        assert (ev.kind, ev.state, ev.entities, ev.duration_seconds) == (ACTIVATION, "on", (), None)


class TestPassThrough:
    @pytest.mark.parametrize("role", [EntityRole.APPLIANCE, EntityRole.OTHER])
    def test_every_change_counts_with_raw_state(self, cfg: PipelineConfig, role: EntityRole) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [_ev("switch.k", role, "off", "on", 0), _ev("switch.k", role, "on", "off", 1)])
        assert [(e.kind, e.state) for e in out] == [(ACTIVATION, "on"), (ACTIVATION, "off")]

    def test_numeric_motion_role_passes_through(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [_ev("sensor.lux", EntityRole.MOTION_KITCHEN, "1", "2", 0), _ev("sensor.lux", EntityRole.MOTION_KITCHEN, "2", "3", 1)])
        assert [e.state for e in out] == ["2", "3"]

    @pytest.mark.parametrize("state", ["unavailable", "unknown"])
    def test_unavailable_emits_nothing(self, cfg: PipelineConfig, state: str) -> None:
        p = ActivityPipeline(cfg)
        assert _run(p, [_ev("switch.k", EntityRole.APPLIANCE, "on", state, 0)]) == []


class TestRisingEdgeDebounce:
    def test_motion_counts_rising_edge_only(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
        ])
        assert len(out) == 1 and out[0].timestamp == _at(0) and out[0].role is EntityRole.MOTION_LIVING

    def test_first_sighting_on_counts(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert len(_run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, None, "on", 0)])) == 1

    def test_on_to_on_is_not_an_edge(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "on", "on", 0)]) == []

    def test_motion_debounce_120(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "on", "off", 30),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 119),  # inside the window: dropped
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "on", "off", 125),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 130),  # 130 s after the last counted edge
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(130)]

    def test_exactly_the_window_counts(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "on", "off", 30),
            _ev("b.pir", EntityRole.MOTION_BATHROOM, "off", "on", 120),
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(120)]

    def test_door_debounce_60(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 20),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 59),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 65),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 90),
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(90)]

    def test_debounce_is_per_entity(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.a", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.b", EntityRole.MOTION_KITCHEN, "off", "on", 10),
        ])
        assert [e.entity_id for e in out] == ["b.a", "b.b"]

    def test_zero_window_counts_every_edge(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0, retrigger_collapse_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 20),
        ])
        assert len(out) == 2

    def test_unavailable_resets_edge_tracking(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0, retrigger_collapse_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "unavailable", 100),
            _ev("b.pir", EntityRole.MOTION_LIVING, "unavailable", "on", 200),  # on after dropout is a rising edge
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(200)]

    def test_flush_returns_nothing_when_idle(self, cfg: PipelineConfig) -> None:
        assert ActivityPipeline(cfg).flush(_at(0)) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.behaviour_monitor.pipeline'`.

- [ ] **Step 3: Create the module**

Create `custom_components/behaviour_monitor/pipeline.py`:

```python
"""Activity pipeline: retrigger collapse, debounce, door open duration, excursions.

Pure Python stdlib only. Zero Home Assistant imports. Sits after ``EventGate``
(stage 1) and turns gated state events into activity events that the routine
model, correlation detector and daily counter consume. State is in-memory
only: after a restart the first rising edge for every entity counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .const import (
    DEFAULT_DOOR_DEBOUNCE_SECONDS,
    DEFAULT_DOOR_OPEN_EXTENDED_SECONDS,
    DEFAULT_DOOR_OPEN_PROLONGED_SECONDS,
    DEFAULT_EXCURSION_WINDOW_SECONDS,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
    DEFAULT_RETRIGGER_COLLAPSE_SECONDS,
    EntityRole,
)
from .routine_model import is_binary_state

ACTIVATION = "activation"
EXCURSION = "excursion"
_DROPOUT = ("unavailable", "unknown")
_EDGE_KINDS = ("motion", "door")


@dataclass(frozen=True)
class PipelineConfig:
    """Stage thresholds in seconds. Zero disables the stage it names."""

    motion_debounce_seconds: int = DEFAULT_MOTION_DEBOUNCE_SECONDS
    door_debounce_seconds: int = DEFAULT_DOOR_DEBOUNCE_SECONDS
    retrigger_collapse_seconds: int = DEFAULT_RETRIGGER_COLLAPSE_SECONDS
    excursion_window_seconds: int = DEFAULT_EXCURSION_WINDOW_SECONDS
    door_open_extended_seconds: int = DEFAULT_DOOR_OPEN_EXTENDED_SECONDS
    door_open_prolonged_seconds: int = DEFAULT_DOOR_OPEN_PROLONGED_SECONDS


@dataclass(frozen=True)
class PipelineEvent:
    """A state change after the event gate."""

    entity_id: str
    role: EntityRole
    old_state: str | None
    new_state: str
    timestamp: datetime


@dataclass(frozen=True)
class ActivityEvent:
    """One unit of activity. ``state`` is what the routine model records."""

    entity_id: str
    role: EntityRole
    timestamp: datetime
    kind: str = ACTIVATION
    state: str = "on"
    entities: tuple[str, ...] = ()  # excursion members, in arrival order
    duration_seconds: float | None = None  # excursion span


@dataclass
class _EntityState:
    role: EntityRole | None = None
    is_on: bool | None = None  # None = unknown (never seen, or after a dropout)
    last_on: datetime | None = None  # most recent on edge, counted or not
    last_counted: datetime | None = None  # most recent counted on edge
    pending_off: datetime | None = None
    last_open_seconds: float | None = None
    last_open_class: str | None = None


def _seconds(value: int) -> timedelta:
    return timedelta(seconds=max(0, int(value)))


class ActivityPipeline:
    """Turn gated state events into activity events."""

    def __init__(self, config: PipelineConfig) -> None:
        self._cfg = config
        self._motion = _seconds(config.motion_debounce_seconds)
        self._door = _seconds(config.door_debounce_seconds)
        self._collapse = _seconds(config.retrigger_collapse_seconds)
        self._excursion_window = _seconds(config.excursion_window_seconds)
        self._states: dict[str, _EntityState] = {}

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def submit(self, event: PipelineEvent) -> list[ActivityEvent]:
        """Feed one gated event; return the activity events it produced."""
        st = self._states.setdefault(event.entity_id, _EntityState())
        st.role = event.role
        sv = event.new_state
        if sv.lower() in _DROPOUT:
            st.is_on = None
            st.pending_off = None
            return []
        if event.role.kind not in _EDGE_KINDS or not is_binary_state(sv):
            return [ActivityEvent(event.entity_id, event.role, event.timestamp, state=sv)]
        prev_on = st.is_on
        if prev_on is None:
            prev_on = event.old_state is not None and event.old_state.lower() == "on"
        if sv.lower() == "on":
            return self._on_edge(event, st, prev_on)
        return self._off_edge(event, st, prev_on)

    def _on_edge(self, event: PipelineEvent, st: _EntityState, prev_on: bool) -> list[ActivityEvent]:
        if prev_on:
            st.is_on = True
            return []
        st.is_on = True
        st.last_on = event.timestamp
        window = self._motion if event.role.kind == "motion" else self._door
        if st.last_counted is not None and window and event.timestamp - st.last_counted < window:
            return []
        st.last_counted = event.timestamp
        return [ActivityEvent(event.entity_id, event.role, event.timestamp)]

    def _off_edge(self, event: PipelineEvent, st: _EntityState, prev_on: bool) -> list[ActivityEvent]:
        st.is_on = False
        return []

    # ------------------------------------------------------------------
    # Flush
    # ------------------------------------------------------------------

    def flush(self, now: datetime, *, force: bool = False) -> list[ActivityEvent]:
        """Release time-dependent output. ``force`` releases everything."""
        return []
```

- [ ] **Step 4: Run the tests to verify they pass, then lint**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -q` → all pass. Run `venv/bin/python -m ruff check custom_components/behaviour_monitor/pipeline.py tests/test_pipeline.py` → clean (ruff may flag the unused `field` import; remove it if so — Task 5 does not need it either).

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/pipeline.py tests/test_pipeline.py
git commit -m "feat: activity pipeline — pass-through and per-kind rising-edge debounce

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Pipeline retrigger collapse and door open duration

**Files:**
- Modify: `custom_components/behaviour_monitor/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `classify_open_duration(seconds: float, extended: int, prolonged: int) -> str`; `ActivityPipeline.door_status(entity_id) -> dict[str, Any]` with keys `last_open_seconds`, `last_open_class`; `ActivityPipeline.seed_door_status(statuses: Mapping[str, Mapping[str, Any]]) -> None`; `flush` now confirms pending offs.

Rules (spec §2.4, §2.5): an off edge for a motion or door entity is held as `pending_off`; an on edge within `retrigger_collapse_seconds` of it discards both (entity treated as continuously on, no new `last_on`, no debounce check); an on edge later than that first confirms the off, then proceeds as a normal rising edge. `flush(now)` confirms pending offs at least `retrigger_collapse_seconds` old; `force` confirms all. Confirming an off for a door role with a known `last_on` records the open duration from `last_on` (counted or not) and its class. With collapse 0, offs confirm immediately.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
from custom_components.behaviour_monitor.const import DOOR_OPEN_BRIEF, DOOR_OPEN_EXTENDED, DOOR_OPEN_PROLONGED
from custom_components.behaviour_monitor.pipeline import classify_open_duration


class TestRetriggerCollapse:
    def test_pair_inside_window_is_discarded(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 10.023),  # 23 ms retrigger
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 30),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 40),  # 10 s later: real edge
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(40)]

    def test_pair_outside_window_is_two_edges(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 15),  # exactly the window: not collapsed
        ])
        assert [e.timestamp for e in out] == [_at(0), _at(15)]

    def test_collapse_zero_disables(self) -> None:
        p = ActivityPipeline(PipelineConfig(motion_debounce_seconds=0, retrigger_collapse_seconds=0))
        out = _run(p, [
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0),
            _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 10),
            _ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 10.5),
        ])
        assert len(out) == 2

    def test_collapsed_off_does_not_close_open_interval(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 20),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 21),   # bounce: still open
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 50),
        ])
        p.flush(_at(60))
        assert p.door_status("b.door") == {"last_open_seconds": 50.0, "last_open_class": DOOR_OPEN_EXTENDED}


class TestOpenDuration:
    @pytest.mark.parametrize(
        ("seconds", "cls"),
        [(0.0, DOOR_OPEN_BRIEF), (14.999, DOOR_OPEN_BRIEF), (15.0, DOOR_OPEN_EXTENDED), (119.9, DOOR_OPEN_EXTENDED), (120.0, DOOR_OPEN_PROLONGED), (4000.0, DOOR_OPEN_PROLONGED)],
    )
    def test_classify(self, seconds: float, cls: str) -> None:
        assert classify_open_duration(seconds, 15, 120) == cls

    def test_status_none_until_first_close(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        assert p.door_status("b.door") == {"last_open_seconds": None, "last_open_class": None}
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0)])
        assert p.door_status("b.door")["last_open_seconds"] is None

    def test_off_confirmed_by_flush_after_collapse_window(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0), _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 8)])
        p.flush(_at(12))  # 4 s after the off: still pending
        assert p.door_status("b.door")["last_open_seconds"] is None
        p.flush(_at(13))  # 5 s: confirmed
        assert p.door_status("b.door") == {"last_open_seconds": 8.0, "last_open_class": DOOR_OPEN_BRIEF}

    def test_force_flush_confirms_immediately(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0), _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 200)])
        p.flush(_at(200), force=True)
        assert p.door_status("b.door")["last_open_class"] == DOOR_OPEN_PROLONGED

    def test_next_on_confirms_pending_off(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 10),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 100),
        ])
        assert p.door_status("b.door")["last_open_seconds"] == 10.0

    def test_debounced_reopen_starts_new_interval(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 0),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 5),
            _ev("b.door", EntityRole.DOOR_INTERIOR, "off", "on", 30),   # debounced (< 60 s), but it IS the new last_on
            _ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 40),
        ])
        p.flush(_at(100))
        assert len(out) == 1
        assert p.door_status("b.door")["last_open_seconds"] == 10.0

    def test_open_at_start_records_nothing(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.door", EntityRole.DOOR_INTERIOR, "on", "off", 0)])
        p.flush(_at(100))
        assert p.door_status("b.door")["last_open_seconds"] is None

    def test_motion_never_gets_open_duration(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.pir", EntityRole.MOTION_LIVING, "off", "on", 0), _ev("b.pir", EntityRole.MOTION_LIVING, "on", "off", 30)])
        p.flush(_at(100))
        assert p.door_status("b.pir")["last_open_seconds"] is None

    def test_seed_door_status(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        p.seed_door_status({"b.door": {"last_open_seconds": 7.5, "last_open_class": DOOR_OPEN_BRIEF}})
        assert p.door_status("b.door") == {"last_open_seconds": 7.5, "last_open_class": DOOR_OPEN_BRIEF}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -q`
Expected: FAIL with `ImportError: cannot import name 'classify_open_duration'`.

- [ ] **Step 3: Implement**

In `pipeline.py`, add the import of the class names and the classifier, then replace `_on_edge`, `_off_edge` and `flush`, and add `_confirm_off`, `door_status`, `seed_door_status`:

```python
from collections.abc import Mapping
from typing import Any

from .const import DOOR_OPEN_BRIEF, DOOR_OPEN_EXTENDED, DOOR_OPEN_PROLONGED  # add to the existing const import


def classify_open_duration(seconds: float, extended: int, prolonged: int) -> str:
    """Brief below ``extended``, extended below ``prolonged``, else prolonged."""
    if seconds < extended:
        return DOOR_OPEN_BRIEF
    if seconds < prolonged:
        return DOOR_OPEN_EXTENDED
    return DOOR_OPEN_PROLONGED
```

```python
    def _on_edge(self, event: PipelineEvent, st: _EntityState, prev_on: bool) -> list[ActivityEvent]:
        if st.pending_off is not None:
            if self._collapse and event.timestamp - st.pending_off < self._collapse:
                # off/on bounce: the entity never really turned off
                st.pending_off = None
                st.is_on = True
                return []
            self._confirm_off(st, st.pending_off)
            prev_on = False
        if prev_on:
            st.is_on = True
            return []
        st.is_on = True
        st.last_on = event.timestamp
        window = self._motion if event.role.kind == "motion" else self._door
        if st.last_counted is not None and window and event.timestamp - st.last_counted < window:
            return []
        st.last_counted = event.timestamp
        return [ActivityEvent(event.entity_id, event.role, event.timestamp)]

    def _off_edge(self, event: PipelineEvent, st: _EntityState, prev_on: bool) -> list[ActivityEvent]:
        st.is_on = False
        if not prev_on:
            return []
        if self._collapse:
            st.pending_off = event.timestamp
        else:
            self._confirm_off(st, event.timestamp)
        return []

    def _confirm_off(self, st: _EntityState, off_at: datetime) -> None:
        """The off edge is real: close the open interval for door roles."""
        st.pending_off = None
        if st.role is None or st.role.kind != "door" or st.last_on is None:
            return
        seconds = (off_at - st.last_on).total_seconds()
        st.last_open_seconds = seconds
        st.last_open_class = classify_open_duration(
            seconds, self._cfg.door_open_extended_seconds, self._cfg.door_open_prolonged_seconds
        )

    # ------------------------------------------------------------------
    # Flush and status
    # ------------------------------------------------------------------

    def flush(self, now: datetime, *, force: bool = False) -> list[ActivityEvent]:
        """Release time-dependent output. ``force`` releases everything."""
        for st in self._states.values():
            if st.pending_off is not None and (force or now - st.pending_off >= self._collapse):
                self._confirm_off(st, st.pending_off)
        return []

    def door_status(self, entity_id: str) -> dict[str, Any]:
        st = self._states.get(entity_id)
        return {
            "last_open_seconds": st.last_open_seconds if st else None,
            "last_open_class": st.last_open_class if st else None,
        }

    def seed_door_status(self, statuses: Mapping[str, Mapping[str, Any]]) -> None:
        """Restore per-door open-duration status (used after a recorder replay)."""
        for eid, status in statuses.items():
            st = self._states.setdefault(eid, _EntityState())
            st.last_open_seconds = status.get("last_open_seconds")
            st.last_open_class = status.get("last_open_class")
```

- [ ] **Step 4: Run the tests to verify they pass, then lint**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -q` → all pass. `venv/bin/python -m ruff check custom_components/behaviour_monitor/pipeline.py tests/test_pipeline.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline retrigger collapse and door open-duration classes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Pipeline excursion grouping and `replay`

**Files:**
- Modify: `custom_components/behaviour_monitor/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `EXCURSION` events from `submit`/`flush`; `replay(events: Iterable[PipelineEvent], config: PipelineConfig) -> tuple[list[ActivityEvent], dict[str, dict[str, Any]]]`.

Rules (spec §2.6, §2.7): a counted `door.exterior` activation starts an excursion anchored at its entity and timestamp when none is open; further counted exterior activations within `excursion_window_seconds` of the anchor join it silently; `flush(now)` emits an excursion whose anchor is at least the window old (`force` emits immediately); a counted exterior activation arriving after the window closes the old one (emitted) and starts a new one. With window 0 exterior doors emit ordinary activations. `replay` sorts by timestamp, submits, flushes at each event's timestamp, force-flushes at the end, and returns door statuses for every door-kind entity seen.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
from custom_components.behaviour_monitor.pipeline import EXCURSION, replay


class TestExcursions:
    def test_two_doors_inside_window_is_one_excursion(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "on", "off", 6),
            _ev("b.side", EntityRole.DOOR_EXTERIOR, "off", "on", 45),
        ])
        assert out == []
        out = p.flush(_at(59))
        assert out == []
        out = p.flush(_at(60))
        assert len(out) == 1
        ex = out[0]
        assert (ex.kind, ex.entity_id, ex.role, ex.timestamp) == (EXCURSION, "b.back", EntityRole.DOOR_EXTERIOR, _at(0))
        assert ex.entities == ("b.back", "b.side")
        assert ex.duration_seconds == 45.0
        assert ex.state == "on"

    def test_single_door_excursion_has_zero_span(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0)])
        out = p.flush(_at(0), force=True)
        assert len(out) == 1 and out[0].entities == ("b.back",) and out[0].duration_seconds == 0.0

    def test_activation_after_window_closes_and_starts_new(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
            _ev("b.side", EntityRole.DOOR_EXTERIOR, "off", "on", 200),
        ])
        assert len(out) == 1 and out[0].entities == ("b.back",)
        out = p.flush(_at(260))
        assert len(out) == 1 and out[0].entities == ("b.side",) and out[0].timestamp == _at(200)

    def test_debounced_exterior_edge_does_not_join(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "on", "off", 10),
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 30),  # < 60 s door debounce
        ])
        out = p.flush(_at(100))
        assert out[0].entities == ("b.back",)

    def test_interior_doors_never_group(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        out = _run(p, [
            _ev("b.hall", EntityRole.DOOR_INTERIOR, "off", "on", 0),
            _ev("b.lounge", EntityRole.DOOR_INTERIOR, "off", "on", 5),
        ])
        assert [e.kind for e in out] == [ACTIVATION, ACTIVATION]

    def test_window_zero_disables(self) -> None:
        p = ActivityPipeline(PipelineConfig(excursion_window_seconds=0))
        out = _run(p, [_ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0)])
        assert len(out) == 1 and out[0].kind == ACTIVATION

    def test_idle_flush_after_excursion_emitted_is_empty(self, cfg: PipelineConfig) -> None:
        p = ActivityPipeline(cfg)
        _run(p, [_ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0)])
        assert len(p.flush(_at(0), force=True)) == 1
        assert p.flush(_at(1000)) == []


class TestReplay:
    def test_sorts_flushes_and_reports_doors(self, cfg: PipelineConfig) -> None:
        events = [
            _ev("b.side", EntityRole.DOOR_EXTERIOR, "off", "on", 40),
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "on", "off", 8),
            _ev("b.pir", EntityRole.MOTION_KITCHEN, "off", "on", 500),
            _ev("b.hall", EntityRole.DOOR_INTERIOR, "off", "on", 600),
            _ev("b.hall", EntityRole.DOOR_INTERIOR, "on", "off", 630),
        ]
        out, doors = replay(events, cfg)
        assert [(e.kind, e.entity_id, e.timestamp) for e in out] == [
            (EXCURSION, "b.back", _at(0)),
            (ACTIVATION, "b.pir", _at(500)),
            (ACTIVATION, "b.hall", _at(600)),
        ]
        assert out[0].entities == ("b.back", "b.side")
        assert set(doors) == {"b.back", "b.side", "b.hall"}
        assert doors["b.back"] == {"last_open_seconds": 8.0, "last_open_class": DOOR_OPEN_BRIEF}
        assert doors["b.hall"] == {"last_open_seconds": 30.0, "last_open_class": DOOR_OPEN_EXTENDED}
        assert doors["b.side"] == {"last_open_seconds": None, "last_open_class": None}

    def test_empty(self, cfg: PipelineConfig) -> None:
        assert replay([], cfg) == ([], {})

    def test_final_force_flush_emits_open_excursion_and_pending_off(self, cfg: PipelineConfig) -> None:
        events = [
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "off", "on", 0),
            _ev("b.back", EntityRole.DOOR_EXTERIOR, "on", "off", 3),
        ]
        out, doors = replay(events, cfg)
        assert len(out) == 1 and out[0].kind == EXCURSION
        assert doors["b.back"]["last_open_seconds"] == 3.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -q`
Expected: FAIL with `ImportError: cannot import name 'EXCURSION'`.

- [ ] **Step 3: Implement**

In `pipeline.py` add `from collections.abc import Iterable, Mapping` (extend the existing import), the `_Excursion` dataclass after `_EntityState`, an `_excursion` attribute in `__init__`, the excursion branch in `_on_edge`, the excursion release in `flush`, and `replay` at module level:

```python
@dataclass
class _Excursion:
    entity_id: str
    role: EntityRole
    anchor: datetime
    last: datetime
    entities: list[str]
```

```python
        self._excursion: _Excursion | None = None  # in __init__
```

In `_on_edge`, replace the final `return [ActivityEvent(...)]` with:

```python
        st.last_counted = event.timestamp
        if event.role is EntityRole.DOOR_EXTERIOR and self._excursion_window:
            return self._join_excursion(event)
        return [ActivityEvent(event.entity_id, event.role, event.timestamp)]

    def _join_excursion(self, event: PipelineEvent) -> list[ActivityEvent]:
        ex = self._excursion
        if ex is not None and event.timestamp - ex.anchor < self._excursion_window:
            ex.entities.append(event.entity_id)
            ex.last = event.timestamp
            return []
        out = [self._close_excursion()] if ex is not None else []
        self._excursion = _Excursion(
            event.entity_id, event.role, event.timestamp, event.timestamp, [event.entity_id]
        )
        return out

    def _close_excursion(self) -> ActivityEvent:
        ex = self._excursion
        assert ex is not None
        self._excursion = None
        return ActivityEvent(
            ex.entity_id, ex.role, ex.anchor, kind=EXCURSION,
            entities=tuple(ex.entities), duration_seconds=(ex.last - ex.anchor).total_seconds(),
        )
```

In `flush`, before `return []`:

```python
        out: list[ActivityEvent] = []
        ex = self._excursion
        if ex is not None and (force or now - ex.anchor >= self._excursion_window):
            out.append(self._close_excursion())
        return out
```

At module level, after the class:

```python
def replay(
    events: Iterable[PipelineEvent], config: PipelineConfig
) -> tuple[list[ActivityEvent], dict[str, dict[str, Any]]]:
    """Run one pipeline over a whole event list (recorder bootstrap, CLI).

    Events are sorted by timestamp; the pipeline is flushed at each event's
    timestamp so time-dependent stages advance, and force-flushed at the end.
    Returns the activity events and ``door_status`` for every door entity seen.
    """
    pipeline = ActivityPipeline(config)
    out: list[ActivityEvent] = []
    doors: set[str] = set()
    last: datetime | None = None
    for ev in sorted(events, key=lambda e: e.timestamp):
        if ev.role.kind == "door":
            doors.add(ev.entity_id)
        out.extend(pipeline.submit(ev))
        out.extend(pipeline.flush(ev.timestamp))
        last = ev.timestamp
    if last is not None:
        out.extend(pipeline.flush(last, force=True))
    return out, {eid: pipeline.door_status(eid) for eid in sorted(doors)}
```

- [ ] **Step 4: Run the tests to verify they pass, then lint**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -q` → all pass. `venv/bin/python -m ruff check custom_components/behaviour_monitor/pipeline.py tests/test_pipeline.py && venv/bin/python -m black custom_components/behaviour_monitor/pipeline.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline exterior-door excursion grouping and replay helper

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Coordinator — roles replace categories, pipeline replaces the debouncer

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py` (imports `:18-56`, constructor `:106-170`, `_refresh_categories` `:287-309`, `_refresh_panic_devices` `:363-366`, `_expected_entities` `:411-412`, `_flush_gate`/`_process_activity` `:469-500`, `_run_detection` `:639-660`, `_derive_welfare` `:724`, `_build_sensor_data` `:766-777`, `_bootstrap_from_recorder`/`_rebootstrap_motion_entities` `:829-885`)
- Modify: `custom_components/behaviour_monitor/const.py` (remove `EntityCategory`, `CATEGORY_WEIGHT`, `DEFAULT_CATEGORY_MOTION/CONTACT/PLUG/LIGHT`; keep `CONF_CATEGORY_*` keys under a "legacy, migrations only" comment)
- Modify: `custom_components/behaviour_monitor/__init__.py` (v11/v12 migrations use `[]` literals instead of the removed `DEFAULT_CATEGORY_*`; drop those imports)
- Delete: `custom_components/behaviour_monitor/entity_category.py`, `tests/test_entity_category.py`
- Modify: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `infer_roles`, `parse_role_overrides`, `derive_weighted_status` (Task 2); `ActivityPipeline`, `PipelineConfig`, `PipelineEvent`, `ActivityEvent`, `replay` (Tasks 3–5).
- Produces (coordinator attributes later tasks and tests rely on): `self._roles: dict[str, EntityRole]`, `self._panic_entities: list[str]`, `self._exterior_doors: list[str]`, `self._role_overrides: dict[str, str]`, `self._pipeline_config: PipelineConfig`, `self._pipeline: ActivityPipeline`, `_refresh_roles()`, `_registry_area_names() -> dict[str, str | None]` (stub returning all `None` in this task; Task 7 fills it), `_consume_activity(events: list[ActivityEvent]) -> None`, `_rebootstrap_motion_entities` kept.

Not in this task: area lookup, role repair issue, role re-bootstrap, status attributes (Task 7); config-flow keys (Task 8). The coordinator reads the new keys with `.get(..., DEFAULT)` so it works before the migration lands.

- [ ] **Step 1: Update the coordinator tests**

Apply these mechanical replacements across `tests/test_coordinator.py` (there are about 60 hits):

| Old | New |
|---|---|
| `EntityCategory` (import and use) | `EntityRole` |
| `c._categories` / `coordinator._categories` | `c._roles` / `coordinator._roles` |
| `EntityRole.MOTION` | `EntityRole.MOTION_LIVING` |
| `EntityRole.CONTACT` | `EntityRole.DOOR_INTERIOR` |
| `EntityRole.PLUG`, `EntityRole.LIGHT` | `EntityRole.APPLIANCE` |
| `_refresh_categories()` | `_refresh_roles()` |
| `patch.object(c, "_registry_device_classes", return_value={...})` | keep, and add `patch.object(c, "_registry_area_names", return_value={})` alongside it in every test that patches device classes |
| `_rebootstrap_motion_entities` | unchanged |

Then edit these specific tests in `class TestEntityCategories` (rename the class `TestEntityRoles`):

```python
    def test_defaults(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import DEFAULT_DOOR_DEBOUNCE_SECONDS, DEFAULT_MOTION_DEBOUNCE_SECONDS

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"])
        assert c._pipeline_config.motion_debounce_seconds == DEFAULT_MOTION_DEBOUNCE_SECONDS
        assert c._pipeline_config.door_debounce_seconds == DEFAULT_DOOR_DEBOUNCE_SECONDS
        assert c._roles == {}
        assert c._exterior_doors == [] and c._role_overrides == {}

    def test_refresh_roles_uses_registry_lists_and_overrides(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        from custom_components.behaviour_monitor.const import CONF_EXTERIOR_DOORS, CONF_ROLE_OVERRIDES, EntityRole

        c = self._make(
            mock_hass,
            mock_config_entry,
            ["binary_sensor.pir", "binary_sensor.door", "binary_sensor.front", "switch.kettle", "light.hall", "sensor.temp"],
            **{CONF_EXTERIOR_DOORS: ["binary_sensor.front"], CONF_ROLE_OVERRIDES: "sensor.temp: door\n"},
        )
        with patch.object(c, "_registry_device_classes", return_value={"binary_sensor.pir": "motion", "binary_sensor.door": "door", "binary_sensor.front": "door"}), \
             patch.object(c, "_registry_area_names", return_value={"binary_sensor.pir": "Kitchen"}):
            c._refresh_roles()
        assert c._roles == {
            "binary_sensor.pir": EntityRole.MOTION_KITCHEN,
            "binary_sensor.door": EntityRole.DOOR_INTERIOR,
            "binary_sensor.front": EntityRole.DOOR_EXTERIOR,
            "switch.kettle": EntityRole.APPLIANCE,
            "light.hall": EntityRole.APPLIANCE,
            "sensor.temp": EntityRole.DOOR_INTERIOR,
        }

    def test_invalid_overrides_are_ignored_with_warning(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import CONF_ROLE_OVERRIDES

        c = self._make(mock_hass, mock_config_entry, ["a.b"], **{CONF_ROLE_OVERRIDES: "nonsense"})
        assert c._role_overrides == {}
```

Replace `test_refresh_categories_forces_numeric_to_other` and `test_refresh_categories_uses_live_state_when_model_empty` with the same tests using `CONF_ROLE_OVERRIDES: "sensor.lux: motion.kitchen\n"` (and `"...\nbinary_sensor.pir: motion"` for the second) and `EntityRole.OTHER` / `EntityRole.MOTION_UNASSIGNED` expectations.

Replace the ingestion tests:

```python
    def test_motion_off_transition_updates_last_seen_but_not_model(self, mock_hass, mock_config_entry) -> None:
        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"])
        c._roles = {"binary_sensor.pir": EntityRole.MOTION_LIVING}
        _fire(c, self._event("binary_sensor.pir", "on", "off"))
        assert "binary_sensor.pir" in c._last_seen
        assert "binary_sensor.pir" not in c._routine_model._entities
        assert c._today_count == 0

    def test_motion_rising_edge_records(self, mock_hass, mock_config_entry) -> None:
        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"])
        c._roles = {"binary_sensor.pir": EntityRole.MOTION_LIVING}
        _fire(c, self._event("binary_sensor.pir", "off", "on"))
        assert "binary_sensor.pir" in c._routine_model._entities
        assert c._today_count == 1
        assert "binary_sensor.pir" in c._correlation_detector._entity_event_counts

    def test_motion_burst_counts_once(self, mock_hass, mock_config_entry) -> None:
        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"])
        c._roles = {"binary_sensor.pir": EntityRole.MOTION_LIVING}
        for _ in range(3):
            _fire(c, self._event("binary_sensor.pir", "off", "on"))
            _fire(c, self._event("binary_sensor.pir", "on", "off"))
        assert c._today_count == 1

    def test_zero_windows_count_every_edge(self, mock_hass, mock_config_entry) -> None:
        from custom_components.behaviour_monitor.const import CONF_MOTION_DEBOUNCE_SECONDS, CONF_RETRIGGER_COLLAPSE_SECONDS

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"], **{CONF_MOTION_DEBOUNCE_SECONDS: 0, CONF_RETRIGGER_COLLAPSE_SECONDS: 0})
        c._roles = {"binary_sensor.pir": EntityRole.MOTION_LIVING}
        for _ in range(3):
            _fire(c, self._event("binary_sensor.pir", "off", "on"))
            _fire(c, self._event("binary_sensor.pir", "on", "off"))
        assert c._today_count == 3

    def test_door_counts_rising_edge_only(self, mock_hass, mock_config_entry) -> None:
        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.door"])
        c._roles = {"binary_sensor.door": EntityRole.DOOR_INTERIOR}
        _fire(c, self._event("binary_sensor.door", "off", "on"))
        _fire(c, self._event("binary_sensor.door", "on", "off"))
        assert c._today_count == 1

    def test_appliance_counts_every_change(self, mock_hass, mock_config_entry) -> None:
        c = self._make(mock_hass, mock_config_entry, ["switch.kettle"])
        c._roles = {"switch.kettle": EntityRole.APPLIANCE}
        _fire(c, self._event("switch.kettle", "off", "on"))
        _fire(c, self._event("switch.kettle", "on", "off"))
        assert c._today_count == 2

    def test_excursion_records_once_under_first_door(self, mock_hass, mock_config_entry) -> None:
        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.back", "binary_sensor.side"])
        c._roles = {"binary_sensor.back": EntityRole.DOOR_EXTERIOR, "binary_sensor.side": EntityRole.DOOR_EXTERIOR}
        c._handle_state_changed(self._event("binary_sensor.back", "off", "on"))
        c._handle_state_changed(self._event("binary_sensor.side", "off", "on"))
        c._flush_gate(force=True)  # force flush closes the excursion immediately
        assert c._today_count == 1
        assert "binary_sensor.back" in c._routine_model._entities
        assert "binary_sensor.side" not in c._routine_model._entities

    def test_pipeline_flushed_on_poll(self, mock_hass, mock_config_entry) -> None:
        from custom_components.behaviour_monitor.pipeline import ActivityEvent

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.back"])
        c._roles = {"binary_sensor.back": EntityRole.DOOR_EXTERIOR}
        pending = [ActivityEvent("binary_sensor.back", EntityRole.DOOR_EXTERIOR, datetime.now())]
        with patch.object(c._pipeline, "flush", return_value=pending) as flush, \
             patch.object(c, "_refresh_health"), patch.object(c, "_run_detection", return_value=[]), \
             patch.object(c, "_handle_alerts", new_callable=AsyncMock):
            import asyncio
            asyncio.get_event_loop().run_until_complete(c._async_update_data())
        flush.assert_called()
        assert c._today_count == 1

    def test_refresh_requested_only_for_activity(self, mock_hass, mock_config_entry) -> None:
        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir"])
        c._roles = {"binary_sensor.pir": EntityRole.MOTION_LIVING}
        c._handle_state_changed(self._event("binary_sensor.pir", "off", "on"))
        c._flush_gate()  # not forced: first rising edge is activity -> refresh
        first = mock_hass.async_create_task.call_count
        c._handle_state_changed(self._event("binary_sensor.pir", "on", "off"))
        c._flush_gate()  # off edge is not activity -> no refresh
        assert mock_hass.async_create_task.call_count == first
```

(`test_pipeline_flushed_on_poll` may be written as an `async def` with `@pytest.mark.asyncio` and `await c._async_update_data()` instead of the event-loop call; use whichever matches the file's existing async tests.)

In `test_sensor_data_includes_category` rename to `test_sensor_data_includes_role` and assert `by_id["binary_sensor.pir"]["role"] == "motion.living"` and `by_id["sensor.other"]["role"] == "other"`; the `"category"` key must be absent.

In the recorder bootstrap class (`_make` at line ~1622): roles map uses `MOTION_LIVING` and `DOOR_INTERIOR`. Update `test_bootstrap_debounces_motion_history`: the door now records 1 event (rising edge only), so `assert sum(len(s.event_times) for s in door.slots) == 1`. `test_rebootstrap_clears_only_motion_and_clears_flag` stays as is (motion re-bootstrap is untouched).

In `TestWeightedWelfare` the fixture uses `EntityRole.MOTION_LIVING` and `EntityRole.APPLIANCE`; rename `test_plug_high_is_concern_not_alert` to `test_appliance_high_is_concern_not_alert`.

For every panic test that sets `c._categories = {...: EntityCategory.PANIC}` use `c._roles = {...: EntityRole.PANIC}`; contact/plug companions become `DOOR_INTERIOR`/`APPLIANCE`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_coordinator.py -q 2>&1 | tail -5`
Expected: many failures, all `AttributeError` on `_roles`, `_pipeline_config`, `_refresh_roles` or `_exterior_doors`. (`EntityRole` imports fine: Task 1 added it.)

- [ ] **Step 3: Implement the coordinator changes**

Imports (`coordinator.py:18-56`): remove `CONF_CATEGORY_CONTACT, CONF_CATEGORY_LIGHT, CONF_CATEGORY_MOTION, CONF_CATEGORY_PLUG` and `EntityCategory`; add `CONF_DOOR_DEBOUNCE_SECONDS, CONF_DOOR_OPEN_EXTENDED_SECONDS, CONF_DOOR_OPEN_PROLONGED_SECONDS, CONF_EXCURSION_WINDOW_SECONDS, CONF_EXTERIOR_DOORS, CONF_RETRIGGER_COLLAPSE_SECONDS, CONF_ROLE_OVERRIDES, DEFAULT_DOOR_DEBOUNCE_SECONDS, DEFAULT_DOOR_OPEN_EXTENDED_SECONDS, DEFAULT_DOOR_OPEN_PROLONGED_SECONDS, DEFAULT_EXCURSION_WINDOW_SECONDS, DEFAULT_EXTERIOR_DOORS, DEFAULT_RETRIGGER_COLLAPSE_SECONDS, DEFAULT_ROLE_OVERRIDES, EntityRole`. Replace the `entity_category` import line with:

```python
from .entity_role import derive_weighted_status, infer_roles, parse_role_overrides
from .pipeline import ActivityEvent, ActivityPipeline, PipelineConfig, PipelineEvent, replay
```

Constructor: replace the `_category_overrides` block through `self._debouncer = ...` with:

```python
        self._panic_entities: list[str] = list(d.get(CONF_CATEGORY_PANIC) or [])
        for eid in self._panic_entities:
            if eid not in self._monitored_entities:
                self._monitored_entities.append(eid)
        self._exterior_doors: list[str] = list(d.get(CONF_EXTERIOR_DOORS) or DEFAULT_EXTERIOR_DOORS)
        try:
            self._role_overrides: dict[str, str] = parse_role_overrides(d.get(CONF_ROLE_OVERRIDES) or DEFAULT_ROLE_OVERRIDES)
        except ValueError as err:
            _LOGGER.warning("Behaviour Monitor: ignoring role overrides: %s", err)
            self._role_overrides = {}
        self._roles: dict[str, EntityRole] = {}
        self._pipeline_config = PipelineConfig(
            motion_debounce_seconds=int(d.get(CONF_MOTION_DEBOUNCE_SECONDS, DEFAULT_MOTION_DEBOUNCE_SECONDS)),
            door_debounce_seconds=int(d.get(CONF_DOOR_DEBOUNCE_SECONDS, DEFAULT_DOOR_DEBOUNCE_SECONDS)),
            retrigger_collapse_seconds=int(d.get(CONF_RETRIGGER_COLLAPSE_SECONDS, DEFAULT_RETRIGGER_COLLAPSE_SECONDS)),
            excursion_window_seconds=int(d.get(CONF_EXCURSION_WINDOW_SECONDS, DEFAULT_EXCURSION_WINDOW_SECONDS)),
            door_open_extended_seconds=int(d.get(CONF_DOOR_OPEN_EXTENDED_SECONDS, DEFAULT_DOOR_OPEN_EXTENDED_SECONDS)),
            door_open_prolonged_seconds=int(d.get(CONF_DOOR_OPEN_PROLONGED_SECONDS, DEFAULT_DOOR_OPEN_PROLONGED_SECONDS)),
        )
        self._pipeline = ActivityPipeline(self._pipeline_config)
```

Delete `self._motion_debounce_seconds` (search for other uses: only the bootstrap, replaced below).

`async_setup`: change `self._refresh_categories()` to `self._refresh_roles()` and the comment to "Roles must be inferred...".

Replace `_refresh_categories` with:

```python
    def _registry_area_names(self) -> dict[str, str | None]:
        """Area name per monitored entity (entity area, else its device's area). Task 7 fills this in."""
        return {eid: None for eid in self._monitored_entities}

    def _refresh_roles(self) -> None:
        """Rebuild the entity -> role map from lists, overrides, registry, areas and model."""
        numeric: set[str] = set()
        for eid in self._monitored_entities:
            r = self._routine_model._entities.get(eid)
            if r is not None:
                if not r.is_binary:
                    numeric.add(eid)
                continue
            state = self.hass.states.get(eid)
            sv = getattr(state, "state", None)
            if isinstance(sv, str) and sv not in ("unavailable", "unknown") and not is_binary_state(sv):
                numeric.add(eid)
        self._roles = infer_roles(
            self._monitored_entities,
            self._panic_entities,
            self._exterior_doors,
            self._role_overrides,
            self._registry_device_classes(),
            self._registry_area_names(),
            numeric,
        )
        for eid, role in self._roles.items():
            if role is EntityRole.PANIC:
                self._routine_model._entities.pop(eid, None)
                self._correlation_detector.remove_entity(eid)
```

Every `self._categories.get(eid) is EntityCategory.PANIC` becomes `self._roles.get(eid) is EntityRole.PANIC` (and `is not`). There are occurrences in `_handle_state_changed`, `_refresh_panic_devices`, `_expected_entities`, `_run_detection` (two), `_build_sensor_data` (two), `_bootstrap_from_recorder`, `_rebootstrap_motion_entities`.

Replace `_flush_gate` and `_process_activity` with:

```python
    @callback
    def _flush_gate(self, force: bool = False) -> None:
        """Release completed one-second buckets from the gate, run the pipeline, consume activity."""
        self._gate_flush_pending = False
        now = dt_util.now()
        events, dropped = self._gate.flush(now, force=force)
        # Last seen is the load-bearing welfare metric: every gated event proves the
        # entity reported, whether or not the pipeline counts it as activity.
        for ev in events:
            self._last_seen[ev.entity_id] = ev.timestamp
        for ev in dropped:
            self._last_seen[ev.entity_id] = ev.timestamp
        if dropped:
            _LOGGER.debug(
                "Discarded burst of %d events across %d entities",
                len(dropped), len({ev.entity_id for ev in dropped}),
            )
        activity: list[ActivityEvent] = []
        for ev in events:
            role = self._roles.get(ev.entity_id, EntityRole.OTHER)
            activity.extend(self._pipeline.submit(PipelineEvent(ev.entity_id, role, ev.old_state, ev.new_state, ev.timestamp)))
        activity.extend(self._pipeline.flush(now, force=force))
        self._consume_activity(activity)
        if self._gate.pending and not force:
            self._gate_flush_pending = True
            self.hass.loop.call_later(1.0, self._flush_gate)
        if activity and not force:
            self.hass.async_create_task(self.async_request_refresh())

    def _consume_activity(self, events: list[ActivityEvent]) -> None:
        """Feed activity events to the routine model, correlation detector and daily count."""
        for ev in events:
            self._routine_model.record(
                entity_id=ev.entity_id, timestamp=ev.timestamp, state_value=ev.state, is_binary=is_binary_state(ev.state)
            )
            self._correlation_detector.record_event(ev.entity_id, ev.timestamp, self._last_seen)
            if self._today_date != ev.timestamp.date():
                self._today_count, self._today_date = 0, ev.timestamp.date()
            self._today_count += 1
```

In `_async_update_data`, immediately after `now = dt_util.now()`, add:

```python
        self._consume_activity(self._pipeline.flush(now))
```

`_derive_welfare`: `derive_weighted_status(welfare_alerts, self._roles)`.

`_build_sensor_data` entity_status: replace `"category": self._categories.get(e, EntityCategory.OTHER).value,` with `"role": self._roles.get(e, EntityRole.OTHER).value,`; `contributing` and the panic spread use `self._roles.get(e) is (not) EntityRole.PANIC`.

Replace `_bootstrap_from_recorder`:

```python
    async def _bootstrap_from_recorder(self, entity_ids: list[str] | None = None) -> None:
        """Replay recorder history through a private pipeline into the routine model.

        All targets are replayed together so cross-entity excursion grouping works.
        Dropout states (unavailable/unknown) are passed to the pipeline, which resets
        edge tracking for that entity: on -> unavailable -> on is a rising edge.
        """
        if recorder_get_instance is None or recorder_state_changes_during_period is None:
            _LOGGER.warning("Behaviour Monitor: recorder unavailable, skipping bootstrap")
            return
        targets = list(entity_ids) if entity_ids is not None else list(self._monitored_entities)
        events: list[PipelineEvent] = []
        try:
            instance = recorder_get_instance(self.hass)
            if instance is None:
                return
            end, start = dt_util.now(), dt_util.now() - timedelta(days=self._history_window_days)
            for eid in targets:
                role = self._roles.get(eid, EntityRole.OTHER)
                if role is EntityRole.PANIC:
                    continue
                prev: str | None = None
                try:
                    for sl in (await instance.async_add_executor_job(
                        recorder_state_changes_during_period, self.hass, start, end, [eid], False,
                    )).values():
                        for s in sl:
                            sv = str(s.state)
                            events.append(PipelineEvent(eid, role, prev, sv, s.last_changed))
                            prev = None if sv in ("unavailable", "unknown") else sv
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Could not load recorder history for %s", eid)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Behaviour Monitor: recorder bootstrap failed", exc_info=True)
            return
        activity, door_status = replay(events, self._pipeline_config)
        for ev in activity:
            self._routine_model.record(ev.entity_id, ev.timestamp, ev.state, is_binary_state(ev.state))
        self._pipeline.seed_door_status(door_status)
```

`_rebootstrap_motion_entities`: filter with `self._roles.get(e, EntityRole.OTHER).kind == "motion"`.

Then delete `custom_components/behaviour_monitor/entity_category.py` and `tests/test_entity_category.py`. In `const.py` delete the `EntityCategory` class, `CATEGORY_WEIGHT`, `DEFAULT_CATEGORY_MOTION/CONTACT/PLUG/LIGHT`; keep `MOTION_DEVICE_CLASSES`, `CONTACT_DEVICE_CLASSES`, `PLUG_DEVICE_CLASSES`, `SEVERITY_POINTS`, `WELFARE_*`; above `CONF_CATEGORY_MOTION` add the comment `# Legacy v5.0 keys: read by the v11 and v14 migrations only.` In `__init__.py` the v11 block uses `new_data.setdefault(CONF_CATEGORY_MOTION, [])` etc. and the `DEFAULT_CATEGORY_MOTION/CONTACT/PLUG/LIGHT` imports are removed. Update the `test_init.py` v10→v11 tests only if they import the removed defaults (they assert `== []`, so they should not).

- [ ] **Step 4: Run the full suite and lint**

Run: `venv/bin/python -m pytest tests/ -q` → all pass; `grep -rn "EntityCategory\|entity_category\|CATEGORY_WEIGHT\|MotionDebouncer\|_categories" custom_components tests` → no hits. `venv/bin/python -m ruff check custom_components/ tests/` → no new findings.

- [ ] **Step 5: Commit**

```bash
git add -A custom_components/behaviour_monitor tests
git commit -m "feat!: roles replace entity categories; activity pipeline replaces motion debouncer

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Coordinator — area names, role repair issue, role re-bootstrap, status attributes

**Files:**
- Modify: `custom_components/behaviour_monitor/coordinator.py` (`_registry_area_names`, `_refresh_health`, `async_setup`, new `_rebootstrap_role_entities`, `_build_sensor_data`)
- Modify: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `CONF_REBOOTSTRAP_ROLES` (Task 1); `ActivityPipeline.door_status` (Task 4).
- Produces: `_registry_area_names()` real implementation; repair issue id `roles_need_assignment` (translation key `roles_need_assignment`, placeholder `entity_ids`); `_rebootstrap_role_entities()`; `entity_status[*].role`, `entity_status[*].last_open_seconds` / `last_open_class` for door kinds; top-level `roles: dict[str, int]` in sensor data (every role value, zeros included).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator.py`:

```python
# ---------------------------------------------------------------------------
# TestRoleWiring — area lookup, role repair issue, role re-bootstrap, status
# ---------------------------------------------------------------------------


class TestRoleWiring:
    def _make(self, mock_hass: MagicMock, mock_config_entry: MagicMock, entities: list[str], **extra: Any) -> BehaviourMonitorCoordinator:
        from custom_components.behaviour_monitor.const import CONF_MONITORED_ENTITIES

        mock_config_entry.data = {**mock_config_entry.data, CONF_MONITORED_ENTITIES: entities, **extra}
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)

    def test_area_names_entity_then_device(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor import coordinator as coord_module

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.a", "binary_sensor.b", "binary_sensor.c", "binary_sensor.d"])
        ent = {
            "binary_sensor.a": MagicMock(area_id="area_kitchen", device_id=None),
            "binary_sensor.b": MagicMock(area_id=None, device_id="dev1"),
            "binary_sensor.c": MagicMock(area_id=None, device_id=None),
        }
        ent_reg = MagicMock(); ent_reg.async_get = lambda eid: ent.get(eid)
        dev_reg = MagicMock(); dev_reg.async_get = lambda did: MagicMock(area_id="area_bath") if did == "dev1" else None
        kitchen, bath = MagicMock(), MagicMock()
        kitchen.name, bath.name = "Kitchen", "Bathroom"
        areas = {"area_kitchen": kitchen, "area_bath": bath}
        area_reg = MagicMock(); area_reg.async_get_area = lambda aid: areas.get(aid)
        with patch.object(coord_module.er, "async_get", return_value=ent_reg), \
             patch.object(coord_module.dr, "async_get", return_value=dev_reg), \
             patch.object(coord_module.ar, "async_get", return_value=area_reg):
            names = c._registry_area_names()
        assert names == {"binary_sensor.a": "Kitchen", "binary_sensor.b": "Bathroom", "binary_sensor.c": None, "binary_sensor.d": None}

    def test_area_names_survive_registry_failure(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor import coordinator as coord_module

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.a"])
        with patch.object(coord_module.er, "async_get", side_effect=RuntimeError("boom")):
            assert c._registry_area_names() == {"binary_sensor.a": None}

    def test_unassigned_motion_raises_issue_and_clears(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor import coordinator as coord_module
        from custom_components.behaviour_monitor.const import EntityRole

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.a", "binary_sensor.b"])
        c._roles = {"binary_sensor.a": EntityRole.MOTION_UNASSIGNED, "binary_sensor.b": EntityRole.MOTION_UNASSIGNED}
        mock_hass.states.get = lambda eid: MagicMock(state="off")
        registry = MagicMock(); registry.async_get = lambda eid: MagicMock(); registry.issues = {}
        with patch.object(coord_module.er, "async_get", return_value=registry), \
             patch.object(coord_module.ir, "async_get", return_value=registry), \
             patch.object(coord_module.ir, "async_create_issue") as create, \
             patch.object(coord_module.ir, "async_delete_issue") as delete:
            c._refresh_health()
            assert "roles_need_assignment" in c._open_issues
            kwargs = create.call_args.kwargs
            assert kwargs["translation_key"] == "roles_need_assignment"
            assert kwargs["translation_placeholders"] == {"entity_ids": "binary_sensor.a, binary_sensor.b"}
            assert kwargs["is_fixable"] is False
            c._roles = {"binary_sensor.a": EntityRole.MOTION_KITCHEN, "binary_sensor.b": EntityRole.MOTION_LIVING}
            c._refresh_health()
        assert "roles_need_assignment" not in c._open_issues
        assert any("roles_need_assignment" in call.args for call in delete.call_args_list)

    def test_roles_issue_seeded_from_registry(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor import coordinator as coord_module
        from custom_components.behaviour_monitor.const import EntityRole

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.a"])
        c._roles = {"binary_sensor.a": EntityRole.MOTION_KITCHEN}
        mock_hass.states.get = lambda eid: MagicMock(state="off")
        registry = MagicMock(); registry.async_get = lambda eid: MagicMock()
        registry.issues = {("behaviour_monitor", "roles_need_assignment"): object(), ("behaviour_monitor", "exterior_doors_unconfirmed"): object()}
        with patch.object(coord_module.er, "async_get", return_value=registry), \
             patch.object(coord_module.ir, "async_get", return_value=registry), \
             patch.object(coord_module.ir, "async_create_issue"), \
             patch.object(coord_module.ir, "async_delete_issue") as delete:
            c._refresh_health()
        deleted = [call.args[-1] for call in delete.call_args_list]
        assert "roles_need_assignment" in deleted
        assert "exterior_doors_unconfirmed" not in deleted  # migration-owned; user dismisses it

    @pytest.mark.asyncio
    async def test_rebootstrap_roles_clears_door_and_appliance_only(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import CONF_REBOOTSTRAP_ROLES, EntityRole
        from custom_components.behaviour_monitor.drift_detector import CUSUMState

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir", "binary_sensor.door", "switch.kettle"], **{CONF_REBOOTSTRAP_ROLES: True})
        c._roles = {"binary_sensor.pir": EntityRole.MOTION_LIVING, "binary_sensor.door": EntityRole.DOOR_INTERIOR, "switch.kettle": EntityRole.APPLIANCE}
        for eid in c._roles:
            c._routine_model.get_or_create(eid, is_binary=True)
            c._correlation_detector._entity_event_counts[eid] = 5
        c._drift_detector._states["binary_sensor.door"] = CUSUMState()
        c._last_seen["binary_sensor.door"] = datetime.now(timezone.utc)
        pir_before = c._routine_model._entities["binary_sensor.pir"]
        with patch.object(c, "_bootstrap_from_recorder", new_callable=AsyncMock) as boot, \
             patch.object(c._store, "async_save", new_callable=AsyncMock) as save:
            await c._rebootstrap_role_entities()
        boot.assert_awaited_once_with(entity_ids=["binary_sensor.door", "switch.kettle"])
        assert c._routine_model._entities["binary_sensor.pir"] is pir_before
        assert "binary_sensor.door" not in c._routine_model._entities
        assert "switch.kettle" not in c._routine_model._entities
        assert "binary_sensor.pir" in c._correlation_detector._entity_event_counts
        assert "binary_sensor.door" not in c._correlation_detector._entity_event_counts
        assert "binary_sensor.door" in c._drift_detector._states and "binary_sensor.door" in c._last_seen
        save.assert_awaited_once()
        assert CONF_REBOOTSTRAP_ROLES not in mock_hass.config_entries.async_update_entry.call_args.kwargs["data"]

    @pytest.mark.asyncio
    async def test_async_setup_runs_role_rebootstrap_when_flag_set(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import CONF_REBOOTSTRAP_ROLES

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.door"], **{CONF_REBOOTSTRAP_ROLES: True})
        stored = {"routine_model": c._routine_model.to_dict(), "coordinator": {}}
        with patch.object(c._store, "async_load", new_callable=AsyncMock, return_value=stored), \
             patch.object(c, "_registry_device_classes", return_value={}), \
             patch.object(c, "_registry_area_names", return_value={}), \
             patch.object(c, "_rebootstrap_role_entities", new_callable=AsyncMock) as reboot, \
             patch.object(c, "_bootstrap_from_recorder", new_callable=AsyncMock) as boot:
            await c.async_setup()
        reboot.assert_awaited_once()
        boot.assert_not_awaited()

    def test_status_has_role_counts_and_door_fields(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
        from custom_components.behaviour_monitor.const import EntityRole

        c = self._make(mock_hass, mock_config_entry, ["binary_sensor.pir", "binary_sensor.door", "switch.kettle"])
        c._roles = {"binary_sensor.pir": EntityRole.MOTION_KITCHEN, "binary_sensor.door": EntityRole.DOOR_EXTERIOR, "switch.kettle": EntityRole.APPLIANCE}
        c._pipeline.seed_door_status({"binary_sensor.door": {"last_open_seconds": 9.0, "last_open_class": "brief"}})
        data = c._build_sensor_data([], datetime.now())
        assert data["roles"]["motion.kitchen"] == 1 and data["roles"]["door.exterior"] == 1 and data["roles"]["appliance"] == 1
        assert data["roles"]["motion.bathroom"] == 0 and "panic" in data["roles"]
        by_id = {e["entity_id"]: e for e in data["entity_status"]}
        assert by_id["binary_sensor.door"]["last_open_seconds"] == 9.0 and by_id["binary_sensor.door"]["last_open_class"] == "brief"
        assert "last_open_seconds" not in by_id["binary_sensor.pir"]
        assert "category" not in by_id["binary_sensor.pir"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_coordinator.py -k TestRoleWiring -q`
Expected: FAIL (`dr`/`ar` not defined on the module, no `_rebootstrap_role_entities`, no `roles` key).

- [ ] **Step 3: Implement**

Import line: `from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, issue_registry as ir`. Add `CONF_REBOOTSTRAP_ROLES` to the const import.

Replace the stub `_registry_area_names`:

```python
    def _registry_area_names(self) -> dict[str, str | None]:
        """Area name per monitored entity: the entity's area, else its device's area."""
        out: dict[str, str | None] = {eid: None for eid in self._monitored_entities}
        try:
            ent_reg, dev_reg, area_reg = er.async_get(self.hass), dr.async_get(self.hass), ar.async_get(self.hass)
        except Exception:  # noqa: BLE001
            return out
        for eid in self._monitored_entities:
            try:
                entry = ent_reg.async_get(eid)
                if entry is None:
                    continue
                area_id = getattr(entry, "area_id", None)
                if not area_id and getattr(entry, "device_id", None):
                    device = dev_reg.async_get(entry.device_id)
                    area_id = getattr(device, "area_id", None) if device is not None else None
                if not isinstance(area_id, str) or not area_id:
                    continue
                area = area_reg.async_get_area(area_id)
                name = getattr(area, "name", None)
                out[eid] = name if isinstance(name, str) else None
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Could not resolve area for %s", eid, exc_info=True)
        return out
```

In `_refresh_health`, generalise the seeding predicate and the wanted set. Replace the body up to `self._refresh_panic_devices()` with:

```python
        if not self._issues_seeded:
            self._issues_seeded = True
            try:
                registry = ir.async_get(self.hass)
                self._open_issues = {
                    iid for (dom, iid) in registry.issues
                    if dom == DOMAIN and isinstance(iid, str) and self._owns_issue(iid)
                }
            except Exception:  # noqa: BLE001
                self._open_issues = set()
        states, in_registry = self._entity_facts()
        self._entity_health = resolve_entity_health(self._monitored_entities, states, in_registry)
        wanted: dict[str, tuple[str, dict[str, str], Any]] = {
            f"missing_entity_{eid}": ("missing_entity", {"entity_id": eid}, ir.IssueSeverity.ERROR)
            for eid, h in self._entity_health.items() if h == HEALTH_MISSING
        }
        unassigned = sorted(e for e, r in self._roles.items() if r is EntityRole.MOTION_UNASSIGNED)
        if unassigned:
            wanted["roles_need_assignment"] = ("roles_need_assignment", {"entity_ids": ", ".join(unassigned)}, ir.IssueSeverity.WARNING)
        for issue_id in set(wanted) - self._open_issues:
            key, placeholders, severity = wanted[issue_id]
            try:
                ir.async_create_issue(
                    self.hass, DOMAIN, issue_id,
                    is_fixable=False, is_persistent=False, severity=severity,
                    translation_key=key, translation_placeholders=placeholders,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not create repair issue %s", issue_id)
        for issue_id in self._open_issues - set(wanted):
            try:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not delete repair issue %s", issue_id)
        self._open_issues = set(wanted)
        self._refresh_panic_devices()

    @staticmethod
    def _owns_issue(issue_id: str) -> bool:
        """Issues the coordinator raises and clears itself (not the migration-owned one)."""
        return issue_id.startswith("missing_entity_") or issue_id == "roles_need_assignment"
```

(No `learn_more_url`: `manifest.json` still carries a placeholder repository URL, so the issue description itself explains what to do. Task 10 records this deviation in the spec.)

In `async_setup`, extend the flag block:

```python
        if stored:
            if self._entry.data.get(CONF_REBOOTSTRAP_MOTION, False):
                await self._rebootstrap_motion_entities()
            if self._entry.data.get(CONF_REBOOTSTRAP_ROLES, False):
                await self._rebootstrap_role_entities()
```

Add after `_rebootstrap_motion_entities`:

```python
    async def _rebootstrap_role_entities(self) -> None:
        """One-shot after the v14 migration: rebuild door and appliance routines with the pipeline.

        Drops the learned routine and correlation counts for every door- and
        appliance-kind entity, replays recorder history for them, saves, then
        clears the rebootstrap_roles flag. Motion, CUSUM drift and last_seen are kept.
        """
        targets = [e for e in self._monitored_entities if self._roles.get(e, EntityRole.OTHER).kind in ("door", "appliance")]
        for eid in targets:
            self._routine_model._entities.pop(eid, None)
            self._correlation_detector.remove_entity(eid)
        if targets:
            await self._bootstrap_from_recorder(entity_ids=targets)
            _LOGGER.info("Behaviour Monitor: re-bootstrapped %d door/appliance entities through the pipeline", len(targets))
        await self._save_data()
        new_data = {k: v for k, v in self._entry.data.items() if k != CONF_REBOOTSTRAP_ROLES}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
```

In `_build_sensor_data`: add `"roles": self._role_counts(),` to the returned dict (next to `"panic"`), and in each `entity_status` entry add after `"role": ...`:

```python
                    **(self._pipeline.door_status(e) if self._roles.get(e, EntityRole.OTHER).kind == "door" else {}),
```

Add the helper:

```python
    def _role_counts(self) -> dict[str, int]:
        counts = {role.value: 0 for role in EntityRole}
        for eid in self._monitored_entities:
            counts[self._roles.get(eid, EntityRole.OTHER).value] += 1
        return counts
```

Also add `"roles": {role.value: 0 for role in EntityRole}` to `_build_safe_defaults`.

- [ ] **Step 4: Run the full suite and lint**

Run: `venv/bin/python -m pytest tests/ -q` → all pass. `venv/bin/python -m ruff check custom_components/ tests/` → no new findings.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/coordinator.py tests/test_coordinator.py
git commit -m "feat: area-based role lookup, roles repair issue, role re-bootstrap, role status attributes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Config flow fields, translations, v13 → v14 migration

**Files:**
- Modify: `custom_components/behaviour_monitor/config_flow.py` (imports, `_validate_category_overrides` → `_validate_roles`, `_build_data_schema`, both flows, `VERSION`)
- Modify: `custom_components/behaviour_monitor/const.py` (`STORAGE_VERSION = 14`)
- Modify: `custom_components/behaviour_monitor/__init__.py` (imports, v14 migration)
- Modify: `custom_components/behaviour_monitor/translations/en.json`
- Modify: `tests/test_config_flow.py`, `tests/test_init.py`

**Interfaces:**
- Consumes: Task 1 keys; `parse_role_overrides`, `ROLE_KINDS` (Task 2); `CONTACT_DEVICE_CLASSES`.
- Produces: `_validate_roles(user_input) -> str | None` with error keys `role_overrides_invalid`, `role_overlap`, `door_open_thresholds`; `_build_data_schema` keyword args `exterior_doors_default`, `role_overrides_default`, `door_debounce_seconds_default`, `retrigger_collapse_seconds_default`, `excursion_window_seconds_default`, `door_open_extended_seconds_default`, `door_open_prolonged_seconds_default` (the four `category_*_default` args are removed); repair issue `exterior_doors_unconfirmed`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config_flow.py`, replace `class TestCategoryFields` with:

```python
class TestRoleFields:
    """v5.3 role lists, override map and pipeline thresholds in both flows."""

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
    def _keys() -> tuple[str, ...]:
        from custom_components.behaviour_monitor.const import (
            CONF_DOOR_DEBOUNCE_SECONDS, CONF_DOOR_OPEN_EXTENDED_SECONDS, CONF_DOOR_OPEN_PROLONGED_SECONDS,
            CONF_EXCURSION_WINDOW_SECONDS, CONF_EXTERIOR_DOORS, CONF_RETRIGGER_COLLAPSE_SECONDS, CONF_ROLE_OVERRIDES,
        )
        return (
            CONF_EXTERIOR_DOORS, CONF_ROLE_OVERRIDES, CONF_DOOR_DEBOUNCE_SECONDS, CONF_RETRIGGER_COLLAPSE_SECONDS,
            CONF_EXCURSION_WINDOW_SECONDS, CONF_DOOR_OPEN_EXTENDED_SECONDS, CONF_DOOR_OPEN_PROLONGED_SECONDS,
        )

    def _base_input(self, **extra: Any) -> dict[str, Any]:
        ext, ovr, ddb, col, exc, opx, opp = self._keys()
        data = {
            CONF_MONITORED_ENTITIES: ["sensor.test1", "sensor.test2"],
            CONF_HISTORY_WINDOW_DAYS: DEFAULT_HISTORY_WINDOW_DAYS,
            CONF_INACTIVITY_MULTIPLIER: DEFAULT_INACTIVITY_MULTIPLIER,
            CONF_DRIFT_SENSITIVITY: SENSITIVITY_MEDIUM,
            CONF_ENABLE_NOTIFICATIONS: DEFAULT_ENABLE_NOTIFICATIONS,
            CONF_NOTIFICATION_COOLDOWN: DEFAULT_NOTIFICATION_COOLDOWN,
            CONF_TRACK_ATTRIBUTES: False,
            ext: [], ovr: "", ddb: 60, col: 5, exc: 60, opx: 15, opp: 120,
        }
        data.update(extra)
        return data

    @pytest.mark.asyncio
    async def test_user_schema_includes_role_fields_and_not_category_lists(self, config_flow) -> None:
        result = await config_flow.async_step_user(user_input=None)
        keys = {str(k) for k in result["data_schema"].keys()}
        for key in self._keys():
            assert any(key in k for k in keys), key
        assert not any("category_motion" in k or "category_contact" in k for k in keys)

    @pytest.mark.asyncio
    async def test_options_schema_includes_role_fields(self, options_flow) -> None:
        result = await options_flow.async_step_init(user_input=None)
        keys = {str(k) for k in result["data_schema"].keys()}
        for key in self._keys():
            assert any(key in k for k in keys), key

    @pytest.mark.asyncio
    async def test_user_rejects_bad_override_line(self, config_flow) -> None:
        _, ovr, *_ = self._keys()
        result = await config_flow.async_step_user(user_input=self._base_input(**{ovr: "sensor.test1 motion"}))
        assert result["type"] == "form" and result["errors"]["base"] == "role_overrides_invalid"

    @pytest.mark.asyncio
    async def test_user_rejects_entity_in_panic_and_exterior(self, config_flow) -> None:
        from custom_components.behaviour_monitor.const import CONF_CATEGORY_PANIC

        ext, *_ = self._keys()
        result = await config_flow.async_step_user(user_input=self._base_input(**{ext: ["binary_sensor.x"], CONF_CATEGORY_PANIC: ["binary_sensor.x"]}))
        assert result["errors"]["base"] == "role_overlap"

    @pytest.mark.asyncio
    async def test_user_rejects_full_role_override_of_exterior_door(self, config_flow) -> None:
        ext, ovr, *_ = self._keys()
        result = await config_flow.async_step_user(user_input=self._base_input(**{ext: ["binary_sensor.x"], ovr: "binary_sensor.x: motion.kitchen"}))
        assert result["errors"]["base"] == "role_overlap"

    @pytest.mark.asyncio
    async def test_user_accepts_kind_override_of_exterior_door(self, config_flow) -> None:
        ext, ovr, *_ = self._keys()
        result = await config_flow.async_step_user(user_input=self._base_input(**{ext: ["binary_sensor.x"], ovr: "binary_sensor.x: door"}))
        assert result["type"] == "create_entry"

    @pytest.mark.asyncio
    async def test_user_rejects_extended_not_below_prolonged(self, config_flow) -> None:
        *_, opx, opp = self._keys()
        result = await config_flow.async_step_user(user_input=self._base_input(**{opx: 120, opp: 120}))
        assert result["errors"]["base"] == "door_open_thresholds"

    @pytest.mark.asyncio
    async def test_options_rejects_bad_override_line(self, options_flow) -> None:
        _, ovr, *_ = self._keys()
        result = await options_flow.async_step_init(user_input=self._base_input(**{ovr: "x: y"}))
        assert result["errors"]["base"] == "role_overrides_invalid"

    @pytest.mark.asyncio
    async def test_options_clears_absent_fields(self, options_flow) -> None:
        ext, ovr, *_ = self._keys()
        user_input = self._base_input()
        user_input.pop(ext); user_input.pop(ovr)
        result = await options_flow.async_step_init(user_input=user_input)
        assert result["type"] == "create_entry"
        saved = options_flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert saved[ext] == [] and saved[ovr] == ""

    @pytest.mark.asyncio
    async def test_options_prefills_existing_values(self, options_flow, mock_config_entry) -> None:
        from custom_components.behaviour_monitor import config_flow as cf_module

        ext, ovr, ddb, col, exc, opx, opp = self._keys()
        mock_config_entry.data.update({ext: ["binary_sensor.front"], ovr: "a.b: motion", ddb: 30, col: 2, exc: 90, opx: 20, opp: 300})
        with patch.object(cf_module, "_build_data_schema", wraps=cf_module._build_data_schema) as build:
            result = await options_flow.async_step_init(user_input=None)
        assert result["type"] == "form"
        kwargs = build.call_args.kwargs
        assert kwargs["exterior_doors_default"] == ["binary_sensor.front"]
        assert kwargs["role_overrides_default"] == "a.b: motion"
        assert (kwargs["door_debounce_seconds_default"], kwargs["retrigger_collapse_seconds_default"], kwargs["excursion_window_seconds_default"]) == (30, 2, 90)
        assert (kwargs["door_open_extended_seconds_default"], kwargs["door_open_prolonged_seconds_default"]) == (20, 300)

    def test_version_is_14(self) -> None:
        assert BehaviourMonitorConfigFlow.VERSION == 14
```

Any other test in the file that passes `category_motion`/`category_contact`/`category_plug`/`category_light` in its input or asserts `category_*_default` kwargs must drop those keys (`TestPanicFields` keeps `category_panic`). A test asserting `category_overlap` for panic-vs-category-list overlap becomes a `role_overlap` assertion using the exterior list.

In `tests/test_init.py`, add to the migration test class (the one with `test_migrate_v12_to_v13_seeds_defaults`):

```python
    @pytest.mark.asyncio
    async def test_migrate_v13_to_v14_converts_lists_and_sets_flag(self) -> None:
        import custom_components.behaviour_monitor as init_module
        from custom_components.behaviour_monitor.const import (
            CONF_CATEGORY_CONTACT, CONF_CATEGORY_LIGHT, CONF_CATEGORY_MOTION, CONF_CATEGORY_PLUG,
            CONF_DOOR_DEBOUNCE_SECONDS, CONF_DOOR_OPEN_EXTENDED_SECONDS, CONF_DOOR_OPEN_PROLONGED_SECONDS,
            CONF_EXCURSION_WINDOW_SECONDS, CONF_EXTERIOR_DOORS, CONF_REBOOTSTRAP_ROLES,
            CONF_RETRIGGER_COLLAPSE_SECONDS, CONF_ROLE_OVERRIDES,
        )

        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = self._make_config_entry(version=13, data={
            "monitored_entities": ["binary_sensor.pir", "binary_sensor.door", "switch.kettle", "light.hall"],
            CONF_CATEGORY_MOTION: ["binary_sensor.pir"], CONF_CATEGORY_CONTACT: ["binary_sensor.door"],
            CONF_CATEGORY_PLUG: ["switch.kettle"], CONF_CATEGORY_LIGHT: ["light.hall"],
        })
        registry = MagicMock(); registry.async_get = lambda eid: MagicMock(device_class="door", original_device_class=None) if eid == "binary_sensor.door" else MagicMock(device_class=None, original_device_class=None)
        with patch.object(init_module.er, "async_get", return_value=registry), \
             patch.object(init_module.ir, "async_create_issue") as create:
            result = await async_migrate_entry(hass, entry)

        assert result is True
        call_args = hass.config_entries.async_update_entry.call_args
        data = call_args.kwargs["data"]
        assert call_args.kwargs["version"] == 14
        for key in (CONF_CATEGORY_MOTION, CONF_CATEGORY_CONTACT, CONF_CATEGORY_PLUG, CONF_CATEGORY_LIGHT):
            assert key not in data
        assert data[CONF_ROLE_OVERRIDES].splitlines() == [
            "binary_sensor.pir: motion", "binary_sensor.door: door", "switch.kettle: appliance", "light.hall: appliance",
        ]
        assert data[CONF_EXTERIOR_DOORS] == []
        assert (data[CONF_DOOR_DEBOUNCE_SECONDS], data[CONF_RETRIGGER_COLLAPSE_SECONDS], data[CONF_EXCURSION_WINDOW_SECONDS]) == (60, 5, 60)
        assert (data[CONF_DOOR_OPEN_EXTENDED_SECONDS], data[CONF_DOOR_OPEN_PROLONGED_SECONDS]) == (15, 120)
        assert data[CONF_REBOOTSTRAP_ROLES] is True
        assert create.call_args.args[2] == "exterior_doors_unconfirmed"
        assert create.call_args.kwargs["translation_key"] == "exterior_doors_unconfirmed"
        assert create.call_args.kwargs["is_persistent"] is True

    @pytest.mark.asyncio
    async def test_migrate_v13_to_v14_no_issue_without_contact_entities(self) -> None:
        import custom_components.behaviour_monitor as init_module

        hass = MagicMock(); hass.config_entries = MagicMock()
        entry = self._make_config_entry(version=13, data={"monitored_entities": ["binary_sensor.pir"]})
        registry = MagicMock(); registry.async_get = lambda eid: MagicMock(device_class="motion", original_device_class=None)
        with patch.object(init_module.er, "async_get", return_value=registry), \
             patch.object(init_module.ir, "async_create_issue") as create:
            assert await async_migrate_entry(hass, entry) is True
        create.assert_not_called()
        data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert data["role_overrides"] == ""

    @pytest.mark.asyncio
    async def test_migrate_v13_to_v14_survives_registry_failure(self) -> None:
        import custom_components.behaviour_monitor as init_module

        hass = MagicMock(); hass.config_entries = MagicMock()
        entry = self._make_config_entry(version=13, data={"monitored_entities": ["binary_sensor.pir"]})
        with patch.object(init_module.er, "async_get", side_effect=RuntimeError("boom")):
            assert await async_migrate_entry(hass, entry) is True
        assert hass.config_entries.async_update_entry.call_args.kwargs["version"] == 14

    @pytest.mark.asyncio
    async def test_migrate_v14_is_noop(self) -> None:
        hass = MagicMock(); hass.config_entries = MagicMock()
        entry = self._make_config_entry(version=14, data={"monitored_entities": ["sensor.test"]})
        assert await async_migrate_entry(hass, entry) is True
        hass.config_entries.async_update_entry.assert_not_called()
```

Update the existing `test_migrate_v13_is_noop` (it now migrates to 14: assert `async_update_entry` called once with `version == 14`), `test_migrate_v2_updates_version_to_13` (rename to `..._to_14`, expect 14), and any test asserting the exact `async_update_entry.call_count` for chains that now include the v14 step (add one). In the v10→v11 tests, `hass.config_entries.async_update_entry.call_count == 3` becomes `4` and the v14 tests above need `patch.object(init_module.er, ...)` only where the chain reaches v14 with monitored entities; for older-chain tests the MagicMock registry returns MagicMock device classes, which are not strings, so no issue is raised and no patch is needed.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_config_flow.py tests/test_init.py -q 2>&1 | tail -5`
Expected: failures on missing schema keys, `VERSION == 13`, and missing v14 migration.

- [ ] **Step 3: Implement**

`config_flow.py` imports: drop `CONF_CATEGORY_CONTACT/LIGHT/MOTION/PLUG` and `DEFAULT_CATEGORY_CONTACT/LIGHT/MOTION/PLUG`; add the seven `CONF_*` and seven `DEFAULT_*` keys from Task 1, plus `ROLE_KINDS`; add `from .entity_role import parse_role_overrides`.

Replace `_CATEGORY_LIST_KEYS` and `_validate_category_overrides` with:

```python
def _validate_roles(user_input: dict[str, Any]) -> str | None:
    """Return an error key when the role inputs conflict, else None."""
    try:
        overrides = parse_role_overrides(user_input.get(CONF_ROLE_OVERRIDES) or "")
    except ValueError:
        return "role_overrides_invalid"
    panic = set(user_input.get(CONF_CATEGORY_PANIC) or [])
    exterior = set(user_input.get(CONF_EXTERIOR_DOORS) or [])
    full_role = {eid for eid, value in overrides.items() if value not in ROLE_KINDS}
    if panic & exterior or full_role & (panic | exterior):
        return "role_overlap"
    extended = int(user_input.get(CONF_DOOR_OPEN_EXTENDED_SECONDS, DEFAULT_DOOR_OPEN_EXTENDED_SECONDS))
    prolonged = int(user_input.get(CONF_DOOR_OPEN_PROLONGED_SECONDS, DEFAULT_DOOR_OPEN_PROLONGED_SECONDS))
    if extended >= prolonged:
        return "door_open_thresholds"
    return None
```

`_build_data_schema`: remove the four `category_*_default` parameters and their `vol.Optional(CONF_CATEGORY_*)` entries; add parameters `exterior_doors_default: list[str] | None = None`, `role_overrides_default: str = DEFAULT_ROLE_OVERRIDES`, `door_debounce_seconds_default: int = DEFAULT_DOOR_DEBOUNCE_SECONDS`, `retrigger_collapse_seconds_default: int = DEFAULT_RETRIGGER_COLLAPSE_SECONDS`, `excursion_window_seconds_default: int = DEFAULT_EXCURSION_WINDOW_SECONDS`, `door_open_extended_seconds_default: int = DEFAULT_DOOR_OPEN_EXTENDED_SECONDS`, `door_open_prolonged_seconds_default: int = DEFAULT_DOOR_OPEN_PROLONGED_SECONDS`. Insert these entries where the category lists were (before `CONF_MOTION_DEBOUNCE_SECONDS`), and the thresholds right after it:

```python
        vol.Optional(
            CONF_EXTERIOR_DOORS,
            default=list(exterior_doors_default or DEFAULT_EXTERIOR_DOORS),
        ): EntitySelector(EntitySelectorConfig(multiple=True, domain="binary_sensor")),
        vol.Optional(
            CONF_ROLE_OVERRIDES, default=role_overrides_default
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)),
```

and after the motion debounce entry:

```python
        vol.Required(CONF_DOOR_DEBOUNCE_SECONDS, default=door_debounce_seconds_default): NumberSelector(
            NumberSelectorConfig(min=0, max=600, step=10, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
        vol.Required(CONF_RETRIGGER_COLLAPSE_SECONDS, default=retrigger_collapse_seconds_default): NumberSelector(
            NumberSelectorConfig(min=0, max=30, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
        vol.Required(CONF_EXCURSION_WINDOW_SECONDS, default=excursion_window_seconds_default): NumberSelector(
            NumberSelectorConfig(min=0, max=600, step=10, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
        vol.Required(CONF_DOOR_OPEN_EXTENDED_SECONDS, default=door_open_extended_seconds_default): NumberSelector(
            NumberSelectorConfig(min=1, max=3600, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
        vol.Required(CONF_DOOR_OPEN_PROLONGED_SECONDS, default=door_open_prolonged_seconds_default): NumberSelector(
            NumberSelectorConfig(min=1, max=86400, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="seconds")
        ),
```

Both flows: replace `elif (category_error := _validate_category_overrides(user_input)):` with `elif (role_error := _validate_roles(user_input)):` and assign `errors["base"] = role_error`. Options flow "cleared field" loop: replace `*_CATEGORY_LIST_KEYS` with `CONF_CATEGORY_PANIC, CONF_EXTERIOR_DOORS` and add after the loop:

```python
                if not user_input.get(CONF_ROLE_OVERRIDES):
                    updated_data[CONF_ROLE_OVERRIDES] = ""
```

Options prefill: drop the four `current_category_*` reads and kwargs; add `current_exterior_doors`, `current_role_overrides`, `current_door_debounce_seconds`, `current_retrigger_collapse_seconds`, `current_excursion_window_seconds`, `current_door_open_extended_seconds`, `current_door_open_prolonged_seconds` reads with their defaults and pass them as the matching `*_default` kwargs. `VERSION = 14`. `STORAGE_VERSION: Final = 14` in `const.py`.

`__init__.py`: imports add `from homeassistant.helpers import entity_registry as er, issue_registry as ir`, the seven `CONF_*`/`DEFAULT_*` keys, `CONF_REBOOTSTRAP_ROLES`, `CONTACT_DEVICE_CLASSES`. After the v13 block:

```python
    if config_entry.version < 14:
        new_data = dict(config_entry.data)
        lines = [ln for ln in (new_data.get(CONF_ROLE_OVERRIDES) or "").splitlines() if ln.strip()]
        for key, value in (
            (CONF_CATEGORY_MOTION, "motion"),
            (CONF_CATEGORY_CONTACT, "door"),
            (CONF_CATEGORY_PLUG, "appliance"),
            (CONF_CATEGORY_LIGHT, "appliance"),
        ):
            lines.extend(f"{eid}: {value}" for eid in (new_data.pop(key, None) or []))
        new_data[CONF_ROLE_OVERRIDES] = "\n".join(lines)
        new_data.setdefault(CONF_EXTERIOR_DOORS, list(DEFAULT_EXTERIOR_DOORS))
        new_data.setdefault(CONF_DOOR_DEBOUNCE_SECONDS, DEFAULT_DOOR_DEBOUNCE_SECONDS)
        new_data.setdefault(CONF_RETRIGGER_COLLAPSE_SECONDS, DEFAULT_RETRIGGER_COLLAPSE_SECONDS)
        new_data.setdefault(CONF_EXCURSION_WINDOW_SECONDS, DEFAULT_EXCURSION_WINDOW_SECONDS)
        new_data.setdefault(CONF_DOOR_OPEN_EXTENDED_SECONDS, DEFAULT_DOOR_OPEN_EXTENDED_SECONDS)
        new_data.setdefault(CONF_DOOR_OPEN_PROLONGED_SECONDS, DEFAULT_DOOR_OPEN_PROLONGED_SECONDS)
        new_data[CONF_REBOOTSTRAP_ROLES] = True
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=14)
        _LOGGER.info("Behaviour Monitor: Config entry migrated to v14 — roles replace categories; door/appliance baselines rebuild once")
        if not new_data[CONF_EXTERIOR_DOORS] and _has_contact_entity(hass, new_data.get(CONF_MONITORED_ENTITIES, [])):
            try:
                ir.async_create_issue(
                    hass, DOMAIN, "exterior_doors_unconfirmed",
                    is_fixable=False, is_persistent=True, severity=ir.IssueSeverity.WARNING,
                    translation_key="exterior_doors_unconfirmed",
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not create repair issue exterior_doors_unconfirmed")

    return True


def _has_contact_entity(hass: HomeAssistant, entity_ids: list[str]) -> bool:
    """True when any monitored entity has a contact device class in the entity registry."""
    try:
        registry = er.async_get(hass)
        for eid in entity_ids:
            entry = registry.async_get(eid)
            if entry is None:
                continue
            dc = entry.device_class or entry.original_device_class
            if isinstance(dc, str) and dc in CONTACT_DEVICE_CLASSES:
                return True
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not inspect entity registry during migration", exc_info=True)
    return False
```

Add `CONF_MONITORED_ENTITIES` to the `__init__.py` const import if missing.

`translations/en.json`: in both `config.step.user` and `options.step.init`, delete the `category_motion`, `category_contact`, `category_plug`, `category_light` entries from `data` and `data_description`; add:

```json
"exterior_doors": "Exterior doors",
"role_overrides": "Role overrides",
"door_debounce_seconds": "Door debounce window",
"retrigger_collapse_seconds": "Retrigger collapse window",
"excursion_window_seconds": "Excursion window",
"door_open_extended_seconds": "Door open: extended from",
"door_open_prolonged_seconds": "Door open: prolonged from"
```

and descriptions:

```json
"exterior_doors": "Door sensors that lead outside. Exterior doors are never inferred; every other contact sensor is an interior door. Exterior door events within the excursion window are grouped into one trip.",
"role_overrides": "One entity per line as 'entity_id: role'. Roles: motion.bathroom, motion.bedroom, motion.living, motion.kitchen, motion.transit, door.interior, door.exterior, appliance, other. A bare kind (motion, door, appliance, other) fixes the kind and lets the entity's area choose the room. Motion sensors are otherwise placed by their Home Assistant area name; panic buttons use the list below.",
"door_debounce_seconds": "Door sensors only count when they open, and repeated openings within this many seconds are merged into one activity. 0 disables merging.",
"retrigger_collapse_seconds": "Motion and door sensors often emit an off/on pair milliseconds apart. An off followed by an on within this many seconds is treated as continuously on. 0 disables.",
"excursion_window_seconds": "Exterior door events from any door within this many seconds of the first are one excursion, recorded once. 0 disables grouping.",
"door_open_extended_seconds": "A door open for at least this many seconds is classed as extended rather than brief.",
"door_open_prolonged_seconds": "A door open for at least this many seconds is classed as prolonged. Must be greater than the extended threshold."
```

Errors in both `config.error` and `options.error`: remove `category_overlap`; add `"role_overrides_invalid": "A role override line could not be read. Use 'entity_id: role', one per line."`, `"role_overlap": "An entity cannot be both a panic button and an exterior door, or have a full role override while in either list."`, `"door_open_thresholds": "The extended door-open threshold must be less than the prolonged threshold."`. Issues: add

```json
"roles_need_assignment": {
  "title": "Motion sensors without a room",
  "description": "Behaviour Monitor could not tell which room these motion sensors are in: {entity_ids}. They still count as motion, but room-based rules will not apply. Assign each entity (or its device) to a Home Assistant area whose name includes a room word (bathroom, bedroom, living, kitchen, hall, ...), or add a line such as 'binary_sensor.pir: motion.kitchen' to Role overrides in the integration options, then reload."
},
"exterior_doors_unconfirmed": {
  "title": "Confirm which doors lead outside",
  "description": "Behaviour Monitor now distinguishes exterior doors from interior ones. All of your contact sensors are currently treated as interior doors. If any lead outside, add them to Exterior doors in the integration options. If none do, dismiss this issue."
}
```

Update the `motion_debounce_seconds` description to mention doors are separate, and the `category_panic` description is unchanged. Validate the JSON with `python3 -m json.tool custom_components/behaviour_monitor/translations/en.json > /dev/null`.

- [ ] **Step 4: Run the full suite and lint**

Run: `venv/bin/python -m pytest tests/ -q` → all pass. `venv/bin/python -m ruff check custom_components/ tests/` → no new findings. `python3 -m json.tool custom_components/behaviour_monitor/translations/en.json > /dev/null` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/config_flow.py custom_components/behaviour_monitor/const.py custom_components/behaviour_monitor/__init__.py custom_components/behaviour_monitor/translations/en.json tests/test_config_flow.py tests/test_init.py
git commit -m "feat: role config fields, translations and v14 migration with one-shot door/appliance re-bootstrap

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Replay CLI, synthetic fixture and smoke test

**Files:**
- Create: `scripts/replay.py`
- Create: `tests/fixtures/replay_week.csv`, `tests/fixtures/replay_week_roles.txt`
- Create: `tests/test_replay_fixture.py`

**Interfaces:**
- Consumes: `replay`, `PipelineConfig`, `PipelineEvent` (Task 5); `parse_role_overrides`, `EntityRole` (Tasks 1–2).
- Produces: `python scripts/replay.py --events <csv> --roles <txt> [--json] [--motion-debounce N --door-debounce N --collapse N --excursion-window N --open-extended N --open-prolonged N]`; module-level `load_events(path, roles) -> list[PipelineEvent]`, `summarise(activity, doors, raw_counts) -> dict`.

The script must run under a bare interpreter with no Home Assistant installed. It loads the integration's pure modules through a stub package so `custom_components/behaviour_monitor/__init__.py` (which imports Home Assistant) is never executed.

- [ ] **Step 1: Generate the fixture**

Create `tests/fixtures/replay_week_roles.txt`:

```
binary_sensor.pir_kitchen: motion.kitchen
binary_sensor.pir_bathroom: motion.bathroom
binary_sensor.pir_hall: motion.transit
binary_sensor.door_back: door.exterior
binary_sensor.door_side: door.exterior
binary_sensor.door_lounge: door.interior
switch.teasmade: appliance
```

Generate `tests/fixtures/replay_week.csv` with this one-off script (run it from the repo root, commit the CSV, do not commit the generator):

```python
import csv
from datetime import datetime, timedelta, timezone

rows = []
base = datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc)


def add(eid, ts, state):
    rows.append((eid, ts.isoformat(), state))


for day in range(7):
    d = base + timedelta(days=day)
    # timer: 07:00 on, 07:03 off, every day
    add("switch.teasmade", d + timedelta(hours=7), "on")
    add("switch.teasmade", d + timedelta(hours=7, minutes=3), "off")
    # bathroom: 07:10 with a 23 ms retrigger pair inside it
    t = d + timedelta(hours=7, minutes=10)
    add("binary_sensor.pir_bathroom", t, "on")
    add("binary_sensor.pir_bathroom", t + timedelta(seconds=40), "off")
    add("binary_sensor.pir_bathroom", t + timedelta(seconds=40, milliseconds=23), "on")
    add("binary_sensor.pir_bathroom", t + timedelta(seconds=90), "off")
    # walk-through hall -> kitchen 07:15
    t = d + timedelta(hours=7, minutes=15)
    add("binary_sensor.pir_hall", t, "on")
    add("binary_sensor.pir_hall", t + timedelta(seconds=30), "off")
    add("binary_sensor.pir_kitchen", t + timedelta(seconds=19), "on")
    add("binary_sensor.pir_kitchen", t + timedelta(minutes=5), "off")
    # lounge door 09:00, open 8 s
    t = d + timedelta(hours=9)
    add("binary_sensor.door_lounge", t, "on")
    add("binary_sensor.door_lounge", t + timedelta(seconds=8), "off")
    # 11:00 four back/side pairs inside 60 s windows = 4 excursions, plus one prolonged side door at 15:00
    for k in range(4):
        t = d + timedelta(hours=11, minutes=6 * k)
        add("binary_sensor.door_back", t, "on")
        add("binary_sensor.door_back", t + timedelta(seconds=6), "off")
        add("binary_sensor.door_side", t + timedelta(seconds=45), "on")
        add("binary_sensor.door_side", t + timedelta(seconds=52), "off")
    t = d + timedelta(hours=15)
    add("binary_sensor.door_side", t, "on")
    add("binary_sensor.door_side", t + timedelta(minutes=3), "off")
    # evening kitchen bursts 18:00 (three on/off cycles inside 2 min = one activation)
    t = d + timedelta(hours=18)
    for k in range(3):
        add("binary_sensor.pir_kitchen", t + timedelta(seconds=30 * k), "on")
        add("binary_sensor.pir_kitchen", t + timedelta(seconds=30 * k + 10), "off")

rows.sort(key=lambda r: r[1])
with open("tests/fixtures/replay_week.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["entity_id", "last_changed", "state"])
    w.writerows(rows)
print(len(rows), "rows")
```

Expected per-day counts, derived from the pipeline rules (defaults): teasmade 2 activations (on and off both pass through); pir_bathroom 1 (the 23 ms pair collapses; the 07:10 edge counts); pir_hall 1; pir_kitchen 2 (07:15 and 18:00; the 18:00 burst debounces to one); door_lounge 1 activation, last open 8 s brief; excursions 5 (four back+side pairs, span 45 s, plus the lone 15:00 side door, span 0); door_side last open 180 s prolonged; door_back last open 6 s brief. Over seven days: teasmade 14, bathroom 7, hall 7, kitchen 14, lounge 7, excursions 35, raw rows 252 (36 per day).

- [ ] **Step 2: Write the failing smoke test**

Create `tests/test_replay_fixture.py`:

```python
"""Replay the synthetic seven-day fixture through the pipeline and the CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from custom_components.behaviour_monitor.const import DOOR_OPEN_BRIEF, DOOR_OPEN_PROLONGED
from custom_components.behaviour_monitor.entity_role import parse_role_overrides
from custom_components.behaviour_monitor.pipeline import EXCURSION, PipelineConfig, replay

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "tests" / "fixtures" / "replay_week.csv"
ROLES = ROOT / "tests" / "fixtures" / "replay_week_roles.txt"


def _load():
    sys.path.insert(0, str(ROOT / "scripts"))
    import replay as cli  # noqa: E402

    roles = {eid: value for eid, value in parse_role_overrides(ROLES.read_text()).items()}
    return cli, cli.load_events(CSV, roles)


def test_fixture_counts() -> None:
    cli, events = _load()
    assert len(events) == 252
    activity, doors = replay(events, PipelineConfig())
    per_entity: dict[str, int] = {}
    excursions = [e for e in activity if e.kind == EXCURSION]
    for e in activity:
        if e.kind != EXCURSION:
            per_entity[e.entity_id] = per_entity.get(e.entity_id, 0) + 1
    assert per_entity == {
        "switch.teasmade": 14,
        "binary_sensor.pir_bathroom": 7,
        "binary_sensor.pir_hall": 7,
        "binary_sensor.pir_kitchen": 14,
        "binary_sensor.door_lounge": 7,
    }
    assert len(excursions) == 35
    assert sum(1 for e in excursions if e.entities == ("binary_sensor.door_back", "binary_sensor.door_side")) == 28
    assert doors["binary_sensor.door_side"]["last_open_class"] == DOOR_OPEN_PROLONGED
    assert doors["binary_sensor.door_back"] == {"last_open_seconds": 6.0, "last_open_class": DOOR_OPEN_BRIEF}


def test_cli_json_runs_without_home_assistant() -> None:
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": ""}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "replay.py"), "--events", str(CSV), "--roles", str(ROLES), "--json"],
        capture_output=True, text=True, env=env, cwd=str(ROOT), check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["entities"]["binary_sensor.pir_bathroom"]["activations"] == 7
    assert out["excursions"]["count"] == 35
    assert len(out["days"]) == 7
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_replay_fixture.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'replay'`.

- [ ] **Step 4: Write the CLI**

Create `scripts/replay.py`:

```python
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
ROLE_KINDS = CONST.ROLE_KINDS


def load_roles(path: Path) -> dict[str, str]:
    """Parse the roles file; every value must be a full role, not a bare kind."""
    parsed = ENTITY_ROLE.parse_role_overrides(path.read_text())
    bad = sorted(eid for eid, value in parsed.items() if value in ROLE_KINDS)
    if bad:
        raise SystemExit(f"roles file: full roles required (not a bare kind) for: {', '.join(bad)}")
    return parsed


def load_events(path: Path, roles: dict[str, str]) -> list[Any]:
    """Read the CSV into PipelineEvents, deriving old_state per entity in time order."""
    rows: list[tuple[str, datetime, str]] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            eid = row["entity_id"].strip().lower()
            if eid not in roles:
                continue
            ts = datetime.fromisoformat(row["last_changed"].strip().replace("Z", "+00:00"))
            rows.append((eid, ts, row["state"].strip()))
    rows.sort(key=lambda r: r[1])
    prev: dict[str, str | None] = {}
    events = []
    for eid, ts, state in rows:
        events.append(PIPELINE.PipelineEvent(eid, EntityRole.from_string(roles[eid]), prev.get(eid), state, ts))
        prev[eid] = None if state in ("unavailable", "unknown") else state
    return events


def summarise(activity: list[Any], doors: dict[str, dict[str, Any]], raw_counts: Counter, roles: dict[str, str]) -> dict[str, Any]:
    per_entity: dict[str, dict[str, Any]] = {
        eid: {"role": roles[eid], "raw_rows": raw_counts.get(eid, 0), "activations": 0, **doors.get(eid, {})}
        for eid in sorted(roles)
    }
    excursions = []
    days: dict[str, int] = defaultdict(int)
    for ev in activity:
        days[ev.timestamp.date().isoformat()] += 1
        if ev.kind == PIPELINE.EXCURSION:
            excursions.append({"at": ev.timestamp.isoformat(), "entities": list(ev.entities), "span_seconds": ev.duration_seconds})
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
        print(f"{eid:40} {info['role']:18} {info['raw_rows']:6d} {info['activations']:6d}  {last}")
    print(f"\nexcursions: {summary['excursions']['count']}")
    for ex in summary["excursions"]["items"]:
        print(f"  {ex['at']}  {' + '.join(ex['entities'])}  span {ex['span_seconds']:.0f}s")
    print("\nactivity per day:")
    for day, n in summary["days"].items():
        print(f"  {day}  {n}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--roles", type=Path, required=True)
    p.add_argument("--json", action="store_true")
    p.add_argument("--motion-debounce", type=int, default=CONST.DEFAULT_MOTION_DEBOUNCE_SECONDS)
    p.add_argument("--door-debounce", type=int, default=CONST.DEFAULT_DOOR_DEBOUNCE_SECONDS)
    p.add_argument("--collapse", type=int, default=CONST.DEFAULT_RETRIGGER_COLLAPSE_SECONDS)
    p.add_argument("--excursion-window", type=int, default=CONST.DEFAULT_EXCURSION_WINDOW_SECONDS)
    p.add_argument("--open-extended", type=int, default=CONST.DEFAULT_DOOR_OPEN_EXTENDED_SECONDS)
    p.add_argument("--open-prolonged", type=int, default=CONST.DEFAULT_DOOR_OPEN_PROLONGED_SECONDS)
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
```

Note for the implementer: `tests/conftest.py` installs Home Assistant mocks and imports the real package, so inside pytest `custom_components.behaviour_monitor` is already in `sys.modules` and `_load_pure_modules` simply reuses it. The subprocess test proves the bare-interpreter path.

- [ ] **Step 5: Run the tests to verify they pass, then lint**

Run: `venv/bin/python -m pytest tests/test_replay_fixture.py tests/test_pipeline.py -q` → all pass. Run the CLI by hand once: `venv/bin/python scripts/replay.py --events tests/fixtures/replay_week.csv --roles tests/fixtures/replay_week_roles.txt` and confirm the table shows bathroom 7, kitchen 14, excursions 35. `venv/bin/python -m ruff check scripts/ tests/test_replay_fixture.py && venv/bin/python -m black scripts/replay.py tests/test_replay_fixture.py` → clean.

If the counts differ from the fixture expectations, the fixture generator and the pipeline disagree: re-derive by hand from spec §2 before changing either, and fix the one that is wrong.

- [ ] **Step 6: Commit**

```bash
git add scripts/replay.py tests/fixtures/replay_week.csv tests/fixtures/replay_week_roles.txt tests/test_replay_fixture.py
git commit -m "feat: replay CLI and synthetic seven-day fixture for the activity pipeline

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Documentation

**Files:**
- Modify: `README.md` (options table `:72-105`, Upgrading `:106-120`, Entity Categories `:328-363`, Troubleshooting `:503-508`, System Integrity `:460-485`)
- Modify: `CLAUDE.md` (File Structure)
- Modify: `docs/design/2026-09-18-detection-gap-analysis.md`
- Modify: `docs/superpowers/specs/2026-09-19-event-pipeline-roles-design.md` (§4.1: note that `panic` is rejected in overrides and duplicates are errors)

- [ ] **Step 1: README options table**

Remove the four rows "Motion sensors", "Contact sensors", "Plugs and switches", "Lights". After "Motion debounce window" add:

```markdown
| Exterior doors | Contact sensors that lead outside; never inferred. Events from exterior doors within the excursion window are grouped into one trip | Empty |
| Role overrides | One `entity_id: role` per line. Full roles (`motion.kitchen`, `door.interior`, `appliance`, ...) or bare kinds (`motion`, `door`, `appliance`, `other`) | Empty |
| Door debounce window | Merge repeated door openings within this many seconds into one activity; 0 disables (0–600) | 60 seconds |
| Retrigger collapse window | An off followed by an on within this many seconds is treated as continuously on; 0 disables (0–30) | 5 seconds |
| Excursion window | Exterior door events within this many seconds of the first are one excursion; 0 disables (0–600) | 60 seconds |
| Door open: extended from | A door open at least this long is classed `extended` rather than `brief` (1–3600) | 15 seconds |
| Door open: prolonged from | A door open at least this long is classed `prolonged`; must exceed the extended threshold (1–86400) | 120 seconds |
```

Upgrading: change "(v2 through v13)" to "(v2 through v14)" and add:

```markdown
- **v14**: Roles replace entity categories. The four category lists become lines in **Role overrides** (motion → `motion`, contact → `door`, plugs and lights → `appliance`); door and appliance baselines are rebuilt once from recorder history through the new event pipeline, so door counts drop to one per opening. A repair issue asks you to confirm which doors lead outside if you have contact sensors and no exterior doors listed.
```

- [ ] **Step 2: README Roles and Pipeline sections**

Replace `### Entity Categories` (through the weighted-welfare table and its paragraph, keeping `#### Panic Button`) with:

````markdown
### Roles

Each monitored entity is assigned a role at startup. Roles carry the semantics later rules reason about; entity ids do not.

| Role | Kind | How it is assigned |
|---|---|---|
| `motion.bathroom`, `motion.bedroom`, `motion.living`, `motion.kitchen`, `motion.transit` | motion | Motion device class, then the entity's Home Assistant area name (entity area, else its device's area) matched against room keywords |
| `motion.unassigned` | motion | A motion sensor whose area matched no keyword. Still counts as motion; a repair issue lists them |
| `door.exterior` | door | **Exterior doors** list only; never inferred |
| `door.interior` | door | Any contact device class (`door`, `window`, `opening`, `garage_door`) not in the exterior list |
| `appliance` | appliance | `outlet`/`plug` device class, or the `switch` and `light` domains |
| `panic` | panic | **Panic buttons** list only |
| `other` | other | Numeric entities and anything unrecognised |

**Inference order** (first match wins): numeric entities are `other`; the panic list; a full-role line in **Role overrides**; the exterior-door list; the kind from a bare-kind override, the device class, or the domain; then for motion the area keyword table.

**Area keywords** (case-insensitive substrings of the area name, English only; use overrides for other languages):

| Role | Keywords |
|---|---|
| `motion.bathroom` | bathroom, toilet, ensuite, en-suite, shower, wc, loo, cloakroom |
| `motion.bedroom` | bedroom, bed |
| `motion.living` | living, lounge, sitting, dining, study, office, conservatory, snug |
| `motion.kitchen` | kitchen, utility, pantry |
| `motion.transit` | hall, landing, stairs, stairway, corridor, porch, entrance, passage |

**Role overrides** take one `entity_id: value` per line. A full role fixes everything; a bare kind (`motion`, `door`, `appliance`, `other`) fixes the kind and lets the area choose the room. `panic` is not accepted here. Roles are resolved when the integration loads, so after changing an area assignment reload the integration. Each entity's role is the `role` attribute on `entity_status_summary`, and the top-level `roles` attribute counts entities per role so a missing bathroom sensor is visible at a glance.

**Weighted welfare.** The welfare status is derived from the highest-scoring active alert, where score = severity points × kind weight: motion 1.0, door 0.8, appliance 0.5, other 1.0. Severity points are LOW 1, MEDIUM 2, HIGH 3; 2.25 or more gives `alert`, 1.25 or more `concern`, otherwise `check_recommended`. These weights are an interim until per-entity entropy weighting replaces them.

### Event Pipeline

Raw state changes are not activity. After the start-up grace period and burst discard (see System Integrity), every event passes through a pure pipeline before it can count:

1. **Retrigger collapse** (motion and door roles). Sensors often emit an off/on pair milliseconds apart. An off followed by an on within the collapse window (default 5 s) is treated as continuously on.
2. **Debounce** (per entity, by kind). Only rising edges count. Motion merges repeats within 120 s, doors within 60 s. Appliances and other entities count every state change.
3. **Door open duration.** When a door closes, the time since it opened is classed `brief` (< 15 s), `extended` (15–120 s) or `prolonged` (≥ 120 s) and shown as `last_open_seconds` and `last_open_class` on that entity's `entity_status_summary` entry.
4. **Excursions** (`door.exterior` only). Exterior-door openings within 60 s of the first are one excursion, recorded once under the first door at its timestamp.

Last-seen time is updated on every raw event before the pipeline, so inactivity detection is never delayed by debounce. Recorder history is replayed through the same pipeline on first install and when upgrading to v5.3.

### Replaying History Offline

`scripts/replay.py` runs the pipeline over a CSV export without Home Assistant installed:

```bash
python scripts/replay.py --events history.csv --roles roles.txt [--json] \
  [--motion-debounce 120 --door-debounce 60 --collapse 5 --excursion-window 60 --open-extended 15 --open-prolonged 120]
```

`history.csv` has columns `entity_id,last_changed,state` (ISO 8601 timestamps). `roles.txt` uses the Role overrides format with full roles. The output lists raw rows and activations per entity, every excursion, and activity per day, so you can check that a known timer, a debounce window or a threshold behaves as expected against real data.
````

In `#### Panic Button` change "shows `category: panic`" to "shows `role: panic`". In Troubleshooting → "Motion Sensor Generates Too Many or Too Few Activities", change `shows motion. If not, add the entity to the "Motion sensors" list` to `starts with motion. If not, add a line such as binary_sensor.pir: motion to Role overrides`. In the README Features list, if it mentions categories, say roles.

- [ ] **Step 3: CLAUDE.md, gap analysis, spec note**

`CLAUDE.md` File Structure: replace the `entity_category.py` line (if present) and add:

```
├── entity_role.py        # EntityRole inference (areas, device classes, overrides), kind-weighted welfare
├── pipeline.py           # ActivityPipeline: retrigger collapse, debounce, open duration, excursions, replay()
```

and under the tree a line `scripts/replay.py  # offline replay CLI over pipeline.replay()`. Update "Testing Strategy" file count if it lists files.

`docs/design/2026-09-18-detection-gap-analysis.md`: in "Proposed decomposition → B. v5.3" mark each delivered bullet with **(done, v5.3)**, change the adjacency bullet to "Deferred to v6.0 (see D)", and add "Optional adjacency graph in options" as the first bullet of D.

Spec §4.1: append "`panic` is not accepted as an override value in either form; an entity id may appear only once, and a duplicate is an error." Spec §3.3: replace the `learn_more_url` sentence with "No `learn_more_url` until the manifest carries a real repository URL; the descriptions explain what to do."

- [ ] **Step 4: Verify and commit**

Run: `venv/bin/python -m pytest tests/ -q` (docs only; confirms nothing else moved) and `grep -n "categor" README.md CLAUDE.md` to confirm only the HACS "select Integration as the category" line and the panic-list key remain.

```bash
git add README.md CLAUDE.md docs/design/2026-09-18-detection-gap-analysis.md docs/superpowers/specs/2026-09-19-event-pipeline-roles-design.md
git commit -m "docs: roles, event pipeline and replay CLI; v14 upgrade note; gap analysis updated

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Final verification (after Task 10)

- `venv/bin/python -m pytest tests/ -q` → all pass.
- `venv/bin/python -m ruff check custom_components/ tests/ scripts/` → no findings that were not already present on `main`.
- `grep -rn "EntityCategory\|entity_category\|CATEGORY_WEIGHT\|MotionDebouncer" custom_components tests scripts` → empty.
- `python3 -m json.tool custom_components/behaviour_monitor/translations/en.json > /dev/null`.
- A bare interpreter run of `scripts/replay.py` on the fixture (no venv) prints the summary.
