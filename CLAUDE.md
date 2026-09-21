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

## Architecture

- `core/` is a pure Python package (stdlib only): `normaliser`, `house_model`,
  `entity_routine`, `chain_model`, `drift_detector`, `health_tracker`,
  `alert_router`, wired by `engine.Engine`. Spec:
  `docs/superpowers/specs/2026-09-20-generic-welfare-core-design.md`.
- `coordinator.py` is the only module that imports both Home Assistant and
  `core`. It resolves rooms from areas, feeds state changes to the engine,
  polls it once a minute and performs the delivery actions it returns.
- Three alert classes: welfare (push, repeated until acknowledged), device
  health (repair issues), statistical (sensor attribute and logbook).
- Learned state persists in `.storage/behaviour_monitor.{entry_id}.json`
  (store version 11) as `Engine.to_dict()`.

## Testing Strategy
- Tests for core and shell live in `tests/core/` and `tests/` respectively.
- Mock Home Assistant components to avoid heavy dependencies in tests.

## Project-specific Conventions

### Commit Messages
- Use conventional commits for automatic versioning
- `feat:` = minor bump, `fix:` = patch bump, `!` or `BREAKING CHANGE:` = major bump

### Versioning
- Never edit the version in `manifest.json` by hand. The release workflow
  reads it, adds the bump implied by the commits since the last tag, and
  writes it back. A manual bump plus the automatic one skips a major
  (5.0.0 written by hand then `feat!:` on merge released as 6.0.0).
- The git tag is the source of truth for the version. Docs and release
  notes should quote the tag, not a number chosen in advance.
- Every push to main with a `docs:`, `chore:`, `ci:` or similar commit
  cuts a patch release. Append `[skip ci]` to docs-only commits on main.

### Code Style
- Black for formatting (line length 88)
- Ruff for linting
- Type hints on all functions
- Async/await for HA integration methods

## File structure

    custom_components/behaviour_monitor/
    ├── __init__.py        # setup, v11 migration, services
    ├── config_flow.py     # site name, notify service, six category lists, options
    ├── coordinator.py     # Engine shell
    ├── sensor.py          # nine sensors on the engine snapshot
    ├── button.py / switch.py / select.py
    ├── const.py
    └── core/              # pure learning and alerting core
    scripts/replay.py           # replay a fixture, print the alert timeline
    scripts/export_fixture.py   # export a real site to the fixture format
    tests/core/                 # core tests and synthetic scenarios
    tests/fixtures/             # jsonl fixtures with sidecars
