# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.9.0] - 2026-03-14

### Added
- add test coverage for new config fields and migration
- wire coordinator to read CONF_LEARNING_PERIOD and CONF_TRACK_ATTRIBUTES
- add v4->v5 migration block to async_migrate_entry
- add learning_period and track_attributes fields to config flow; bump VERSION to 5
- add CONF_LEARNING_PERIOD, CONF_TRACK_ATTRIBUTES constants; bump STORAGE_VERSION to 5

### Changed
- Documentation: complete phase execution
- Documentation: complete v2.9 milestone closeout plan
- Documentation: add v2.9 milestone entry to MILESTONES.md
- Documentation: complete bootstrap fix and closeout plan
- Documentation: plan phase 8 bootstrap fix and closeout
- Documentation: create phase 8 plan — bootstrap fix and closeout
- Documentation: complete phase execution
- Documentation: complete coordinator wiring and test coverage plan
- Documentation: complete config flow additions plan 01
- Documentation: plan phase 7 config flow additions
- Documentation: create phase 7 plan
- Documentation: complete phase execution
- Documentation: complete test alignment plan — ML stub test removal
- remove stub key assertions from test_coordinator.py
- remove ML stub test methods from test_sensor.py
- Documentation: complete dead-code-removal plan 01 — sensor stubs and legacy constants
- remove dead legacy constants and unused CONF_* from const.py
- remove coordinator stub keys from coordinator.py
- remove deprecated ML sensor descriptions from sensor.py
- Documentation: plan phase 6 dead code removal
- Documentation: create phase 6 plan
- Documentation: create milestone v2.9 roadmap (3 phases)
- Documentation: define milestone v2.9 requirements
- Documentation: start milestone v2.9 Housekeeping & Config

### Fixed
- add post-bootstrap _save_data() call in async_setup

## [2.8.11] - 2026-03-13

### Fixed
- prevent double-remove of state change listener on shutdown

## [2.8.10] - 2026-03-13

### Changed
- Documentation: change log
- Documentation: update README and CHANGELOG for v1.1 detection rebuild

### Fixed
- replace hardcoded cwd paths in tests with dynamic Path resolution

### Added
- **Routine Model**: Pure-Python baseline learning engine with 168 hour-of-day × day-of-week slots per entity, replacing the old 672 time-bucket z-score approach
- **Acute Detection**: Inactivity alerts (no expected activity for configurable multiplier of learned interval) and unusual-time alerts (activity at rarely-seen times), both requiring sustained evidence across 3 consecutive polling cycles before firing
- **Drift Detection**: Bidirectional CUSUM change-point detection for persistent behavior shifts over days/weeks, with configurable sensitivity (high/medium/low)
- **Routine Reset Service**: `behaviour_monitor.routine_reset` service to clear drift accumulator when a routine change is intentional
- **Recorder Bootstrap**: Routine model bootstraps from existing HA recorder history on first load — no cold-start for existing installations
- **Config Flow Options**: History window length (7-90 days), inactivity alert multiplier (1.5-10.0×), and drift sensitivity dropdown

### Changed
- **Coordinator rewrite**: Rebuilt from 1,213 lines to 348 lines, wiring RoutineModel + AcuteDetector + DriftDetector
- **Config migration**: Existing config entries automatically migrate from v2/v3 to v4 with sensible defaults for new options
- **Detection approach**: Alerts now require sustained evidence (multiple consecutive cycles) instead of single-point z-score deviations
- **Storage format**: Migrated to v4 format with routine model baselines and CUSUM state persistence

### Removed
- **Z-score analyzer** (`analyzer.py`): Replaced by RoutineModel + AcuteDetector — z-score buckets were fundamentally noisy for irregular human behavior
- **River ML analyzer** (`ml_analyzer.py`): Replaced by routine-based detection — zero external ML dependencies required
- **ML config options**: `enable_ml`, `ml_learning_period`, `retrain_period`, `cross_sensor_window` removed from config flow
- **Sigma-based sensitivity**: Old Low/Medium/High (3σ/2.5σ/1σ) sensitivity replaced by drift sensitivity and inactivity multiplier controls

