# Roadmap: Behaviour Monitor

## Milestones

- ✅ **v1.0 False Positive Reduction** — Phases 1-2 (shipped 2026-03-13)
- ✅ **v1.1 Detection Rebuild** — Phases 3-5 (shipped 2026-03-13)
- ✅ **v2.9 Housekeeping & Config** — Phases 6-8 (shipped 2026-03-14)
- 🚧 **v3.0 Detection Accuracy** — Phases 9-11 (in progress)

## Phases

<details>
<summary>✅ v1.0 False Positive Reduction (Phases 1-2) — SHIPPED 2026-03-13</summary>

- [x] Phase 1: Coordinator Suppression (2/2 plans) — completed 2026-03-13
- [x] Phase 2: Analyzer Tightening (3/3 plans) — completed 2026-03-13

</details>

<details>
<summary>✅ v1.1 Detection Rebuild (Phases 3-5) — SHIPPED 2026-03-13</summary>

- [x] Phase 3: Foundation and Routine Model (4/4 plans) — completed 2026-03-13
- [x] Phase 4: Detection Engines (2/2 plans) — completed 2026-03-13
- [x] Phase 5: Integration (3/3 plans) — completed 2026-03-13

</details>

<details>
<summary>✅ v2.9 Housekeeping & Config (Phases 6-8) — SHIPPED 2026-03-14</summary>

- [x] Phase 6: Dead Code Removal (2/2 plans) — completed 2026-03-14
- [x] Phase 7: Config Flow Additions (2/2 plans) — completed 2026-03-14
- [x] Phase 8: Bootstrap Fix and Closeout (2/2 plans) — completed 2026-03-14

</details>

### 🚧 v3.0 Detection Accuracy (In Progress)

**Milestone Goal:** Reduce false positives and notification fatigue by making detection smarter — weekday/weekend-aware drift, recency-weighted baselines, auto-learned inactivity thresholds, and persistent alert suppression.

- [x] **Phase 9: Alert Suppression** — Fire-once-then-throttle notifications with configurable repeat interval (completed 2026-03-14)
- [ ] **Phase 10: Drift Accuracy** — Weekday/weekend split and recency-weighted CUSUM baselines
- [ ] **Phase 11: Adaptive Inactivity** — Per-entity inactivity thresholds auto-learned from observed variance

## Phase Details

### Phase 9: Alert Suppression
**Goal**: Notifications fire once per alert condition, then throttle to a configurable repeat interval instead of firing every polling cycle
**Depends on**: Phase 8
**Requirements**: SUPR-01, SUPR-02, SUPR-03
**Success Criteria** (what must be TRUE):
  1. When an alert fires for an entity+alert-type, subsequent notifications for the same condition are suppressed until the repeat interval elapses
  2. The alert repeat interval is configurable from the HA options flow and persists across restarts
  3. When an alert condition clears and later re-triggers, a fresh notification fires immediately without waiting for the repeat interval
  4. Config migration upgrades existing entries to include the new repeat interval default without user intervention
**Plans**: 2 plans

Plans:
- [ ] 09-01-PLAN.md — Core suppression logic: constants + coordinator _alert_suppression dict with clear-on-resolve
- [ ] 09-02-PLAN.md — Config UI + v5->v6 migration: options flow field, schema version bump, migration block

### Phase 10: Drift Accuracy
**Goal**: CUSUM drift detection uses day-type-aware and recency-weighted baselines so weekend behavior is only compared to weekends and recent patterns outweigh stale history
**Depends on**: Phase 8 (independent of Phase 9)
**Requirements**: DRFT-01, DRFT-02
**Success Criteria** (what must be TRUE):
  1. The drift baseline for weekday slots is computed only from weekday observations, and weekend slots only from weekend observations
  2. Recent days contribute more to the drift baseline than older days via exponential decay weighting
  3. A weekend-only behavior change triggers a drift alert without being diluted by weekday data
  4. Existing drift detection behavior is preserved for entities with insufficient day-type-split data (graceful fallback)
**Plans**: TBD

Plans:
- [ ] 10-01: TBD
- [ ] 10-02: TBD

### Phase 11: Adaptive Inactivity
**Goal**: Each entity's inactivity threshold is derived from its own observed inter-event variance rather than applying a single global multiplier
**Depends on**: Phase 8 (independent of Phases 9-10)
**Requirements**: INAC-01
**Success Criteria** (what must be TRUE):
  1. Each entity's inactivity threshold reflects that entity's historical inter-event timing variance, not a uniform global multiplier
  2. Entities with highly regular patterns (low variance) get tighter thresholds; entities with irregular patterns (high variance) get looser thresholds
  3. The global inactivity multiplier config option continues to function as a scaling factor applied on top of the per-entity learned threshold
**Plans**: TBD

Plans:
- [ ] 11-01: TBD

## Progress

**Execution Order:**
Phases 9, 10, 11 are independent and can execute in any order.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Coordinator Suppression | v1.0 | 2/2 | Complete | 2026-03-13 |
| 2. Analyzer Tightening | v1.0 | 3/3 | Complete | 2026-03-13 |
| 3. Foundation and Routine Model | v1.1 | 4/4 | Complete | 2026-03-13 |
| 4. Detection Engines | v1.1 | 2/2 | Complete | 2026-03-13 |
| 5. Integration | v1.1 | 3/3 | Complete | 2026-03-13 |
| 6. Dead Code Removal | v2.9 | 2/2 | Complete | 2026-03-14 |
| 7. Config Flow Additions | v2.9 | 2/2 | Complete | 2026-03-14 |
| 8. Bootstrap Fix and Closeout | v2.9 | 2/2 | Complete | 2026-03-14 |
| 9. Alert Suppression | 2/2 | Complete    | 2026-03-14 | - |
| 10. Drift Accuracy | v3.0 | 0/? | Not started | - |
| 11. Adaptive Inactivity | v3.0 | 0/? | Not started | - |
