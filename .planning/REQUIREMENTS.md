# Requirements: Behaviour Monitor

**Defined:** 2026-03-14
**Core Value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.

## v2.9 Requirements

### Tech Debt

- [x] **DEBT-01**: Deprecated ML sensor stubs (ml_status, cross_sensor_patterns, ml_training_remaining) and their coordinator stub keys are removed
- [x] **DEBT-02**: Dead legacy constants block removed from const.py (lines 129-184: z-score thresholds, ML contamination, EMA alpha, etc.)
- [x] **DEBT-03**: Unused CONF_* constant definitions removed from const.py (CONF_SENSITIVITY, CONF_ENABLE_ML, CONF_RETRAIN_PERIOD, CONF_ML_LEARNING_PERIOD, CONF_CROSS_SENSOR_WINDOW, CONF_TRACK_ATTRIBUTES, CONF_LEARNING_PERIOD)
- [ ] **DEBT-04**: Post-bootstrap `_save_data()` call added to coordinator so routine model survives an immediate restart after first load

### Config UI

- [x] **CONF-01**: User can configure the learning period (days) from the config flow UI, with a default of 7
- [x] **CONF-02**: User can toggle attribute tracking on/off from the config flow UI, defaulting to on
- [x] **CONF-03**: Existing installs automatically receive the new config options with defaults on upgrade (no manual reconfiguration required)

### Versioning

- [ ] **VERS-01**: MILESTONES.md records the package version range for v2.9 when the milestone closes (establishes the convention going forward)

## Future Requirements

*(None identified — all deferred items tracked in PROJECT.md Out of Scope)*

## Out of Scope

| Feature | Reason |
|---------|--------|
| Per-entity sensitivity tuning UI | Future milestone — larger design surface |
| Cross-entity routine correlation | Future milestone |
| Seasonal pattern adjustment | Future milestone |
| Daily digest notifications | May revisit in future milestone |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEBT-01 | Phase 6 | Complete |
| DEBT-02 | Phase 6 | Complete |
| DEBT-03 | Phase 6 | Complete |
| DEBT-04 | Phase 8 | Pending |
| CONF-01 | Phase 7 | Complete |
| CONF-02 | Phase 7 | Complete |
| CONF-03 | Phase 7 | Complete |
| VERS-01 | Phase 8 | Pending |

**Coverage:**
- v2.9 requirements: 8 total
- Mapped to phases: 8
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-14*
*Last updated: 2026-03-14 — traceability populated after roadmap creation*
