# Behaviour Monitor

A Home Assistant custom integration that learns entity state patterns and detects anomalies using statistical analysis and optional machine learning. Ideal for **elder care monitoring**, security, and detecting unusual activity patterns.

## Features

- **Statistical Pattern Learning**: Tracks state changes in 15-minute buckets with per-weekday distinction (672 buckets per entity)
- **Machine Learning** (optional): Half-Space Trees for streaming anomaly detection using River
- **Cross-Sensor Correlation**: Learns relationships between sensors (e.g., "motion sensor usually triggers before light turns on")
- **Hybrid Detection**: Combines Z-score statistics with ML for comprehensive anomaly detection
- **Elder Care Monitoring**: Welfare status, routine progress tracking, and severity-graded alerts
- **Attribute Tracking**: Optionally track attribute changes, not just state changes
- **Notifications**: Sends persistent notifications with severity levels for unusual activity patterns
- **HACS Compatible**: Install via HACS for easy updates

## Elder Care Use Case

This integration is designed for monitoring the wellbeing of elderly family members by learning their daily patterns and alerting when something is out of character:

**What it monitors:**
- Motion sensor activity (movement around the home)
- Door/window sensors (exits, entries, room changes)
- Light switches (daily routine indicators)
- Appliance usage (kettle, TV, etc.)

**What it detects:**
- No morning activity when there usually is
- Significantly reduced activity compared to normal
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
- "🚨 No activity for 4 hours (usually active every 45 minutes)"
- "⚠️ Daily routine only 20% complete by 10am (usually 80%)"
- "ℹ️ Motion sensor showing unusual inactivity for Tuesday 09:15"

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

### Enabling ML Features (Optional)

ML features require the River library. **The integration works perfectly without it** using statistical analysis only. Most users won't need ML - statistical Z-score detection is effective for pattern anomaly detection.

**Home Assistant Core (any platform):**
```bash
pip install river
```

**Home Assistant OS / Supervised / Container:**

1. Install the **SSH & Web Terminal** add-on from the Add-on Store (or **Advanced SSH & Web Terminal** from the community add-ons)

2. Configure the add-on to disable "Protection mode" (required to access the HA container)

3. Start the add-on and open the terminal

4. Run the following command:
   ```bash
   docker exec -it homeassistant pip install river
   ```

5. Restart Home Assistant for the changes to take effect

**Alternative method using the Terminal & SSH add-on:**
```bash
# If you have the Terminal & SSH add-on with protection mode disabled:
ha core exec -it bash
pip install river
exit
ha core restart
```

**Note:** The River library will need to be reinstalled after Home Assistant OS updates, as the container is recreated. Consider adding this to your startup automation or checking the ML Status sensor after updates.

River is designed for streaming data and works well on Home Assistant OS because:
- It has pre-built wheels for multiple Python versions including 3.13
- It doesn't require compilation of C extensions (unlike scikit-learn)
- It uses incremental/streaming learning which is ideal for Home Assistant's event-driven architecture
- Package size is small (~2.5MB) compared to scikit-learn (~25MB+)

If River is not installed, the integration will log a warning and automatically disable ML features. Statistical analysis will continue to work.

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Behaviour Monitor"
3. Select the entities you want to monitor
4. Configure settings

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| Entities to monitor | Select entities whose state changes should be tracked | Required |
| Sensitivity | Anomaly detection threshold (Low=3σ, Medium=2σ, High=1σ) | Medium |
| Learning period | Days before statistical anomaly detection activates | 7 days |
| Enable notifications | Send persistent notifications when anomalies are detected | Yes |
| Enable ML | Enable Half-Space Trees machine learning (requires River) | Yes |
| ML learning period | Days before ML notifications are sent (requires 100+ samples too) | 7 days |
| ML retrain period | How often to replay historical data for model warmup | 14 days |
| Cross-sensor window | Time window for detecting sensor correlations | 300 seconds |
| Track attributes | Also track attribute changes, not just state changes | Yes |
| Mobile notification services | Services to send mobile notifications (e.g., `notify.mobile_app_iphone`) | Empty |

## Sensors

The integration creates the following sensors:

### Core Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.behaviour_monitor_last_activity` | Timestamp of the most recent detected state change |
| `sensor.behaviour_monitor_activity_score` | Current activity level (0-100%) compared to baseline |
| `sensor.behaviour_monitor_anomaly_detected` | "on" when an anomaly is currently detected |
| `sensor.behaviour_monitor_baseline_confidence` | Progress of statistical pattern learning (0-100%) |
| `sensor.behaviour_monitor_daily_activity_count` | Total state changes recorded today |
| `sensor.behaviour_monitor_cross_sensor_patterns` | Number of detected cross-sensor correlations |
| `sensor.behaviour_monitor_ml_status` | ML status: "Ready", "Trained (learning)", "Learning", or "Disabled" |
| `sensor.behaviour_monitor_statistical_training_remaining` | Time remaining until statistical learning completes |
| `sensor.behaviour_monitor_ml_training_remaining` | Time remaining until ML learning completes |
| `sensor.behaviour_monitor_last_notification` | Timestamp of the last notification sent |

