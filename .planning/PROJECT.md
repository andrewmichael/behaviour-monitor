# Behaviour Monitor

## What This Is

A Home Assistant custom integration that monitors entity behavior patterns and detects anomalies. Learns per-entity routines from a mix of entity types (motion, doors, lights, climate, power) using 168 hour-of-day × day-of-week slots. Provides two detection modes: acute alerts for out-of-character events happening right now (inactivity, unusual timing), and drift alerts when behavior persistently changes over days or weeks (CUSUM change-point detection).

## Core Value

Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.

## Requirements

### Validated

- ✓ Per-entity notification cooldown — v1.0
- ✓ Anomaly deduplication and cross-path merge — v1.0
- ✓ Severity minimum gate for notifications — v1.0
- ✓ Welfare status debounce (3-cycle hysteresis) — v1.0
- ✓ Routine model that learns expected behavior per entity from configurable history window — v1.1
- ✓ Acute detection engine — flags out-of-character events with configurable inactivity threshold — v1.1
- ✓ Drift detection engine — detects persistent behavior changes via CUSUM — v1.1
- ✓ Rebuilt coordinator wiring routine model, acute detection, and drift detection — v1.1
- ✓ Support for binary entities (motion, doors) and numeric entities (climate, power) — v1.1
- ✓ Config flow options for history window, inactivity multiplier, and drift sensitivity — v1.1
- ✓ Graceful config migration from v1.0 through v4 — v1.1
- ✓ Bootstrap routine model from HA recorder history on first load — v1.1
- ✓ Deprecated ML sensors preserved as stubs (no broken automations) — v1.1
- ✓ 14 sensor entity IDs remain stable across upgrades — v1.1
- ✓ Pure Python — no River ML or external dependencies required — v1.1

### Active

- [ ] Remove deprecated ML sensor stubs and associated coordinator stub keys — v2.9
- [ ] Remove dead legacy constants block from const.py (lines 129-184) — v2.9
- [ ] Remove unused CONF_* keys from const.py (ML and old z-score remnants) — v2.9
- [ ] Fix missing post-bootstrap _save_data() in coordinator — v2.9
- [ ] Expose learning period as user-configurable option in config flow — v2.9
- [ ] Expose attribute tracking toggle as user-configurable option in config flow — v2.9
- [ ] Add config migration step for new options with sensible defaults — v2.9
- [ ] Align GSD milestone versioning to match package version (v2.9 target) — v2.9

### Out of Scope

- Daily digest or summary notifications — may revisit in future milestone
- Offline mode — real-time monitoring is core value
- Per-entity sensitivity tuning UI — future milestone
- Cross-entity routine correlation — future milestone
- Seasonal pattern adjustment — future milestone
- Population-based norms — privacy concern; per-individual learning only
- Deep learning models — complexity/dependency overhead; pure Python constraint

## Context

Shipped v1.1 with 7,934 LOC Python across `custom_components/behaviour_monitor/` and `tests/`. 343 tests passing.

Tech stack: Home Assistant custom integration, Python async, pure stdlib (no ML dependencies).

Architecture:
- `routine_model.py` — pure-Python baseline engine (168 slots × Welford statistics)
- `acute_detector.py` — inactivity and unusual-time detection with sustained-evidence gating
- `drift_detector.py` — bidirectional CUSUM change-point detection
- `coordinator.py` — 348-line DataUpdateCoordinator wiring all engines
- `sensor.py` — 14 sensor entity descriptions
- `config_flow.py` — v4 config with history window, inactivity multiplier, drift sensitivity
- `__init__.py` — service registration (holiday, snooze, routine_reset), config migration chain

Known tech debt (from v1.1 audit):
- Post-bootstrap `_save_data()` missing in coordinator — re-bootstrap risk on immediate restart
- Legacy constants dead code in const.py (lines 129-184)
- Coordinator emits unused stub keys for deprecated sensors

## Constraints

- **Compatibility**: Must remain compatible with Home Assistant 2024.1.0+
- **Sensor stability**: Existing sensor entity IDs must not change (users have automations depending on them)
- **Config migration**: Existing config entries must migrate gracefully to new options
- **Testing**: All detection logic must have corresponding tests
- **No new dependencies**: Pure Python — no River or other ML libraries required

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Tune both analyzers | User reports false positives from both/unknown source | ✓ Good — both needed tightening |
| Focus on thresholds and logic, not architecture | Existing dual-analyzer approach is sound; sensitivity is the issue | ⚠️ Revisit — FPs still too high, approach itself is the problem |
| Replace z-score/ML with routine-based detection | Bucket-based z-scores are fundamentally noisy for irregular human behavior | ✓ Good — routine model + sustained evidence = dramatically fewer false positives |
| Drop River ML dependency | Routine model replaces ML; pure Python reduces install friction | ✓ Good — zero external dependencies, simpler install |
| Two detection modes (acute + drift) | Different problems need different engines: immediate events vs gradual changes | ✓ Good — clean separation, independently testable |
| HA-free detection components | Enable testing without mocking HA infrastructure | ✓ Good — 86 pure-Python tests run in 0.23s |
| Coordinator rewrite (not patch) | Old 1,213 lines shared almost no code with target architecture | ✓ Good — 348 lines, clean wiring |
| Sustained evidence gating (3 cycles) | Single-observation alerts are too noisy for home automation | ✓ Good — eliminates single-point false positives |
| Bidirectional CUSUM for drift | Detects both increases and decreases in activity | ✓ Good — catches both "stopped going outside" and "new nighttime activity" |

## Current Milestone: v2.9 Housekeeping & Config

**Goal:** Clean out all v1.1 tech debt, remove dead ML remnants, and expose hardcoded config options in the UI.

**Target features:**
- Remove deprecated ML sensor stubs + coordinator stub keys
- Remove dead legacy constants from const.py
- Fix missing post-bootstrap _save_data() in coordinator
- Expose learning period and attribute tracking in config flow
- Config migration for new options with defaults

---
*Last updated: 2026-03-14 after v2.9 milestone start*