### Deprecated
- `ml_status`, `ml_training_remaining`, and `cross_sensor_patterns` sensors now return stub values ("Removed in v1.1", "N/A", 0) — preserved to avoid breaking existing automations, will be removed in a future version

### Fixed
- False positives from single-point z-score deviations eliminated by sustained-evidence gating
- Coordinator data never returns None on first refresh — safe defaults always populated

## [2.8.9] - 2026-03-13

### Changed
- Documentation: update README with v1.0 sensitivity and config changes

## [2.8.8] - 2026-02-12

### Fixed
- further reduce welfare status sensitivity thresholds

## [2.8.7] - 2026-02-06

### Fixed
- reduce time-based welfare status sensitivity thresholds

## [2.8.6] - 2026-02-05

### Fixed
- use add_suggested_values_to_schema for notification persistence

## [2.8.5] - 2026-02-05

### Fixed
- remove suggested_values for Home Assistant compatibility

## [2.8.4] - 2026-02-05

### Changed
- Version bump

## [2.8.3] - 2026-02-05

### Fixed
- preserve notification services when updating config options

## [2.8.2] - 2026-02-01

### Changed
- Version bump

## [2.8.1] - 2026-02-01

### Fixed
- capture test results in same step to avoid file access issues
- capture test results in same step to avoid file access issues
- enable tests to run without Home Assistant installation

## [2.8.0] - 2026-02-01

### Added
- add holiday mode and visitor snooze controls

## [2.7.0] - 2026-02-01

### Added
- persist daily counts and coordinator state across reboots

## [2.6.0] - 2026-01-31

### Added
- add logo files for HACS branding

### Fixed
- add dark mode logos for HACS

## [2.5.6] - 2026-01-31

### Fixed
- add integration icons for HACS

## [2.5.5] - 2026-01-31

### Fixed
- add dark mode icons

## [2.5.4] - 2026-01-31

### Fixed
- fix the icon
- update badly name attribute

## [2.5.2] - 2026-01-29

### Fixed
- ml learning status must take samples and window into consideration

## [2.5.1] - 2026-01-28

### Fixed
- zip structure for updates

## [2.5.0] - 2026-01-28

### Added
- add sensors for the last sent notification

## [2.4.5] - 2026-01-28

### Fixed
- output sensor for status or training, and allow more than one mobile service

## [2.4.4] - 2026-01-28

### Fixed
- add configurable min learning peroiid, dont send out notificaitons until learning is complete

## [2.4.3] - 2026-01-28

### Changed
- Version bump

## [2.4.1] - 2025-01-28

### Fixed
- Fixed timezone handling when loading stored datetime values from storage
- All datetime comparisons now use timezone-aware datetimes (UTC)
- Resolved "can't subtract offset-naive and offset-aware datetimes" error on startup

## [2.4.0] - 2025-01-28

### Added
- GitHub Actions workflow for automatic releases
- GitHub Actions workflow for automatic version bumping with conventional commits
- HACS zip release support

### Changed
- Updated HACS configuration for proper version tracking via releases

## [2.3.0] - 2025-01-28

### Changed
- Replaced scikit-learn with River for ML features
- ML now uses streaming Half-Space Trees instead of batch-trained Isolation Forest
- Better compatibility with Home Assistant OS and Python 3.13
- No compilation required for ML features

## [2.2.0]

### Added
- Attribute tracking option
- ML Status sensor
- Elder care sensors and welfare monitoring

### Fixed
- Options flow for entity configuration changes

## [2.0.0]

### Added
- Initial release with statistical and ML-based anomaly detection
- Elder care monitoring features
- Cross-sensor correlation
- Z-score based statistical analysis
- Per-weekday 15-minute bucket pattern learning (672 buckets per entity)
- Persistent notifications with severity levels
- HACS compatibility
