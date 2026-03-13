# Requirements: Behaviour Monitor

**Defined:** 2026-03-13
**Core Value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.

## v1.1 Requirements

Requirements for Detection Rebuild milestone. Each maps to roadmap phases.

### Routine Model

- [x] **ROUTINE-01**: System learns per-entity behavior baselines using 168 hour-of-day x day-of-week slots from a configurable rolling history window (default 4 weeks)
- [ ] **ROUTINE-02**: System bootstraps routine model from existing HA recorder history on first load, enabling immediate detection for existing installations
- [x] **ROUTINE-03**: System uses event frequency/timing for binary entities (motion, door) and value distributions for numeric entities (temperature, power)

### Acute Detection

- [ ] **ACUTE-01**: System alerts when no expected activity occurs for a configurable multiplier of the learned typical interval per entity
- [ ] **ACUTE-02**: System alerts on activity at times that have never or rarely occurred in learned history (e.g., front door at 3am)
- [ ] **ACUTE-03**: System requires sustained evidence (multiple consecutive polling cycles) before firing any acute alert — no single-point alerts

### Drift Detection

- [ ] **DRIFT-01**: System detects persistent changes in daily behavior metrics using CUSUM change point detection
- [ ] **DRIFT-02**: User can call a routine_reset service to tell the model their routine changed intentionally, preventing false drift alerts
- [ ] **DRIFT-03**: User can configure drift detection sensitivity in the config flow UI

### Infrastructure

- [ ] **INFRA-01**: System migrates from v2 z-score storage format to new routine format and cleans up orphaned ML storage files
- [ ] **INFRA-02**: ML-specific sensor entities (ml_status, ml_training_remaining, cross_sensor_patterns) are preserved as deprecated stubs with safe default states
- [ ] **INFRA-03**: Config flow UI includes options for history window length, inactivity alert multiplier, and drift sensitivity

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Notifications

- **NOTIF-01**: Daily digest summarizing detected anomalies and drift trends
- **NOTIF-02**: Per-entity sensitivity tuning UI (override global sensitivity per entity)

### Advanced Detection

- **ADV-01**: Cross-entity routine correlation (e.g., "kitchen motion usually follows bedroom motion within 30 minutes")
- **ADV-02**: Seasonal pattern adjustment (routine model accounts for daylight/seasonal variation)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Keeping z-score analyzer | Fundamentally noisy for irregular human behavior; being replaced |
| Keeping River ML dependency | No new dependencies constraint; routine model replaces ML |
| Offline mode | Real-time monitoring is core value |
| Population-based norms | Privacy concern; per-individual learning only |
| Deep learning models | Complexity and dependency overhead; pure Python constraint |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ROUTINE-01 | Phase 3 | Complete |
| ROUTINE-02 | Phase 3 | Pending |
| ROUTINE-03 | Phase 3 | Complete |
| ACUTE-01 | Phase 4 | Pending |
| ACUTE-02 | Phase 4 | Pending |
| ACUTE-03 | Phase 4 | Pending |
| DRIFT-01 | Phase 4 | Pending |
| DRIFT-02 | Phase 4 | Pending |
| DRIFT-03 | Phase 4 | Pending |
| INFRA-01 | Phase 3 | Pending |
| INFRA-02 | Phase 3 | Pending |
| INFRA-03 | Phase 5 | Pending |

**Coverage:**
- v1.1 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-03-13 after roadmap creation*
