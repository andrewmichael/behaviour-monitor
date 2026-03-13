# Architecture

**Analysis Date:** 2026-03-13

## Pattern Overview

**Overall:** Observer-Coordinator Pattern with Dual Anomaly Detection Pipeline

**Key Characteristics:**
- Real-time state change observation via Home Assistant event bus
- Parallel statistical and machine learning analysis
- Event-driven coordinator managing pattern updates and notifications
- Persistent storage for statistical patterns and ML models
- Optional ML layer gracefully disabled when dependencies unavailable

## Layers

**Integration Entry Point:**
- Purpose: Home Assistant integration setup/teardown and service registration
- Location: `custom_components/behaviour_monitor/__init__.py`
- Contains: `async_setup_entry()`, `async_unload_entry()`, `async_reload_entry()`
- Depends on: Coordinator, Config flow
- Used by: Home Assistant core

**Coordination & Data Flow:**
- Purpose: Manages data updates, orchestrates analysis, sends notifications
- Location: `custom_components/behaviour_monitor/coordinator.py` (BehaviourMonitorCoordinator)
- Contains: State change listening, anomaly detection orchestration, persistence, notifications
- Depends on: PatternAnalyzer, MLPatternAnalyzer, Home Assistant Store
- Used by: Sensor, Switch, Select platforms

**Statistical Analysis:**
- Purpose: Z-score based anomaly detection on time-bucketed historical patterns
- Location: `custom_components/behaviour_monitor/analyzer.py` (PatternAnalyzer, EntityPattern, TimeBucket)
- Contains: 672 time buckets (7 days × 96 intervals), anomaly detection logic, welfare assessment
- Depends on: None (pure statistical)
- Used by: Coordinator

**Machine Learning Analysis:**
- Purpose: Optional streaming anomaly detection using Half-Space Trees
- Location: `custom_components/behaviour_monitor/ml_analyzer.py` (MLPatternAnalyzer, MLAnomalyResult)
- Contains: River-based anomaly detection, cross-sensor correlation patterns, model retraining
- Depends on: River library (optional)
- Used by: Coordinator

**Platform Entities:**
- Purpose: Expose integration data to Home Assistant
- Locations:
  - `custom_components/behaviour_monitor/sensor.py` (14 sensor types)
  - `custom_components/behaviour_monitor/switch.py` (Holiday Mode control)
  - `custom_components/behaviour_monitor/select.py` (Snooze Duration control)
- Depends on: Coordinator
- Used by: Home Assistant UI/automations

**Configuration:**
- Purpose: Configuration flow UI and constants
- Locations:
  - `custom_components/behaviour_monitor/config_flow.py`
  - `custom_components/behaviour_monitor/const.py`
- Contains: Entity selection, sensitivity settings, feature toggles, notification options
- Depends on: Home Assistant helpers
- Used by: Coordinator, Sensors

## Data Flow

**Setup Flow:**

1. Home Assistant calls `async_setup_entry()` (`__init__.py`)
2. Create BehaviourMonitorCoordinator instance
3. Coordinator loads persistent data from `.storage/behaviour_monitor.{entry_id}.json`
4. Coordinator loads ML data (if enabled) from `.storage/behaviour_monitor_ml.{entry_id}.json`
5. Subscribe to `EVENT_STATE_CHANGED` on Home Assistant event bus
6. Forward setup to platforms (sensor, switch, select)
7. Register four service handlers (enable_holiday_mode, disable_holiday_mode, snooze, clear_snooze)

**State Change Event Flow:**

1. Home Assistant event bus fires `EVENT_STATE_CHANGED`
2. Coordinator's `_handle_state_changed()` callback fires (synchronous, low latency)
3. Check: Skip if holiday mode enabled or entity not monitored
4. StatisticalAnalyzer records change (updates day bucket for timestamp)
5. If ML enabled: Record event in MLPatternAnalyzer (unless snoozed)
6. Trigger async refresh of coordinator data

**Data Update Flow (60-second interval via DataUpdateCoordinator):**

1. `_async_update_data()` executes periodically
2. Check for statistical anomalies via `analyzer.check_for_anomalies()` (Z-score based)
3. If ML enabled and trained: Check ML anomalies and cross-sensor patterns
4. Determine if anomalies should trigger notifications (respect learning periods and snooze state)
5. Send notifications to configured services (or persistent_notification)
6. Save coordinator state and ML model state to persistent storage
7. Build data dictionary for sensors:
   - last_activity, activity_score, anomaly_detected, confidence, daily_count
   - anomalies list, ml_status, cross_sensor_patterns
   - welfare_status, routine_progress, activity_context, entity_status
   - last_notification, holiday_mode, snooze_active
8. Return data dictionary (triggers sensor state updates via CoordinatorEntity)

**Sensor Update Flow:**

1. CoordinatorEntity base class receives data dictionary
2. Each SensorEntityDescription applies value_fn to extract value
3. extra_attrs_fn builds additional attributes
4. Sensor state and attributes updated in Home Assistant

## State Management

**Pattern State:**
- Stored in PatternAnalyzer.patterns dict (entity_id → EntityPattern)
- Each EntityPattern contains 7 days × 96 intervals of TimeBucket statistics
- TimeBucket tracks: count, sum_values, sum_squared (for mean/std_dev calculation)
- Serialized via `to_dict()`/`from_dict()` to JSON on-demand

