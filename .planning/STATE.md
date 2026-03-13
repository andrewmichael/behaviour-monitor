---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Detection Rebuild
status: planning
stopped_at: Completed 05-integration-01-PLAN.md
last_updated: "2026-03-13T21:38:18.872Z"
last_activity: 2026-03-13 — Roadmap created, 3 phases defined (3, 4, 5), 12/12 requirements mapped
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 9
  completed_plans: 7
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.
**Current focus:** Phase 3 — Foundation and Routine Model

## Current Position

Phase: 3 of 5 (Foundation and Routine Model — first v1.1 phase)
Plan: 0 of ? in current phase
Status: Ready to plan
Last activity: 2026-03-13 — Roadmap created, 3 phases defined (3, 4, 5), 12/12 requirements mapped

Progress: [░░░░░░░░░░] 0% (v1.1; v1.0 complete)

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full log. Key decisions affecting current work:

- [v1.0 post-mortem]: z-score bucket approach is fundamentally noisy — replacing analyzers entirely
- [v1.1 arch]: Pure Python stdlib only — no River, no numpy; CUSUM ~15 lines, statistics.NormalDist for z-scores
- [v1.1 arch]: Build order: const → routine_model → detectors → coordinator → sensor/config_flow
- [v1.1 arch]: Three HA-free components (routine_model, acute_detector, drift_detector) enable testing without mocking HA
- [Phase 03-01]: Population stdev (sqrt(M2/count)) for ActivitySlot numeric — appropriate for 56-item bounded window
- [Phase 03-01]: MIN_SLOT_OBSERVATIONS=4 sparse slot guard: expected_gap_seconds and slot_distribution return None below threshold
- [Phase 03-01]: ISO timestamp strings in deque (not datetime objects) — zero HA dependency in routine_model.py confirmed
- [Phase 03]: ML constants kept in const.py until coordinator is rewritten in Plan 03
- [Phase 03]: async_migrate_entry uses dict copy + pop pattern, never mutates config_entry.data directly, per HA developer docs
- [Phase 03]: Bootstrap only runs when RoutineModel._entities is empty — prevents re-bootstrap on every startup
- [Phase 03]: Guard _bootstrap_from_recorder on recorder_get_instance only (not state_changes_fn) for test patchability
- [Phase 03]: CONF_HISTORY_WINDOW_DAYS is the correct config key for RoutineModel history window; CONF_LEARNING_PERIOD retained only for PatternAnalyzer (statistical learning period)
- [Phase 04-01]: Severity ratio relative to threshold: LOW/MEDIUM/HIGH based on elapsed/threshold ratio, not elapsed/expected_gap
- [Phase 04-01]: AcuteDetector per-entity counter dicts reset to 0 on every not-met code path (research Pitfall 2 compliance)
- [Phase 04-detection-engines]: Stdev=0 fallback to max(1.0, baseline_mean*0.1): preserves sensitivity for low-count signals; avoids infinite z-scores on constant signals
- [Phase 04-detection-engines]: reset() preserves last_update_date: prevents double-processing same day if reset_entity() and check() called in same coordinator cycle
- [Phase 05-integration]: Legacy constants (SENSITIVITY_THRESHOLDS, ML_CONTAMINATION, etc.) retained in const.py until old analyzer/coordinator are replaced in Plan 02
- [Phase 05-integration]: Migration chaining: v2->v3->v4 in single async_migrate_entry with independent version guards

### Blockers/Concerns

- [Phase 3]: Verify `get_significant_states` async call pattern against HA 2025.x before implementing recorder bootstrap
- [Phase 4]: CUSUM parameters (k=0.5, h=4.0) are MEDIUM confidence — validate against simulated data before coding

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | fix lint warnings and stale config flow label | 2026-03-13 | d02c5e2 | [1-fix-lint-warnings-and-stale-config-flow-](./quick/1-fix-lint-warnings-and-stale-config-flow-/) |

## Session Continuity

Last session: 2026-03-13T21:38:18.869Z
Stopped at: Completed 05-integration-01-PLAN.md
Resume file: None
