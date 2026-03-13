# Testing Patterns

**Analysis Date:** 2026-03-13

## Test Framework

**Runner:**
- Pytest (configured in `pytest.ini`)
- Async support via `pytest-asyncio` (auto mode enabled)
- Config: `pytest.ini` with settings: testpaths, python_files, python_classes, python_functions
- All DeprecationWarnings filtered to reduce noise

**Assertion Library:**
- Standard Python `assert` statements
- Pytest's built-in assertion rewriting provides detailed failure messages

**Run Commands:**
```bash
make test              # Run all tests in tests/ directory
make test-cov          # Run tests with coverage (HTML report in htmlcov/)
make test-watch        # Watch mode - re-runs on file changes (pytest-watch)
make test-sensor       # Run sensor tests only
make test-init         # Run integration init tests only
make test-analyzer     # Run analyzer tests only
make test-ml           # Run ML analyzer tests only
make test-coordinator  # Run coordinator tests only
make test-config       # Run config flow tests only
```

Coverage target: Monitored via `--cov=custom_components/behaviour_monitor` with HTML report generation.

## Test File Organization

**Location:**
- Co-located in separate `tests/` directory (not alongside source files)
- Structure mirrors source: `tests/test_analyzer.py` for `analyzer.py`, etc.
- Directory: `/Users/abourne/Documents/source/behaviour-monitor/tests/`

**Naming:**
- Test files: `test_*.py` (pytest convention)
- Test classes: `Test*` (e.g., `TestTimeBucket`, `TestPatternAnalyzer`)
- Test functions: `test_*` (e.g., `test_empty_bucket_mean()`, `test_initialization()`)

**Structure:**
```
tests/
├── __init__.py           # Empty file
├── conftest.py           # Shared fixtures (443 lines)
├── test_analyzer.py      # PatternAnalyzer tests (641 lines)
├── test_ml_analyzer.py   # MLPatternAnalyzer tests (388 lines)
├── test_coordinator.py   # BehaviourMonitorCoordinator tests (825 lines)
├── test_sensor.py        # Sensor platform tests (600 lines)
├── test_config_flow.py   # Config flow tests (195 lines)
├── test_init.py          # Integration setup tests (322 lines)
├── test_select.py        # Select entity tests (268 lines)
└── test_switch.py        # Switch entity tests (177 lines)
```

**Total Test Code:** 3,860 lines across 9 test files + conftest

## Test Structure

**Suite Organization:**
```python
class TestTimeBucket:
    """Tests for TimeBucket class."""

    def test_empty_bucket_mean(self) -> None:
        """Test mean of empty bucket is 0."""
        bucket = TimeBucket()
        assert bucket.mean == 0.0

    def test_multiple_observations_mean(self) -> None:
        """Test mean with multiple observations."""
        bucket = TimeBucket()
        for val in [2.0, 4.0, 6.0, 8.0]:
            bucket.add_observation(val)
        assert bucket.mean == 5.0
```

**Patterns:**
- One test class per component/class being tested
- Docstring on class explains what's being tested
- Each test method has single responsibility (one assertion concept per test)
- Test names describe the scenario being tested (test_empty_bucket_mean, test_multiple_observations_mean)
- Arrange-Act-Assert pattern (implicit - setup, action, assertion)

**Async Test Pattern:**
```python
@pytest.mark.asyncio
async def test_async_setup_subscribes_to_events(
    self, coordinator: BehaviourMonitorCoordinator, mock_hass: MagicMock
) -> None:
    """Test setup subscribes to state changed events."""
    with patch.object(coordinator._store, "async_load", return_value=None):
        with patch.object(coordinator._ml_store, "async_load", return_value=None):
            await coordinator.async_setup()

    mock_hass.bus.async_listen.assert_called()
```

## Mocking

**Framework:** Python's `unittest.mock` (MagicMock, AsyncMock, patch)

**Home Assistant Mocking:**
Comprehensive HA mocking setup in `conftest.py` (lines 15-374) allows tests to run without installing full Home Assistant:

