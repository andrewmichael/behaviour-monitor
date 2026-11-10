# Behaviour Monitor

A Home Assistant custom integration that learns a household's routine from
its sensors and alerts when behaviour departs from what the home has learned
is normal. Built for **elder care and welfare monitoring**: it tracks where
the household probably is (home, watching TV, asleep, lying in or out) to
catch a fall or illness at home within about an hour, and it learns
per-entity routines and the ordered chains of rooms people move through. It
keeps welfare concerns apart from device problems and from merely unusual
activity.

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots menu and select "Custom repositories"
3. Add this repository URL and select "Integration" as the category
4. Click "Install"
5. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/behaviour_monitor` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Behaviour Monitor"
3. Enter a **site name** (used to label the device and to shorten room names
   in explanations)
4. Assign each entity you want monitored to exactly one of the six
   categories below
5. On the next step, choose the outside doors, bedrooms and sitting
   appliances (see [Whereabouts](#whereabouts))
6. Configure the options
7. To get phone notifications, import the blueprint (see
   [Notifications](#notifications))

An entity assigned to no category is not monitored. An entity can only be
in one category's list.

### Categories

| Category | Counts as activity |
|---|---|
| Motion | A rising edge to `on`, debounced against retriggers |
| Contact | A rising edge to `on` (opening) |
| Plug | A numeric reading rising above its learned idle level plus a margin, or a switch turning `on` |
| Panic | A rising edge to `on` — bypasses every model and suppression |
| Light | Turning `on` |
| Other | Any change between two real states |

### Options

| Option | Default |
|--------|---------|
| Motion debounce (s) | 90 |
| Plug margin (W) | 5 |
| Learning days | 14 |
| Window days | 28 |
| Health grace period (s) | 900 |
| Low battery level (%) | 20 |
| Minimum attention severity | medium |
| Chain window (s) | 1800 |
| Timing drift promotion (days) | 7 |
| Drift sensitivity | medium |
| Night-time downstairs alert (minutes) | 30 (10 to 120) |

The options flow has a second step with the outside doors, bedrooms,
sitting appliances and upstairs rooms lists.

## Entities

### Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.<site>_welfare_status` | Overall welfare status: `ok`, `degraded`, `low`, `medium`, `high`, or `critical`, with `reasons` (needs-attention explanations only), the `attention` and `information` alert lists, `snoozed` (true while a snooze is active), and the whereabouts: `where` (`home`, `home_tv`, `asleep`, `lying_in` or `out`), `where_since`, `last_room` and `limit_min` (the stillness limit in force) |
| `sensor.<site>_house_activity` | Seconds since the last whole-house activity event, with the expected gap, last room, and rooms visited today |
| `sensor.<site>_anomaly` | Count of open statistical alerts, listed in an attribute |
| `sensor.<site>_device_health` | `ok` or the worst open health condition, with per-entity state |
| `sensor.<site>_learning` | Learning progress as a percentage, with per-model confidence and days remaining |
| `sensor.<site>_entity_status` | Summary of monitored entities, with category, room, last seen, expected windows, and health per entity, plus learned chains |
| `sensor.<site>_last_activity` | Timestamp of the most recent activity event |
| `sensor.<site>_daily_activity_count` | Total activity events recorded today |

### Controls

| Entity | Description |
|--------|-------------|
| `switch.<site>_holiday_mode` | Pauses learning and suppresses welfare and statistical alerts while the household is away. Panic and device health still alert |
| `select.<site>_snooze` | Suppresses welfare and statistical delivery for a chosen duration (1 hour, 2 hours, 4 hours, or 1 day). Panic and device health still alert; needs-attention events are held back and a `reminder` follows when the snooze ends |
| `button.<site>_clear_panic` (`_acknowledge` on existing installs) | **Clear panic**: clears every open panic. Other alerts close on their own |
| `button.<site>_test_alert` (`_test_notification` on existing installs) | **Test alert**: opens a test panic and fires a `behaviour_monitor_alert` event with `test: true`. The next refresh clears it, so its `cleared` event follows almost at once. Learned state is untouched |

## Services

