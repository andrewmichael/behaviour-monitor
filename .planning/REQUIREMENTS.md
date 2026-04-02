# Requirements: Behaviour Monitor

**Defined:** 2026-03-28
**Core Value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.

## v3.1 Requirements

Requirements for Activity-Rate Classification milestone. Each maps to roadmap phases.

### Classification

- [ ] **CLASS-01**: System auto-classifies each entity into HIGH/MEDIUM/LOW frequency tier based on median daily event rate from observed routine data
- [ ] **CLASS-02**: Classification is gated on learning confidence — entities without sufficient data use conservative defaults
- [ ] **CLASS-03**: Tier is reclassified at most once per day to prevent flapping
- [ ] **CLASS-04**: Computed tier is exposed as an attribute on the entity status summary sensor
- [ ] **CLASS-05**: Tier changes are logged at debug level for troubleshooting

### Detection

- [ ] **DET-01**: High-frequency entities use a higher effective multiplier AND an absolute minimum inactivity floor before alerting
- [ ] **DET-02**: Alert explanations display minutes (not hours) when typical interval is under 1 hour
- [ ] **DET-03**: A shared `format_duration()` utility replaces duplicated formatting logic in acute_detector and coordinator

### Config

- [ ] **CFG-01**: User can override the auto-classified tier via a global setting in the HA config UI
- [ ] **CFG-02**: Config migration v7→v8 preserves existing user-tuned multiplier values and injects defaults for new keys

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

### Entity-Level Tuning

- **ENT-01**: Per-entity tier override in config UI
- **ENT-02**: Configurable tier boundary thresholds (high/low cutoff values)
- **ENT-03**: Tier-specific sustained evidence cycles

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Per-entity tier override UI | PROJECT.md constraint: per-entity sensitivity tuning is future milestone |
| ML-based classification | Hard constraint: pure Python, no external dependencies |
| Dynamic tier reassignment every cycle | Causes instability — tier should be stable over hours/days |
| Tier-specific drift detection | CUSUM operates on daily rates, not inter-event intervals; problem is acute-detection-specific |
| Separate notification channels per tier | Over-engineering; existing severity gating handles notification volume |
| Configurable tier boundary thresholds | Premature; ship fixed defaults, add only if user feedback demands it |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLASS-01 | 13 | Pending |
| CLASS-02 | 13 | Pending |
| CLASS-03 | 13 | Pending |
| CLASS-04 | 15 | Pending |
| CLASS-05 | 13 | Pending |
| DET-01 | 14 | Pending |
| DET-02 | 14 | Pending |
| DET-03 | 12 | Pending |
| CFG-01 | 16 | Pending |
| CFG-02 | 16 | Pending |

**Coverage:**
- v3.1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-28*
*Last updated: 2026-03-28 after initial definition*
