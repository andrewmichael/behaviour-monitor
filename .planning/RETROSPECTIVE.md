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

## Milestone: v1.1 — Detection Rebuild

**Shipped:** 2026-03-13
**Phases:** 3 | **Plans:** 9

### What Was Built
- RoutineModel — pure-Python baseline engine with 168 hour×day slots, Welford online statistics, and recorder bootstrap
- AcuteDetector — inactivity and unusual-time detection with 3-cycle sustained-evidence gating
- DriftDetector — bidirectional CUSUM change-point detection with configurable sensitivity (high/medium/low)
- Coordinator rewrite — 1,213 to 348 lines wiring all three detection engines
- Config flow v4 with history window, inactivity multiplier, drift sensitivity options
- Graceful v1.0 to v4 config migration chain; deleted z-score analyzer and River ML analyzer

### What Worked
- HA-free detection components (routine_model, acute_detector, drift_detector) enabled fast pure-Python TDD without HA mocks — 86 detection tests run in 0.23s
- Discuss-phase before planning captured critical decisions (sensor mapping, coordinator line budget, config migration pattern) that prevented mid-execution pivots
- Sequential wave execution (config then coordinator then sensor/tests) prevented import-cycle and missing-constant errors
- Phase 3's gap closure pattern (03-04) caught a real wiring bug (wrong config key) before it reached Phase 5 integration

### What Was Inefficient
- Legacy constants were not cleaned up during Phase 5 despite being marked for removal — tech debt that could have been a 2-line deletion in Plan 03
- Coordinator stub keys (ml_status_stub, etc.) were emitted without corresponding sensor consumers — a disconnect between Plan 02 and Plan 03 decisions
- Post-bootstrap _save_data() was documented in Phase 3 SUMMARY but dropped in Phase 5 coordinator rewrite — cross-plan continuity gap

### Patterns Established
- Dict copy + pop for HA config entry migration — never mutate config_entry.data directly
- Population stdev (sqrt(M2/count)) for bounded-window Welford accumulators
- Sustained evidence gating (3 cycles) as the anti-false-positive pattern for all detection types
- Phase 3 then Phase 4 then Phase 5 layering: data model then algorithms then integration is a clean decomposition for detection systems

### Key Lessons
1. HA-free components should be the default architecture for any detection/analysis logic — the testing speed difference (0.23s vs 15s) pays for the upfront abstraction cost
2. When rewriting a large file (coordinator.py), start from scratch in a single task rather than incrementally patching — the old code is more confusing than helpful
3. Cross-plan continuity for specific implementation details (like post-bootstrap persist) needs explicit tracking — SUMMARY.md one-liners don't reliably carry forward to later phases

### Cost Observations
- Model mix: orchestrators on opus, subagents (researcher, planner, checker, executor, verifier, integration-checker) on sonnet
- Notable: Phase 4 was the fastest (2 plans, pure-Python TDD, no HA mocking needed) — confirms that HA-free components accelerate development

---

## Milestone: v2.9 — Housekeeping & Config

**Shipped:** 2026-03-14
**Phases:** 3 | **Plans:** 6

### What Was Built
- Removed 3 deprecated ML sensor stubs (ml_status, cross_sensor_patterns, ml_training_remaining) from sensor.py, coordinator.py, and all tests
- Removed dead legacy constants block from const.py (15 constants + 7 unused CONF_* names)
- Added learning period (1-30 days, default 7) as user-configurable option in HA config UI
- Added attribute tracking toggle (default enabled) as user-configurable option in HA config UI
- Config v4→v5 migration with setdefault — existing installs auto-upgrade with no user action required
- Fixed post-bootstrap persistence gap — coordinator now calls _save_data() after bootstrapping from recorder; immediate restart no longer re-bootstraps

### What Worked
- Surgical approach to dead code: grep first, remove all instances in one pass, verify tests pass — zero stragglers
- TDD for the one-line bootstrap fix: write failing test first, apply fix, confirm green — the discipline matters even for trivial changes
- Separate learning_period from history_window_days conceptually in the plan — caught a subtle naming collision before it became a bug
- setdefault migration pattern: avoids clobbering user values, idempotent on repeat migration calls

### What Was Inefficient
- MILESTONES.md entry was created by Plan 08-02 using a live git range, but required the executor to determine the final commit hash at execution time — slightly awkward but worked correctly
- Phase 8 could have been a single plan; splitting bootstrap fix and MILESTONES entry into two autonomous wave-1 plans added trivial coordination overhead

### Patterns Established
- setdefault migration: the canonical pattern for injecting new config keys with defaults without overwriting existing user values
- Separate learning window from history fetch window — two different concepts should have distinct constants even if they default to the same value
- TDD red-green even for one-liners: the test catches the absence, the fix makes it green, the second test (no-save-when-storage-exists) prevents over-eager saves

### Key Lessons
1. Tech debt cleanup is fastest when scoped as its own milestone — no feature pressure means clean removal without backward-compatibility gymnastics
2. The post-bootstrap _save_data() bug was documented in v1.1 SUMMARY but not fixed — cross-phase continuity gaps need explicit tracking (add to MILESTONES.md Known Debt, not just SUMMARY)
3. Config UI fields are cheap to add when migration is already planned — the schema extension, migration block, and coordinator read are a predictable 3-step pattern

### Cost Observations
- Model mix: orchestrators on sonnet, executors and verifiers on sonnet
- Sessions: 2 (planning + execution were combined in one session, completion in second)
- Notable: All 3 phases completed in under 2 hours — housekeeping milestones are fast when scope is tightly defined

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 2 | 5 | Tuning existing code — thresholds, guards, smoothing |
| v1.1 | 3 | 9 | Full architecture replacement — routine model + detection engines |
| v2.9 | 3 | 6 | Tech debt clearance + config UI surface area expansion |

### Cumulative Quality

| Milestone | Tests | Key Metric |
|-----------|-------|------------|
| v1.0 | 240 | FP rate 4.5% to 1.2% |
| v1.1 | 343 | Sustained-evidence gating eliminates single-point FPs entirely |
| v2.9 | 333 | Zero tech debt items remaining; learning period and attribute tracking configurable |

### Top Lessons (Verified Across Milestones)

1. False positive reduction requires architectural change, not just threshold tuning — v1.0 proved tuning has limits, v1.1 proved routine-based detection is fundamentally better
2. HA-free pure-Python components are dramatically faster to develop and test — established in v1.1, should be mandatory for all future detection logic
3. TDD red-green split across plans is fast and safe for integration work — verified in both v1.0 and v1.1
4. Tech debt milestones are fast and high-value — v2.9 cleared 8 requirements in under 2 hours; keep a short-cycle housekeeping milestone between major features
