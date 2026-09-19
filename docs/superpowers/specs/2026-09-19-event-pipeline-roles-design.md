# Event Pipeline and Roles — v5.3 Design

**Date:** 2026-09-19
**Status:** Approved for planning
**Milestone:** v5.3 (second of five from `docs/design/2026-09-18-detection-gap-analysis.md`)
**Source:** `docs/design/2026-09-18-detection-and-weighting-design.md` §Entity model, §Event pipeline stages 2–4, §Door open duration, §Replay testing
**Builds on:** branch `feat/entity-categories` (v5.0 categories, v5.1 panic, v5.2 system integrity)

## Goal

Give every monitored entity a semantic role so later rules can reason about
"a bathroom motion sensor" or "an exterior door" instead of an entity id.
Turn raw state changes into activity events through a pure, replayable
pipeline: retrigger collapse, per-kind debounce, door open-duration
classification and exterior-door excursion grouping. Make recorder history
replayable offline through the same code the live path uses.

## Non-goals

- Adjacency graph, transit timing, derived sleep or active windows, away
  state, rules 1–6, escalation levels, per-level notification targets
  (v6.0 and v6.1).
- Entropy weighting (v5.4). Per-kind welfare weights stay as an interim.
- Changing the event gate (v5.2 stage 1). The pipeline composes it.
- Deriving room roles from anything other than the Home Assistant area
  registry and explicit overrides.
- Any consumer of door open-duration classes beyond status attributes and
  the activity-event stream.

## Decisions carried in

- Roles are inferred from Home Assistant areas and device classes, with an
  exterior-door list and a per-entity override map as the only manual input.
- Adjacency is deferred to v6.0.
- Upgrade re-bootstraps door and appliance baselines from recorder history
  through the new pipeline; motion baselines are kept.
- Roles replace categories entirely. A role's kind takes over every job a
  category does today.
- The pipeline is a new pure module that composes, not absorbs, `EventGate`.

## Architecture

Two pure-Python modules plus coordinator, config-flow and migration wiring:

- `entity_role.py` (renames `entity_category.py`): `EntityRole` inference
  from panic list, overrides, exterior list, device class and area name;
  `derive_weighted_status(...)` keyed by role kind. `MotionDebouncer` is
  removed from this module.
- `pipeline.py` (new): `ActivityPipeline` turning gated state events into
  `ActivityEvent`s through retrigger collapse, debounce, open-duration
  classification and excursion grouping. Also `replay(...)`, a convenience
  that drives one pipeline over a sorted event list with a final flush.
- `scripts/replay.py` (new): command-line harness over `replay(...)` that
  reads a recorder CSV export. Imports nothing from Home Assistant.
- `coordinator.py`: supplies area names alongside device classes, feeds
  gated events to the pipeline, consumes activity events uniformly, runs
  the one-shot role re-bootstrap, and raises the two role repair issues.
- `config_flow.py`, `const.py`, `__init__.py`, `strings.json`,
  `translations/en.json`: new fields, removed fields, v13 → v14 migration.

Data flow on the live path:

```
state_changed
  → coordinator: panic short-circuit, attribute filter
  → EventGate.submit / flush             (v5.2, unchanged)
  → coordinator: last_seen[eid] = ts      (before the pipeline, always)
  → ActivityPipeline.submit(event) / flush(now)
  → for each ActivityEvent:
        routine_model.record(...)
        correlation_detector.record_event(...)
        today_count += 1
```

## 1. Role model

### 1.1 `EntityRole`

`EntityRole` replaces `EntityCategory` in `const.py`. Values are the dotted
strings from the design document plus one fallback for motion without a
room and the existing catch-all:

| Role | Kind | Notes |
|---|---|---|
| `motion.bathroom` | motion | |
| `motion.bedroom` | motion | |
| `motion.living` | motion | |
| `motion.kitchen` | motion | |
| `motion.transit` | motion | hall, landing, stairs |
| `motion.unassigned` | motion | motion sensor with no recognised area |
| `door.exterior` | door | exterior-door list only; never inferred |
| `door.interior` | door | default for every contact class, windows included |
| `appliance` | appliance | replaces `plug` and `light` |
| `panic` | panic | panic list only; unchanged from v5.1 |
| `other` | other | numeric entities and anything unrecognised |

