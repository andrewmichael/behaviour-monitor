# Roadmap: Behaviour Monitor

## Milestones

- ✅ **v1.0 False Positive Reduction** — Phases 1-2 (shipped 2026-03-13)
- 🚧 **v1.1 Detection Rebuild** — Phases 3-5 (in progress)

## Phases

<details>
<summary>✅ v1.0 False Positive Reduction (Phases 1-2) — SHIPPED 2026-03-13</summary>

- [x] Phase 1: Coordinator Suppression (2/2 plans) — completed 2026-03-13
- [x] Phase 2: Analyzer Tightening (3/3 plans) — completed 2026-03-13

</details>

### 🚧 v1.1 Detection Rebuild (In Progress)

**Milestone Goal:** Replace z-score/ML analyzers with routine-based detection — acute events and drift tracking — so anomaly alerts represent genuinely unusual behavior rather than bucket-based statistical noise.

- [x] **Phase 3: Foundation and Routine Model** - Migrate storage, stub deprecated sensors, and build the per-entity baseline learning engine (completed 2026-03-13)
- [ ] **Phase 4: Detection Engines** - Build acute and drift detectors as pure-Python, HA-free components against the routine model API
- [ ] **Phase 5: Integration** - Wire detection engines into coordinator, extend config flow, verify full sensor data contract

## Phase Details

### Phase 3: Foundation and Routine Model
**Goal**: Storage is safely migrated to v3 format, deprecated ML sensors return defined stub states, and a routine model learns per-entity baselines from configurable rolling history — enabling both detection engines to consume structured baseline data
**Depends on**: Nothing (first v1.1 phase)
**Requirements**: INFRA-01, INFRA-02, ROUTINE-01, ROUTINE-02, ROUTINE-03
**Success Criteria** (what must be TRUE):
  1. Upgrading from v1.0 does not crash HA on startup — old z-score storage is detected and discarded gracefully with a log message, not a deserialization error
  2. The three deprecated ML sensors (ml_status, ml_training_remaining, cross_sensor_patterns) return defined stub states rather than going unavailable, so user automations that read them do not break
  3. After startup, the routine model bootstraps from HA recorder history — an existing installation with weeks of data begins with a populated baseline rather than a cold-start blank slate
  4. The routine model tracks per-entity baselines using 168 hour-of-day x day-of-week slots, distinguishing binary event-interval patterns from numeric value distributions
  5. When the routine model has insufficient history to make confident predictions, the system surfaces an explicit "detection inactive" status rather than silently producing no alerts
**Plans:** 4/4 plans complete

Plans:
- [x] 03-01-PLAN.md — RoutineModel TDD (pure-Python baseline learning engine with 168 slots)
- [x] 03-02-PLAN.md — Config migration and deprecated sensor stubs (const.py, __init__.py, sensor.py)
- [x] 03-03-PLAN.md — Coordinator storage migration, ML cleanup, and recorder bootstrap
- [ ] 03-04-PLAN.md — Gap closure: fix history_window_days config key + partial history confidence test

### Phase 4: Detection Engines
**Goal**: Acute and drift detectors are implemented as HA-free pure-Python components that consume the routine model API and produce structured alert results — fully testable without mocking HA infrastructure
**Depends on**: Phase 3
**Requirements**: ACUTE-01, ACUTE-02, ACUTE-03, DRIFT-01, DRIFT-02, DRIFT-03
**Success Criteria** (what must be TRUE):
  1. Acute detection fires when an entity has been silent for longer than a configurable multiplier of its learned typical interval — not based on a fixed hour threshold
  2. Acute detection fires when activity occurs at a time that has never or rarely appeared in the learned history (e.g., front door at 3am not in baseline)
  3. No acute alert fires from a single observation — the detector requires multiple consecutive polling cycles of sustained evidence before producing a result
  4. Drift detection identifies a persistent shift in daily activity rates using CUSUM — a minimum evidence window of several days is required before an alert is produced
  5. Calling the routine_reset service clears the drift accumulator for an entity, so a voluntary routine change (e.g., started working from home) does not continue triggering drift alerts
**Plans**: TBD

### Phase 5: Integration
**Goal**: Detection engines are wired into a rebuilt coordinator under 350 lines, all 14 sensor entity IDs remain stable and return safe defaults, and the config flow exposes history window, inactivity multiplier, and drift sensitivity options with graceful migration from v1.0 config entries
**Depends on**: Phase 4
**Requirements**: INFRA-03
**Success Criteria** (what must be TRUE):
  1. Users can configure history window length, inactivity alert multiplier, and drift sensitivity in the config flow UI — existing v1.0 config entries load without error and receive sensible defaults for the new options
  2. All 14 sensor entity IDs are unchanged — no sensor goes unavailable on upgrade and coordinator.data is never None on first refresh
  3. An acute or drift alert produces a notification via the configured notification service (or persistent_notification fallback), with existing suppression logic (holiday mode, snooze, cooldown, welfare debounce) fully preserved
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Coordinator Suppression | v1.0 | 2/2 | Complete | 2026-03-13 |
| 2. Analyzer Tightening | v1.0 | 3/3 | Complete | 2026-03-13 |
| 3. Foundation and Routine Model | 4/4 | Complete   | 2026-03-13 | - |
| 4. Detection Engines | v1.1 | 0/? | Not started | - |
| 5. Integration | v1.1 | 0/? | Not started | - |
