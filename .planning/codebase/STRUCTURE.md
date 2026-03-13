# Codebase Structure

**Analysis Date:** 2026-03-13

## Directory Layout

```
behaviour-monitor/
├── custom_components/behaviour_monitor/    # Main integration code
│   ├── __init__.py                         # Integration entry point (setup/unload)
│   ├── analyzer.py                         # Statistical pattern analyzer (PatternAnalyzer)
│   ├── ml_analyzer.py                      # ML pattern analyzer (MLPatternAnalyzer, optional)
│   ├── coordinator.py                      # Data coordinator (BehaviourMonitorCoordinator)
│   ├── config_flow.py                      # Configuration UI flow
│   ├── const.py                            # Constants and defaults
│   ├── sensor.py                           # 14 sensor platform entities
│   ├── switch.py                           # Holiday Mode switch control
│   ├── select.py                           # Snooze Duration select control
│   ├── manifest.json                       # Integration metadata
│   ├── services.yaml                       # Service definitions
│   ├── translations/                       # Localization files
│   └── custom_components/                  # (nested, symlink during development)
│
├── tests/                                  # Test suite
│   ├── conftest.py                         # Pytest fixtures and mock helpers
│   ├── test_analyzer.py                    # PatternAnalyzer unit tests
│   ├── test_ml_analyzer.py                 # MLPatternAnalyzer unit tests
│   ├── test_coordinator.py                 # BehaviourMonitorCoordinator tests
│   ├── test_init.py                        # Integration setup/teardown tests
│   ├── test_config_flow.py                 # Config flow UI tests
│   ├── test_sensor.py                      # Sensor platform tests
│   ├── test_switch.py                      # Switch platform tests
│   └── test_select.py                      # Select platform tests
│
├── .github/                                # GitHub CI/CD
├── .planning/codebase/                     # GSD codebase analysis docs
├── Makefile                                # Build/test commands
├── pytest.ini                              # Pytest configuration
├── requirements-dev.txt                    # Dev dependencies
├── requirements-test.txt                   # Test dependencies
├── README.md                               # User documentation
├── README-DEV.md                           # Developer setup guide
└── CHANGELOG.md                            # Release notes
```

## Directory Purposes

**custom_components/behaviour_monitor/:**
- Purpose: Home Assistant custom integration implementation
- Contains: Core analyzer logic, coordinator, platform entities, configuration
- Key files: `__init__.py` (entry), `coordinator.py` (orchestrator), `analyzer.py` (algorithms)

**tests/:**
- Purpose: Complete test coverage of all components
- Contains: Unit tests for analyzers, integration tests with mocked Home Assistant
- Key files: `conftest.py` (fixtures), one test_*.py per module

**custom_components/behaviour_monitor/translations/:**
- Purpose: Localization files (one directory per language)
- Contains: .json files for UI strings
- Pattern: `en/strings.json` for English, etc.

## Key File Locations

**Entry Points:**
- `custom_components/behaviour_monitor/__init__.py`: Integration lifecycle (async_setup_entry, async_unload_entry, async_reload_entry), service registration

**Configuration:**
- `custom_components/behaviour_monitor/const.py`: All constants, defaults, sensitivity thresholds
- `custom_components/behaviour_monitor/config_flow.py`: Config UI, options flow, validation
- `custom_components/behaviour_monitor/manifest.json`: Integration metadata, version, dependencies

**Core Logic:**
- `custom_components/behaviour_monitor/analyzer.py`: PatternAnalyzer (Z-score), EntityPattern (time buckets), TimeBucket (statistics)
- `custom_components/behaviour_monitor/ml_analyzer.py`: MLPatternAnalyzer (River stream anomaly), CrossSensorPattern, StateChangeEvent
- `custom_components/behaviour_monitor/coordinator.py`: BehaviourMonitorCoordinator (data flow, notifications, persistence)

