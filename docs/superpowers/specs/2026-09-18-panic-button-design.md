# Panic Button Category with Instant Alert and Acknowledgement — v5.1 Design

**Date:** 2026-09-18
**Status:** Approved for planning
**Milestone:** v5.1
**Builds on:** `2026-09-18-entity-categories-design.md` (v5.0), branch `feat/entity-categories`

## Goal

Let a user nominate one or more binary sensors as panic buttons. A press
notifies immediately, bypassing every suppression, and keeps re-notifying at
a configurable interval until someone acknowledges it. Releasing the button
clears the alert and the acknowledgement.

## Non-goals

- Inferring panic from a device class or domain. Panic is override-list only.
- Stateless `event` / `button` domain entities. Only binary sensors with an
  `on` / `off` state are supported.
- A per-entity acknowledgement UI. The button entity acknowledges all active
  panics; the service accepts an optional entity_id.
- Exact-second re-notification timing. Re-notification rides the existing
  60-second poll, so the interval has up to 60 s of jitter.
- Changing any existing alert, suppression or welfare behaviour for
  non-panic entities.

## Background

All alerts today originate from the 60-second poll in
`_async_update_data` → `_run_detection` → `_handle_alerts`, and every
notification passes the enable-notifications toggle, holiday mode, snooze,
the minimum severity gate and the per-alert repeat interval. There is no
acknowledgement concept. v5.0 introduced `EntityCategory` with override
lists, which this feature extends.

## Architecture

A new pure-Python module `custom_components/behaviour_monitor/panic_monitor.py`
owns the panic state machine (`PanicMonitor`). The coordinator gains a
dedicated branch in `_handle_state_changed` for panic entities, two additions
to the poll (panic alerts and due re-notifications), an `async_acknowledge_panic`
method, and persistence of the monitor state. A new `button.py` platform
exposes one acknowledge button; `__init__.py` registers an
`acknowledge_panic` service. `entity_category.py` learns the `PANIC` value
but never infers it.

## 1. Category and config

### Category

`EntityCategory` gains `PANIC = "panic"`. `infer_categories` assigns it only
from the override mapping; `_category_for_device_class` and the domain
fallback never return it. `CATEGORY_WEIGHT` does not include PANIC because
panic alerts bypass weighted scoring (see §3); `derive_weighted_status` must
skip alerts of type `PANIC` so an unknown-weight lookup can never occur.

Panic entities are excluded from: routine model recording, tier
classification, correlation detection, motion debounce, last-seen updates,
and recorder bootstrap / re-bootstrap. They remain in `monitored_entities`
and appear in `entity_status` with `category: "panic"`.

### New config keys

| Key | Type | Default | UI |
|---|---|---|---|
| `category_panic` | list[str] | `[]` | EntitySelector(multiple) after `category_light` |
| `panic_renotify_minutes` | int | `5` | NumberSelector 1–60 step 1, minutes, after `motion_debounce_seconds` |

`category_panic` joins the existing category overlap validation
(`category_overlap` error) and the cleared-selector normalisation.

Config entry version and `STORAGE_VERSION` become **12**.

## 2. `PanicMonitor`

```
PanicMonitor()
    .press(entity_id: str, now: datetime) -> bool
        Mark active from `now`, unacknowledged, last_notified = now.
        Returns True only if the entity was not already active.
    .release(entity_id: str) -> None
        Remove the entity entirely (clears acknowledgement too). No-op if absent.
    .acknowledge(now: datetime, entity_id: str | None = None) -> list[str]
        Mark the named entity, or every active entity, acknowledged.
        Returns the entity ids that changed from unacknowledged to acknowledged.
    .due(now: datetime, interval: timedelta) -> list[str]
        Active, unacknowledged entities whose last_notified is at least
        `interval` ago (exactly `interval` counts). Stamps last_notified = now
        on the returned entities only.
    .active() -> list[tuple[str, datetime, bool]]
        (entity_id, active_since, acknowledged) for every active entity,
        ordered by active_since.
    .is_active(entity_id) -> bool
    .to_dict() -> dict / PanicMonitor.from_dict(dict)
        Persist active_since, acknowledged, last_notified per entity as ISO
        strings. from_dict drops entries whose timestamps fail to parse.
```