`EntityRole.kind` returns the part before the dot, or the whole value when
there is none. `EntityRole.from_string(value)` accepts a role value and
raises `ValueError` otherwise. `ROLE_KINDS` is the frozenset of kinds.

Every place that today checks `EntityCategory.MOTION` checks
`role.kind == "motion"`; `EntityCategory.PANIC` becomes
`role is EntityRole.PANIC`. `CATEGORY_WEIGHT` becomes `KIND_WEIGHT`:

| Kind | Weight |
|---|---|
| motion | 1.0 |
| door | 0.8 |
| appliance | 0.5 |
| other | 1.0 |

Panic never reaches weighted scoring, as today. These weights are the
interim until v5.4 replaces them with per-entity entropy.

### 1.2 Inference

`infer_roles(entity_ids, panic, exterior_doors, overrides, device_classes,
area_names, numeric_entities) -> dict[str, EntityRole]` in `entity_role.py`.
Pure; the coordinator supplies every mapping. `overrides` maps entity id to
a string that is either a full role value or a bare kind. Precedence per
entity, first match wins:

1. Numeric entity → `other`.
2. In the panic list → `panic`.
3. Override names a full role → that role.
4. In the exterior-door list → `door.exterior`.
5. Kind is decided by, in order: an override naming a bare kind; the
   registry device class (motion classes → motion, contact classes → door,
   outlet/plug classes → appliance); the domain (`switch` and `light` →
   appliance). No match → `other`.
6. Kind `door` → `door.interior`. Kind `appliance` → `appliance`.
   Kind `motion` → the area lookup in 1.3.

An override naming a full role that conflicts with the exterior-door list
is rejected at config-flow validation, so step 3 and step 4 cannot disagree
at runtime.

### 1.3 Area lookup

`AREA_ROLE_KEYWORDS` in `const.py` maps each motion room role to a tuple of
lower-case keywords:

| Role | Keywords |
|---|---|
| `motion.bathroom` | bathroom, toilet, ensuite, en-suite, shower, wc, loo, cloakroom |
| `motion.bedroom` | bedroom, bed |
| `motion.living` | living, lounge, sitting, dining, study, office, conservatory, snug |
| `motion.kitchen` | kitchen, utility, pantry |
| `motion.transit` | hall, landing, stairs, stairway, corridor, porch, entrance, passage |

The area name is lower-cased and each keyword tested as a substring, in
table order; the first role with a hit wins. A name that matches nothing,
or no area at all, gives `motion.unassigned`. The table is English only.
Deployments in other languages use the override map, which is why the map
accepts full roles.

The coordinator's `_registry_area_names()` returns the area name per
monitored entity: the entity-registry entry's `area_id` first, falling
back to its device's `area_id`, resolved through the area registry. Any
lookup failure yields `None`. This sits beside the existing
`_registry_device_classes()` and follows its error handling.

### 1.4 What `motion.unassigned` means

It is a motion sensor for every purpose in this milestone: motion debounce,
weight 1.0, welfare, retrigger collapse. It only loses room-specific rules
in v6.0. It is surfaced through the repair issue in §3.3 and the `role`
attribute in status so the gap is never silent.

## 2. Pipeline

### 2.1 Types

```python
@dataclass(frozen=True)
class PipelineEvent:
    entity_id: str
    role: EntityRole
    old_state: str | None
    new_state: str
    timestamp: datetime

@dataclass(frozen=True)
class ActivityEvent:
    entity_id: str          # first entity for an excursion
    role: EntityRole
    timestamp: datetime
    kind: str               # "activation" | "excursion"
    entities: tuple[str, ...] = ()   # excursion members, in order
    duration_seconds: float | None = None  # excursion span
```

Open-duration classes are not carried on `ActivityEvent`; they are
recorded per entity (§2.5) because the close edge arrives after the
activation has already been emitted.

### 2.2 `ActivityPipeline`

```python
class ActivityPipeline:
    def __init__(self, config: PipelineConfig) -> None: ...
    def submit(self, event: PipelineEvent) -> list[ActivityEvent]: ...
    def flush(self, now: datetime, *, force: bool = False) -> list[ActivityEvent]: ...
    def door_status(self, entity_id: str) -> dict[str, Any]: ...
```