- Mock modules for: `homeassistant.core`, `homeassistant.const`, `homeassistant.config_entries`
- Mock helper modules: `homeassistant.helpers.storage`, `homeassistant.helpers.update_coordinator`
- Mock components: `homeassistant.components.sensor`, `homeassistant.components.select`, `homeassistant.components.switch`
- Mock classes: `MockConfigFlow`, `MockStore`, `MockDataUpdateCoordinator`, `MockCoordinatorEntity`
- Sys.modules injection allows code to `import homeassistant.*` without actual dependency

**Fixture-Based Mocking:**
```python
@pytest.fixture
def mock_hass() -> MagicMock:
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    return hass

@pytest.fixture
def mock_config_entry() -> MagicMock:
    """Create a mock config entry."""
    class MockConfigEntry:
        def __init__(self):
            self.entry_id = "test_entry_id"
            self.data = {
                "monitored_entities": ["sensor.test1", "sensor.test2"],
                "sensitivity": "medium",
                ...
            }
    return MockConfigEntry()
```

**Patch Usage:**
```python
with patch.object(coordinator._store, "async_load", return_value=None):
    await coordinator.async_setup()

with patch.object(coordinator._store, "async_save", new_callable=AsyncMock) as mock_save:
    await coordinator.async_shutdown()

mock_save.assert_called_once()
```

**What to Mock:**
- External dependencies (Home Assistant framework, storage, event bus)
- Network I/O (if any)
- Time-dependent operations use fixed timestamps

**What NOT to Mock:**
- Business logic (analyzer algorithms, pattern detection)
- Data structures (TimeBucket, EntityPattern dataclasses)
- Coordinator logic (mocking internals makes tests brittle)

## Fixtures and Factories

**Test Data:**

Module-level fixtures in `conftest.py`:
```python
@pytest.fixture
def sample_timestamps() -> list[datetime]:
    """Generate sample timestamps for testing."""
    base = datetime(2024, 1, 15, 9, 0, 0)  # Monday 9:00 AM
    return [base + timedelta(minutes=i * 15) for i in range(10)]

@pytest.fixture
def weekday_timestamps() -> dict[int, list[datetime]]:
    """Generate timestamps for each day of the week."""
    timestamps: dict[int, list[datetime]] = {}
    base = datetime(2024, 1, 15, 9, 0, 0)  # Monday
    for day_offset in range(7):
        day_base = base + timedelta(days=day_offset)
        timestamps[day_base.weekday()] = [
            day_base + timedelta(hours=h) for h in range(24)
        ]
    return timestamps
```

**Test-Class Fixtures:**
```python
class TestBehaviourMonitorCoordinator:
    @pytest.fixture
    def coordinator(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> BehaviourMonitorCoordinator:
        """Create a coordinator instance."""
        return BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
```

**Location:**
- Module-level fixtures in `conftest.py` for reuse across test files
- Class-level fixtures in test classes when only used locally
- Fixtures are parameterized for different scenarios when needed

## Coverage

**Requirements:** No explicit minimum enforced (not configured in pytest.ini)

**View Coverage:**
```bash
make test-cov    # Generate HTML report
# Open htmlcov/index.html to view
```

Reports generated to:
- Terminal: `--cov-report=term-missing` shows missing lines
- HTML: `--cov-report=html` creates `htmlcov/index.html`

## Test Types

**Unit Tests:**
- Scope: Individual classes and functions in isolation
- Approach: Test one behavior per test method
- Examples:
  - `TestTimeBucket`: Tests mean/std_dev calculations with various inputs
  - `TestIntervalFunctions`: Tests interval indexing edge cases (midnight, noon, 23:45)
  - `TestPatternAnalyzer`: Tests pattern creation, recording, confidence calculation