| Service | Description |
|---------|-------------|
| `behaviour_monitor.enable_holiday_mode` | Pause learning and welfare alerts while the household is away |
| `behaviour_monitor.disable_holiday_mode` | Resume learning and welfare alerts |
| `behaviour_monitor.snooze` | Suppress welfare and statistical delivery for a duration (requires `duration`) |
| `behaviour_monitor.clear_snooze` | Resume delivery immediately |
| `behaviour_monitor.clear_alert` | Clear a panic. Takes an optional `alert_id`; without one it clears every open panic. Other alerts close on their own |
| `behaviour_monitor.reset_learning` | Wipe learned patterns for one entity, or the whole site if no `entity_id` is given, then relearn from the recorder |
| `behaviour_monitor.test_panic` | Open a test panic and fire its events without touching learned state |

## Alert Classes

Every alert belongs to exactly one of three classes:

- **Welfare** — the primary product. Open welfare alerts are split into two
  groups. **Attention** holds welfare alerts at or above the minimum
  attention severity (default `medium`) and every panic; an alert that
  reaches attention stays there until it clears. **Information** holds the
  rest, including low-severity welfare alerts. Both groups are published on
  the Welfare Status sensor, and every alert fires
  `behaviour_monitor_alert` events (see [Notifications](#notifications)).
- **Device health** — the sensing itself has degraded (unavailable
  entities, a site-wide dropout, a silent sensor, a low battery). Raised as a Home
  Assistant repair issue, and the issue is deleted when the condition
  clears. Events fire with group `health`.

  **Low battery.** Readings come from the battery sensor on each monitored
  sensor's device. The alert fires at or below the low battery level and
  clears once the level is 5 points above it. A panic button's low battery
  is high severity, any other sensor's medium. To get these on a phone, tick
  `health` in the notification automation's Alert groups.

- **Statistical** — unusual but not a welfare concern on its own (the
  three card kinds in [Unusual days and nights](#unusual-days-and-nights),
  and drift). Appended to the anomaly sensor's attributes
  and logged to the logbook. They sit in the `information` group.
  A drift alert's `details` carry `direction` (the way it drifted), `days`,
  `baseline`, `today`, `current` (`above`, `below` or `near` usual today) and
  `settled` (true once today is no longer on the drift's side). A drift
  closes by itself after three days back near or past usual; its severity
  follows how far it moved, not how long it has lasted.

**Panic always bypasses snooze and holiday mode.** A panic press fires its
events immediately regardless of any suppression in effect, and is never
treated as a silent-sensor candidate. A panic stays open until a person
clears it with the Clear panic button or `behaviour_monitor.clear_alert`.

## Whereabouts

Behaviour Monitor keeps track of where the household probably is and raises
a welfare alert when there has been no movement for longer than is normal for
that place and time. It catches a fall in the day usually within about an
hour and a half, and doesn't treat an outing as a fall.

Room sensors can't tell people apart, so with more than one person living
there the alerts are about the whole household: "still at home" means no one
has moved, and "out" means the house is empty. A fall by one person while
another is moving about can't be detected from room sensors; panic buttons
cover that.

### Setup lists

The setup step asks for four lists. Each is optional, but without them the
matching states can't be told apart.

- **Outside doors**: the doors that lead outside. Without them the
  integration can't tell that the house is empty, so a long outing looks
  like a fall. Tick only real outside doors: not the fridge, a cupboard or
  an internal door, which would hold back fall alerts.
- **Bedrooms**: the rooms people sleep in. Rooms with "bedroom" in the name
  are pre-ticked, and are used when the list is left unset. If no room is a
  bedroom, the night rules apply to every room.
- **Sitting appliances**: the TV, or a plug that shows someone is sitting
  down with something on. Quiet time with one on is allowed to run longer,
  so a film isn't mistaken for a fall.
- **Upstairs rooms**: the rooms people go up to at bedtime, such as the
  bathroom and landing. Bedrooms count already. A move from these to the
  rest of the house during the night is a night trip. Rooms on floors above
  the lowest are suggested when the site's areas have floors. Leave it empty
  in a bungalow: night rooms are then the bedrooms only.

### States and alerts

| State | Meaning |
|---|---|
| Home | Moving about indoors |
| Home with TV on | Last movement in a room with a sitting appliance on |
| Asleep | Last movement in a bedroom during the usual night |
| Lying in | Last movement in a bedroom after the night ends, before the usual lie-in ends |
| Out | An outside door opened and no indoor movement followed within 10 minutes |

Welfare alerts have source `whereabouts` and one of four kinds:

| Kind | Fires when |
|---|---|
| `still_at_home` | Home and no movement for longer than the home limit for that hour |
| `still_tv` | Home with the TV on and no movement for 90 minutes |
| `not_up` | Asleep, and no one up an hour after the usual waking time. Also used after a lie-in, with no movement 90 minutes after stirring |
| `not_back` | House empty for longer than the longest outing so far, plus a quarter |

Severity is medium when an alert opens and high at one and a half times the
limit, or an hour past the deadline for `not_up` and `not_back`. An outside
door opening while the house is out, or soon after someone left, counts as
coming back.

### What it learns

- the home limit for each hour of the day (between 45 and 60 minutes)
- the usual waking time
- when the night starts and ends
- the longest outing

Each needs 3 days of data. Trips of 24 hours or more are not learned as
outings. A day's waking time counts once the day is over, and a return to bed
of an hour or more before noon cancels that morning's waking. Bedtime is the
first bedroom stretch of an hour or more after 18:00. Until values are
learned, fixed defaults apply.

### Restarts

Stillness keeps counting through a Home Assistant restart of under 30
minutes. A longer outage restarts the count from when it ends, except in bed
or out, where the original time is kept. Stretches of stillness cut short by a
restart teach slightly shorter limits.

A sensor that stops reporting while still shown as available can cause
stillness alerts in the rooms it covered until it is fixed. If one of these
appears, the device health repair for that sensor is the likely cause.

## Unusual days and nights

Five kinds report something out of the ordinary for this house. Each needs 14
days of the entity's, or the house's, own history inside the 28-day window,
so a sensor added last week stays quiet. Sensors unavailable at any point
today, including an outage that began the day before, are skipped for the
card kinds.

Three are cards: statistical, low severity, in the `information` group, never
pushed.

| Kind | Shown when | Clears when |
|---|---|---|
| `not_yet_today` | An entity used on at least 90% of days hasn't fired by its usual time (the 90th percentile of its first use after the morning starts) plus an allowance of at least an hour. Held while the house is out; after an outing it waits at least an hour from the return | It fires, or the day ends |
| `trip_missed` | A usual outing for this weekday (out at that time on at least 75% of at least 4 learned same weekdays) passed with nobody going out | The day ends |
| `unusual_now` | An entity fires in an hour where it never fired on any learned day, an hour either side included | 2 hours later, or the day ends |

Two are welfare alerts with source `night`, medium severity, in the
`attention` group, so the notify blueprint pushes them:

| Kind | Fires when | Clears when |
|---|---|---|
| `night_downstairs` | A night trip has lasted the night-time downstairs alert (default 30 minutes) | Only night rooms are active again, or morning starts |
| `night_door` | An outside door opens during the night, unless the house was out (that's someone coming home) | Night-room activity follows the door, or morning starts |

Night starts when someone goes from a day room to a night room (the bedrooms
and upstairs rooms) within 5 minutes, the day rooms then stay quiet for 30
minutes and no sitting appliance in a day room is on. It can't start before
the learned night start. It ends at the first day-room activity after the
learned waking time. A night trip is day-room activity during the night; it
ends after 5 minutes of night rooms only. Both pushes need 14 learned nights,
and each stays quiet when it is normal for the house: a long trip on more
than 10% of nights, or a door opening within an hour of that time on more
than 10% of nights. Holiday mode stops both and snooze holds them.

A `not_yet_today` while nobody went out today counts as a missed routine sign
for an open whereabouts alert, which raises it one severity step at two or
more signs.

## Notifications

Behaviour Monitor does not send notifications itself. It fires events, and
Home Assistant decides who is told, how and how often.

[![Import the blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fandrewmichael%2Fbehaviour-monitor%2Fmain%2Fblueprints%2Fautomation%2Fbehaviour_monitor%2Fnotify.yaml)

The blueprint takes a notify service, the groups to notify (default
attention), a repeat interval while an alert is open (default 30 minutes,
0 for none), whether to send a "Cleared" message, and whether a panic gets an
"I'm on it" button that clears it. Repeats apply to attention and information
alerts: before each repeat the blueprint checks the alert is still listed on a
Welfare Status sensor and stops if it is not, and while that sensor is
`snoozed` only a panic repeats.

### The `behaviour_monitor_alert` event

| Field | Meaning |
|---|---|
| `entry_id` | Config entry, for sites with several entries |
| `site` | Site name |
| `type` | `opened`, `escalated`, `reminder`, `cleared` |
| `reason` | `reminder` only: `pressed_again`, `restart`, `snooze_ended` |
| `id` | Stable alert id, unique per opening |
| `group` | `attention`, `information` or `health` |
| `class`, `kind`, `severity`, `source`, `room` | As in the alert |
| `message` | The explanation, with display room names |
| `raised_at` | ISO time the alert opened |
| `test` | `true` only for a test alert |
| `cleared_by` | `"user"` when a person cleared a panic |

- `opened` when an alert first appears; `escalated` when its severity rises.
  A welfare alert often opens in `information` and reaches `attention` with
  an `escalated` event, so notify on both.
- `reminder` means "still open, tell people again". It keeps the alert id and
  fires when a panic button is pressed again (`pressed_again`), once per open
  attention alert after Home Assistant starts (`restart`), and for attention
  alerts held back during a snooze that are still open when it ends
  (`snooze_ended`).
- `cleared` fires whenever an alert closes, including during snooze and
  holiday mode. It can arrive for an id you never saw open, for example an
  alert that opened and closed during a snooze.

### Writing your own automation

```yaml
automation:
  - alias: Behaviour Monitor push
    triggers:
      - trigger: event
        event_type: behaviour_monitor_alert
        event_data:
          group: attention
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.type != 'cleared' }}"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "{{ trigger.event.data.site }} welfare"
          message: "{{ trigger.event.data.message }}"
          data:
            tag: "{{ trigger.event.data.id }}"
```

### Clearing a panic

Press **Clear panic**, or call `behaviour_monitor.clear_alert` with the
alert's `id` (or with no `alert_id` to clear every open panic). A cleared
panic fires `cleared` with `cleared_by: "user"`.

## Upgrading

### Upgrading to this release

- Routine notes (`routine_missed`), chain stalls (`chain_stall`) and
  `routine_agreement` events are no longer sent. Automations that match them
  must change. They are replaced by the five kinds in
  [Unusual days and nights](#unusual-days-and-nights).
- Learning is kept. On the first start the new history (first use each day,
  outings, nights) is rebuilt from recorder history. Each new kind stays
  quiet until it has 14 days of its own history, and the night pushes start
  after 14 learned nights.
- Open the integration's options and, on the second step, tick the upstairs
  rooms. Until then night rooms are the bedrooms only.
- The config entry migrates to version 14.

### Upgrading to v8

- The welfare alert with kind `inactivity` and source `house` is replaced by
  source `whereabouts` and the four kinds in [Whereabouts](#whereabouts).
  Automations that match `inactivity` must be changed. The notify blueprint
  needs nothing.
- Welfare Status gains `where`, `where_since`, `last_room` and `limit_min`.
- The "house quiet ratio" option is gone.
- After upgrading, open the integration's options and, on the second step,
  set the outside doors and sitting appliances and check the Bedrooms list.
  Until outside doors are set, an outing raises "still at home".
- The integration relearns from recorder history. Welfare alerts stay off
  until 14 days are learned; with Home Assistant's default 10-day recorder
  that is about 4 days of waiting. Panic buttons keep working throughout.
- The config entry migrates to version 13.

### Upgrading to v7

From v7, Behaviour Monitor no longer sends notifications; import the blueprint to keep receiving them. The notify
service and push options are removed, the Last Notification sensor is
removed, and the Acknowledge button and `acknowledge` service are replaced by
Clear panic and `clear_alert`. The config entry migrates to version 12, and
a site that had a notify service gets a repair issue linking the blueprint.

### Upgrading from v4

Learned data from v4 is discarded — the storage schema is bumped to a new
major version, so nothing is carried forward.

The config entry migrates automatically (it is now at version 13). Your previously
monitored entities are kept but left unassigned, and a repair issue asks
you to place them into the new categories under the integration's options.
Until you do, nothing is monitored and the integration creates no entities.

Once categories are assigned, v4 sensors with a v5 counterpart of the same
key (`welfare_status`, `last_activity`, `daily_activity_count`,
the holiday switch and the snooze select) keep their
existing entity ids. New sensors and the Clear panic button get ids from the
site name. v4-only sensors (`activity_score`, `anomaly_detected`,
`baseline_confidence`, `entity_status_summary`, `routine_progress`,
`statistical_training_remaining`, `time_since_activity`) remain in the
entity registry as `unavailable` and can be deleted; dashboards that
reference them need repointing at the v5 sensors.

## Exporting Site Data for Tuning

The learned store is the output of the current rules, so it cannot be used to
test new ones. What refines the monitor is the raw state-change history of the
monitored sensors, which can be replayed through the engine as often as needed
and the alert timelines compared.

`scripts/export_fixture.py` pulls that history from the Home Assistant recorder
through the REST API and writes an anonymised fixture: a `.jsonl` file of state
changes and a `.sidecar.json` with categories and rooms. Entity ids and room
names are replaced with generic ones in the files; the real names are printed
to the terminal only.

1. Create a long-lived access token under your Home Assistant profile,
   Security tab, and save it to `~/.ha_token`.
2. Write `site_entities.json` listing each monitored entity:

   ```json
   [{"entity_id": "binary_sensor.kitchen_motion", "category": "motion", "room": "Kitchen"}]
   ```

3. From a checkout of this repository:

   ```bash
   source venv/bin/activate
   python scripts/export_fixture.py --url http://homeassistant.local:8123 \
     --token "$(cat ~/.ha_token)" --entities site_entities.json \
     --days 28 --out tests/fixtures/site_real.jsonl --site "Real site"
   ```

4. Replay it with `python scripts/replay.py tests/fixtures/site_real.jsonl`.

The recorder keeps 10 days of history by default, so an export covers at most
that. The models learn over a 28-day window; set `purge_keep_days: 35` under
`recorder:` in `configuration.yaml` now to have a full window available later.

### Long-term history from InfluxDB

For months of history, record the monitored sensors to InfluxDB 1.8 with
Home Assistant's `influxdb` integration (`measurement_attr: entity_id`, so
each entity is its own measurement with `state` and `value` fields), then
export with `scripts/export_influx.py`. It reads credentials from
`~/.influx_bm` (`host`, `port`, `database`, `username`, `password` lines),
takes the monitored entities from a fixture sidecar, writes rows in local
time, and can merge into an existing fixture so one file keeps growing:

```bash
python scripts/export_influx.py --sidecar site.sidecar.json \
  --start 2026-11-08T23:36:00+00:00 --merge site.jsonl --out site.jsonl \
  --context site.context.jsonl
```

`--context` also writes everything else recorded (batteries, `sensor.uptime`
restarts, Behaviour Monitor's own sensors) to a separate file. These exports
are not anonymised; keep them out of git.

### Scoring a change against real data

`scripts/scorecard.py` replays a fixture through the current engine and
scores it against a hand-written truth file of what really happened (outings,
visitors, sensor faults, maintenance, real concerns, data gaps; the format is
in the script's docstring). It reports welfare alerts the truth explains or
doesn't, sensor faults caught or missed, restart storms, information-alert
volume, panic presses, and injected falls: on ordinary days after learning it
stops all activity at set times and measures how long welfare takes to alert.

```bash
python scripts/scorecard.py site.jsonl --truth site.truth.yaml \
  --fall-times 10:00,15:00 --fall-days 10
```

Run it before and after a change to see the difference on real data.

Restart storms in data exported from the recorder as CSV are mostly an export
artefact: the "unavailable" row at a restart can survive while the "back to
normal" row a second later is lost, so sensors look offline for hours. Live,
the outage lasts under a second and never raises a repair. InfluxDB exports
keep both rows.

## Development

See [README-DEV.md](README-DEV.md) for complete development setup
instructions.

The pure-Python core (no Home Assistant imports) can be exercised directly
against a fixture with the replay CLI:

```bash
python scripts/replay.py tests/fixtures/<name>.jsonl
```

Run just the core test suite with:

```bash
make test-core
```

## License

MIT License