### Elder Care Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.behaviour_monitor_welfare_status` | Overall welfare status: `ok`, `check_recommended`, `concern`, or `alert` |
| `sensor.behaviour_monitor_routine_progress` | Daily routine completion percentage (0-100%) |
| `sensor.behaviour_monitor_time_since_activity` | Human-readable time since last activity with context |
| `sensor.behaviour_monitor_entity_status_summary` | Summary of entity statuses (e.g., "5 OK, 2 Need Attention") |

### Sensor Attributes

**ML Status** sensor values:
| Value | Meaning |
|-------|---------|
| `Ready` | Both 100+ samples AND learning period complete - will send notifications |
| `Trained (learning)` | Has 100+ samples but learning period not elapsed - won't send notifications yet |
| `Learning` | Still collecting samples (< 100) |
| `Disabled` | ML disabled or River not installed |

**ML Status** sensor attributes:
- `enabled`: Whether ML is enabled in config AND River is available
- `trained`: Whether the model has processed enough samples (100+)
- `ready`: Whether ML is fully ready to send notifications (samples + learning period)
- `sample_count`: Number of events processed by the ML model
- `samples_needed`: Events needed before ML becomes active
- `learning_period_complete`: Whether the configured learning days have passed
- `scikit_learn_available`: Whether River library is installed

**Welfare Status** sensor includes:
- `reasons`: List of reasons for current status
- `summary`: Brief description of welfare state
- `recommendation`: Suggested action (e.g., "Immediate welfare check recommended")
- `entity_count_by_status`: Breakdown of entities by alert level

**Routine Progress** sensor includes:
- `expected_by_now`: Expected activity count by current time
- `actual_today`: Actual activity count today
- `expected_full_day`: Total expected activities for the day
- `status`: `on_track`, `below_normal`, `concerning`, or `alert`
- `summary`: Human-readable progress description

**Time Since Activity** sensor includes:
- `time_since_activity`: Seconds since last activity
- `typical_interval`: Expected interval between activities (seconds)
- `typical_interval_formatted`: Human-readable typical interval
- `concern_level`: Ratio of actual to typical interval (>2.0 is concerning)
- `context`: Full context string (e.g., "Last activity 4 hours ago (usually every 45 minutes)")

**Entity Status Summary** sensor includes:
- `entity_status`: Detailed list of each monitored entity with:
  - Status (`normal`, `attention`, `concern`, `alert`)
  - Severity (`normal`, `minor`, `moderate`, `significant`, `critical`)
  - Time since last activity
  - Z-score deviation from expected

**Anomaly Detected** sensor includes:
- `anomaly_details`: List of current anomalies with entity, type, severity, and description

**Baseline Confidence** sensor includes:
- `learning_progress`: "learning" or "complete"
- `ml_status`: ML training status, sample count, last/next retrain times
- `last_retrain`: Timestamp of last ML model training

**Cross-Sensor Patterns** sensor includes:
- `cross_sensor_patterns`: List of learned correlations with strength and timing

**Statistical Training Remaining** sensor includes:
- `complete`: Whether statistical learning is complete
- `days_remaining`: Days until learning period completes
- `days_elapsed`: Days since first observation
- `total_days`: Configured learning period in days
- `first_observation`: Timestamp of first recorded event

**ML Training Remaining** sensor includes:
- `complete`: Whether ML is fully ready (samples + time)
- `status`: Current status description
- `days_remaining`: Days until learning period completes
- `samples_remaining`: Samples needed to reach 100
- `samples_processed`: Current sample count
- `first_event`: Timestamp of first ML event

**Last Notification** sensor includes:
- `type`: Type of last notification sent (`statistical`, `ml`, or `welfare`)

## How It Works

### Statistical Analysis (Z-score)

The integration tracks state changes for each monitored entity in:
- **96 time buckets** per day (15-minute intervals)
- **7 day types** (Monday through Sunday)
- **672 total buckets** per entity

For each bucket, it calculates mean and standard deviation. Anomalies are flagged when current activity deviates significantly from the baseline:

```
Z-score = |actual - expected_mean| / standard_deviation
```

Sensitivity levels:
- **Low (3σ)**: Only extreme anomalies (~0.3% false positive rate)
- **Medium (2σ)**: Moderate anomalies (~5% false positive rate)
- **High (1σ)**: Any deviation (~32% false positive rate)