**Platforms:**
- `custom_components/behaviour_monitor/sensor.py`: 14 sensors (last_activity, activity_score, anomaly_detected, baseline_confidence, etc.)
- `custom_components/behaviour_monitor/switch.py`: Holiday Mode switch
- `custom_components/behaviour_monitor/select.py`: Snooze Duration selector

**Services:**
- `custom_components/behaviour_monitor/services.yaml`: Service schema definitions (enable_holiday_mode, disable_holiday_mode, snooze, clear_snooze)

**Testing:**
- `tests/conftest.py`: Fixtures for Home Assistant mock, coordinator factory, sample configs
- `tests/test_analyzer.py`: TimeBucket, EntityPattern, PatternAnalyzer unit tests (670+ lines)
- `tests/test_ml_analyzer.py`: MLPatternAnalyzer, StateChangeEvent, CrossSensorPattern tests (360+ lines)
- `tests/test_coordinator.py`: BehaviourMonitorCoordinator integration tests (780+ lines)
- `tests/test_init.py`: Integration setup/unload lifecycle tests (350+ lines)
- `tests/test_sensor.py`: Sensor platform entity tests (550+ lines)
- `tests/test_switch.py`: Switch platform tests (210+ lines)
- `tests/test_select.py`: Select platform tests (330+ lines)

## Naming Conventions

**Files:**
- Snake case: `analyzer.py`, `ml_analyzer.py`, `config_flow.py`
- Test files: `test_*.py` prefix (matches pytest discovery)
- Platform files: `sensor.py`, `switch.py`, `select.py` (Home Assistant convention)

**Directories:**
- Snake case: `custom_components`, `behaviour_monitor`, `translations`
- Standard Home Assistant layout: `custom_components/{domain}/{files}`

**Classes:**
- PascalCase: `PatternAnalyzer`, `MLPatternAnalyzer`, `BehaviourMonitorCoordinator`, `EntityPattern`
- Platform entities: `BehaviourMonitorSensor`, `HolidayModeSwitch`, `SnoozeDurationSelect`
- Dataclasses: `TimeBucket`, `EntityPattern`, `AnomalyResult`, `MLAnomalyResult`, `StateChangeEvent`, `CrossSensorPattern`

**Functions/Methods:**
- Snake case: `record_activity()`, `check_for_anomalies()`, `async_setup_entry()`
- Async Home Assistant: `async_*` prefix (e.g., `async_setup()`, `async_shutdown()`, `_async_update_data()`)
- Event handlers: `_handle_*` prefix (e.g., `_handle_state_changed()`)
- Private methods: `_*` prefix (e.g., `_save_data()`, `_send_notification()`)

**Variables/Constants:**
- Constants: UPPERCASE with underscores (e.g., `DOMAIN`, `DEFAULT_LEARNING_PERIOD`, `SENSITIVITY_THRESHOLDS`)
- Module-level: Private with `_` prefix (e.g., `_LOGGER = logging.getLogger(__name__)`)
- Properties: Snake case (e.g., `entity_id`, `holiday_mode`, `is_trained`)

## Where to Add New Code

**New Feature (e.g., new sensor type):**
- Primary code: `custom_components/behaviour_monitor/sensor.py` (add BehaviourMonitorSensorDescription to SENSOR_DESCRIPTIONS tuple)
- Coordinator support: `custom_components/behaviour_monitor/coordinator.py` (_async_update_data returns dict with new key)
- Tests: `tests/test_sensor.py` (add test for new sensor in test fixtures and assertions)
- Constants: `custom_components/behaviour_monitor/const.py` (add ATTR_* constant for attribute)

**New Analysis Method (e.g., new anomaly type):**
- Analyzer core: `custom_components/behaviour_monitor/analyzer.py` (add method to PatternAnalyzer)
- Result type: Use existing AnomalyResult or create new dataclass
- Coordinator integration: `custom_components/behaviour_monitor/coordinator.py` (_async_update_data calls new method)
- Tests: `tests/test_analyzer.py` (unit tests for new method)

