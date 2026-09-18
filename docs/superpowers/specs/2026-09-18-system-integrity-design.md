# System Integrity — v5.2 Design

**Date:** 2026-09-18
**Status:** Approved for planning
**Milestone:** v5.2 (first of five from `docs/design/2026-09-18-detection-gap-analysis.md`)
**Source:** `docs/design/2026-09-18-detection-and-weighting-design.md` §System integrity, §Event pipeline stage 1, §Panic device liveness
**Builds on:** branch `feat/entity-categories` (v5.0 categories, v5.1 panic)

## Goal

Make the monitor able to tell when it is blind, and say so. Fix the four
confirmed defects: the status summary that always reads "0 OK, 0 Need
Attention", silent skipping of configured entities that no longer exist,
unqualified "ok", and invisible panic-device health. Stop restarts and
resync bursts from corrupting the baseline.

## Non-goals

- Roles, door debounce, excursions, weighting, rules, escalation levels
  (later milestones).
- Deliberate-disconnection semantics beyond surfacing `unavailable`.
- Changing what counts as a welfare alert.

## Decisions carried in

- Blind monitor reports a distinct welfare status `blind`; partial input loss
  reports `degraded` when nothing worse is happening.
- Work stacks on `feat/entity-categories`.

## Architecture

Three small pure-Python units plus coordinator wiring:

- `entity_health.py` (new): `resolve_entity_health(...)` classifies each
  monitored entity as `present` / `unavailable` / `missing` from state and
  registry facts the coordinator supplies; `qualify_welfare(...)` applies the
  blind/degraded override to a computed welfare dict.
- `panic_monitor.py` (extend): device-liveness bookkeeping per panic entity
  (`last_reported`, `battery`, `available`, `last_test`, `test_window_until`)
  and the heartbeat/reminder checks.
- `event_gate.py` (new): `EventGate` implementing the start-up grace period
  and same-second burst discard over a small buffer, HA-free.
- Coordinator: resolves health each poll, raises/clears repair issues, feeds
  the gate, qualifies welfare, and emits the corrected counts.

## 1. Entity health and repair issues

### Classification (per monitored entity, each poll and at setup)

| Condition | Health |
|---|---|
| `hass.states.get(eid)` is None **and** no entity-registry entry | `missing` |
| state exists and `state in ("unavailable", "unknown")`, or registry entry exists but no state | `unavailable` |
| otherwise | `present` |

Pure function: `resolve_entity_health(entity_ids, states: Mapping[str, str | None], in_registry: Collection[str]) -> dict[str, str]` where `states[eid]` is the raw state string or None when absent.

### Repair issues

For every `missing` entity the coordinator creates a repair issue via
`homeassistant.helpers.issue_registry.async_create_issue` with
`issue_id=f"missing_entity_{eid}"`, `is_fixable=False`,
`severity=IssueSeverity.ERROR`, `translation_key="missing_entity"`,
`translation_placeholders={"entity_id": eid}`. When the entity becomes
`present` or `unavailable` again, or is removed from the config, the issue is
deleted with `async_delete_issue`. Issues are created/deleted only on
transitions (the coordinator keeps the set of open issue ids), so a missing
entity does not spam the registry every poll.

`translations/en.json` gains:
```json
"issues": {
  "missing_entity": {
    "title": "Monitored entity {entity_id} no longer exists",
    "description": "Behaviour Monitor is configured to watch {entity_id} but it is not in Home Assistant. Restore the entity or remove it from the integration options. Until then the monitor is running blind for this entity."
  }
}
```

### Entity status payload

Each `entity_status` entry gains `health` (`present|unavailable|missing`) and
`contributing` (bool: `health == "present"` and category is not `panic`).
`status` keeps its current values (`active`/`unknown`) for `present`
entities and becomes the health value for the other two.

## 2. Qualified welfare

### Counts

`expected_entities` = monitored entities whose category is not `panic`.
`contributing_entities` = those with health `present`.
`missing_entities` / `unavailable_entities` = lists of ids.

### Status override

`qualify_welfare(welfare, contributing, expected, missing, unavailable) -> welfare`:

1. If the computed status is `alert` **and** came from a panic alert: unchanged (panic outranks everything).
2. Else if `expected > 0 and contributing == 0`: status `blind`, recommendation
   "No monitored entities are reporting. Check sensors and the integration options.",
   summary `"blind: 0 of {expected} entities reporting"`. Reasons are kept.
