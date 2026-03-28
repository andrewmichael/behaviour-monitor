# Behaviour Monitor

## What This Is

A Home Assistant custom integration that monitors entity behavior patterns and detects anomalies. Learns per-entity routines from a mix of entity types (motion, doors, lights, climate, power) using 168 hour-of-day × day-of-week slots. Provides two detection modes: acute alerts for out-of-character events happening right now (inactivity, unusual timing), and drift alerts when behavior persistently changes over days or weeks (CUSUM change-point detection). Inactivity thresholds auto-adapt to each entity's observed variance; drift baselines split weekday from weekend activity with recency weighting; notifications fire once then throttle at a configurable interval. All detection parameters are user-configurable from the HA config UI.

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

- ✓ Alert suppression — fire once, then throttle at configurable repeat interval — v3.0
- ✓ Weekday/weekend split drift baseline — separate Saturday from Tuesday in CUSUM — v3.0
- ✓ Recency-weighted drift baseline — exponential decay weights recent days more heavily — v3.0
- ✓ Per-entity adaptive inactivity threshold — auto-learned from observed timing variance — v3.0

### Active

**Current Milestone: v3.1 Activity-Rate Classification**

**Goal:** Eliminate false-positive inactivity alerts on high-frequency entities by classifying entities into activity tiers with tier-appropriate detection logic.

**Target features:**
- Auto-classify entities into frequency tiers (high/medium/low) based on observed event rates, with user override in config UI
- Separate inactivity detection for high-frequency entities: higher multiplier AND minimum absolute floor
- Fix alert display formatting — show minutes instead of hours when typical interval < 1h

### Out of Scope

- Daily digest or summary notifications — may revisit in future milestone
- Offline mode — real-time monitoring is core value
- Per-entity sensitivity tuning UI — future milestone
- Cross-entity routine correlation — future milestone
- Seasonal pattern adjustment — future milestone
- Population-based norms — privacy concern; per-individual learning only
- Deep learning models — complexity/dependency overhead; pure Python constraint

## Context

Shipped v3.0 with ~9,892 LOC Python across `custom_components/behaviour_monitor/` and `tests/`. 403 tests passing.

Tech stack: Home Assistant custom integration, Python async, pure stdlib (no ML dependencies). Config schema at v7.

Architecture:
- `routine_model.py` — pure-Python baseline engine (168 slots × Welford statistics); `ActivitySlot.interval_cv()` for variance computation
- `acute_detector.py` — inactivity detection with CV-adaptive thresholds; unusual-time detection with sustained-evidence gating
- `drift_detector.py` — bidirectional CUSUM with day-type split and exponential decay weighting
- `coordinator.py` — DataUpdateCoordinator wiring all engines; fire-once-then-throttle alert suppression via `_alert_suppression` dict
- `sensor.py` — 11 sensor entity descriptions
- `config_flow.py` — v7 config with alert repeat interval, min/max inactivity multiplier bounds, learning period, attribute tracking, history window, inactivity multiplier, drift sensitivity; min>max cross-field validation
- `__init__.py` — service registration, config migration chain (v2→v3→v4→v5→v6→v7)
- `translations/en.json` — user-friendly labels for all config fields

Known tech debt: Phase 10 fallback path derives baseline data twice (informational, not a defect).

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
| Fire-once-then-throttle suppression (v3.0) | Polling-based detectors fire every cycle; first-fire semantics prevent notification spam | ✓ Good — `_alert_suppression` dict with clear-on-resolve; 4 h default throttle |
| Day-type split for CUSUM baseline (v3.0) | Weekend behavior diluted by 5× more weekday data under unified baseline | ✓ Good — weekend anomalies now detected in isolation |
| CV-based adaptive inactivity threshold (v3.0) | Uniform multiplier was too tight for irregular entities, too loose for regular ones | ✓ Good — per-slot CV auto-calibrates threshold to observed variance |
| Compute CV at query time, no new storage (v3.0) | Avoids storage schema complexity; existing `event_times` deques hold enough data | ✓ Good — zero new persistence, all data already captured |
| setdefault for v6→v7 migration (v3.0) | Consistent with v2.9 pattern; preserves any pre-existing custom values | ✓ Good — identical to v5 migration pattern |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-28 after v3.1 milestone started*
