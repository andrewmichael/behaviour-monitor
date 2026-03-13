# Coding Conventions

**Analysis Date:** 2026-03-13

## Naming Patterns

**Files:**
- Lowercase with underscores: `analyzer.py`, `config_flow.py`, `ml_analyzer.py`
- Test files prefixed with `test_`: `test_analyzer.py`, `test_coordinator.py`
- Platform handlers named by feature: `sensor.py`, `switch.py`, `select.py`

**Functions:**
- Snake case for all functions: `get_interval_index()`, `async_setup_entry()`, `record_state_change()`
- Async functions prefixed with `async_`: `async_setup()`, `async_shutdown()`, `async_setup_entry()`
- Private functions prefixed with single underscore: `_get_interval_index()`, `_interval_to_time_str()`, `_get_severity()`
- Helper/utility functions are module-level: `_format_duration()` in `analyzer.py`

**Variables:**
- Snake case: `sensitivity_threshold`, `learning_period_days`, `monitored_entities`
- Constants use UPPERCASE: `INTERVALS_PER_DAY`, `MINUTES_PER_INTERVAL`, `DAYS_IN_WEEK`, `DOMAIN`
- Private instance variables prefixed with underscore: `self._store`, `self._ml_store`, `self._holiday_mode`
- Collection variables use plural names: `patterns`, `monitored_entities`, `day_buckets`

**Types:**
- PascalCase for classes: `TimeBucket`, `EntityPattern`, `PatternAnalyzer`, `BehaviourMonitorCoordinator`
- Type hints on all functions using full Python type syntax: `def foo(bar: str) -> int:`
- Union types use pipe syntax: `str | None`, `dict[int, list[TimeBucket]]`
- Dataclass descriptors use PascalCase with "Description" suffix: `BehaviourMonitorSensorDescription`, `SensorEntityDescription`

## Code Style

**Formatting:**
- Black for code formatting (line length 88 characters)
- Run via `make format` which applies Black and Ruff
- All files have docstring at module level
- Consistent use of `from __future__ import annotations` at top of every file

**Linting:**
- Ruff for linting (see `make lint`)
- Mypy for type checking (separate `make lint` step)
- Configuration in `Makefile` targeting `custom_components/` and `tests/`

**Docstrings:**
- Triple-quote docstrings at module, class, and function level
- First line is summary (imperative mood): "Record an activity at the given timestamp."
- Method docstrings follow immediately after `def` line
- No blank line between def and docstring

Example from `analyzer.py`:
```python
def add_observation(self, value: float) -> None:
    """Add a new observation to this bucket."""
    self.count += 1
    self.sum_values += value
    self.sum_squared += value**2
```

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first)
2. Standard library imports (`logging`, `math`, `dataclasses`, etc.)
3. Third-party library imports (`homeassistant.*`, `voluptuous`, `river`)
4. Local imports (relative imports from same package like `from .const import ...`)

**Path Aliases:**
- No path aliases used - all imports are absolute or relative within the package
- Relative imports use dot notation: `from .const import DOMAIN`, `from .analyzer import PatternAnalyzer`

**Import Style:**
- Specific imports preferred over star imports: `from .const import DOMAIN, SERVICE_SNOOZE`
- Group-related imports on same line when importing from same module
- Example from `sensor.py`:
```python
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
```

## Error Handling

**Patterns:**
- Try/except used sparingly - only at critical boundaries
- Exception catching is specific (not bare `except:`)
- Example from `coordinator.py`:
```python
try:
    # operation
except Exception as err:
    _LOGGER.error("Error message: %s", err)
```
- Logging used for error context instead of raising
- Home Assistant integrations use callbacks for error handling (`@callback` decorator)

## Logging

**Framework:** Python's standard `logging` module

**Patterns:**
- Module-level logger: `_LOGGER = logging.getLogger(__name__)`
- Lazy string formatting: `_LOGGER.error("Message: %s", variable)` not f-strings
- Log levels used:
  - `_LOGGER.info()` for setup/startup messages
  - `_LOGGER.warning()` for feature unavailability (e.g., River not installed)
  - `_LOGGER.error()` for operation failures