3. Else if `contributing < expected` and status is `ok`: status `degraded`,
   recommendation "Some monitored entities are not reporting.", summary
   `"degraded: {contributing} of {expected} entities reporting"`.
4. Else unchanged, but summary gains the suffix ` ({contributing} of {expected} reporting)`.

The welfare dict always carries `contributing_entities`, `expected_entities`,
`missing_entities`, `unavailable_entities`.

New constants: `WELFARE_BLIND = "blind"`, `WELFARE_DEGRADED = "degraded"`.

The blind override applies in the holiday/snooze path too (the safe-defaults
payload is qualified the same way), because a blind monitor on holiday is
still blind.

### Input loss lowers the score

`RoutineModel.overall_confidence(now, expected_ids=None)`: when `expected_ids`
is given, the mean is taken over `len(expected_ids)` with entities absent
from the model counting 0.0. The coordinator passes the contributing entity
ids **and** the expected count, i.e. missing/unavailable entities pull the
score down rather than being renormalised away. `learning_status` uses the
same value. `baseline_confidence` / `activity_score` in the payload therefore
drop when inputs are lost.

## 3. Status summary counter

The coordinator emits `welfare["entity_count_by_status"]` as
`{"ok": int, "attention": int, "unavailable": int, "missing": int}` where
`attention` = contributing entities with at least one active non-correlation
alert, `ok` = contributing entities with none. The per-entity alert counts that
used to live under that key move to `welfare["alert_count_by_entity"]`.

`entity_status_summary` value becomes
`f"{ok} OK, {attention} Need Attention"` plus `f", {missing} Missing"` when
missing > 0 and `f", {unavailable} Unavailable"` when unavailable > 0.

## 4. Panic device liveness

### Tracked per panic entity (in `PanicMonitor`, persisted)

| Field | Source |
|---|---|
| `available` | health from §1 is `present` |
| `last_reported` | `State.last_reported` (fallback `last_updated`) read each poll |
| `battery` | `attributes["battery_level"]` or `attributes["battery"]` if numeric, else None |
| `last_test` | set by a test press (below); persisted |
| `test_window_until` | set by the `panic_test` service; not persisted |

`PanicMonitor.update_device(entity_id, available, last_reported, battery)`
and `PanicMonitor.device_status(entity_id) -> dict`.

### Test press

Service `behaviour_monitor.panic_test` (optional `entity_id`; all panic
entities when omitted) opens a test window of `PANIC_TEST_WINDOW_SECONDS = 120`.
A rising edge inside the window is recorded as a test: `last_test = now`, the
window closes, event `behaviour_monitor_panic_tested` fires, **no**
notification and **no** panic activation. Outside the window a press is a real
panic exactly as today.

### Device-health alerts

Each poll, for each panic entity, `PanicMonitor.device_alerts(now, heartbeat, reminder)` yields:
- `available == False` → `DEVICE_HEALTH`, severity HIGH, "panic button {eid} is unavailable".
- `heartbeat` > 0 and `now - last_reported > heartbeat` → `DEVICE_HEALTH`, HIGH, "panic button {eid} has not reported for {duration}".
- `battery` is not None and `battery <= PANIC_LOW_BATTERY_PERCENT (20)` → `DEVICE_HEALTH`, MEDIUM, "panic button {eid} battery at {n}%".
- `reminder` > 0 and (`last_test` is None or `now - last_test > reminder`) → `DEVICE_HEALTH`, LOW, "panic button {eid} has not been test-pressed for {duration}" (or "has never been test-pressed").

`AlertType.DEVICE_HEALTH = "device_health"` is added. Device-health alerts go
through the ordinary notification path (severity gate and repeat interval
apply; snooze and holiday do **not** suppress them, because they are about
the equipment, not the resident) and are **excluded** from weighted welfare
scoring like correlation breaks. Any device-health alert makes the welfare
status `degraded` when it would otherwise be `ok`.

### Button and status surfaces

`entity_status` entries for panic entities include `available`, `battery`,
`last_reported`, `last_test`. The Acknowledge Panic button's attributes gain
`devices: {eid: {...device_status}}`.

## 5. Start-up grace and burst discard

