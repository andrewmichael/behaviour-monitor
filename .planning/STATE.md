---
gsd_state_version: 1.0
milestone: v6.1
milestone_name: Generic Welfare Core
status: complete
stopped_at: Shipped v6.1.1 (test push isolation)
last_updated: "2026-09-21T09:30:00.000Z"
last_activity: 2026-09-21
progress:
  total_phases: 2
  completed_phases: 2
  total_plans: 2
  completed_plans: 2
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.
**Current focus:** Real-site tuning of the v6 generic welfare core

## Current Position

Milestone: v6.1 Generic Welfare Core (shipped 2026-09-21 as v6.0.0, v6.0.1, v6.1.0, v6.1.1)
Built outside GSD with the superpowers workflow. Spec:
docs/superpowers/specs/2026-09-20-generic-welfare-core-design.md. Plans and
outcomes: docs/superpowers/plans/2026-09-20-generic-welfare-*.md.
Status: Complete. Next work is data-driven tuning once a real-site fixture
is exported (README, "Exporting Site Data for Tuning").
Last activity: 2026-09-21

Progress: [██████████] 100% (2/2 parts: pure core, Home Assistant shell)

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
- [Phase 19]: Correlation breaks excluded entirely from welfare derivation (reasons, counts, status) per D-03
- [Phase 20]: Cleanup runs inside existing correlation_state restore block, only after from_dict

### Blockers/Concerns

None.

### Known Tech Debt

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | fix lint warnings and stale config flow label | 2026-03-13 | d02c5e2 | [1-fix-lint-warnings-and-stale-config-flow-](./quick/1-fix-lint-warnings-and-stale-config-flow-/) |

## Session Continuity

Last session: 2026-09-21T09:30:00.000Z
Stopped at: Shipped v6.1.1; deferred tuning items listed in the Part 1 and Part 2 outcomes docs
Resume file: None