Pure stdlib; no Home Assistant imports. Timestamps are whatever the
coordinator passes (`dt_util.now()`, tz-aware in HA).

## 3. Coordinator flow

### State-changed handler

For an entity whose category is `PANIC`, a dedicated branch runs
**before** the track_attributes filter and before any last-seen update:

- `new_state.state == "on"` and old state not `on` (None counts as not on):
  `pressed = monitor.press(eid, now)`. If `pressed`: send a panic
  notification for `[eid]`, then `await self._save_data()` and request a
  refresh.
- `new_state.state == "off"`: `monitor.release(eid)`, save, request refresh.
- Any other transition (attribute-only, unavailable, unknown): ignored.
- The branch always returns; panic entities never reach the routine model,
  correlation detector, daily count or last-seen.

Because `_handle_state_changed` is a sync callback, the notification and
save are scheduled with `self.hass.async_create_task(...)`.

### Poll (`_async_update_data`)

Two additions that run **regardless** of holiday mode or snooze:

1. `_panic_alerts(now)`: one `AlertResult` per active entity:
   `alert_type=AlertType.PANIC`, `severity=HIGH`, `confidence=1.0`,
   `explanation=f"{eid}: PANIC button pressed {format_duration(elapsed)} ago"`,
   `details={"acknowledged": bool, "active_since": iso}`.
2. `_renotify_panic(now)`: `due = monitor.due(now, timedelta(minutes=renotify))`;
   if non-empty, send a panic notification for `due` and save.

When holiday mode or snooze is active, `_async_update_data` returns
`_build_safe_defaults()` **augmented** with the panic alerts and the forced
welfare (below), so the sensors still show the panic. Otherwise the panic
alerts are appended to the detection results before `_handle_alerts` and
`_build_sensor_data`.

`_handle_alerts` filters `PANIC` alerts out before its suppression and
notification logic, so panic never writes to `_alert_suppression` or
`_notification_cooldowns` and is never re-sent through the ordinary path.
The welfare debounce is bypassed for panic: `_current_welfare_status` is set
to `alert` immediately when any panic is active.

### Welfare

`_derive_welfare` checks the alert list for any `PANIC` alert first. If
present: `status="alert"`, `recommendation="Panic button pressed. Respond now."`,
reasons include the panic explanations first, `entity_count_by_status`
counts them. Otherwise the existing weighted path runs on the non-panic,
non-correlation alerts unchanged.

### Panic notification

`_send_panic_notification(entity_ids, now)`:
- title `"Behaviour Monitor: PANIC"`
- message one line per entity: `"- PANIC: <entity_id> pressed <duration> ago"`
  (`"just now"` when under a minute)
- persistent notification id `"behaviour_monitor_panic"` (distinct from
  `"behaviour_monitor"`)
- sent to every configured notify service as well
- ignores `_enable_notifications`, holiday mode, snooze, the severity gate and
  the repeat interval
- updates `_last_notification_info` with type `"panic"`

### Acknowledge

`async_acknowledge_panic(entity_id: str | None = None) -> None` on the
coordinator: `changed = monitor.acknowledge(now, entity_id)`; if `changed`,
save the store, fire `behaviour_monitor_panic_acknowledged` with
`{"entity_ids": changed}`, and request a refresh. Acknowledged entities stop
re-notifying but stay in the alert list and keep welfare at `alert` until
released.

Surfaces:
- Service `behaviour_monitor.acknowledge_panic` with optional `entity_id`
  (string), registered in `__init__.py` alongside the others and removed on
  unload.
- New `button.py` platform (`Platform.BUTTON` added to `PLATFORMS`) with one
  `AcknowledgePanicButton(CoordinatorEntity, ButtonEntity)`: unique id
  `f"{entry.entry_id}_acknowledge_panic"`, name "Acknowledge Panic", icon
  `mdi:alarm-light-off`, same `DeviceInfo` as the switch. `async_press` calls
  `coordinator.async_acknowledge_panic()`. Extra attributes: `active_panics`
  (list of entity ids) and `unacknowledged` (count).

