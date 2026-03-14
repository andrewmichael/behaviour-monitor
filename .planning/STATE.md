---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: Detection Accuracy
status: planning
stopped_at: Completed 11-adaptive-inactivity 11-01-PLAN.md
last_updated: "2026-03-14T19:49:37.610Z"
last_activity: 2026-03-14 — Roadmap created for v3.0
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 6
  completed_plans: 5
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-14)

**Core value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.
**Current focus:** v3.0 Detection Accuracy — ready to plan Phase 9

## Current Position

Phase: 9 of 11 (Alert Suppression)
Plan: —
Status: Ready to plan
Last activity: 2026-03-14 — Roadmap created for v3.0

Progress: [░░░░░░░░░░] 0%

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full log.
- [Phase 09-alert-suppression]: Keep _notification_cooldowns intact for backward compatibility; _alert_suppression is the new active suppression gate
- [Phase 09-alert-suppression]: DEFAULT_ALERT_REPEAT_INTERVAL = 240 min (4 hours); clear-on-resolve prunes suppression entries when conditions disappear
- [Phase 09-alert-suppression]: STORAGE_VERSION and ConfigFlow.VERSION both bumped to 6 simultaneously to keep storage and config entry versions aligned
- [Phase 09-alert-suppression]: alert_repeat_interval placed after notification_cooldown in schema to group notification-related fields
- [Phase 10-drift-accuracy]: Keep _compute_baseline_rates intact for fallback path in DriftDetector
- [Phase 10-drift-accuracy]: decay_factor=0.95 for CUSUM baseline: halves weight every ~14 days
- [Phase 10-drift-accuracy]: _compute_baseline_rates_for_day_type returns dict[date,int] to preserve age for decay weighting
- [Phase 10-drift-accuracy]: Fresh routine per simulated day in recency weighting test prevents baseline decay over simulation iterations
- [Phase 10-drift-accuracy]: old_start_offset=15 gap in _build_recency_routine ensures old/recent history windows never overlap on a calendar date
- [Phase 11-adaptive-inactivity]: CV computed at query time from event_times deque — no serialization overhead, always fresh
- [Phase 11-adaptive-inactivity]: Adaptive threshold clamps scalar between min=1.5 and max=10.0; fallback to plain multiplier x gap when CV=None (sparse slot)
- [Phase 11-adaptive-inactivity]: adaptive_scalar stored in AlertResult.details for diagnostics without altering alert API

### Blockers/Concerns

None.

### Known Tech Debt

None from prior milestones.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | fix lint warnings and stale config flow label | 2026-03-13 | d02c5e2 | [1-fix-lint-warnings-and-stale-config-flow-](./quick/1-fix-lint-warnings-and-stale-config-flow-/) |

## Session Continuity

Last session: 2026-03-14T19:49:37.607Z
Stopped at: Completed 11-adaptive-inactivity 11-01-PLAN.md
Resume file: None
