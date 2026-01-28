# Behaviour Monitor

A Home Assistant custom integration that learns entity state patterns and detects anomalies using statistical analysis and optional machine learning.

## Features

- **Statistical Pattern Learning**: Tracks state changes in 15-minute buckets with per-weekday distinction (672 buckets per entity)
- **Machine Learning** (optional): Isolation Forest for multivariate anomaly detection
- **Cross-Sensor Correlation**: Learns relationships between sensors (e.g., "motion sensor usually triggers before light turns on")
- **Hybrid Detection**: Combines Z-score statistics with ML for comprehensive anomaly detection
- **Notifications**: Sends persistent notifications for unusual activity patterns
- **HACS Compatible**: Install via HACS for easy updates

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

ML features require scikit-learn. The integration works without it (statistical analysis only).

**Home Assistant Core:**
```bash
pip install scikit-learn numpy
```

**Home Assistant OS / Supervised:**
```bash
# Via SSH & Web Terminal add-on
docker exec -it homeassistant pip install scikit-learn numpy
```

**Home Assistant Container:**
```bash
docker exec -it homeassistant pip install scikit-learn numpy
```

If scikit-learn is not installed, the integration will log a warning and disable ML features automatically.

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
| Enable ML | Enable Isolation Forest machine learning (requires scikit-learn) | Yes |
| ML retrain period | How often to retrain the ML model | 14 days |
| Cross-sensor window | Time window for detecting sensor correlations | 300 seconds |

## Sensors

The integration creates the following sensors:

| Sensor | Description |
|--------|-------------|
| `sensor.behaviour_monitor_last_activity` | Timestamp of the most recent detected state change |
| `sensor.behaviour_monitor_activity_score` | Current activity level (0-100%) compared to baseline |
| `sensor.behaviour_monitor_anomaly_detected` | "on" when an anomaly is currently detected |
| `sensor.behaviour_monitor_baseline_confidence` | Progress of statistical pattern learning (0-100%) |
| `sensor.behaviour_monitor_daily_activity_count` | Total state changes recorded today |
| `sensor.behaviour_monitor_cross_sensor_patterns` | Number of detected cross-sensor correlations |

### Sensor Attributes

**Anomaly Detected** sensor includes:
- `anomaly_details`: List of current anomalies with entity, type, and description

**Baseline Confidence** sensor includes:
- `learning_progress`: "learning" or "complete"
- `ml_status`: ML training status, sample count, last/next retrain times
- `last_retrain`: Timestamp of last ML model training

**Cross-Sensor Patterns** sensor includes:
- `cross_sensor_patterns`: List of learned correlations with strength and timing

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

### Machine Learning (Isolation Forest)

When ML is enabled and scikit-learn is installed, the integration uses Isolation Forest for anomaly detection based on:

| Feature | Description |
|---------|-------------|
| Hour of day | Normalized time (0-1) |
| Minute bucket | 15-minute interval within hour |
| Day of week | 0=Monday through 6=Sunday |
| Weekend flag | Binary weekend indicator |
| Time since last activity | Seconds since entity's last change |
| Recent activity rate | Activity count in last hour |
| Entity identifier | Normalized entity index |

The model is automatically retrained at the configured interval (default: 2 weeks). First training occurs after 100 state change events.

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
- **ML**: Catches complex multivariate patterns, requires training data (100+ events)

## Notifications

When an anomaly is detected, a persistent notification includes:
- Entity ID
- Time slot (e.g., "monday 09:15")
- Detection method (Statistical or ML)
- Anomaly details and scores
- Related entities (for cross-sensor anomalies)

## Data Storage

- Statistical patterns: `.storage/behaviour_monitor.{entry_id}`
- ML data and events: `.storage/behaviour_monitor_ml.{entry_id}`

Data persists across Home Assistant restarts.

## Troubleshooting

### "Config flow could not be loaded" / 500 Error

This usually means a Python dependency is missing. Check the Home Assistant logs for details.

If you see `ModuleNotFoundError: No module named 'sklearn'`:
- This is expected if scikit-learn isn't installed
- The integration should still work with statistical analysis only
- To enable ML, install scikit-learn (see [Enabling ML Features](#enabling-ml-features-optional))

### ML Features Not Working

Check the `ml_status` attribute on the `baseline_confidence` sensor:
- `enabled`: Whether ML is enabled in config AND scikit-learn is available
- `trained`: Whether the model has been trained (requires 100+ events)
- `sample_count`: Number of recorded events

### No Anomalies Detected

- Check `baseline_confidence` sensor - must reach 100% before detection starts
- Verify monitored entities are actually changing state
- Consider adjusting sensitivity level

## Requirements

- Home Assistant 2024.1.0 or newer
- Recorder integration (dependency, enabled by default)
- **Optional**: scikit-learn, numpy (for ML features)

## Hardware Notes

- Works well on Raspberry Pi 4+ and x86 systems
- Statistical analysis works on all hardware
- Pi 3: ML training may be slow - consider disabling ML or using longer retrain periods
- First ML training occurs after 100 state change events

## Development

### Running Tests

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements-test.txt

# Run tests
PYTHONPATH=. pytest tests/ -v
```

## License

MIT License
