# Behaviour Monitor

## What This Is

A Home Assistant custom integration that monitors entity behavior patterns and detects anomalies. Learns per-entity routines from a mix of entity types (motion, doors, lights, climate, power) using 168 hour-of-day × day-of-week slots. Provides two detection modes: acute alerts for out-of-character events happening right now (inactivity, unusual timing), and drift alerts when behavior persistently changes over days or weeks (CUSUM change-point detection). Learning period and attribute tracking are user-configurable from the HA config UI.

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
- ✓ Deprecated ML sensor stubs and coordinator stub keys removed — v2.9
- ✓ Dead legacy constants block removed from const.py — v2.9
- ✓ Post-bootstrap _save_data() call added — routine model survives immediate restart — v2.9
- ✓ Learning period configurable from HA config UI (default 7 days) — v2.9
- ✓ Attribute tracking toggle configurable from HA config UI (default enabled) — v2.9
- ✓ Config v4→v5 migration with automatic defaults for existing installs — v2.9

### Active

*(No active requirements — planning next milestone)*

### Out of Scope

- Daily digest or summary notifications — may revisit in future milestone
- Offline mode — real-time monitoring is core value
- Per-entity sensitivity tuning UI — future milestone
- Cross-entity routine correlation — future milestone
- Seasonal pattern adjustment — future milestone
- Population-based norms — privacy concern; per-individual learning only
- Deep learning models — complexity/dependency overhead; pure Python constraint

## Context

Shipped v2.9 with 7,863 LOC Python across `custom_components/behaviour_monitor/` and `tests/`. 333 tests passing.

Tech stack: Home Assistant custom integration, Python async, pure stdlib (no ML dependencies).

Architecture:
- `routine_model.py` — pure-Python baseline engine (168 slots × Welford statistics)
- `acute_detector.py` — inactivity and unusual-time detection with sustained-evidence gating
- `drift_detector.py` — bidirectional CUSUM change-point detection
- `coordinator.py` — DataUpdateCoordinator wiring all engines; now saves after bootstrap
- `sensor.py` — 11 sensor entity descriptions (3 ML stubs removed)
- `config_flow.py` — v5 config with learning period, attribute tracking, history window, inactivity multiplier, drift sensitivity
- `__init__.py` — service registration, config migration chain (v2→v3→v4→v5)

Known tech debt: None from prior milestones — v2.9 cleared all v1.1 tech debt items.

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
| Remove ML stubs entirely (v2.9) | Stubs created risk of users building automations on stub sensors; clean removal is safer | ✓ Good — 3 dead sensor descriptions gone, no automation regression risk |
| learning_period separate from history_window (v2.9) | Learning window (when baseline is "ready") differs conceptually from history fetch window | ✓ Good — coordinator now passes learning_period_days to RoutineModel instead of conflating with history_window_days |
| setdefault for v4→v5 migration (v2.9) | Preserves any values users may have set; only injects defaults where keys are absent | ✓ Good — zero broken configs on upgrade |

---
*Last updated: 2026-03-14 after v2.9 milestone*
