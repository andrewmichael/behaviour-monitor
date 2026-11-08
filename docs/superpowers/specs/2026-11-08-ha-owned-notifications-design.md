# Home Assistant owns notifications

Date: 8 Nov 2026. Status: draft for approval. Breaking change (`feat!:`).

## Intent

Behaviour Monitor stops sending notifications. It publishes what it knows as
events and entity state, and the Home Assistant installation decides who is
told, how, and how often, through ordinary automations.

Why:

- The built-in delivery does not work well in practice. The owner has not had
  a phone push for a long time, and the delivery path gives no sign of why
  (`coordinator.py:_push` returns silently when the notify service setting is
  empty or malformed).
- Acknowledgement does not stick (finding 287 in
  `docs/handoff/ha-review-17.md`): `raised_at` moves forward on every poll, so
  Home Assistant reads each poll as a new alert, and the router's real
  `acknowledged` flag is never published.
- The Open alerts list is too noisy. Drift and other statistical alerts sit
  beside welfare alerts with the same weight (finding 288 shows the worst of
  it).
- Every household wants different delivery: who gets told, at what hours,
  actionable buttons, critical-alert sounds, repeats. Home Assistant already
  does all of this well.

## Goals

1. Remove the integration's own push delivery: the notify service setting,
   repeat pushes, "Cleared" pushes, the persistent notification, and the
   acknowledgement model.
2. Publish alert lifecycle events with a stable identity that an automation
   can rely on.
3. Split open alerts into **needs attention** and **for information**, so
   dashboards and automations can ignore the noise without filtering it
   themselves.
4. A panic alert stays open until a person clears it.
5. Ship a blueprint, so a fresh install gets phone notifications without a
   hand-written automation.

## Non-goals

