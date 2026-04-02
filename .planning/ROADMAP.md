# Roadmap: Behaviour Monitor

## Milestones

- ✅ **v1.0 False Positive Reduction** — Phases 1-2 (shipped 2026-03-13)
- ✅ **v1.1 Detection Rebuild** — Phases 3-5 (shipped 2026-03-13)
- ✅ **v2.9 Housekeeping & Config** — Phases 6-8 (shipped 2026-03-14)
- ✅ **v3.0 Detection Accuracy** — Phases 9-11 (shipped 2026-03-14)
- **v3.1 Activity-Rate Classification** — Phases 12-16

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

### v3.1 Activity-Rate Classification (Phases 12-16)

**Goal:** Eliminate false-positive inactivity alerts on high-frequency entities by classifying entities into frequency tiers and applying tier-appropriate detection parameters.

- [x] **Phase 12: Constants and Utilities** — DET-03 (completed 2026-04-02)
- [x] **Phase 13: Tier Classification** — CLASS-01, CLASS-02, CLASS-03, CLASS-05 (completed 2026-04-02)
- [ ] **Phase 14: Tier-Aware Detection** — DET-01, DET-02
- [ ] **Phase 15: Coordinator Integration** — CLASS-04
- [ ] **Phase 16: Config UI and Migration** — CFG-01, CFG-02

### Phase 12: Constants and Utilities

**Goal:** Define ActivityTier enum, tier boundary constants, floor/boost lookup dicts, and shared format_duration() utility.

**Files:** `const.py`, `routine_model.py`
**Requirements:** DET-03
**Depends on:** None
**Plans:** 1/1 plans complete

Plans:
- [x] 12-01-PLAN.md — ActivityTier enum, tier constants, format_duration utility, and tests

### Phase 13: Tier Classification

**Goal:** Auto-classify entities into HIGH/MEDIUM/LOW frequency tiers from observed routine data, gated on learning confidence, reclassified at most once per day.

**Files:** `routine_model.py`
**Requirements:** CLASS-01, CLASS-02, CLASS-03, CLASS-05
**Depends on:** Phase 12
**Plans:** 1/1 plans complete

Plans:
- [x] 13-01-PLAN.md — classify_tier method, activity_tier property, and classification tests

### Phase 14: Tier-Aware Detection

**Goal:** Apply tier-specific multiplier boost and absolute minimum floor in check_inactivity(), fix sub-hour display formatting.

**Files:** `acute_detector.py`
**Requirements:** DET-01, DET-02
**Depends on:** Phase 12, Phase 13
**Plans:** 1 plan

Plans:
- [ ] 14-01-PLAN.md — Tier-aware threshold (boost + floor) and formatted duration display

### Phase 15: Coordinator Integration

**Goal:** Wire daily reclassification, tier override injection, tier as sensor attribute, and formatted durations into coordinator.

**Files:** `coordinator.py`, `sensor.py`
**Requirements:** CLASS-04
**Depends on:** Phase 13, Phase 14

### Phase 16: Config UI and Migration

**Goal:** Add global tier override setting in config UI, migrate config v7 to v8 preserving user-tuned multiplier values.

**Files:** `config_flow.py`, `__init__.py`, `const.py`
**Requirements:** CFG-01, CFG-02
**Depends on:** Phase 15

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
| 12. Constants and Utilities | v3.1 | 1/1 | Complete    | 2026-04-02 |
| 13. Tier Classification | v3.1 | 1/1 | Complete    | 2026-04-02 |
| 14. Tier-Aware Detection | v3.1 | 0/0 | Pending | — |
| 15. Coordinator Integration | v3.1 | 0/0 | Pending | — |
| 16. Config UI and Migration | v3.1 | 0/0 | Pending | — |
