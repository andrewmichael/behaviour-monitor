# External Integrations

**Analysis Date:** 2026-03-13

## APIs & External Services

**None detected** - This is a self-contained Home Assistant integration that does not call external APIs or cloud services. All processing is local.

## Data Storage

**Databases:**
- Not applicable - Integration uses Home Assistant's local storage system

**File Storage:**
- Local filesystem only - Uses Home Assistant `.storage/` directory
  - Connection: Local file system (JSON files)
  - Coordinator: `BehaviourMonitorCoordinator` with `Store` helper class

**Storage Structure:**
- `.storage/behaviour_monitor.{entry_id}.json` - Statistical patterns (672 time buckets per entity), daily activity counts, coordinator state, holiday/snooze modes
- `.storage/behaviour_monitor_ml.{entry_id}.json` - ML model events, cross-sensor patterns, sample counts, retrain timestamps

**Caching:**
- In-memory caching only
- Recent anomalies tracked in `_recent_anomalies` and `_recent_ml_anomalies` lists
- State event history maintained for cross-sensor correlation analysis

## Authentication & Identity

**Auth Provider:**
- Not applicable - Local integration, no external authentication needed

**Authorization:**
- Home Assistant user/admin authorization (delegated to Home Assistant core)
- No additional auth layer

## Monitoring & Observability

**Error Tracking:**
- None - Integration uses Python logging only (no external error tracking)

**Logs:**
- Standard Python logging via `_LOGGER` instances
- Log level controlled by Home Assistant
- Key events logged: ML availability, coordinator setup, state changes, anomalies detected

**Logging Points:**
- `custom_components/behaviour_monitor/__init__.py` - Integration setup/unload
- `custom_components/behaviour_monitor/coordinator.py` - Data updates, notifications
- `custom_components/behaviour_monitor/analyzer.py` - Anomaly calculations
- `custom_components/behaviour_monitor/ml_analyzer.py` - ML feature availability, model status

## CI/CD & Deployment

**Hosting:**
- No hosting required - Installed directly into Home Assistant instance
- HACS-compatible for easy discovery and updates
- Manual installation via copying to `custom_components/` directory

**CI Pipeline:**
- Not detected - Tests run locally via `make test` command
- GitHub Actions not configured in repository

**Distribution:**
- GitHub repository with HACS support
- Semantic versioning via conventional commits (feat: minor bump, fix: patch bump)

## Environment Configuration

**Required env vars:**
- None - Configuration done via Home Assistant ConfigFlow UI

**Integration Configuration (via UI):**
- `monitored_entities` - List of entity IDs to track
- `sensitivity` - Anomaly detection threshold (low/medium/high = 3σ/2σ/1σ)
- `learning_period` - Days before statistical detection activates (default: 7)
- `enable_notifications` - Send persistent notifications (default: True)
- `enable_ml` - Enable ML features if River available (default: True)
- `ml_learning_period` - Days before ML notifications send (default: 7)
- `retrain_period` - How often to replay historical data for model warmup (default: 14)
- `cross_sensor_window` - Time window for detecting sensor correlations (default: 300 seconds)
- `track_attributes` - Track attribute changes in addition to state (default: True)
- `notify_services` - Mobile notification service targets (default: empty, persistent_notification only)

**Optional Runtime Installation:**
- River ML library: `pip install river` or `docker exec -it homeassistant pip install river`

**Secrets location:**
- Not applicable - No API keys, tokens, or credentials used

## Webhooks & Callbacks

**Incoming:**
- None - Integration subscribes to Home Assistant EventBus (internal), doesn't expose HTTP endpoints

**Outgoing:**
- Mobile notifications sent to configured `notify.*` services (built-in Home Assistant notification dispatch)
- Persistent notifications sent via Home Assistant notification system
- Services registered for external automation triggers:
  - `behaviour_monitor.enable_holiday_mode`
  - `behaviour_monitor.disable_holiday_mode`
  - `behaviour_monitor.snooze`
  - `behaviour_monitor.clear_snooze`

## Home Assistant Integration Points

**Platforms:**
- SENSOR - 14 sensor entities providing anomaly data, welfare status, activity tracking
- SWITCH - Holiday mode toggle (`switch.behaviour_monitor_holiday_mode`)
- SELECT - Snooze duration selector (`select.behaviour_monitor_snooze_notifications`)

**Dependencies:**
- `recorder` - Required (tracks historical state changes)

**Event Subscriptions:**
- `EVENT_STATE_CHANGED` - Monitors all monitored entity state changes
- `async_on_unload` - Cleanup on integration unload

**Storage Helper:**
- `homeassistant.helpers.storage.Store` - JSON file-based persistence

**Coordinator Pattern:**
- Extends `DataUpdateCoordinator[dict[str, Any]]` from `homeassistant.helpers.update_coordinator`
- Update interval: 60 seconds (configurable)

**Configuration Flow:**
- `ConfigFlow` + `OptionsFlow` for installation and runtime configuration updates
- Entity selector for monitored entities list
- Number/text/boolean selectors for configuration parameters

## Optional Machine Learning Library Integration

**Library:** River (https://riverml.xyz/)

**Import Handling:**
```python
try:
    from river import anomaly
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
```

**Location:** `custom_components/behaviour_monitor/ml_analyzer.py`

**Features When Available:**
- Half-Space Trees streaming anomaly detection
- Incremental learning from each state change event
- Model warm-up via historical data replay
- Cross-sensor pattern correlation

**Fallback:** Integration fully functional without River - uses Z-score statistical analysis exclusively

---

*Integration audit: 2026-03-13*
