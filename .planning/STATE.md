---
gsd_state_version: 1.0
milestone: v5.2
milestone_name: System Integrity
status: shipped
stopped_at: v5.2 shipped on feat/entity-categories; PR #2 awaiting manual live-HA gate
last_updated: "2026-09-19T09:40:00.000Z"
last_activity: 2026-09-19
progress:
  total_phases: 1
  completed_phases: 1
  total_plans: 1
  completed_plans: 1
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.
**Current focus:** Phase 25 — System Integrity

## Current Position

Phase: 25
Plan: Not started
Status: Shipped
Last activity: 2026-09-18

Progress: [██████████] 100% (1/1 v5.2 phases)

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
- [v5.0]: Category lives in entity_category.py (pure Python); coordinator supplies registry device classes and numeric-ness
- [v5.0]: Welfare uses max weighted score, not sum; plugs/lights 0.5, contact 0.8, motion/other 1.0
- [v5.0]: Motion debounce default 120s, on by default; last_seen updates on raw events, model/correlation/daily count on debounced events
- [v5.0]: Upgrade re-bootstraps motion routines from recorder via one-shot rebootstrap_motion entry flag
- [v5.1]: Panic is override-list only; no device-class inference (safety/problem are too ambiguous)
- [v5.1]: Panic notifications bypass every suppression; re-notify rides the 60 s poll (≤60 s jitter accepted)
- [v5.1]: Release clears acknowledgement; acknowledge stops repeats but keeps welfare at alert
- [v5.2]: Welfare precedence is panic > blind > ordinary alert/concern/check > degraded > ok — an ordinary alert outranks degraded, but blind (nothing reporting) outranks an ordinary alert
- [v5.2]: Event gate is armed at coordinator setup, which runs on both Home Assistant start and integration reload, so both synthetic-state moments get the start-up grace period
- [v5.2]: Device-health alerts travel the ordinary notification path (severity gate, repeat interval) rather than a separate channel; snooze and holiday do not suppress them because they concern the equipment, not the resident

### Blockers/Concerns

None.

### Known Tech Debt

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | fix lint warnings and stale config flow label | 2026-03-13 | d02c5e2 | [1-fix-lint-warnings-and-stale-config-flow-](./quick/1-fix-lint-warnings-and-stale-config-flow-/) |

## Session Continuity

Last session: 2026-09-19T09:40:00.000Z
Stopped at: v5.2 shipped on feat/entity-categories; PR #2 awaiting manual live-HA gate. Next: v5.3 event pipeline and roles spec
Resume file: None
