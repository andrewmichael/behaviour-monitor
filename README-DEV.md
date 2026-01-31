# Development Guide

This guide explains how to set up a local development environment for the Behaviour Monitor integration.

## Quick Start

```bash
# 1. Set up the development environment
make dev-setup

# 2. Activate the virtual environment
source venv/bin/activate

# 3. Install Home Assistant (see notes below)
pip install homeassistant

# 4. Run tests
make test
```

## Prerequisites

- Python 3.9 or higher
- Git
- Make (usually pre-installed on macOS/Linux)

## Development Setup

### 1. Clone and Setup

```bash
# The Makefile will create a virtual environment and install dependencies
make dev-setup
```

This creates a `venv/` directory and installs all development dependencies from `requirements-dev.txt`.

### 2. Activate Virtual Environment

```bash
source venv/bin/activate
```

To deactivate later:
```bash
deactivate
```

### 3. Install Home Assistant

**Important:** Home Assistant is not included in `requirements-dev.txt` because it has a large dependency tree and may have compilation issues on some systems.

#### Option A: Install via pip (may fail on some systems)

```bash
pip install homeassistant
```

**Note:** On macOS with ARM (M1/M2), you may encounter compilation errors with `lru-dict`. If this happens, try Option B or C.

#### Option B: Test within existing Home Assistant installation

If you already have Home Assistant running:

1. Copy the integration to your Home Assistant's custom_components:
   ```bash
   cp -r custom_components/behaviour_monitor /path/to/homeassistant/config/custom_components/
   ```

2. SSH into your Home Assistant and run tests from there:
   ```bash
   cd /path/to/homeassistant/config/custom_components/behaviour_monitor
   pytest tests/
   ```

#### Option C: Use Docker with Home Assistant

```bash
# Run tests in a Home Assistant docker container
docker run --rm -v $(pwd):/workspace -w /workspace homeassistant/home-assistant:latest \
  bash -c "pip install pytest pytest-asyncio pytest-cov && pytest tests/"
```

## Available Make Commands

### Development Workflow

- `make help` - Show all available commands
- `make dev-setup` - Complete development setup (recommended first step)
- `make venv` - Create virtual environment only
- `make install` - Install all dependencies
- `make activate` - Show how to activate the venv

### Testing

- `make test` or `make t` - Run all tests
- `make test-cov` or `make tc` - Run tests with coverage report
- `make test-sensor` - Run sensor platform tests only
- `make test-init` - Run integration setup tests only
- `make test-analyzer` - Run statistical analyzer tests only
- `make test-ml` - Run ML analyzer tests only
- `make test-coordinator` - Run coordinator tests only
- `make test-config` - Run config flow tests only

### Code Quality

- `make lint` or `make l` - Run linters (ruff, mypy)
- `make format` or `make f` - Format code with black and ruff
- `make check` - Run both linters and tests

### Cleanup

- `make clean` - Remove Python cache files and test artifacts
- `make clean-all` - Remove venv and all generated files

## Running Tests

### Run all tests
```bash
make test
```

### Run tests with coverage
```bash
make test-cov
```

This generates an HTML coverage report at `htmlcov/index.html`.

### Run specific test files
```bash
# Sensor platform tests
make test-sensor

# Integration setup tests
make test-init

# Pattern analyzer tests
make test-analyzer

# ML analyzer tests
make test-ml
```

### Run tests directly with pytest
```bash
# Run a specific test file
pytest tests/test_sensor.py -v

# Run a specific test class
pytest tests/test_sensor.py::TestSensorDescriptions -v

# Run a specific test
pytest tests/test_sensor.py::TestSensorDescriptions::test_last_activity_sensor_with_timestamp -v

# Run with verbose output and show print statements
pytest tests/test_sensor.py -v -s

# Run with coverage for a specific file
pytest tests/test_sensor.py --cov=custom_components/behaviour_monitor/sensor --cov-report=term-missing
```

## Code Quality

### Linting

```bash
# Run all linters
make lint

# Run ruff only
venv/bin/python -m ruff check custom_components/ tests/

# Run mypy only
venv/bin/python -m mypy custom_components/behaviour_monitor/
```

