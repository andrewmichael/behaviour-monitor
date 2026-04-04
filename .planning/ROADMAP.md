# Roadmap: Behaviour Monitor

## Milestones

- ✅ **v1.0 False Positive Reduction** — Phases 1-2 (shipped 2026-03-13)
- ✅ **v1.1 Detection Rebuild** — Phases 3-5 (shipped 2026-03-13)
- ✅ **v2.9 Housekeeping & Config** — Phases 6-8 (shipped 2026-03-14)
- ✅ **v3.0 Detection Accuracy** — Phases 9-11 (shipped 2026-03-14)
- ✅ **v3.1 Activity-Rate Classification** — Phases 12-16 (shipped 2026-04-03)
- 🚧 **v4.0 Cross-Entity Correlation** — Phases 17-20 (in progress)

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

<details>
<summary>✅ v3.0 Detection Accuracy (Phases 9-11) — SHIPPED 2026-03-14</summary>

- [x] Phase 9: Alert Suppression (2/2 plans) — completed 2026-03-14
- [x] Phase 10: Drift Accuracy (2/2 plans) — completed 2026-03-14
- [x] Phase 11: Adaptive Inactivity (2/2 plans) — completed 2026-03-14

</details>

<details>
<summary>✅ v3.1 Activity-Rate Classification (Phases 12-16) — SHIPPED 2026-04-03</summary>

- [x] Phase 12: Constants and Utilities (1/1 plans) — completed 2026-04-02
- [x] Phase 13: Tier Classification (1/1 plans) — completed 2026-04-02
- [x] Phase 14: Tier-Aware Detection (1/1 plans) — completed 2026-04-03
- [x] Phase 15: Coordinator Integration (1/1 plans) — completed 2026-04-03
- [x] Phase 16: Config UI and Migration (1/1 plans) — completed 2026-04-03

</details>

### v4.0 Cross-Entity Correlation (In Progress)

**Milestone Goal:** Add cross-entity routine correlation to detect when normally co-occurring entities diverge, plus fix startup tier rehydration gap.

- [x] **Phase 17: Foundation and Rehydration** - Constants, config migration v8->v9, config UI for correlation window, and startup tier rehydration fix (completed 2026-04-03)
- [x] **Phase 18: Correlation Discovery** - CorrelationDetector with PMI-based discovery, sensor attribute exposure, and persistence (completed 2026-04-04)
- [ ] **Phase 19: Break Detection and Alerting** - Alert on broken correlations with sustained evidence and group-level deduplication
- [ ] **Phase 20: Correlation Lifecycle** - Stale pair decay and cleanup on entity removal

## Phase Details

### Phase 17: Foundation and Rehydration
**Goal**: Tier classification works correctly from first startup cycle, and all constants, config keys, and migration infrastructure for correlation are in place
**Depends on**: Phase 16
**Requirements**: RHY-01, CFG-01, CFG-02
**Success Criteria** (what must be TRUE):
  1. After a restart, entity tiers are classified on the first coordinator update cycle (not deferred to midnight)
  2. The HA config UI shows a correlation time window option that the user can adjust
  3. Existing installs upgrading from config v8 to v9 preserve all current settings and receive correlation defaults automatically
**Plans**: 2 plans
Plans:
- [x] 17-01-PLAN.md — Fix tier classification rehydration bug
- [x] 17-02-PLAN.md — Correlation constants, config UI, and v8->v9 migration

### Phase 18: Correlation Discovery
**Goal**: The system automatically discovers which entities co-occur and exposes those relationships to the user
**Depends on**: Phase 17
**Requirements**: COR-01, COR-02, COR-03, COR-04
**Success Criteria** (what must be TRUE):
  1. After sufficient observation, entity pairs that regularly fire within the configured time window appear as discovered correlation groups
  2. Pairs with fewer than the minimum co-occurrence count are not promoted to learned correlations (no premature discoveries)
  3. The entity_status_summary sensor includes a cross_sensor_patterns attribute listing discovered correlation groups with their co-occurrence rates
  4. Correlation state survives a Home Assistant restart (persisted to storage, restored on startup)
**Plans**: 2 plans
Plans:
- [x] 18-01-PLAN.md — CorrelationDetector class with PMI-based discovery and tests
- [x] 18-02-PLAN.md — Coordinator wiring, sensor exposure, and persistence

### Phase 19: Break Detection and Alerting
**Goal**: Users are alerted when learned correlations break, with noise suppression that prevents false or redundant alerts
**Depends on**: Phase 18
**Requirements**: COR-05, COR-06, COR-07
**Success Criteria** (what must be TRUE):
  1. When entity A fires without its expected companion entity B within the correlation window, a correlation break alert is generated
  2. Break alerts only fire after multiple consecutive missed co-occurrences (sustained evidence gating), not on a single miss
  3. A multi-entity correlation group produces one alert per broken group, not one alert per missing pair
**Plans**: TBD

### Phase 20: Correlation Lifecycle
**Goal**: Correlation state stays clean over time without manual intervention
**Depends on**: Phase 18
**Requirements**: COR-08, COR-09
**Success Criteria** (what must be TRUE):
  1. Correlation pairs that stop co-occurring gradually decay and are eventually removed from the learned set
  2. When a monitored entity is removed from the integration, all correlation pairs involving that entity are cleaned up
**Plans**: TBD

## Progress

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
| 9. Alert Suppression | v3.0 | 2/2 | Complete | 2026-03-14 |
| 10. Drift Accuracy | v3.0 | 2/2 | Complete | 2026-03-14 |
| 11. Adaptive Inactivity | v3.0 | 2/2 | Complete | 2026-03-14 |
| 12. Constants and Utilities | v3.1 | 1/1 | Complete | 2026-04-02 |
| 13. Tier Classification | v3.1 | 1/1 | Complete | 2026-04-02 |
| 14. Tier-Aware Detection | v3.1 | 1/1 | Complete | 2026-04-03 |
| 15. Coordinator Integration | v3.1 | 1/1 | Complete | 2026-04-03 |
| 16. Config UI and Migration | v3.1 | 1/1 | Complete | 2026-04-03 |
| 17. Foundation and Rehydration | v4.0 | 2/2 | Complete    | 2026-04-03 |
| 18. Correlation Discovery | v4.0 | 2/2 | Complete    | 2026-04-04 |
| 19. Break Detection and Alerting | v4.0 | 0/0 | Not started | - |
| 20. Correlation Lifecycle | v4.0 | 0/0 | Not started | - |