`PipelineConfig` is a frozen dataclass with `motion_debounce_seconds`,
`door_debounce_seconds`, `retrigger_collapse_seconds`,
`excursion_window_seconds`, `door_open_extended_seconds`,
`door_open_prolonged_seconds`. Zero disables the stage it names.

State is in-memory only. After a restart the first rising edge for every
entity counts, matching the v5.0 debouncer.

### 2.3 Stage order and eligibility

| Stage | Applies to | Emits |
|---|---|---|
| Retrigger collapse | binary motion and door roles | nothing; may discard |
| Debounce | binary motion and door roles | one activation per counted rising edge |
| Open duration | door roles | nothing; updates `door_status` |
| Excursion grouping | `door.exterior` | one excursion per window, on flush |

Everything else passes through: a numeric entity, an `appliance`, or an
`other` entity emits one activation per `submit`, with no debounce, exactly
as v5.0 counted them. Panic events never reach the pipeline. Binary-ness
is decided by `is_binary_state(new_state)` from `routine_model.py`, as
today; `unavailable` and `unknown` states reset that entity's edge tracking
and emit nothing, matching the bootstrap rule in v5.0.

### 2.4 Retrigger collapse and debounce

For a binary motion or door entity:

- An **off edge** (on → not-on) is held as pending with its timestamp. It is
  not emitted.
- An **on edge** (not-on → on, or first sighting on) arriving while an off is
  pending and within `retrigger_collapse_seconds` of it discards the pending
  off and is itself discarded: the entity is treated as continuously on.
- An on edge arriving after the collapse window, or with no pending off,
  first confirms any pending off (§2.5) and then goes to debounce.
- Debounce counts the on edge only if at least `motion_debounce_seconds`
  (motion) or `door_debounce_seconds` (door) have elapsed since the last
  counted edge for that entity. Counted edges emit an activation and, for
  `door.exterior`, enter excursion grouping instead (§2.6).
- `flush(now)` confirms every pending off older than the collapse window.
  `force=True` confirms all pending offs regardless of age.

### 2.5 Door open duration

When an off edge is confirmed for a door role, the open interval runs from
the timestamp of the most recent on edge for that entity, whether debounce
counted it or not, to the confirmed off. Debounce decides what counts as
activity; it must not stretch a later re-open back to an earlier one. If no
on edge has been seen (the entity was already open at start), nothing is
recorded. Duration is classified:

| Class | Condition |
|---|---|
| `brief` | duration < `door_open_extended_seconds` |
| `extended` | extended ≤ duration < `door_open_prolonged_seconds` |
| `prolonged` | duration ≥ `door_open_prolonged_seconds` |

`door_status(entity_id)` returns `{"last_open_seconds": float | None,
"last_open_class": str | None}`; both `None` until the first close.

### 2.6 Excursion grouping

A counted `door.exterior` activation that arrives while no excursion is
open starts one, anchored at that activation's entity and timestamp. Any
further counted `door.exterior` activation from any entity within
`excursion_window_seconds` of the anchor joins the excursion and is not
emitted. On `flush(now)`, an excursion whose anchor is older than the
window is emitted as one `ActivityEvent(kind="excursion")` with `entities`
in arrival order and `duration_seconds` equal to the span from the anchor
to the last member (0.0 for a single door). `force=True` emits an open
excursion immediately. With the window set to 0, every counted
exterior-door edge emits an ordinary activation.

### 2.7 `replay`

```python
def replay(
    events: Iterable[PipelineEvent], config: PipelineConfig
) -> tuple[list[ActivityEvent], dict[str, dict[str, Any]]]
```

Sorts by timestamp, submits each event, calls `flush(ts)` after each
submit so time-dependent stages advance, ends with a forced flush, and
returns the activity events plus `door_status` per door entity. Both the
recorder bootstrap and the CLI use it.

## 3. Coordinator wiring

### 3.1 Live path

`_process_activity` is replaced. `_flush_gate` sets `last_seen` for every
kept and dropped gated event, then submits kept events to the pipeline,
then calls `pipeline.flush(now)`, then consumes the returned activity
events. `_async_update_data` also calls `pipeline.flush(now)` at the top of
each sixty-second cycle and consumes the result, so a pending off or an
open excursion cannot wait longer than one poll. `async_shutdown` force-
flushes the gate, then force-flushes the pipeline, then unsubscribes.

