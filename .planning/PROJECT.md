# Behaviour Monitor

## What This Is

A Home Assistant custom integration that monitors entity behavior patterns and detects anomalies. Learns routines from a mix of entity types (motion, doors, lights, climate, power) and provides two detection modes: acute alerts when something out of character happens right now (e.g., someone may have fallen), and drift alerts when behavior persistently changes over days or weeks.

## Core Value

Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.

## Requirements

### Validated

- ✓ Statistical anomaly detection using z-score on 672 time buckets (7 days x 96 intervals) — existing
- ✓ Optional ML anomaly detection using River Half-Space Trees — existing
- ✓ Cross-sensor correlation pattern detection — existing
- ✓ Configurable sensitivity levels (Low/Medium/High) — existing
- ✓ Learning period before detection activates — existing
- ✓ Holiday mode to suppress monitoring — existing
- ✓ Snooze functionality to temporarily suppress alerts — existing
- ✓ Persistent storage of patterns and ML models — existing
- ✓ 14 sensor types exposed to Home Assistant — existing
- ✓ Notification via configured services or persistent_notification — existing
- ✓ Welfare status assessment — existing
- ✓ Config flow UI for entity selection and settings — existing
- ✓ Per-entity notification cooldown — v1.0
- ✓ Anomaly deduplication and cross-path merge — v1.0
- ✓ Severity minimum gate for notifications — v1.0
- ✓ Welfare status debounce (3-cycle hysteresis) — v1.0
- ✓ Sparse-bucket observation guard (MIN_BUCKET_OBSERVATIONS=3) — v1.0
- ✓ Raised default sensitivity (MEDIUM 2.0σ → 2.5σ) — v1.0
- ✓ Per-entity adaptive thresholds via coefficient of variation — v1.0
- ✓ ML EMA score smoothing (α=0.3) — v1.0
- ✓ Tightened ML contamination values — v1.0
- ✓ Cross-sensor co-occurrence threshold raised to 30 — v1.0

### Active

- [ ] Routine model that learns expected behavior per entity from configurable history window (default 4 weeks)
- [ ] Acute detection engine — flags out-of-character events in real time with configurable inactivity threshold
- [ ] Drift detection engine — detects persistent behavior changes over days/weeks
- [ ] New coordinator to manage routine learning, both detection engines, and notifications
- [ ] Support for binary entities (motion, doors) and numeric entities (climate, power)
- [ ] Config flow options for history window and alert thresholds

### Out of Scope

- Daily digest or summary notifications — may revisit in future milestone
- Offline mode — real-time monitoring is core value
- Keeping the old z-score/ML analyzer code — being replaced entirely

## Current Milestone: v1.1 Detection Rebuild

**Goal:** Replace z-score/ML analyzers and coordinator with routine-based detection — acute events + drift tracking.

**Target features:**
- Routine model learning from configurable history (default 4 weeks)
- Acute detection with configurable inactivity thresholds
- Drift detection via change point analysis
- Rebuilt coordinator for new detection engines
- Support for binary + numeric entity types

## Context

Shipped v1.0 with 8,827 LOC Python. Despite v1.0 false positive reduction work (FP rate from ~4.5% to ~1.2%), the z-score bucket approach is fundamentally noisy for home automation data — human behavior is too irregular for fixed time buckets. Decision: replace analyzers entirely with routine-based detection that requires sustained evidence before alerting.

Keeping: sensors (14 types), config flow (extended), storage layer, HA integration shell.
Replacing: analyzer.py, ml_analyzer.py, coordinator.py.

Tech stack: Home Assistant custom integration, Python async. River ML dependency being removed.

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
| Replace z-score/ML with routine-based detection | Bucket-based z-scores are fundamentally noisy for irregular human behavior | — Pending |
| Drop River ML dependency | Routine model replaces ML; pure Python reduces install friction | — Pending |
| Two detection modes (acute + drift) | Different problems need different engines: immediate events vs gradual changes | — Pending |

---
*Last updated: 2026-03-13 after v1.1 milestone start*