### Persistence

`_save_data` writes `"panic_state": self._panic_monitor.to_dict()`;
`async_setup` restores it when present. On restart with a button still
held, the alert and re-notification loop resume from the stored timestamps.
On setup, restored panic entries whose live entity state is not `on` are released.

### Sensor data

`entity_status` entries for panic entities carry `category: "panic"` and a
`panic_active: bool`. The top-level payload gains
`"panic": {"active": [entity ids], "unacknowledged": [entity ids]}` so
dashboards can read it; the safe-defaults payload includes the same key.

## 4. Migration, docs, release

### Migration v11 → v12

`setdefault(category_panic, [])`, `setdefault(panic_renotify_minutes, 5)`,
bump to 12. No re-bootstrap flag. Chained tests gain one more step.
`STORAGE_VERSION = 12` loads through `BehaviourMonitorStore._async_migrate_func`.

### Docs

- README: "Panic Button" subsection under Entity Categories; two
  configuration-table rows; a services-table row for `acknowledge_panic`;
  a control-entity row for the acknowledge button; a v12 upgrading bullet.
- `translations/en.json`: labels and descriptions for the two new fields in
  both flows.
- `.planning/PROJECT.md` and `.planning/ROADMAP.md`: v5.1 milestone.

### Release

Additive, no change to existing alert behaviour: `feat:` commits, minor
release 5.1.0 (on top of the pending 5.0.0 from PR #2).

## 5. Testing (all without Home Assistant)

- **PanicMonitor:** press returns True once until release; repeated press
  keeps original active_since; release clears acknowledgement; acknowledge
  all vs one; acknowledge returns only newly-acked ids; due honours the
  exact-interval boundary and stamps only returned ids; acknowledged never
  due; entities independent; to_dict/from_dict round trip; from_dict drops
  malformed entries.
- **Category inference:** PANIC from override list; never from `safety` /
  `problem` device class or any domain.
- **derive_weighted_status:** PANIC alerts are skipped (no KeyError).
- **Coordinator:** rising edge notifies immediately with notifications
  disabled, in holiday mode, and while snoozed; second `on` does not
  re-notify; `off` releases and clears the alert; panic entity never touches
  routine model, correlation, daily count or last-seen; poll adds a HIGH
  PANIC alert per active entity and forces welfare `alert` with the panic
  recommendation; safe-defaults payload carries panic alerts during
  holiday/snooze; poll re-notifies only when due and not after acknowledge;
  `_handle_alerts` never writes suppression entries for panic; acknowledge
  fires the event, saves, and refreshes; state survives save/restore.
- **Config flow:** `category_panic` and `panic_renotify_minutes` present in
  both flows; overlap across the five lists rejected; normalisation; prefill.
- **Migration:** v11 → v12 seeds, preserves existing values, v12 no-op;
  chained counts +1; version constants 12.
- **Button platform:** press calls `async_acknowledge_panic`; attributes
  reflect coordinator state.
- **Service:** `acknowledge_panic` with and without entity_id reaches the
  coordinator; registered on setup and removed on unload.

## Decisions log

| Decision | Choice |
|---|---|
| Suppressions | None apply to panic: notifies through disable, holiday, snooze, severity gate, repeat interval |
| Re-notification | Every `panic_renotify_minutes` (default 5) until acknowledged; rides the 60 s poll |
| Acknowledge reset | Releasing the button (`off`) clears the panic and its acknowledgement |
| Acknowledge surface | Service with optional entity_id plus a single button entity that acknowledges all |
| Entity types | Binary sensors only |
| Inference | Override list only; no device-class or domain inference |
| Welfare | Any active panic forces `alert` ahead of weighted scoring |
| Where state lives | `panic_monitor.py` pure module; coordinator holds one instance and persists it |
| Version | v5.1 minor; config entry and storage version 12 |
| Restart reconciliation | On setup, a restored panic whose live state is not "on" is released (button released while HA was down) |
| Monitored entities | Panic override entities are unioned into monitored entities by the coordinator; no separate listing required |
