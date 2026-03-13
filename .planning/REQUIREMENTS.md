# Requirements: Behaviour Monitor — False Positive Reduction

**Defined:** 2026-03-13
**Core Value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual

## v1 Requirements

### Notification Suppression

- [ ] **NOTIF-01**: Notification cooldown per entity prevents re-alerting the same entity within a configurable time window
- [ ] **NOTIF-02**: Anomaly deduplication prevents re-alerting for the same ongoing anomaly type on the same entity
- [ ] **NOTIF-03**: Severity minimum gate only sends notifications for anomalies above a minimum severity threshold

### Statistical Analyzer Tuning

- [ ] **STAT-01**: Minimum observation count per time bucket prevents flagging when insufficient data exists (fixes float("inf") z-scores from zero-variance buckets)
- [ ] **STAT-02**: Minimum mean activity guard skips anomaly detection for time buckets with near-zero historical activity
- [ ] **STAT-03**: Default sensitivity thresholds raised so Medium sensitivity no longer flags ~4.5% of normal events
- [ ] **STAT-04**: Adaptive thresholds adjust per-entity based on historical variance profile (high-variance entities get wider thresholds)

### ML Analyzer Tuning

- [ ] **ML-01**: Cross-sensor correlation thresholds raised — minimum co-occurrence count increased from 10 to a statistically meaningful level
- [ ] **ML-02**: ML anomaly score threshold raised to reduce marginal detections
- [ ] **ML-03**: ML score smoothing via exponential moving average reduces noise from single-point spikes

### Welfare Status

- [ ] **WELF-01**: Welfare status hysteresis/debounce prevents rapid flapping between normal/concern/alert states

## v2 Requirements

### Advanced Filtering

- **ADV-01**: Cross-analyzer agreement weighting — require both statistical and ML to flag for highest confidence notifications
- **ADV-02**: Anomaly severity tiers (Info/Warning/Critical) with different notification behaviors per tier
- **ADV-03**: Context-aware sensitivity — different thresholds for time-of-day and day-of-week transitions

## Out of Scope

| Feature | Reason |
|---------|--------|
| Per-entity sensitivity UI | Too complex; global tuning first |
| Real-time ML retraining on user feedback | Complexity not justified for HA integration |
| New anomaly types or detection patterns | Focus is reducing noise, not adding features |
| Daily digest notifications | May revisit later, separate concern from detection quality |
| Complex multi-entity correlation rules | Already have cross-sensor patterns |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| NOTIF-01 | — | Pending |
| NOTIF-02 | — | Pending |
| NOTIF-03 | — | Pending |
| STAT-01 | — | Pending |
| STAT-02 | — | Pending |
| STAT-03 | — | Pending |
| STAT-04 | — | Pending |
| ML-01 | — | Pending |
| ML-02 | — | Pending |
| ML-03 | — | Pending |
| WELF-01 | — | Pending |

**Coverage:**
- v1 requirements: 11 total
- Mapped to phases: 0
- Unmapped: 11 ⚠️

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-03-13 after initial definition*
