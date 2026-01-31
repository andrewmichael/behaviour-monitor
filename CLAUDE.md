# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This is a Home Assistant custom integration for behavior monitoring and anomaly detection.

## Development Setup

- **Development Guide**: See `README-DEV.md` for complete setup instructions
- **Quick Start**: `make dev-setup` to set up the development environment
- **Run Tests**: `make test` (after installing Home Assistant - see README-DEV.md)
- **Code Quality**: `make lint` and `make format`

## Build and Test Commands

### Development Setup
```bash
make dev-setup    # Create venv and install dependencies
source venv/bin/activate  # Activate virtual environment
```

### Testing
```bash
make test         # Run all tests
make test-cov     # Run tests with coverage
make test-sensor  # Run sensor tests only
make test-init    # Run integration setup tests only
```

### Code Quality
```bash
make lint         # Run linters (ruff, mypy)
make format       # Format code (black, ruff --fix)
make check        # Run both linters and tests
```

### Cleanup
```bash
make clean        # Remove cache files
make clean-all    # Remove venv and all generated files
```

## Architecture Decisions

### Dual Analysis Approach
- **Statistical Analyzer** (`analyzer.py`): Z-score based anomaly detection using 672 time buckets (7 days × 96 intervals)
- **ML Analyzer** (`ml_analyzer.py`): Optional streaming ML using River's Half-Space Trees
- Both analyzers run in parallel, managed by `coordinator.py`

### Testing Strategy
- Unit tests for each component (analyzer, ml_analyzer, coordinator, config_flow, sensor, init)
- Mock Home Assistant components to avoid heavy dependencies in tests
- Total: 6 test files, ~2,449 lines of test code
- Home Assistant must be installed separately for tests to run

### Persistence
- Statistical patterns stored in `.storage/behaviour_monitor.{entry_id}.json`
- ML patterns stored in `.storage/behaviour_monitor_ml.{entry_id}.json`
- Serialization via `to_dict`/`from_dict` methods on dataclasses

## Project-specific Conventions

### Commit Messages
- Use conventional commits for automatic versioning
- `feat:` = minor bump, `fix:` = patch bump, `!` or `BREAKING CHANGE:` = major bump

### Code Style
- Black for formatting (line length 88)
- Ruff for linting
- Type hints on all functions
- Async/await for HA integration methods

### File Structure
```
custom_components/behaviour_monitor/
├── __init__.py           # Integration entry point (setup/unload)
├── sensor.py             # 14 sensors via BehaviourMonitorSensor
├── coordinator.py        # BehaviourMonitorCoordinator (data updates, notifications)
├── analyzer.py           # PatternAnalyzer (statistical)
├── ml_analyzer.py        # MLPatternAnalyzer (optional ML)
├── config_flow.py        # Configuration UI
└── const.py              # Constants and defaults
```
