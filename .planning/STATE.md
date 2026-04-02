---
gsd_state_version: 1.0
milestone: v3.1
milestone_name: Activity-Rate Classification
status: verifying
stopped_at: Completed 12-constants-and-utilities 12-01-PLAN.md
last_updated: "2026-04-02T17:48:11.981Z"
last_activity: 2026-04-02
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 1
  completed_plans: 1
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-14)

**Core value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.
**Current focus:** Phase 12 — Constants and Utilities

## Current Position

Phase: 13
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-04-02

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
- [Phase 11-adaptive-inactivity]: VERSION and STORAGE_VERSION both bumped to 7 in same task — consistent with Phase 9 pattern of keeping storage and config entry versions aligned
- [Phase 12]: TIER_BOUNDARY_HIGH=24 events/day, TIER_BOUNDARY_LOW=4 events/day per research ARCHITECTURE.md
- [Phase 12]: format_duration() placed in routine_model.py (logic, not constants) for shared use by acute_detector and coordinator

### Blockers/Concerns

None.

### Known Tech Debt

None from prior milestones.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | fix lint warnings and stale config flow label | 2026-03-13 | d02c5e2 | [1-fix-lint-warnings-and-stale-config-flow-](./quick/1-fix-lint-warnings-and-stale-config-flow-/) |

## Session Continuity

Last session: 2026-04-02T17:45:32.881Z
Stopped at: Completed 12-constants-and-utilities 12-01-PLAN.md
Resume file: None