- Setup: Minimal - usually just instantiate class with known params
- Assertion: Single concept per test (don't test multiple things in one test)

**Integration Tests:**
- Scope: Coordinator + Analyzer interaction, state persistence
- Approach: Test real data flow and side effects
- Examples:
  - `test_async_setup_subscribes_to_events`: Tests coordinator setup with mocked storage
  - `test_on_state_changed_triggers_analysis`: Tests full event flow
  - `test_to_dict_and_from_dict`: Tests serialization round-trip
- Setup: Use coordinator fixture with mocked HA components
- Assertion: Verify both output and side effects (storage called, listeners registered)

**Configuration Tests:**
- Scope: Config flow validation, defaults, error handling
- Approach: Test form submission, validation, entry creation
- Examples from `test_config_flow.py`:
  - `test_step_user_no_entities_selected`: Validation error
  - `test_step_user_valid_input`: Success case
  - Options flow tests for updating configuration
- Setup: Create ConfigFlow instance with mocked hass
- Assertion: Verify form type, errors dict, and result type

**E2E Tests:**
- Not used (Home Assistant integration framework makes full E2E testing complex)
- Integration tests serve this role by testing coordinator with realistic scenarios

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_async_operation(self, coordinator: BehaviourMonitorCoordinator) -> None:
    """Test async operation."""
    with patch.object(coordinator._store, "async_load", return_value=None):
        await coordinator.async_setup()

    # Verify side effects
    coordinator._unsubscribe_state_changed.assert_called()
```

**Error Testing:**
```python
def test_serialization_with_missing_fields(self) -> None:
    """Test handling of incomplete data during deserialization."""
    data = {"count": 5}  # Missing sum_values and sum_squared
    bucket = TimeBucket.from_dict(data)
    assert bucket.count == 5
    assert bucket.sum_values == 0.0  # Defaults to 0.0
    assert bucket.sum_squared == 0.0
```

**Time-Based Testing:**
```python
def test_confidence_with_data(self) -> None:
    """Test confidence increases with data."""
    analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)

    # Record data from 3 days ago
    ts = datetime.now(timezone.utc) - timedelta(days=3)
    analyzer.record_state_change("sensor.test", ts)

    confidence = analyzer.get_confidence()
    # 3 days / 7 days = ~42.8%
    assert 40 < confidence < 45
```

**Anomaly Detection Testing:**
```python
def test_detects_unusual_activity(self) -> None:
    """Test detection of unusual activity after learning."""
    analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=1)

    # Build baseline over past days
    base_ts = datetime.now(timezone.utc) - timedelta(days=2)
    for day_offset in range(2):
        ts = base_ts + timedelta(days=day_offset)
        analyzer.record_state_change("sensor.test", ts)

    # Simulate current interval with anomalous activity
    now = datetime.now(timezone.utc)
    for _ in range(10):
        analyzer.record_state_change("sensor.test", now)

    # Check for anomalies
    current_activity = analyzer.get_current_interval_activity()
    anomalies = analyzer.check_for_anomalies(current_activity)

    assert isinstance(anomalies, list)
```

**Serialization Testing:**
```python
def test_to_dict_and_from_dict(self) -> None:
    """Test serialization round-trip."""
    analyzer = PatternAnalyzer(sensitivity_threshold=2.0, learning_period_days=7)
    ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    analyzer.record_state_change("sensor.test", ts)

    # Serialize
    data = analyzer.to_dict()

    # Deserialize
    restored = PatternAnalyzer.from_dict(data)

    assert "sensor.test" in restored.patterns
    assert restored._sensitivity_threshold == 2.0
    assert restored._learning_period_days == 7
```

## Test Isolation

**Setup/Teardown:**
- No explicit teardown needed (fixtures auto-clean)
- Fixtures create fresh instances per test
- Mock objects isolated per test via pytest fixture scope

**State Management:**
- Each test class operates on fresh coordinator/analyzer instances
- No shared state between tests
- Mocked storage prevents side effects on real files

**Flakiness Prevention:**
- No sleep/wait in tests (use mocks)
- Time-based tests use fixed timestamps (datetime.now replaced with controlled values)
- All async operations properly awaited
- Pytest asyncio mode set to "auto" for automatic async test detection

---

*Testing analysis: 2026-03-13*