### Formatting

```bash
# Format code
make format

# Check formatting without making changes
venv/bin/python -m black --check custom_components/ tests/
```

## Project Structure

```
behaviour-monitor/
├── custom_components/
│   └── behaviour_monitor/
│       ├── __init__.py          # Integration entry point
│       ├── sensor.py            # Sensor platform (14 sensors)
│       ├── config_flow.py       # Configuration UI
│       ├── coordinator.py       # Data update coordinator
│       ├── analyzer.py          # Statistical pattern analyzer
│       ├── ml_analyzer.py       # ML pattern analyzer (optional)
│       ├── const.py             # Constants
│       └── manifest.json        # Integration metadata
├── tests/
│   ├── conftest.py              # Shared test fixtures
│   ├── test_init.py             # Integration setup tests
│   ├── test_sensor.py           # Sensor platform tests
│   ├── test_analyzer.py         # Statistical analyzer tests
│   ├── test_ml_analyzer.py      # ML analyzer tests
│   ├── test_coordinator.py      # Coordinator tests
│   └── test_config_flow.py      # Config flow tests
├── Makefile                     # Development commands
├── requirements-dev.txt         # Development dependencies
├── requirements-test.txt        # Test-only dependencies
└── README-DEV.md               # This file
```

## Test Coverage

Current test coverage:

- ✅ `test_analyzer.py` - Statistical pattern analyzer (495 lines)
- ✅ `test_ml_analyzer.py` - ML pattern analyzer (389 lines)
- ✅ `test_coordinator.py` - Data update coordinator (339 lines)
- ✅ `test_config_flow.py` - Config flow (196 lines)
- ✅ `test_sensor.py` - Sensor platform (713 lines) **NEW**
- ✅ `test_init.py` - Integration setup/unload (317 lines) **NEW**

Total: 6 test files, ~2,449 lines of test code

## Writing Tests

### Test Structure

Follow the existing test patterns:

```python
"""Tests for the feature."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

class TestFeature:
    """Tests for Feature class."""

    def test_feature_initialization(self) -> None:
        """Test feature initialization."""
        feature = Feature()
        assert feature is not None

    @pytest.mark.asyncio
    async def test_async_feature(self) -> None:
        """Test async feature."""
        result = await async_function()
        assert result is not None
```

### Using Fixtures

Shared fixtures are defined in `tests/conftest.py`:

- `mock_hass` - Mock Home Assistant instance
- `mock_config_entry` - Mock configuration entry
- `sample_timestamps` - Sample timestamps for testing
- `weekday_timestamps` - Timestamps for each weekday

```python
def test_with_fixtures(mock_hass: MagicMock, mock_config_entry: MagicMock) -> None:
    """Test using fixtures."""
    coordinator = BehaviourMonitorCoordinator(mock_hass, mock_config_entry)
    assert coordinator is not None
```

## Troubleshooting

### Virtual environment issues

```bash
# Remove and recreate
make clean-all
make dev-setup
```

### Import errors

Make sure the virtual environment is activated:
```bash
source venv/bin/activate
```

### Home Assistant import errors

The integration requires Home Assistant to run tests. See "Install Home Assistant" section above for options.

### Test failures

Run tests with verbose output to see more details:
```bash
pytest tests/test_sensor.py -vv -s
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Run tests: `make test`
4. Run linters: `make lint`
5. Format code: `make format`
6. Commit with conventional commit messages (e.g., `feat:`, `fix:`, `docs:`)
7. Push and create a pull request

## Conventional Commits

This project uses conventional commits for automatic versioning:

- `feat:` - New feature (minor version bump)
- `fix:` - Bug fix (patch version bump)
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Maintenance tasks
- `perf:` - Performance improvements
- `!` or `BREAKING CHANGE:` - Breaking change (major version bump)

Example:
```bash
git commit -m "feat: add new sensor for routine monitoring"
git commit -m "fix: correct anomaly detection threshold"
git commit -m "docs: update installation instructions"
```

## Additional Resources

- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [pytest Documentation](https://docs.pytest.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)