Consuming an activity event: `routine_model.record(entity_id, timestamp,
"on", True)` for binary activations and excursions, or the actual state
value and numeric flag for pass-through entities; `correlation_detector.
record_event(entity_id, timestamp, last_seen)`; `today_count += 1`. An
excursion records once, under its first entity. A refresh is requested
only when at least one activity event was consumed, keeping the v5.0
"dropped events wait for the poll" behaviour.

### 3.2 Bootstrap and re-bootstrap

`_bootstrap_from_recorder` builds one `PipelineEvent` per recorder state
row (skipping panic entities and `unavailable`/`unknown` rows as today),
runs `replay(...)` once over all targets together so cross-entity
excursion grouping works, and records the activity events. `door_status`
from the replay seeds the live pipeline's per-entity door status.

`_rebootstrap_role_entities` mirrors `_rebootstrap_motion_entities`: runs
once when `CONF_REBOOTSTRAP_ROLES` is present on the entry, drops routine
and correlation state for every entity whose role kind is `door` or
`appliance`, replays recorder history for those entities, saves, and
removes the flag. Motion, drift and last seen are kept.
`_rebootstrap_motion_entities` and `CONF_REBOOTSTRAP_MOTION` remain for
entries that skipped v11.

### 3.3 Repair issues

Both use the existing `_refresh_health` seeding and diffing so reloads do
not orphan them. Both are `is_fixable=False`, severity warning, with a
`learn_more_url` to the README roles section.

- `roles_need_assignment`: wanted while any monitored entity resolves to
  `motion.unassigned`. Placeholder `entity_ids` is the comma-separated
  list. Deleted when none remain.
- `exterior_doors_unconfirmed`: created by the v14 migration in
  `__init__.py` when the migrated entry has at least one entity whose
  registry device class is a contact class and `exterior_doors` is empty.
  Never re-created by the coordinator; the user dismisses it. An
  all-interior deployment is legitimate.

### 3.4 Status

`entity_status_summary` per-entity entries replace `category` with `role`
and, for door roles, add `last_open_seconds` and `last_open_class`. A new
top-level attribute `roles` maps each role value to its entity count,
including zeros, so a missing bathroom sensor is visible at a glance. The
welfare payload is unchanged.

## 4. Config and migration

### 4.1 Keys

Removed: `category_motion`, `category_contact`, `category_plug`,
`category_light`. Kept unchanged: `category_panic`,
`motion_debounce_seconds`. Added:

| Key | Selector | Range | Default |
|---|---|---|---|
| `exterior_doors` | entity, multiple | | `[]` |
| `role_overrides` | text, multiline | | `""` |
| `door_debounce_seconds` | number, box | 0–600 | 60 |
| `retrigger_collapse_seconds` | number, box | 0–30 | 5 |
| `excursion_window_seconds` | number, box | 0–600 | 60 |
| `door_open_extended_seconds` | number, box | 1–3600 | 15 |
| `door_open_prolonged_seconds` | number, box | 1–86400 | 120 |

`role_overrides` is stored as the raw text. Parsing lives in
`entity_role.py` as `parse_role_overrides(text) -> dict[str, str]`: one
`entity_id: value` per line, blank lines and `#` comments ignored, entity
id lower-cased and stripped, value validated against role values and
kinds. It raises `ValueError` naming the offending line.

### 4.2 Validation

`_validate_roles(user_input)` returns an error key or `None`, checked in
both the config and options flows alongside the existing validators:

- `role_overrides_invalid`: a line fails to parse.
- `role_overlap`: an entity appears in more than one of the panic list, the
  exterior-door list, or the override map with a full role.
- `door_open_thresholds`: extended is not strictly less than prolonged.

### 4.3 Migration v13 → v14

In `async_migrate_entry`:

1. Build override lines from the four old lists: each motion entry becomes
   `<eid>: motion`, contact → `door`, plug and light → `appliance`. Append
   to any existing `role_overrides` text (there is none on a v13 entry, but
   the code is idempotent).
2. Drop the four old keys. Seed every new key with its default.
3. Set `CONF_REBOOTSTRAP_ROLES = True`.
4. Raise `exterior_doors_unconfirmed` per §3.3 if applicable.
5. Update the entry to version 14. `STORAGE_VERSION` becomes 14;
   `_async_migrate_func` still passes data through unchanged.

`config_flow.py` `VERSION = 14`.

## 5. Replay CLI

