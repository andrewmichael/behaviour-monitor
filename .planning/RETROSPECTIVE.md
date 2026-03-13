# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — False Positive Reduction

**Shipped:** 2026-03-13
**Phases:** 2 | **Plans:** 5 | **Sessions:** ~3

### What Was Built
- Notification suppression layer: severity gate, per-entity cooldown, cross-path dedup, welfare debounce
- Statistical analyzer hardening: bucket observation guard, raised sensitivity, adaptive per-entity thresholds
- ML analyzer tightening: EMA score smoothing, raised contamination/cross-sensor thresholds
- 30 new tests across coordinator, analyzer, and ML analyzer (240 total passing)

### What Worked
- TDD red-green pattern: writing failing tests first (Plan 01) then implementing to pass (Plan 02) was fast and produced zero regressions
- Coarse granularity: 2 phases instead of 4+ kept planning overhead minimal
- Phase ordering: coordinator suppression first gave a clean notification baseline before analyzer tightening
- Research phase identified correct approach — no mid-milestone direction changes

### What Was Inefficient
- Phase 2 plan checkboxes in ROADMAP.md were not checked off (cosmetic but indicates manual tracking gap)
- Nyquist validation was added retroactively rather than during execution
- STATE.md current position was not updated after Phase 2 completion (still showed Phase 1)

### Patterns Established
- Suppression gate pattern: filter → record → prune on each update cycle
- Bucket guard pattern: check count < threshold before any statistical calculation
- EMA smoothing for noisy score streams (alpha=0.3)
- Named constants for all guard thresholds (no magic numbers in implementation files)

### Key Lessons
1. TDD with explicit red-green plan split (scaffolds in one plan, implementation in the next) is efficient for integration work — tests define the contract clearly
2. Subsumption simplifies: MIN_BUCKET_OBSERVATIONS=3 made the separate near-zero-mean guard unnecessary, reducing code and test surface
3. Provisional values should be clearly flagged (ML contamination, debounce cycles) for production monitoring

### Cost Observations
- Model mix: ~70% sonnet (execution), ~20% haiku (research/validation), ~10% opus (planning)
- Sessions: ~3
- Notable: Phase 2 plans executed in 3-5 minutes each — very fast due to well-defined TDD contracts from Phase 1 pattern

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~3 | 2 | Established TDD red-green plan pattern, coarse granularity |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | 240 | - | 0 (no new dependencies) |

### Top Lessons (Verified Across Milestones)

1. TDD red-green split across plans is fast and safe for integration work
2. Coarse granularity (2 phases) keeps planning overhead low without sacrificing quality