- No logging in tests (logging context is mocked away)

Example from `ml_analyzer.py`:
```python
except ImportError:
    ML_AVAILABLE = False
    _LOGGER.warning(
        "River not available. ML features will be disabled. "
        "Install with: pip install river"
    )
```

## Comments

**When to Comment:**
- Explain WHY, not WHAT (code should be self-documenting for WHAT)
- Complex algorithms get inline comments explaining logic
- Example from `analyzer.py` on floating point handling:
```python
# Handle floating point errors that could make variance slightly negative
return math.sqrt(max(0, variance))
```
- Domain-specific constants explained in comments:
```python
# 15-minute intervals per day (96 buckets)
INTERVALS_PER_DAY = 96
MINUTES_PER_INTERVAL = 15
```

**JSDoc/TSDoc:**
- Not used (Python codebase uses Python docstrings)
- Type hints provide equivalent information in Python 3.10+

## Function Design

**Size:**
- Most functions 5-30 lines
- Functions follow single responsibility principle
- Analyzer functions like `record_activity()`, `get_expected_activity()` do one thing
- Coordinator methods handle specific tasks (loading data, handling events, etc.)

**Parameters:**
- Type hints required on all parameters and return values
- Default parameters common in dataclass usage and config defaults
- Optional parameters use `| None` notation: `first_observation: datetime | None = None`
- Variadic args not used

**Return Values:**
- Explicit returns - no implicit None returns
- Tuple returns used for multiple values: coordinator methods return structured dicts
- Dataclass `to_dict()` and `from_dict()` methods handle serialization

## Module Design

**Exports:**
- No explicit `__all__` declarations
- Classes/functions are module-public by default
- Private functions/modules use leading underscore: `_get_interval_index()`
- Each module has single responsibility:
  - `analyzer.py`: Statistical anomaly detection
  - `coordinator.py`: Data coordination and state management
  - `sensor.py`: Home Assistant sensor platform
  - `config_flow.py`: Configuration UI
  - `const.py`: Constants and configuration defaults

**Dataclasses:**
- Used extensively for data modeling: `TimeBucket`, `EntityPattern`, `StateChangeEvent`
- Frozen dataclasses for immutable value objects (e.g., sensor descriptions)
- Non-frozen dataclasses for mutable state (patterns, analyzers)
- Post-init methods used for initialization: `EntityPattern.__post_init__()` initializes day_buckets
- Serialization handled via `to_dict()` and `from_dict()` classmethods

**Configuration Pattern:**
- All configuration constants in `const.py` with `Final` type hints
- Configuration keys prefixed with `CONF_`: `CONF_MONITORED_ENTITIES`, `CONF_SENSITIVITY`
- Defaults prefixed with `DEFAULT_`: `DEFAULT_SENSITIVITY`, `DEFAULT_LEARNING_PERIOD`
- Thresholds as dicts mapping string keys to numeric values:
```python
SENSITIVITY_THRESHOLDS: Final = {
    SENSITIVITY_LOW: 3.0,
    SENSITIVITY_MEDIUM: 2.0,
    SENSITIVITY_HIGH: 1.0,
}
```

## Async/Await Conventions

**Entry Point Pattern:**
- `async_setup_entry()` and `async_unload_entry()` at module level for Home Assistant integration
- Platforms (sensor, switch, select) implement `async_setup_entry()` for setup
- Coordinator extends `DataUpdateCoordinator` providing async update mechanism

**Async Methods:**
- Methods that perform I/O prefixed with `async_`: `async_setup()`, `async_shutdown()`
- Exception handling wraps entire async operation

**Properties vs Async Methods:**
- Read-only computed properties use `@property`: `coordinator.monitored_entities`
- State-changing operations use `async def`: `async_enable_holiday_mode()`

---

*Convention analysis: 2026-03-13*