`scripts/replay.py`, runnable as `python scripts/replay.py --events
history.csv --roles roles.txt [--motion-debounce 120 ...]`:

- `--events`: CSV with columns `entity_id,last_changed,state`, any order;
  ISO 8601 timestamps. This is the shape of a Home Assistant history export
  and of `recorder.state_changes_during_period` rows written out by the
  developer.
- `--roles`: the same format as `role_overrides`, but every entity must
  resolve to a full role, since there is no registry to infer from.
- One flag per `PipelineConfig` field, defaulting to the same values as
  `const.py`.
- Output: per entity, counts of raw rows, activations and, for doors, open
  classes; a list of excursions with members and span; a per-day table of
  activations. `--json` prints the same as JSON.

The script adds `custom_components` to `sys.path` and imports only
`entity_role`, `pipeline` and `const`. It must run under a bare Python
interpreter with no Home Assistant installed.

## 6. Docs

- README: replace the Entity Categories section with Roles (table from
  §1.1, inference order from §1.2, keyword table from §1.3, override map
  format, what `motion.unassigned` means), add a Pipeline section (four
  stages, defaults, how to read `last_open_class` and excursions), add a
  Replay section for the CLI, and the v14 line under version history.
- README options table: remove the four category rows, add the seven new
  rows.
- `docs/design/2026-09-18-detection-gap-analysis.md`: mark row B items
  delivered here; move adjacency to D.
- `CLAUDE.md` file structure: add `entity_role.py`, `pipeline.py`,
  `scripts/replay.py`; remove `entity_category.py`.

## 7. Testing (all HA-free unless stated)

- `test_entity_role.py` (replaces `test_entity_category.py`): kind and
  weight per role; each precedence step in §1.2 with a case that only that
  step decides; area keyword table incl. case, substring and no-area;
  `parse_role_overrides` valid, comment, blank, bad entity, bad value;
  `derive_weighted_status` by kind.
- `test_pipeline.py`: pass-through for numeric, appliance, other; motion
  rising edge only; door rising edge only; motion 120 s and door 60 s
  debounce; retrigger collapse discards both edges inside the window and
  neither outside; a collapsed off does not close the open interval; open
  duration class boundaries at exactly 15 s and 120 s; no class when open
  at start; excursion grouping across two doors inside the window, one
  outside, single-door excursion span 0, window 0 disables; flush versus
  force flush for pending offs and open excursions; `unavailable` resets
  edge tracking; `replay` ordering and final flush; each stage disabled by
  zero.
- `test_replay_fixture.py`: replays `tests/fixtures/replay_week.csv` (a
  synthetic seven-day trace with a known timer, a bathroom pattern, a
  retrigger pair and four excursion pairs) and asserts per-entity
  activation counts, class counts and excursion count.
- `test_coordinator.py` (mock HA, as today): area names resolved via
  entity then device; pipeline events consumed into routine, correlation
  and daily count; excursion records once; last seen set before the
  pipeline; flush on poll; shutdown order gate → pipeline → unsubscribe;
  `roles_need_assignment` created and deleted; `roles` attribute; door
  status attributes.
- `test_init.py`: v13 → v14 migration converts each list, seeds defaults,
  sets the flag, raises `exterior_doors_unconfirmed` only when a contact
  entity exists and the list is empty; re-bootstrap drops door and
  appliance state only and clears the flag.
- `test_config_flow.py`: each validation error; new fields round-trip
  through the options flow.
- `scripts/replay.py` gets a smoke test that runs it in a subprocess on
  the fixture with `--json` and checks the exit code and one count.

## Decisions log

- Roles replace categories; kind is the derived grouping. One lookup
  everywhere.
- Windows are `door.interior` by default. Only `door.exterior` gets
  special treatment in this milestone, so the distinction costs nothing.
- Appliances keep counting every state change without debounce. Changing
  that is a v5.4 weighting question.
- Open-duration class is per-entity state, not an event field, because the
  close arrives after the activation was emitted.
- An excursion is recorded in the routine model once, under its first
  door, at the anchor timestamp.
- The exterior-door repair issue is raised once by migration and never by
  the coordinator, so an all-interior deployment is not nagged.
- Adjacency graph deferred to v6.0, where its first consumer lives.
- Re-bootstrap covers door and appliance entities only; motion event
  semantics did not change.