**New Configuration Option:**
- Constants: `custom_components/behaviour_monitor/const.py` (add CONF_*, DEFAULT_*, validation maps)
- Config flow: `custom_components/behaviour_monitor/config_flow.py` (add selector to data_schema and options_schema)
- Coordinator: `custom_components/behaviour_monitor/coordinator.py` (__init__ reads config, stores as instance variable)
- Tests: `tests/test_config_flow.py` (test new option in config flow)

**New Control (switch/select/button):**
- Implementation: Create new entity class in appropriate file (switch.py, select.py, etc.)
- Coordinator callback: `custom_components/behaviour_monitor/coordinator.py` (add async method, e.g., async_snooze)
- Setup: `custom_components/behaviour_monitor/sensor.py` async_setup_entry (instantiate and add entity)
- Tests: Create test_*.py if new platform, or add to existing test file

**New Test:**
- Location: `tests/test_*.py` matching component (or existing test_*.py if adding to existing component)
- Fixtures: Use conftest.py fixtures (hass_mock, coordinator, config_entry)
- Imports: Follow existing pattern (pytest, mock, component imports)
- Naming: `test_*` function names, `Test*` class names

## Special Directories

**translations/:**
- Purpose: Localization files
- Generated: No (manually curated)
- Committed: Yes
- Structure: `en/strings.json` for each language code
- Triggers: Config flow UI text, service descriptions

**.storage/ (at runtime):**
- Purpose: Home Assistant persistent storage
- Generated: Yes (created by Home Assistant Store)
- Committed: No (in .gitignore)
- Files: `behaviour_monitor.{entry_id}.json` (analyzer state), `behaviour_monitor_ml.{entry_id}.json` (ML state)
- Managed by: Coordinator.async_setup() loads, _save_data() persists

**venv/ (development):**
- Purpose: Python virtual environment
- Generated: Yes (by `make dev-setup`)
- Committed: No (in .gitignore)
- Created by: `python -m venv venv`

## Import Patterns

**From coordinator (most common):**
```python
from .coordinator import BehaviourMonitorCoordinator
coordinator: BehaviourMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
```

**From analyzer:**
```python
from .analyzer import PatternAnalyzer, AnomalyResult
```

**From constants:**
```python
from .const import (
    DOMAIN,
    CONF_MONITORED_ENTITIES,
    DEFAULT_LEARNING_PERIOD,
    ATTR_ANOMALY_DETAILS,
)
```

**Home Assistant standard:**
```python
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
```

## Module Dependencies

```
__init__.py
  ├─ coordinator.py
  ├─ config_flow.py
  └─ const.py

coordinator.py
  ├─ analyzer.py
  ├─ ml_analyzer.py
  ├─ const.py
  └─ Home Assistant Store/Bus

sensor.py, switch.py, select.py
  ├─ coordinator.py
  ├─ const.py
  └─ Home Assistant Entity Base Classes

analyzer.py
  └─ [No external dependencies except Python stdlib]

ml_analyzer.py
  └─ river (optional, graceful degradation)

config_flow.py
  ├─ const.py
  └─ Home Assistant Selectors/Validators
```

## Code Organization Principles

**Separation of Concerns:**
- `analyzer.py`: Pure algorithm (no Home Assistant, testable in isolation)
- `ml_analyzer.py`: ML algorithm (optional dependency, graceful if missing)
- `coordinator.py`: Orchestration (manages analyzers, handles events, persists state)
- Platforms: Presentation only (sensor.py, switch.py, select.py read from coordinator)

**Data Flow Direction:**
- Event bus → coordinator → analyzers
- Analyzers → coordinator data update
- Coordinator data → platform entities → Home Assistant UI

**Storage Pattern:**
- All state in coordinator instance
- Persist via `_save_data()` (async, uses Home Assistant Store)
- Restore via `async_setup()` (load from storage, reconstruct analyzers)
- Stateless platforms (read from coordinator.data via CoordinatorEntity)

---

*Structure analysis: 2026-03-13*
