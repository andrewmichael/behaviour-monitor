# Behaviour Monitor

A Home Assistant custom integration that learns a household's routine from
its sensors and alerts when the occupant's behaviour departs from what the
home has learned is normal. Built for **elder care and welfare monitoring**:
it learns whole-house activity, per-entity routines, and the ordered chains
of rooms an occupant moves through, then separates welfare concerns from
device problems from merely unusual activity.

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
5. Configure the options
6. To get phone notifications, import the blueprint (see
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
| Minimum attention severity | medium |
| House low ratio | 3 |
| Chain window (s) | 1800 |
| Timing drift promotion (days) | 7 |
| Drift sensitivity | medium |

## Entities

### Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.<site>_welfare_status` | Overall welfare status: `ok`, `degraded`, `low`, `medium`, `high`, or `critical`, with `reasons` (needs-attention explanations only) and the `attention` and `information` alert lists |
| `sensor.<site>_house_activity` | Seconds since the last whole-house activity event, with the expected gap, ratio, last room, and rooms visited today |
| `sensor.<site>_anomaly` | Count of open statistical alerts, listed in an attribute |
| `sensor.<site>_device_health` | `ok` or the worst open health condition, with per-entity state |
| `sensor.<site>_learning` | Learning progress as a percentage, with per-model confidence and days remaining |
| `sensor.<site>_entity_status` | Summary of monitored entities, with category, room, last seen, expected windows, and health per entity, plus learned chains |
| `sensor.<site>_last_activity` | Timestamp of the most recent activity event |
| `sensor.<site>_daily_activity_count` | Total activity events recorded today |

### Controls

| Entity | Description |
|--------|-------------|
| `switch.<site>_holiday_mode` | Pauses learning and suppresses welfare and statistical alerts while the occupant is away. Panic and device health still alert |
| `select.<site>_snooze` | Suppresses welfare and statistical delivery for a chosen duration (1 hour, 2 hours, 4 hours, or 1 day). Panic and device health still alert; needs-attention events are held back and a `reminder` follows when the snooze ends |
| `button.<site>_clear_panic` (`_acknowledge` on existing installs) | **Clear panic**: clears every open panic. Other alerts close on their own |
| `button.<site>_test_notification` | **Test alert**: opens a test panic and fires a `behaviour_monitor_alert` event with `test: true`, then clears it on the next press. Learned state is untouched |

## Services

| Service | Description |
|---------|-------------|
| `behaviour_monitor.enable_holiday_mode` | Pause learning and welfare alerts while the occupant is away |
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
  entities, a site-wide dropout, a silent sensor). Raised as a Home
  Assistant repair issue, and the issue is deleted when the condition
  clears. Events fire with group `health`.
- **Statistical** — unusual but not a welfare concern on its own (routine
  notes, chain stalls, drift). Appended to the anomaly sensor's attributes
  and logged to the logbook. They sit in the `information` group.

**Panic always bypasses snooze and holiday mode.** A panic press fires its
events immediately regardless of any suppression in effect, and is never
treated as a silent-sensor candidate. A panic stays open until a person
clears it with the Clear panic button or `behaviour_monitor.clear_alert`.

## Notifications

Behaviour Monitor does not send notifications itself. It fires events, and
Home Assistant decides who is told, how and how often.

[![Import the blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fandrewmichael%2Fbehaviour-monitor%2Fmain%2Fblueprints%2Fautomation%2Fbehaviour_monitor%2Fnotify.yaml)

The blueprint takes a notify service, the groups to notify (default
attention), a repeat interval while an alert is open (default 30 minutes,
0 for none), whether to send a "Cleared" message, and whether a panic gets an
"I'm on it" button that clears it.

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

From the version that ships this change, Behaviour Monitor no longer sends
notifications; import the blueprint to keep receiving them. The notify
service and push options are removed, the Last Notification sensor is
removed, and the Acknowledge button and `acknowledge` service are replaced by
Clear panic and `clear_alert`. The config entry migrates to version 12, and
a site that had a notify service gets a repair issue linking the blueprint.

## Upgrading from v4

Learned data from v4 is discarded — the storage schema is bumped to a new
major version, so nothing is carried forward.

The config entry migrates automatically (it is now at version 12). Your previously
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
