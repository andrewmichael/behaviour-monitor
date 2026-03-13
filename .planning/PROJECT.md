# Behaviour Monitor

## What This Is

A Home Assistant custom integration that monitors entity behavior patterns and detects anomalies using dual statistical (z-score) and ML (Half-Space Trees) analysis. After v1.0, notifications are trustworthy — suppression gates, adaptive thresholds, and ML smoothing ensure only genuinely unusual events trigger alerts.

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

(None — define in next milestone)

### Out of Scope

- New anomaly types or smarter detection patterns — focus was on reducing noise, not adding features
- Daily digest or summary notifications — may revisit in future milestone
- Per-entity sensitivity tuning UI — global tuning delivered first; may revisit
- Offline mode — real-time monitoring is core value

## Context

Shipped v1.0 with 8,827 LOC Python.
Tech stack: Home Assistant custom integration, Python async, River ML (optional).
The integration had been generating floods of false positive notifications. v1.0 addressed this with a two-pronged approach: coordinator suppression gates (cooldown, dedup, severity gate, welfare debounce) plus analyzer tightening (bucket guards, adaptive thresholds, ML smoothing). Statistical false positive rate reduced from ~4.5% to ~1.2% at medium sensitivity. 240 tests passing (2 skipped).

Known provisional values to monitor in production:
- ML contamination (LOW=0.005, MEDIUM=0.02, HIGH=0.05)
- Welfare debounce cycle count (N=3)
- SENSITIVITY_MEDIUM=2.5σ only affects new installs

## Constraints

- **Compatibility**: Must remain compatible with Home Assistant 2024.1.0+
- **Non-breaking**: Config flow options and sensor entities must not change (users have automations depending on them)
- **ML optional**: River library remains optional; ML features degrade gracefully
- **Testing**: All threshold/logic changes must have corresponding test updates

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Tune both analyzers | User reports false positives from both/unknown source | ✓ Good — both needed tightening |
| Focus on thresholds and logic, not architecture | Existing dual-analyzer approach is sound; sensitivity is the issue | ✓ Good — no rearchitecture needed |
| Coordinator suppression before analyzer tightening | Phase 1 gates have zero detection regression risk | ✓ Good — clean baseline for Phase 2 |
| MIN_BUCKET_OBSERVATIONS=3 subsumed STAT-02 | Count guard is strictly stronger than mean guard | ✓ Good — simpler implementation |
| SENSITIVITY_MEDIUM=2.5σ | Reduces FP rate from ~4.5% to ~1.2% | ✓ Good — significant improvement |
| EMA alpha=0.3 for ML smoothing | Single spike from 0.5 baseline stays at 0.647, below threshold | ✓ Good — eliminates single-spike FPs |
| Adaptive thresholds via CV | High-variance entities get wider thresholds automatically | ✓ Good — no per-entity config needed |

---
*Last updated: 2026-03-13 after v1.0 milestone*
