# Behaviour Monitor — False Positive Reduction

## What This Is

A Home Assistant custom integration that monitors entity behavior patterns and detects anomalies using dual statistical (z-score) and ML (Half-Space Trees) analysis. Currently generates too many false positives, making the alerting unusable. This milestone focuses on tightening detection so only genuinely unusual events get flagged.

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

### Active

- [ ] Reduce statistical analyzer false positive rate
- [ ] Reduce ML analyzer false positive rate
- [ ] Ensure only genuinely unusual events trigger notifications
- [ ] Maintain detection of real anomalies (no regression in true positive rate)

### Out of Scope

- New anomaly types or smarter detection patterns — focus is on reducing noise, not adding features
- Daily digest or summary notifications — may revisit later but not this milestone
- Per-entity sensitivity tuning UI — would add complexity; global tuning first

## Context

- The integration is live and generating floods of false positive notifications
- Both the statistical and ML analyzers may be contributing
- The z-score thresholds, minimum observation counts, and sensitivity multipliers in `analyzer.py` and `ml_analyzer.py` are the primary tuning targets
- Recent commits (v2.8.7, v2.8.8) already attempted to reduce welfare status sensitivity thresholds, suggesting this is an ongoing issue
- The coordinator's notification logic in `coordinator.py` may also need tightening (e.g., deduplication, cooldown periods, confidence thresholds)

## Constraints

- **Compatibility**: Must remain compatible with Home Assistant 2024.1.0+
- **Non-breaking**: Config flow options and sensor entities must not change (users have automations depending on them)
- **ML optional**: River library remains optional; ML features degrade gracefully
- **Testing**: All threshold/logic changes must have corresponding test updates

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Tune both analyzers | User reports false positives from both/unknown source | — Pending |
| Focus on thresholds and logic, not architecture | Existing dual-analyzer approach is sound; sensitivity is the issue | — Pending |

---
*Last updated: 2026-03-13 after initialization*
