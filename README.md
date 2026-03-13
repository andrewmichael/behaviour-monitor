# Behaviour Monitor

A Home Assistant custom integration that learns entity behavior patterns and detects anomalies using routine-based detection. Ideal for **elder care monitoring**, security, and detecting unusual activity patterns.

## Features

- **Routine Learning**: Learns per-entity behavior baselines using 168 hour-of-day x day-of-week slots from configurable rolling history (default 4 weeks)
- **Acute Detection**: Alerts when expected activity is missing (inactivity) or activity occurs at unusual times — requires sustained evidence across multiple polling cycles before firing
- **Drift Detection**: Detects persistent behavior changes over days/weeks using CUSUM change-point analysis with configurable sensitivity
- **Elder Care Monitoring**: Welfare status, routine progress tracking, and severity-graded alerts
- **Recorder Bootstrap**: Bootstraps baselines from existing HA recorder history on first load — no cold start for existing installations
- **Holiday Mode**: Completely pause tracking and notifications when person is away
- **Visitor Snooze**: Temporarily pause learning and alerts during expected unusual activity
- **Attribute Tracking**: Optionally track attribute changes, not just state changes
- **Notifications**: Sends persistent notifications with severity levels for unusual activity patterns
- **Pure Python**: No external ML dependencies required — pure Python stdlib
- **HACS Compatible**: Install via HACS for easy updates

## Elder Care Use Case

This integration is designed for monitoring the wellbeing of elderly family members by learning their daily patterns and alerting when something is out of character:

**What it monitors:**
- Motion sensor activity (movement around the home)
- Door/window sensors (exits, entries, room changes)
- Light switches (daily routine indicators)
- Appliance usage (kettle, TV, etc.)

**What it detects:**
- No morning activity when there usually is (inactivity detection)
- Significantly reduced activity compared to normal (drift detection)
- Missing expected routines (e.g., kitchen not used by usual breakfast time)
- Unusual activity patterns (awake at unusual hours)

**Severity levels:**
| Level | Meaning | Recommended Action |
|-------|---------|-------------------|
| `ok` | Activity patterns are normal | No action needed |
| `check_recommended` | Slight deviation from normal | Consider checking in |
| `concern` | Notable deviation from patterns | Welfare check recommended soon |
| `alert` | Significant anomaly detected | Immediate welfare check recommended |

**Example notifications:**
- "Inactivity alert: No activity from motion_sensor.kitchen for 4 hours (usually active every 45 minutes)"
- "Drift alert: Daily activity from binary_sensor.front_door has decreased persistently over 5 days"
- "Unusual time: Activity from motion_sensor.hallway at 03:15 — no baseline for this time slot"

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
3. Select the entities you want to monitor
4. Configure settings

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| Entities to monitor | Select entities whose state changes should be tracked | Required |
| History window | Rolling history window for baseline learning (7-90 days) | 28 days |
| Inactivity multiplier | Alert when inactive for this multiple of learned typical interval (1.5-10.0×) | 3.0× |
| Drift sensitivity | CUSUM change-point detection sensitivity (High/Medium/Low) | Medium |
| Enable notifications | Send persistent notifications when anomalies are detected | Yes |
| Notification cooldown | Minutes before re-alerting the same entity | 30 minutes |
| Minimum notification severity | Minimum anomaly severity to trigger a notification | significant |
| Mobile notification services | Services to send mobile notifications (e.g., `notify.mobile_app_iphone`) | Empty |
| Track attributes | Also track attribute changes, not just state changes | Yes |

### Upgrading from v2.x

Existing config entries migrate automatically to v4 format. Old ML-related options (enable_ml, ml_learning_period, retrain_period, cross_sensor_window) are removed and replaced with the new detection controls. No manual intervention is needed.

## Holiday Mode and Visitor Snooze

The integration provides two modes for managing tracking during exceptional circumstances:

### Holiday Mode

**Complete pause** - Use when the monitored person is away on vacation or extended absence.

**What it does:**
- Stops all state tracking (state changes completely ignored)
- Pauses all pattern learning (no baseline updates)
- Disables all anomaly detection
- Suppresses all notifications
- Persists across Home Assistant reboots

**How to use:**
```yaml
# Via service
service: behaviour_monitor.enable_holiday_mode

# Or toggle the switch entity
entity_id: switch.behaviour_monitor_holiday_mode
```

### Visitor/Snooze Mode

**Temporary pause** - Use when unusual but expected activity occurs (visitors, care workers, etc.)

**What it does:**
- Continues state tracking (events are logged)
- Pauses pattern learning (baseline not affected by visitor activity)
- Disables anomaly detection
- Suppresses notifications
- Auto-expires after selected duration
- Persists across reboots (with expiration check)

**Available durations:**
- 1 Hour
- 2 Hours
- 4 Hours
- 1 Day

