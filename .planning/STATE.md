---
gsd_state_version: 1.0
milestone: v4.0
milestone_name: Cross-Entity Correlation
status: planning
stopped_at: "v4.0 roadmap created, ready to plan Phase 17"
last_updated: "2026-04-03T17:00:00.000Z"
last_activity: 2026-04-03 — v4.0 roadmap created
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.
**Current focus:** Phase 17 - Foundation and Rehydration

## Current Position

Phase: 17 of 20 (Foundation and Rehydration)
Plan: 0 of 0 in current phase
Status: Ready to plan
Last activity: 2026-04-03 — v4.0 roadmap created

Progress: [░░░░░░░░░░] 0% (0/4 v4.0 phases)

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full log.

- [v4.0-roadmap]: PMI-based correlation with daily batch recomputation (follows classify_tier scheduling pattern)
- [v4.0-roadmap]: CORRELATION_BREAK alerts should NOT contribute to welfare status escalation (LOW severity only)
- [v4.0-roadmap]: Startup tier rehydration fix uses _tiers_initialized flag pattern
- [v4.0-roadmap]: PMI threshold constants defined as named constants in const.py for easy tuning (medium-confidence values)

### Blockers/Concerns

None.

### Known Tech Debt

- Phase 10 fallback path derives baseline data twice (informational, not a defect)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | fix lint warnings and stale config flow label | 2026-03-13 | d02c5e2 | [1-fix-lint-warnings-and-stale-config-flow-](./quick/1-fix-lint-warnings-and-stale-config-flow-/) |

## Session Continuity

Last session: 2026-04-03
Stopped at: v4.0 roadmap created, ready to plan Phase 17
Resume file: None
