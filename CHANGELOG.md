# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