**How to use:**
```yaml
# Via service
service: behaviour_monitor.snooze
data:
  duration: "4_hours"  # Options: 1_hour, 2_hours, 4_hours, 1_day

# Clear snooze early
service: behaviour_monitor.clear_snooze

# Or use the select entity
entity_id: select.behaviour_monitor_snooze_notifications
```

### Example Automations

**Auto-enable holiday mode from calendar:**
```yaml
automation:
  - alias: "Enable Holiday Mode on Vacation"
    trigger:
      - platform: calendar
        event: start
        entity_id: calendar.vacation
    action:
      - service: behaviour_monitor.enable_holiday_mode

  - alias: "Disable Holiday Mode After Vacation"
    trigger:
      - platform: calendar
        event: end
        entity_id: calendar.vacation
    action:
      - service: behaviour_monitor.disable_holiday_mode
```

**Snooze during care worker visit:**
```yaml
automation:
  - alias: "Snooze for Care Worker"
    trigger:
      - platform: state
        entity_id: binary_sensor.care_worker_present
        to: "on"
    action:
      - service: behaviour_monitor.snooze
        data:
          duration: "4_hours"
```

**Dashboard card:**
```yaml
type: entities
title: Behaviour Monitor Controls
entities:
  - entity: switch.behaviour_monitor_holiday_mode
    name: Holiday Mode
    icon: mdi:beach
  - entity: select.behaviour_monitor_snooze_notifications
    name: Snooze Duration
    icon: mdi:bell-sleep
```

For detailed documentation, see [HOLIDAY_SNOOZE_MODE.md](HOLIDAY_SNOOZE_MODE.md).

## Services

The integration provides the following services:

| Service | Description |
|---------|-------------|
| `behaviour_monitor.enable_holiday_mode` | Enable holiday mode - completely pause all tracking and notifications |
| `behaviour_monitor.disable_holiday_mode` | Disable holiday mode - resume normal operation |
| `behaviour_monitor.snooze` | Snooze notifications for specified duration (requires `duration` parameter) |
| `behaviour_monitor.clear_snooze` | Clear active snooze - immediately resume notifications |
| `behaviour_monitor.routine_reset` | Reset drift detection for an entity after an intentional routine change (requires `entity_id` parameter) |

**Service call examples:**
```yaml
# Enable holiday mode
service: behaviour_monitor.enable_holiday_mode

# Snooze for 2 hours
service: behaviour_monitor.snooze
data:
  duration: "2_hours"

# Reset drift detection after intentional routine change
service: behaviour_monitor.routine_reset
data:
  entity_id: "binary_sensor.front_door"

# Clear snooze
service: behaviour_monitor.clear_snooze
```

## Sensors & Controls

The integration creates the following sensors and control entities:

### Control Entities

| Entity | Type | Description |
|--------|------|-------------|
| `switch.behaviour_monitor_holiday_mode` | Switch | Enable/disable holiday mode (complete pause of all tracking) |
| `select.behaviour_monitor_snooze_notifications` | Select | Choose snooze duration (Off, 1hr, 2hr, 4hr, 1 day) |

### Core Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.behaviour_monitor_last_activity` | Timestamp of the most recent detected state change |
| `sensor.behaviour_monitor_activity_score` | Current activity level (0-100%) compared to baseline |
| `sensor.behaviour_monitor_anomaly_detected` | "on" when an anomaly is currently detected |
| `sensor.behaviour_monitor_baseline_confidence` | Progress of routine model learning (0-100%) |
| `sensor.behaviour_monitor_daily_activity_count` | Total state changes recorded today |
| `sensor.behaviour_monitor_statistical_training_remaining` | Time remaining until detection activates |
| `sensor.behaviour_monitor_last_notification` | Timestamp of the last notification sent |

### Elder Care Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.behaviour_monitor_welfare_status` | Overall welfare status: `ok`, `check_recommended`, `concern`, or `alert` |
| `sensor.behaviour_monitor_routine_progress` | Daily routine completion percentage (0-100%) |
| `sensor.behaviour_monitor_time_since_activity` | Human-readable time since last activity with context |
| `sensor.behaviour_monitor_entity_status_summary` | Summary of entity statuses (e.g., "5 OK, 2 Need Attention") |

### Deprecated Sensors (preserved for backward compatibility)

| Sensor | Description |
|--------|-------------|
| `sensor.behaviour_monitor_cross_sensor_patterns` | Returns `0` (stub — will be removed in a future version) |
| `sensor.behaviour_monitor_ml_status` | Returns `"Removed in v1.1"` (stub) |
| `sensor.behaviour_monitor_ml_training_remaining` | Returns `"N/A"` (stub) |

## How It Works

### Routine Model

The integration learns per-entity behavior baselines using:
- **168 time slots** per entity (24 hours × 7 days of the week)
- **Binary entities** (motion, doors): tracks event frequency and inter-event intervals
- **Numeric entities** (temperature, power): tracks value distributions using Welford online statistics