`EventGate(grace_seconds, burst_threshold)`:
- `arm(now)`: sets `grace_until = now + grace_seconds`. Called at coordinator
  setup, which runs on Home Assistant start **and** on integration reload,
  the two moments that inject synthetic states.
- `submit(entity_id, old_state, new_state, now) -> None`: drops the event if
  `now < grace_until`; otherwise appends it to the current one-second bucket
  keyed by `int(now.timestamp())`.
- `flush(now) -> list[Event]`: returns the events of every bucket whose second
  is strictly earlier than `now`'s second, **omitting** any bucket in which
  `>= burst_threshold` distinct entities appear (`burst_threshold == 0`
  disables the check). Dropped buckets are counted in `dropped_bursts`.

Coordinator wiring: `_handle_state_changed` still runs the monitored /
panic / track_attributes filters, then calls `gate.submit(...)` and schedules
a flush with `self.hass.loop.call_later(1.0, self._flush_gate)` if none is
pending. `_flush_gate` processes each returned event through the existing
path (last-seen update, debounce, record, correlation, daily count) using the
event's original timestamp, then requests one refresh. Panic events bypass
the gate entirely. The gate is HA-free and unit-tested on its own.

Configuration: `startup_grace_seconds` (0–300, default 90; 0 disables),
`burst_discard_threshold` (0–10, default 3; 0 disables).

## 6. Config and migration

| Key | Type | Default | UI |
|---|---|---|---|
| `startup_grace_seconds` | int | 90 | NumberSelector 0–300 step 10, seconds |
| `burst_discard_threshold` | int | 3 | NumberSelector 0–10 step 1 |
| `panic_heartbeat_hours` | int | 24 | NumberSelector 0–168 step 1, hours (0 disables) |
| `panic_test_reminder_days` | int | 30 | NumberSelector 0–365 step 1, days (0 disables) |

Config entry and `STORAGE_VERSION` become **13**; the migration seeds the four
defaults. Storage gains `panic_state[*].last_test` and the panic device
fields; the pass-through store migration handles the version bump.

## 7. Docs

README: "System integrity" section (health, repair issues, blind/degraded,
summary counts, panic device liveness and the test service, start-up grace
and burst discard); four configuration rows; services rows for `panic_test`;
v13 upgrade bullet. Translations for the four fields and the repair issue.
PROJECT/ROADMAP/STATE for v5.2.

## 8. Testing (all HA-free)

- `entity_health`: every classification row; qualify_welfare precedence
  (panic > blind > degraded > ok suffix); counts and lists.
- `event_gate`: grace drops, bucket-by-second, burst threshold at exactly N
  distinct entities, threshold 0 disables, same entity repeated in one second
  is one distinct entity, flush returns only completed seconds, dropped count.
- `panic_monitor`: update_device/device_status round trip; each device alert
  condition and its severity; test window opens/closes; press inside window
  records a test and does not activate; persistence of `last_test`.
- `routine_model`: `overall_confidence(expected_ids=...)` counts absent as 0.
- Coordinator: health resolved from states/registry; repair issue created once
  on missing and deleted on return; blind status when nothing contributes
  (including holiday path); degraded on partial loss; confidence drops with
  missing entities; counts emitted with the new shape and the sensor renders
  them; panic press inside a test window is a test; device-health alerts
  reach `_handle_alerts` and set degraded; gate wiring: events buffered and
  flushed, grace period respected, burst dropped, panic bypasses.
- Sensor: summary value from the new counts; welfare attrs include the new
  fields.
- Config flow / migration: four fields, v12 → v13 seeds, v13 no-op, chain
  counts +1.
- `__init__`: `panic_test` service registered/removed.

## Decisions log

| Decision | Choice |
|---|---|
| Blind reporting | Distinct `blind` status; `degraded` for partial loss or device-health alerts |
| Panic vs blind precedence | Panic alert outranks blind; blind outranks everything else |
| Score under input loss | Mean over expected entities with absent = 0 (no renormalisation) |
| Repair issues | One per missing entity, created/deleted on transitions only |
| Burst discard | One-second buffer keyed by wall-clock second, threshold 3 distinct entities, panic bypasses |
| Grace period | Armed at coordinator setup (covers HA start and reload), default 90 s |
| Device-health alerts | Own alert type; ordinary notification path minus snooze/holiday; excluded from welfare scoring; force `degraded` |
| Test press | `panic_test` service opens a 120 s window; press inside is recorded, not alerted |
