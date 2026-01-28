# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
