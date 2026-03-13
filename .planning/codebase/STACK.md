# Technology Stack

**Analysis Date:** 2026-03-13

## Languages

**Primary:**
- Python 3.9+ - Integration codebase, all application logic
- YAML - Service definitions and translations
- JSON - Configuration and manifest files

**Secondary:**
- Shell - Build/development scripts (Makefile)

## Runtime

**Environment:**
- Home Assistant (2024.1.0+)
- Python 3.9+ (required by Home Assistant)

**Package Manager:**
- pip - Standard Python package management
- Lockfile: Not present (requirements files used directly)

## Frameworks

**Core:**
- Home Assistant Core - Integration framework providing config entries, platforms (SENSOR, SWITCH, SELECT), coordinators, async/await support

**Testing:**
- pytest 7.0.0+ - Test runner
- pytest-asyncio 0.21.0+ - Async test support
- pytest-cov 4.0.0+ - Coverage reporting
- pytest-mock 3.10.0+ - Mocking for unit tests

**Build/Dev:**
- black 23.0.0+ - Code formatting
- ruff 0.1.0+ - Linting and import sorting
- mypy 1.0.0+ - Type checking
- pylint 2.17.0+ - Additional linting

## Key Dependencies

**Critical Runtime:**
- voluptuous - Configuration schema validation for Home Assistant config flow

**Optional ML (installed separately):**
- river 0.19.0+ - Streaming anomaly detection using Half-Space Trees (optional, integration continues without it)

**Required for testing:**
- scikit-learn 1.3.0+ - Needed for tests (not used in production code)
- numpy 1.24.0+ - Required by scikit-learn and some test scenarios

**Build/Packaging:**
- build 0.10.0+ - PEP 517 build backend
- twine 4.0.0+ - Package distribution

## Configuration

**Environment:**
- Home Assistant configuration through ConfigFlow UI
- Monitored entities selected via Home Assistant entity selector
- No `.env` files used - configuration stored in Home Assistant data directory

**Build:**
- `Makefile` - Development automation
- `manifest.json` - Integration metadata and dependencies
- `pyproject.toml` - Not present (traditional setup not used)

**Key Configs Required:**
- Monitored entity list (required)
- Sensitivity level (Low/Medium/High)
- Learning period (days before anomaly detection activates)
- Notification services (optional mobile app targets)
- ML enabled flag (boolean)

## Platform Requirements

**Development:**
- Python 3.9+
- Git
- Make utility (for development commands)
- Home Assistant installation (separate from requirements)

**Production:**
- Home Assistant 2024.1.0+
- Recorder integration (dependency, enabled by default)
- Optional: River library for ML features (installed via pip inside HA container)

**Supported Platforms:**
- Home Assistant OS (with SSH & Web Terminal add-on for River installation)
- Home Assistant Supervised
- Home Assistant Container (Docker)
- Home Assistant Core (any Linux/macOS/Windows with Python 3.9+)
- Raspberry Pi 4+ (works well, no special requirements)
- x86 systems

## Storage & Persistence

**Data Storage:**
- `.storage/behaviour_monitor.{entry_id}.json` - Statistical patterns, daily counts, coordinator state, holiday/snooze modes (JSON serialization via dataclasses)
- `.storage/behaviour_monitor_ml.{entry_id}.json` - ML events, cross-sensor patterns, model metadata

**Serialization:**
- JSON with custom `to_dict()`/`from_dict()` methods on dataclasses
- Timestamps stored in ISO format with UTC timezone

## Integration Architecture

**Data Flow:**
1. State change events captured from Home Assistant EventBus (EVENT_STATE_CHANGED)
2. Processed by `BehaviourMonitorCoordinator` (DataUpdateCoordinator pattern)
3. Analyzed by `PatternAnalyzer` (statistical Z-score) and optionally `MLPatternAnalyzer` (River Half-Space Trees)
4. Results persisted to `.storage/`
5. 14 sensors expose data via standard Home Assistant sensor platform
6. Services registered for holiday mode and snooze functionality

**Asynchronous Processing:**
- Async/await throughout (Home Assistant requirement)
- UpdateCoordinator manages update interval (60 seconds default)
- State event subscriptions via callback pattern

---

*Stack analysis: 2026-03-13*
