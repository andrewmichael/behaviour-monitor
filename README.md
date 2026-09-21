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
   in explanations) and a **notify service** for push delivery
4. Assign each entity you want monitored to exactly one of the six
   categories below
5. Configure the options

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
| Push repeat interval (s) | 1800 |
| Minimum push severity | medium |
| House low ratio | 3 |
| Chain window (s) | 1800 |
| Timing drift promotion (days) | 7 |
| Drift sensitivity | medium |

## Entities

### Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.<site>_welfare_status` | Overall welfare status: `ok`, `degraded`, `low`, `medium`, `high`, or `critical`, with reasons and open alerts |
| `sensor.<site>_house_activity` | Seconds since the last whole-house activity event, with the expected gap, ratio, last room, and rooms visited today |
| `sensor.<site>_anomaly` | Count of open statistical alerts, listed in an attribute |
| `sensor.<site>_device_health` | `ok` or the worst open health condition, with per-entity state |
| `sensor.<site>_learning` | Learning progress as a percentage, with per-model confidence and days remaining |
| `sensor.<site>_entity_status` | Summary of monitored entities, with category, room, last seen, expected windows, and health per entity, plus learned chains |
| `sensor.<site>_last_activity` | Timestamp of the most recent activity event |
| `sensor.<site>_daily_activity_count` | Total activity events recorded today |
| `sensor.<site>_last_notification` | Timestamp and kind of the last notification sent |

### Controls

| Entity | Description |
|--------|-------------|
| `switch.<site>_holiday_mode` | Pauses learning and suppresses welfare and statistical alerts while the occupant is away. Panic and device health still alert |
| `select.<site>_snooze` | Suppresses welfare and statistical delivery for a chosen duration (1 hour, 2 hours, 4 hours, or 1 day). Panic and device health still alert |
| `button.<site>_acknowledge` | Stops repeat pushes for open welfare alerts; the alert stays open until the house recovers |

## Services

| Service | Description |
|---------|-------------|
| `behaviour_monitor.enable_holiday_mode` | Pause learning and welfare alerts while the occupant is away |
| `behaviour_monitor.disable_holiday_mode` | Resume learning and welfare alerts |
| `behaviour_monitor.snooze` | Suppress welfare and statistical delivery for a duration (requires `duration`) |
| `behaviour_monitor.clear_snooze` | Resume delivery immediately |
| `behaviour_monitor.acknowledge` | Stop repeat pushes for open welfare alerts |
| `behaviour_monitor.reset_learning` | Wipe learned patterns for one entity, or the whole site if no `entity_id` is given, then relearn from the recorder |
| `behaviour_monitor.test_panic` | Send a panic push through the real delivery path without touching learned state |

## Alert Classes

Every alert belongs to exactly one of three classes, and the class alone
decides how it is delivered:

- **Welfare** — the primary product. Pushed via the configured notify
  service when severity is at or above the minimum push severity, and
  repeated on an interval until acknowledged. A clear sends one push saying
  the condition has resolved.
- **Device health** — the sensing itself has degraded (unavailable
  entities, a site-wide dropout, a silent sensor). Raised as a Home
  Assistant repair issue rather than pushed, and the issue is deleted when
  the condition clears.
- **Statistical** — unusual but not a welfare concern on its own (routine
  notes, chain stalls, drift). Appended to the anomaly sensor's attributes
  and logged to the logbook; never pushed.

**Panic always bypasses snooze and holiday mode.** A panic press is
delivered as an immediate critical push regardless of any suppression in
effect, and is never treated as a silent-sensor candidate.

## Upgrading from v4

Learned data from v4 is discarded — the storage schema is bumped to a new
major version, so nothing is carried forward.

The config entry migrates automatically to version 11. Your previously
monitored entities are kept but left unassigned, and a repair issue asks
you to place them into the new categories under the integration's options.
Until you do, nothing is monitored and the welfare sensor reports
`unconfigured`.

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