### Machine Learning (Half-Space Trees)

When ML is enabled and River is installed, the integration uses Half-Space Trees (HST) for streaming anomaly detection. Unlike batch-trained models, HST learns incrementally from each event:

| Feature | Description |
|---------|-------------|
| Hour of day | Normalized time (0-1) |
| Minute bucket | 15-minute interval within hour |
| Day of week | 0=Monday through 6=Sunday |
| Weekend flag | Binary weekend indicator |
| Time since last activity | Seconds since entity's last change |
| Recent activity rate | Activity count in last hour |
| Entity identifier | Normalized entity index |

**Streaming vs Batch Learning:**
- The model starts learning immediately from the first event
- Each event updates the model incrementally (no "training" step needed)
- The model becomes effective after ~100 events
- Historical data can be replayed to warm up the model after restarts

### Cross-Sensor Correlation

The integration learns patterns between sensors:

```
Example learned patterns:
- motion_sensor.hallway → light.hallway (usually within 5 seconds)
- door_sensor.front → motion_sensor.entry (usually within 10 seconds)
```

When a sensor triggers but its correlated sensor doesn't respond within the expected window, an anomaly is flagged. This can detect:

- **Missing activity**: Door opened but no motion detected
- **Broken patterns**: Usual sequence didn't occur

### Hybrid Detection

Both statistical and ML anomalies are reported:
- **Statistical**: Quick, explainable (Z-score), works immediately after learning period
- **ML**: Catches complex multivariate patterns, learns continuously from each event

## Notifications

When an anomaly is detected, a persistent notification includes:
- Entity ID
- Time slot (e.g., "monday 09:15")
- Detection method (Statistical or ML)
- Anomaly details and scores
- Related entities (for cross-sensor anomalies)

### Mobile Notifications

There are two ways to receive notifications on your mobile device:

#### Option 1: Built-in Mobile Notification Services

The integration includes a "Mobile notification services" configuration option that supports multiple devices. To use it:

1. Install the Home Assistant Companion app on each device you want to notify
2. Find your notification service names:
   - Go to **Developer Tools** → **Services**
   - Search for "mobile_app" to find services like `notify.mobile_app_your_phone`
3. Add each service name (e.g., `notify.mobile_app_iphone`, `notify.mobile_app_ipad`) in the Behaviour Monitor configuration
   - You can add multiple services to notify multiple devices simultaneously

Mobile notifications include:
- Sound alerts for critical/significant anomalies
- Badge counts showing number of anomalies
- Time-sensitive interruption levels for critical welfare alerts
- Grouped notifications by type (statistical, ML, welfare)

#### Option 2: Custom Automations

For more control over when and how notifications are sent, create automations triggered by the Behaviour Monitor sensors.

**Basic Welfare Alert Automation:**

```yaml
alias: "Elder Care - Welfare Alert"
description: "Send mobile notification when welfare status changes to alert or concern"
trigger:
  - platform: state
    entity_id: sensor.behaviour_monitor_welfare_status
    to:
      - alert
      - concern
condition: []
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "🚨 Elder Care Welfare {{ states('sensor.behaviour_monitor_welfare_status') | title }}"
      message: >-
        {{ state_attr('sensor.behaviour_monitor_welfare_status', 'summary') }}

        Recommendation: {{ state_attr('sensor.behaviour_monitor_welfare_status', 'recommendation') }}

        Triggered sensors:
        {% set statuses = state_attr('sensor.behaviour_monitor_entity_status_summary', 'entity_status') %}
        {% for e in statuses if e.status in ['alert', 'concern', 'attention'] %}
        - {{ e.entity_id }}: {{ e.status }} ({{ e.time_since_activity }})
        {% endfor %}
      data:
        push:
          sound: default
          interruption-level: time-sensitive
        group: elder-care
        tag: welfare-alert
mode: single
```

**Anomaly Detection Automation:**

```yaml
alias: "Behaviour Monitor - Anomaly Alert"
description: "Send notification when any anomaly is detected"
trigger:
  - platform: state
    entity_id: sensor.behaviour_monitor_anomaly_detected
    to: "on"
condition:
  - condition: numeric_state
    entity_id: sensor.behaviour_monitor_baseline_confidence
    above: 99
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "⚠️ Unusual Activity Detected"
      message: >-
        {% set anomalies = state_attr('sensor.behaviour_monitor_anomaly_detected', 'anomaly_details') %}
        {% for a in anomalies %}
        - {{ a.entity_id }}: {{ a.description }} ({{ a.severity }})
        {% endfor %}
      data:
        push:
          sound: default
        group: behaviour-monitor
        tag: anomaly-alert
mode: single
```

**Low Activity Alert Automation:**

