# Roadmap: Behaviour Monitor

## Milestones

- ✅ **v1.0 False Positive Reduction** — Phases 1-2 (shipped 2026-03-13)
- ✅ **v1.1 Detection Rebuild** — Phases 3-5 (shipped 2026-03-13)
- 🚧 **v2.9 Housekeeping & Config** — Phases 6-8 (in progress)

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

### 🚧 v2.9 Housekeeping & Config (In Progress)

**Milestone Goal:** Clean out all v1.1 tech debt, remove dead ML remnants, and expose hardcoded config options in the UI.

- [x] **Phase 6: Dead Code Removal** - Strip deprecated ML sensor stubs and dead constants from const.py and sensor.py (completed 2026-03-14)
- [x] **Phase 7: Config Flow Additions** - Expose learning period and attribute tracking as user-configurable options, with migration (completed 2026-03-14)
- [x] **Phase 8: Bootstrap Fix and Closeout** - Fix missing post-bootstrap save and record milestone versioning convention (completed 2026-03-14)

## Phase Details

### Phase 6: Dead Code Removal
**Goal**: All deprecated ML remnants and dead constant blocks are gone from the codebase
**Depends on**: Nothing (first phase of milestone)
**Requirements**: DEBT-01, DEBT-02, DEBT-03
**Success Criteria** (what must be TRUE):
  1. The three deprecated ML sensor entities (ml_status, cross_sensor_patterns, ml_training_remaining) no longer appear in HA's entity registry after integration reload
  2. The coordinator update method no longer emits stub keys for the removed sensor descriptions
  3. The dead constants block (lines 129-184 of const.py) is absent from the file and all tests still pass
  4. The unused CONF_* constant names (CONF_SENSITIVITY, CONF_ENABLE_ML, CONF_RETRAIN_PERIOD, CONF_ML_LEARNING_PERIOD, CONF_CROSS_SENSOR_WINDOW, CONF_TRACK_ATTRIBUTES, CONF_LEARNING_PERIOD) are absent from const.py
**Plans**: 2 plans

Plans:
- [ ] 06-01-PLAN.md — Remove deprecated sensor descriptions, coordinator stubs, and dead constants from production files
- [ ] 06-02-PLAN.md — Update tests to remove ML stub assertions and deleted sensor test methods

### Phase 7: Config Flow Additions
**Goal**: Users can configure learning period and attribute tracking from the HA config UI, and existing installs upgrade without manual reconfiguration
**Depends on**: Phase 6
**Requirements**: CONF-01, CONF-02, CONF-03
**Success Criteria** (what must be TRUE):
  1. The Options flow presents a "Learning period (days)" field and accepts a numeric value, defaulting to 7
  2. The Options flow presents an "Attribute tracking" toggle, defaulting to enabled
  3. An existing install that upgrades without touching its config entry automatically receives both new options at their defaults (no broken config, no HA error log entries)
  4. A fresh install presents both new fields during initial setup
**Plans**: 2 plans

Plans:
- [ ] 07-01-PLAN.md — Add constants, update config flow schema (both initial and options), add v4->v5 migration
- [ ] 07-02-PLAN.md — Wire coordinator to read new config values and add test coverage

### Phase 8: Bootstrap Fix and Closeout
**Goal**: The coordinator correctly persists routine model data after bootstrap, and the milestone versioning convention is established in MILESTONES.md
**Depends on**: Phase 7
**Requirements**: DEBT-04, VERS-01
**Success Criteria** (what must be TRUE):
  1. After a fresh HA restart with no prior storage file, the coordinator calls _save_data() following bootstrap so that an immediate second restart does not re-bootstrap from recorder history
  2. MILESTONES.md records the package version range covered by v2.9 when the milestone closes
**Plans**: 2 plans

Plans:
- [ ] 08-01-PLAN.md — Fix post-bootstrap _save_data() call in coordinator and add regression test
- [ ] 08-02-PLAN.md — Add v2.9 milestone entry to MILESTONES.md

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Coordinator Suppression | v1.0 | 2/2 | Complete | 2026-03-13 |
| 2. Analyzer Tightening | v1.0 | 3/3 | Complete | 2026-03-13 |
| 3. Foundation and Routine Model | v1.1 | 4/4 | Complete | 2026-03-13 |
| 4. Detection Engines | v1.1 | 2/2 | Complete | 2026-03-13 |
| 5. Integration | v1.1 | 3/3 | Complete | 2026-03-13 |
| 6. Dead Code Removal | 2/2 | Complete   | 2026-03-14 | - |
| 7. Config Flow Additions | 2/2 | Complete   | 2026-03-14 | - |
| 8. Bootstrap Fix and Closeout | 2/2 | Complete   | 2026-03-14 | - |
