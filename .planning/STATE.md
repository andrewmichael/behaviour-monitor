---
gsd_state_version: 1.0
milestone: v4.0
milestone_name: Cross-Entity Correlation
status: executing
stopped_at: Completed 19-01-PLAN.md
last_updated: "2026-04-05T10:20:39.037Z"
last_activity: 2026-04-05
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 6
  completed_plans: 5
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.
**Current focus:** Phase 19 — Break Detection and Alerting

## Current Position

Phase: 19 (Break Detection and Alerting) — EXECUTING
Plan: 2 of 2
Status: Ready to execute
Last activity: 2026-04-05

Progress: [░░░░░░░░░░] 0% (0/4 v4.0 phases)

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full log.

- [v4.0-roadmap]: PMI-based correlation with daily batch recomputation (follows classify_tier scheduling pattern)
- [v4.0-roadmap]: CORRELATION_BREAK alerts should NOT contribute to welfare status escalation (LOW severity only)
- [v4.0-roadmap]: Startup tier rehydration fix uses _tiers_initialized flag pattern
- [v4.0-roadmap]: PMI threshold constants defined as named constants in const.py for easy tuning (medium-confidence values)
- [Phase 17]: Only set _tier_classified_date when _activity_tier is assigned a real tier (not None)
- [Phase 17]: PMI_THRESHOLD=1.0 as medium-confidence tunable constant; correlation window 30-600s range in config UI
- [Phase 18]: record_event placed after last_seen update so all_last_seen includes current entity timestamp
- [Phase 19]: Confidence uses co_occurrence_rate of highest-rate missing partner

### Blockers/Concerns

None.

### Known Tech Debt

- Phase 10 fallback path derives baseline data twice (informational, not a defect)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | fix lint warnings and stale config flow label | 2026-03-13 | d02c5e2 | [1-fix-lint-warnings-and-stale-config-flow-](./quick/1-fix-lint-warnings-and-stale-config-flow-/) |

## Session Continuity

Last session: 2026-04-05T10:20:39.033Z
Stopped at: Completed 19-01-PLAN.md
Resume file: None
