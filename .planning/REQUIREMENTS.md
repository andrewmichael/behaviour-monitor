# Requirements: Behaviour Monitor

**Defined:** 2026-04-03
**Core Value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.

## v4.0 Requirements

Requirements for Cross-Entity Correlation milestone. Each maps to roadmap phases.

### Rehydration

- [x] **RHY-01**: Tier classification runs on first coordinator update cycle after startup, not just at day boundary

### Correlation Discovery

- [ ] **COR-01**: System discovers entity pairs that co-occur within a configurable time window using PMI-based correlation strength
- [ ] **COR-02**: Discovery is gated on minimum co-occurrence count to prevent premature correlations
- [x] **COR-03**: Discovered correlation groups are exposed as sensor attributes on entity_status_summary
- [x] **COR-04**: Correlation state is persisted to storage and restored on startup

### Correlation Alerting

- [x] **COR-05**: System alerts when a learned correlation breaks (entity A fires without expected companion B within the window)
- [x] **COR-06**: Break alerts require sustained evidence (multiple consecutive misses) before firing
- [x] **COR-07**: Alerts are deduplicated at the group level — one alert per broken group, not per pair

### Config & Lifecycle

- [x] **CFG-01**: User can configure the correlation time window via the HA config UI
- [x] **CFG-02**: Config migration v8 to v9 preserves existing values and injects correlation defaults
- [ ] **COR-08**: Stale correlation pairs decay automatically when entities stop co-occurring
- [x] **COR-09**: Correlation state is cleaned up when monitored entities are removed

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

### Entity-Level Tuning

- **ENT-01**: Per-entity tier override in config UI
- **ENT-02**: Configurable tier boundary thresholds (high/low cutoff values)
- **ENT-03**: Tier-specific sustained evidence cycles

### Correlation Enhancements

- **COR-F01**: Sequence detection (ordered A→B within N minutes)
- **COR-F02**: Time-of-day scoped correlations (morning vs evening groups)
- **COR-F03**: User-defined correlation groups (manual override of auto-discovery)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Causal inference between entities | Complexity far exceeds benefit; co-occurrence is sufficient |
| ML-based correlation discovery | Hard constraint: pure Python, no external dependencies |
| Per-pair correlation tuning UI | Premature; ship auto-discovery, add tuning only if needed |
| Correlation contributing to welfare escalation | Risk of false welfare alerts; keep correlation breaks at LOW severity |
| Daily digest notifications | Separate feature, not related to correlation |
| Seasonal pattern adjustment | Future milestone |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| RHY-01 | Phase 17 | Complete |
| COR-01 | Phase 18 | Pending |
| COR-02 | Phase 18 | Pending |
| COR-03 | Phase 18 | Complete |
| COR-04 | Phase 18 | Complete |
| COR-05 | Phase 19 | Complete |
| COR-06 | Phase 19 | Complete |
| COR-07 | Phase 19 | Complete |
| CFG-01 | Phase 17 | Complete |
| CFG-02 | Phase 17 | Complete |
| COR-08 | Phase 20 | Pending |
| COR-09 | Phase 20 | Complete |

**Coverage:**
- v4.0 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0

---
*Requirements defined: 2026-04-03*
*Last updated: 2026-04-03 after roadmap creation*