```yaml
alias: "Elder Care - Low Activity Alert"
description: "Alert when routine progress falls significantly below normal"
trigger:
  - platform: numeric_state
    entity_id: sensor.behaviour_monitor_routine_progress
    below: 50
    for:
      hours: 2
condition:
  - condition: time
    after: "09:00:00"
    before: "21:00:00"
  - condition: numeric_state
    entity_id: sensor.behaviour_monitor_baseline_confidence
    above: 99
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "ℹ️ Low Activity Detected"
      message: >-
        Routine progress is only {{ states('sensor.behaviour_monitor_routine_progress') }}%
        ({{ state_attr('sensor.behaviour_monitor_routine_progress', 'actual_today') }} activities,
        expected ~{{ state_attr('sensor.behaviour_monitor_routine_progress', 'expected_by_now') | round(0) }})

        Last activity: {{ states('sensor.behaviour_monitor_time_since_activity') }}

        Sensor status:
        {% set statuses = state_attr('sensor.behaviour_monitor_entity_status_summary', 'entity_status') %}
        {% for e in statuses %}
        - {{ e.entity_id }}: {{ e.status }} (last: {{ e.time_since_activity }})
        {% endfor %}
      data:
        push:
          sound: default
        group: elder-care
        tag: low-activity
mode: single
```

**No Activity for Extended Period:**

```yaml
alias: "Elder Care - Extended Inactivity"
description: "Alert when no activity for longer than typical interval"
trigger:
  - platform: template
    value_template: >-
      {{ state_attr('sensor.behaviour_monitor_time_since_activity', 'concern_level') | float(0) > 2.0 }}
    for:
      minutes: 30
condition:
  - condition: time
    after: "07:00:00"
    before: "23:00:00"
  - condition: numeric_state
    entity_id: sensor.behaviour_monitor_baseline_confidence
    above: 99
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "🚨 Extended Inactivity"
      message: >-
        {{ state_attr('sensor.behaviour_monitor_time_since_activity', 'context') }}

        Inactive sensors:
        {% set statuses = state_attr('sensor.behaviour_monitor_entity_status_summary', 'entity_status') %}
        {% for e in statuses if e.status != 'normal' %}
        - {{ e.entity_id }}: {{ e.time_since_activity }} ({{ e.severity }})
        {% endfor %}
      data:
        push:
          sound: default
          interruption-level: time-sensitive
        group: elder-care
        tag: extended-inactivity
        actions:
          - action: ACKNOWLEDGE
            title: "Acknowledged"
          - action: CALL_RELATIVE
            title: "Call Now"
mode: single
```

**Tips for Automations:**

- Always check `baseline_confidence` is above 99% to avoid false alerts during learning
- Use `for:` duration on triggers to avoid transient state changes
- Set appropriate time conditions to avoid night-time alerts
- Use notification `tag` to replace previous notifications instead of stacking
- Use `group` to organize notifications on mobile devices
- Add actionable buttons for quick responses

## Data Storage

- Statistical patterns: `.storage/behaviour_monitor.{entry_id}`
- ML data and events: `.storage/behaviour_monitor_ml.{entry_id}`

Data persists across Home Assistant restarts.

## Troubleshooting

### "Config flow could not be loaded" / 500 Error

This usually means a Python dependency is missing. Check the Home Assistant logs for details.

### ML Features Not Working

Check the `ml_status` sensor or the `ml_status` attribute on the `baseline_confidence` sensor:
- `enabled`: Whether ML is enabled in config AND River is available
- `trained`: Whether the model has processed enough events (100+)
- `sample_count`: Number of recorded events

If River is not installed, you'll see a warning in the logs:
```
Behaviour Monitor: ML features DISABLED - River library not installed.
Statistical analysis will still work. To enable ML, install: pip install river
```

### No Anomalies Detected

- Check `baseline_confidence` sensor - must reach 100% before detection starts
- Verify monitored entities are actually changing state
- Consider adjusting sensitivity level
- Check if "Track attributes" is enabled if your entities only change attributes

### Activity Not Being Tracked

- Ensure the entity is in the monitored entities list
- Check if "Track attributes" is enabled - some entities only change attributes, not state
- Look at debug logs to see if events are being received

## Requirements

- Home Assistant 2024.1.0 or newer
- Recorder integration (dependency, enabled by default)
- **Optional**: River (for ML features) - `pip install river`

## Hardware Notes

- Works well on Raspberry Pi 4+ and x86 systems
- Statistical analysis works on all hardware
- River's streaming ML is lightweight and works on all platforms
- ML becomes effective after ~100 state change events

## Development

### Running Tests

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements-test.txt
pip install river  # Optional, for ML tests

# Run tests
PYTHONPATH=. pytest tests/ -v
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed list of changes.

## License

MIT License