**ML Model State:**
- Stored in MLPatternAnalyzer instance
- Half-Space Tree model from River library (serializable via state snapshots)
- Cross-sensor correlation patterns tracked in list
- Serialized via `to_dict()`/`from_dict()` to JSON

**Coordinator State:**
- Transient: recent_anomalies, recent_ml_anomalies, recent_events
- Persistent: holiday_mode, snooze_until, last_notification_time/type, last_welfare_status
- Loaded on `async_setup()`, saved on state changes and periodic updates

## Key Abstractions

**EntityPattern:**
- Purpose: Represents learned behavior for a single entity
- Examples: `"light.living_room"`, `"sensor.door_motion"`
- Pattern: 672 statistical buckets keyed by (day_of_week, 15-min interval)
- Method: `record_activity(timestamp)` → updates bucket
- Method: `get_expected_activity(timestamp)` → returns (mean, std_dev) for time slot
- Storage: Persistent JSON with all bucket statistics

**TimeBucket:**
- Purpose: Holds statistics for one time slot (e.g., Monday 14:45-15:00)
- Pattern: Welford online algorithm (count, sum, sum_squared for numerical stability)
- Computed properties: mean, std_dev (calculated on-demand from sums)

**AnomalyResult:**
- Purpose: Result of statistical anomaly detection
- Contains: entity_id, anomaly_type, description, severity, z_score
- Created by: `analyzer.check_for_anomalies()`
- Used by: Notifications and sensor data

**MLAnomalyResult:**
- Purpose: Result of ML anomaly detection
- Contains: entity_id (optional), anomaly_type, description, timestamp
- Created by: `ml_analyzer.check_anomaly()` and `check_cross_sensor_anomalies()`
- Used by: Notifications and sensor data

**StateChangeEvent:**
- Purpose: Recorded state transition for ML analysis
- Contains: entity_id, timestamp, old_state, new_state
- Created by: `_handle_state_changed()` event callback
- Used by: MLPatternAnalyzer for pattern learning and anomaly detection
- Storage: Transient list kept in coordinator; full history in ML storage

**CrossSensorPattern:**
- Purpose: Tracks correlation between two entities
- Computed: correlation_strength = function of co-occurrence_count and ordering consistency
- Used by: ML anomaly detection to detect unusual combinations
- Storage: Stored in MLPatternAnalyzer.cross_sensor_patterns list

## Entry Points

**Integration Setup:**
- Location: `custom_components/behaviour_monitor/__init__.py::async_setup_entry()`
- Triggers: User adds integration via Home Assistant UI (config_flow)
- Responsibilities: Create coordinator, load data, subscribe to state changes, register services, set up platforms

**State Change Events:**
- Location: `custom_components/behaviour_monitor/coordinator.py::_handle_state_changed()`
- Triggers: Home Assistant EVENT_STATE_CHANGED for any monitored entity
- Responsibilities: Record activity in analyzers, trigger refresh request

**Periodic Update:**
- Location: `custom_components/behaviour_monitor/coordinator.py::_async_update_data()`
- Triggers: DataUpdateCoordinator interval (60 seconds) via async_request_refresh()
- Responsibilities: Check anomalies, send notifications, save state, provide sensor data

**Configuration Changes:**
- Location: `custom_components/behaviour_monitor/config_flow.py`
- Triggers: User modifies options in UI (reload via async_reload_entry)
- Responsibilities: Validate input, update coordinator configuration, recreate patterns if needed

**Service Calls:**
- Location: `custom_components/behaviour_monitor/__init__.py` service handlers
- Triggers: User calls service via service.yaml or automations
- Responsibilities: Enable/disable holiday mode, apply/clear snooze

## Error Handling

**Strategy:** Graceful degradation with logging

**Patterns:**
- ML features: If River library missing, ML_AVAILABLE flag False, features silently disabled
- Pattern loading: If stored data format changes, fallback to empty patterns
- Notification failure: Log error, continue operating (don't block updates)
- Learning periods: Don't send notifications until learning complete (prevents false positives)
- Snooze expired: Check during state changes, remove if past due time

## Cross-Cutting Concerns

**Logging:**
- Module logger: `_LOGGER = logging.getLogger(__name__)`
- DEBUG: Per-entity state changes, pattern loading details
- INFO: Startup summary, entity counts, feature status (ML enabled/disabled)
- WARNING: ML library not available, learning period not met

**Validation:**
- Config flow: Entity selector, numeric ranges (sensitivity, periods), boolean toggles
- State changes: Verify entity_id in monitored set, check old_state/new_state not None
- Anomaly detection: Only after learning periods complete, respect snooze/holiday mode

**Authentication:**
- Home Assistant integration: No auth required (uses HA's permission model)
- Services: Registered with coordinator instance (access via DOMAIN + entry_id)

**Persistence:**
- Storage: Home Assistant's Store helper (`.storage/` directory)
- Format: JSON via `to_dict()`/`from_dict()` methods
- Frequency: Saved on state changes, periodic updates, graceful shutdown
- Versioning: STORAGE_VERSION = 2 (supports format migration)

---

*Architecture analysis: 2026-03-13*
