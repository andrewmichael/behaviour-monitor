# Roadmap: Behaviour Monitor — False Positive Reduction

## Overview

Two phases eliminate the notification flood. Phase 1 adds suppression gates in the coordinator — the highest-impact changes with zero detection regression risk (nothing about what gets detected changes, only what gets sent). Phase 2 tightens both analyzers so fewer anomalies reach the coordinator in the first place, complementing and validating Phase 1's gates. After both phases ship, the integration should fire notifications only for genuinely unusual events.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Coordinator Suppression** - Add notification cooldown, deduplication, severity gate, and welfare hysteresis in coordinator.py
- [x] **Phase 2: Analyzer Tightening** - Add observation guards, raise default thresholds, tighten ML scoring and cross-sensor correlation in analyzer.py and ml_analyzer.py (completed 2026-03-13)

## Phase Details

### Phase 1: Coordinator Suppression
**Goal**: Notifications only fire when an anomaly is new, significant, and not recently reported
**Depends on**: Nothing (first phase)
**Requirements**: NOTIF-01, NOTIF-02, NOTIF-03, WELF-01
**Success Criteria** (what must be TRUE):
  1. An anomaly that persists across multiple update cycles sends at most one notification per configurable cooldown window (not one per 60-second update)
  2. When both statistical and ML paths flag the same entity in the same cycle, exactly one notification is sent
  3. Minor-severity anomalies (below the minimum severity threshold) update sensor state but do not trigger push notifications
  4. Welfare status does not flip between normal and concern on back-to-back update cycles — a transition requires N consecutive cycles at the new status before a notification fires
**Plans:** 2/2 plans executed

Plans:
- [x] 01-01-PLAN.md — Constants, config flow fields, and test scaffolds (foundation)
- [x] 01-02-PLAN.md — Coordinator suppression logic: severity gate, cooldown, dedup, cross-path merge, welfare debounce

### Phase 2: Analyzer Tightening
**Goal**: Analyzers produce fewer false anomalies so the coordinator has less noise to suppress
**Depends on**: Phase 1
**Requirements**: STAT-01, STAT-02, STAT-03, STAT-04, ML-01, ML-02, ML-03
**Success Criteria** (what must be TRUE):
  1. Entities that activate with perfect consistency (zero historical variance) no longer generate infinite z-scores and are not flagged as anomalous
  2. Time buckets with fewer than the minimum observation count are skipped — sparse-data buckets do not produce anomaly results
  3. The default sensitivity threshold for new installs no longer flags routine variation at medium sensitivity
  4. ML anomaly scores from single-interval spikes are smoothed — a one-off spike below the smoothed threshold does not reach the coordinator
  5. Cross-sensor correlation patterns require a statistically meaningful co-occurrence count before triggering — low-sample correlations are not reported
**Plans:** 3/3 plans complete

Plans:
- [ ] 02-01-PLAN.md — Bucket observation guard and raised sensitivity threshold (STAT-01, STAT-02, STAT-03)
- [ ] 02-02-PLAN.md — Per-entity adaptive thresholds (STAT-04)
- [ ] 02-03-PLAN.md — ML cross-sensor guard, contamination tuning, EMA score smoothing (ML-01, ML-02, ML-03)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Coordinator Suppression | 2/2 | Complete | 2026-03-13 |
| 2. Analyzer Tightening | 3/3 | Complete   | 2026-03-13 |