- Fixing drift accuracy (finding 288's detector changes). This design only
  moves drift out of the needs-attention list.
- Battery monitoring (finding 262). Separate piece of work.
- Changing detection, learning, or what counts as a welfare alert.
- Changing device health delivery (repair issues) or statistical logbook
  entries.
- Editing the Biddulph Road dashboard or automations. That happens in the
  Home Assistant repo after release (see "Home Assistant side").

## Anti-goals

- A panic alert must never close by itself on a timer, and must never be lost
  from the open list before a person clears it.
- An open alert must not look new to Home Assistant just because the engine
  re-evaluated it. One opening is one `opened` event.
- After upgrading, a site must not lose welfare notifications without being
  told. The upgrade has to say plainly that an automation is now needed.

## Design

### What is removed

- `CONF_NOTIFY_SERVICE` from the config flow, entry data and translations.
- Options `push_repeat_s` (repeats move to the blueprint). `push_min_severity`
  stays but is renamed to `attention_min_severity` (see the split below).
- `DeliveryAction` kinds `push` and `push_clear`; `coordinator._push`; the
  `persistent_notification` create and dismiss calls.
- `_Open.last_push`, `_Open.acknowledged`, `AlertRouter.acknowledge`, and the
  repeat loop at the end of `AlertRouter.submit`.
- The `acknowledge` service and the Acknowledge button (its entity is
  replaced, below).
- The Last Notification sensor and `last_notification` in the snapshot. Its
  entity is removed from the registry on migration.

### Alert identity and `raised_at`

An open alert keeps the `raised_at` of the moment it opened. When the engine
re-submits the same alert key, the router updates severity, explanation and
details but keeps `raised_at`. This is the handoff's fix for 287, minus the
acknowledgement part.

The stable id published to Home Assistant is the alert `key` plus the
`raised_at` of its opening, so that the same key closing and reopening later
gives a new id. Format is the builder's call; it must be a string that is
unique per opening and stable while open.

### Needs attention and for information

Every open alert gets a `group`:

- `attention`: class `welfare` at or above `attention_min_severity`
  (default `medium`, the current `push_min_severity` default). Panic is
  always `attention`, whatever the threshold. Once an alert is `attention`
  it stays `attention` until it clears, even if its severity falls, so it
  never slips out of the list while a phone is still being reminded about
  it.
- `information`: everything else in classes `welfare` and `statistical`,
  which includes drift, routine, chain and low-severity welfare alerts.
- Health alerts keep their own list and their repair issues and are in
  neither group.

Published as:

- Welfare Status sensor: the state stays as now (`ok`, `learning`,
  `degraded`, or the highest welfare severity), but computed from the
  `attention` group only. Attributes `attention` and `information`, each a
  list of alert dicts, replace `open_alerts`. `reasons` lists the attention
  explanations only.
- Each alert dict gains `id` and `group`.
- The Anomaly sensor is unchanged.

### Events

Event type `behaviour_monitor_alert`, fired on the HA bus by the coordinator.
Data:

| Field | Meaning |
|---|---|
| `entry_id` | config entry, for sites with several entries |
| `site` | site name |
| `type` | `opened`, `escalated`, `reminder`, `cleared` |
| `reason` | `reminder` only: `pressed_again`, `restart`, `snooze_ended` |
| `id` | stable alert id (above) |
| `group` | `attention` or `information` |
| `class`, `kind`, `severity`, `source`, `room` | as in the alert dict |
| `message` | the rendered explanation, with display room names |
| `raised_at` | ISO time the alert opened |
| `test` | true only for a test alert |

- `opened` when an alert key first appears.
- `escalated` when its severity rises. If that moves it from `information`
  to `attention`, the event carries the new group.
- `reminder` means "this is still open, tell people again". It keeps the
  alert's id. It fires for an open attention alert when:
  - `pressed_again`: a panic button that already has an open panic is
    pressed again. The open panic keeps its id and `raised_at`; today's
    `submit_panic` replaces it with a fresh alert, which must change.
  - `restart`: Home Assistant has finished starting
    (`homeassistant_started`, or straight away if it already has). One
    reminder per open attention alert, so automations that died in the
    restart pick the alert up again. Events for alerts opened during
    startup are held back until then and sent as `opened`.
  - `snooze_ended`: an attention alert opened or escalated during a snooze
    and is still open when the snooze ends.
- `cleared` when it leaves the open list, including a panic cleared by a
  person (with `cleared_by: "user"`). `cleared` always fires, including
  during snooze and holiday mode (today's `_on_clear` suppresses it), so
  automation repeats always stop.
- Health alerts fire events too, for completeness, with group `health`;
  repair issues stay as they are.
- Statistical alerts still write the logbook entries they write today.

Snooze and holiday mode:

- Holiday mode is unchanged: welfare and statistical alerts are not opened at
  all, so no events fire for them.
- Snooze holds back `opened` and `escalated` events for `attention` alerts
  other than panic, and logbook entries, as today. The alerts still show in
  the attention list. Panic events are never held back. When snooze ends,
  the coordinator fires a `reminder` (`snooze_ended`) for any attention
  alert held back during the snooze that is still open. (Builder's call how
  to track this.)

### Panic

- A panic alert stays open until cleared by a person, as now.
- New service `behaviour_monitor.clear_alert`, with an optional `alert_id`.
  Given an id, it clears that alert if it is a panic. Without one, it clears
  every open panic. Non-panic welfare alerts close on their own, so the
  service ignores them (logs a warning if a non-panic id is given).
- The Acknowledge button becomes **Clear panic**, calling the same path.
  It keeps the old button's unique id, so dashboards and automations that
  press it keep working.
- Clearing fires `cleared` with `cleared_by: "user"`.

### Test

The Test notification button and `test_panic` service stay. They open a
self-contained test panic (source `test`, as today) and fire `opened` with
`test: true`, then clear it on the next submit and fire `cleared`. It never
touches a real panic. The button is renamed **Test alert**; its unique id
stays.

### Blueprint

`blueprints/automation/behaviour_monitor/notify.yaml`, shipped in the repo
and linked from the README with an import button. Inputs:

- notify service (one, required)
- groups to notify (default: attention only)
- repeat interval while open (default 30 min, 0 for none; panic only, or all
  attention alerts: builder's call, default all attention)
- send a "Cleared" message (default on)
- actionable "I'm on it" button on panic, which calls `clear_alert` with the
  alert id (default on)

The blueprint treats `reminder` like `opened`: it pushes straight away and
restarts the repeat loop for that id. Repeats stop when the alert's
`cleared` event arrives.

### Migration

- Config entry version 11 to 12: drop `notify_service`; rename option
  `push_min_severity` to `attention_min_severity`; drop `push_repeat_s`.
- If `notify_service` was set, create a repair issue on upgrade saying
  Behaviour Monitor no longer sends notifications, naming the service it used
  to call, and linking the blueprint. It is dismissible.
- Store version 11 to 12: drop `last_push` and `acknowledged` from saved
  router state; keep each open alert's `raised_at` and record its group.
  This must be a real migration: bumping `STORAGE_VERSION` alone hits
  `_EngineStore._async_migrate_func` in `coordinator.py`, which throws away
  all learned state.
- Remove the Last Notification entity from the registry.

### Docs

README: replace the notification section with the events table, the two
groups, the blueprint, and a short upgrade note. Update `services.yaml`,
translations, and the architecture notes in `CLAUDE.md` ("welfare (push,
repeated until acknowledged)" becomes events).

## Home Assistant side, after release

Not part of this work; in the Home Assistant repo:

- Import the blueprint, or write an automation, for the phone push.
- Point the welfare page banner and alert cards at `attention`, and show
  `information` separately.
- Retire `binary_sensor.welfare_alert_unacknowledged` and the Acknowledge
  card; use Clear panic.
- Update `docs/known-and-accepted.md` and `docs/followups.md`; mark 287 done.

## Calls made in this design (not discussed with the owner)

- Snooze holds back attention events and keeps working; holiday mode is
  unchanged.
- Low-severity welfare alerts go to `information`; health alerts are in
  neither group.
- `push_min_severity` survives as `attention_min_severity`.
- Buttons keep their unique ids and are renamed.
- An upgrade repair issue warns sites that had a notify service.
- The Welfare Status state follows the attention group only.
- An alert that has been `attention` stays `attention` until it clears.

## Left to the builder

- The id format, how snooze-held openings are tracked, and code layout.
- Whether health alerts fire events (recommended above, not essential).
- Blueprint wording.
- Tests: the router keeps `raised_at` across submits and escalation; group
  assignment, including panic below the threshold and sticky attention;
  event sequence for open, escalate, clear, panic clear, panic pressed
  again, test; reminders after restart and after snooze; `cleared` during
  snooze and holiday; both migrations, with learned state surviving the
  store one; the removed entities and services are gone.