The model bootstraps from existing HA recorder history on first load, so existing installations start with populated baselines immediately.

### Acute Detection

Two types of acute alerts, both requiring **sustained evidence** (3 consecutive polling cycles) before firing:

**Inactivity**: Fires when an entity has been silent for longer than a configurable multiplier of its learned typical interval. For example, if a motion sensor usually triggers every 45 minutes and the multiplier is 3×, an alert fires after ~2.25 hours of silence (sustained across 3 cycles).

**Unusual Time**: Fires when activity occurs at a time slot that has very few historical observations — e.g., front door activity at 3am when baseline shows no history for that slot.

Severity is graded based on how far the inactivity exceeds the threshold:
| Severity | Condition |
|----------|-----------|
| LOW | 2-3× threshold |
| MEDIUM | 3-5× threshold |
| HIGH | 5×+ threshold |

### Drift Detection

Uses **bidirectional CUSUM** (Cumulative Sum) to detect persistent shifts in daily activity rates. Unlike acute detection (which catches immediate events), drift detection identifies gradual changes over days or weeks.

Examples:
- "Daily activity from bedroom motion sensor has decreased persistently" (possible reduced mobility)
- "Front door activity has increased persistently" (new visitor pattern, changed schedule)

Sensitivity tiers control how quickly drift is detected:
| Sensitivity | CUSUM Parameters | Detection Speed |
|-------------|-----------------|-----------------|
| High | k=0.25, h=2.0 | Fastest — catches subtle shifts |
| Medium | k=0.5, h=4.0 | Balanced (default) |
| Low | k=1.0, h=6.0 | Slowest — only large sustained shifts |

The `routine_reset` service clears the drift accumulator for an entity when a routine change is intentional (e.g., started working from home).

### Suppression Logic

All notifications pass through suppression filters:
- **Holiday mode**: Blocks all notifications
- **Snooze**: Blocks all notifications for the snooze duration
- **Per-entity cooldown**: Prevents re-alerting the same entity within the cooldown window
- **Welfare debounce**: Requires 3 consecutive cycles of elevated welfare status before changing the welfare state

## Notifications

When an anomaly is detected, notifications include:
- Entity ID and alert type (inactivity, unusual time, or drift)
- Human-readable explanation from the detection engine
- Severity level

### Mobile Notifications

The integration includes a "Mobile notification services" configuration option that supports multiple devices. To use it:

1. Install the Home Assistant Companion app on each device you want to notify
2. Find your notification service names:
   - Go to **Developer Tools** → **Services**
   - Search for "mobile_app" to find services like `notify.mobile_app_your_phone`
3. Add each service name in the Behaviour Monitor configuration

For more control, create automations triggered by the Behaviour Monitor sensors (see example automations in the Holiday Mode section above or the HOLIDAY_SNOOZE_MODE.md file).

## Data Storage

The integration stores data in Home Assistant's `.storage` directory:

- **Routine model and coordinator state**: `.storage/behaviour_monitor.{entry_id}.json`
  - Per-entity routine baselines (168 slots with Welford accumulators)
  - CUSUM drift detection state
  - Daily activity counts
  - Notification tracking history
  - Holiday mode and snooze status

All data persists across Home Assistant restarts. Daily counts are only restored if from the same day (resets automatically at midnight).

## Troubleshooting

### No Anomalies Detected

- Check `baseline_confidence` sensor — detection activates as the routine model learns (proportional to history window)
- Verify monitored entities are actually changing state
- Check if "Track attributes" is enabled if your entities only change attributes
- Inactivity alerts require the learned interval to be established (sufficient slot observations)

### Activity Not Being Tracked

- Ensure the entity is in the monitored entities list
- Check if "Track attributes" is enabled — some entities only change attributes, not state
- **Check if Holiday Mode is enabled** — all tracking is paused when ON
- **Check if Snoozed** — pattern learning is paused during snooze

### Drift Alerts After Intentional Routine Change

Use the `routine_reset` service to clear the drift accumulator:
```yaml
service: behaviour_monitor.routine_reset
data:
  entity_id: "binary_sensor.front_door"
```

### Holiday Mode or Snooze Not Working

**Holiday Mode not pausing:**
- Verify `switch.behaviour_monitor_holiday_mode` shows "on"
- Check logs — should see no "Recorded state change" messages when ON

**Snooze not pausing:**
- Verify `select.behaviour_monitor_snooze_notifications` shows selected duration
- Check sensor attributes for `snooze_active: true` and `snooze_until` timestamp
- Verify snooze hasn't expired (check current time vs `snooze_until`)

## Requirements

- Home Assistant 2024.1.0 or newer
- Recorder integration (dependency, enabled by default)
- No external Python dependencies required

## Development

### Running Tests

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements-test.txt

# Run tests
make test
```

See [README-DEV.md](README-DEV.md) for complete development setup instructions.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed list of changes.

## License

MIT License
