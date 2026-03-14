# Requirements: Behaviour Monitor

**Defined:** 2026-03-14
**Core Value:** Anomaly alerts must be trustworthy — when a notification fires, it should represent something genuinely unusual, not normal routine variation.

## v3.0 Requirements

### Alert Suppression

- [x] **SUPR-01**: After an alert fires for a given entity+alert-type, subsequent notifications are suppressed for a configurable repeat interval (default 4 hours) rather than firing every polling cycle
- [ ] **SUPR-02**: The alert repeat interval is user-configurable from the HA config UI
- [x] **SUPR-03**: Suppression state resets when the alert condition clears — if the condition resolves and re-triggers, a fresh notification fires immediately

### Drift Detection

- [ ] **DRFT-01**: The CUSUM drift baseline splits daily activity rates by day-type (weekdays vs weekends) so weekend activity is only compared to other weekend days
- [ ] **DRFT-02**: The drift baseline applies exponential decay weighting so recent days influence the baseline more than data from 60+ days ago

### Inactivity Detection

- [ ] **INAC-01**: The inactivity threshold for each entity is derived from that entity's own observed inter-event variance rather than applying a single global multiplier uniformly

## Future Requirements

- Per-entity sensitivity tuning UI — deferred (INAC-01 handles it automatically)
- Entity aliveness / dead sensor detection — future milestone
- Alert correlation / multi-entity welfare escalation — future milestone
- Per-slot confidence gating for unusual-time alerts — future milestone

## Out of Scope

| Feature | Reason |
|---------|--------|
| Per-entity sensitivity UI | INAC-01 auto-learns it; manual override adds complexity without clear benefit |
| Cross-entity routine correlation | Future milestone — different architecture required |
| Seasonal pattern adjustment | Future milestone |
| Daily digest notifications | Future milestone |
| Population-based norms | Privacy concern; per-individual learning only |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SUPR-01 | Phase 9 | Complete |
| SUPR-02 | Phase 9 | Pending |
| SUPR-03 | Phase 9 | Complete |
| DRFT-01 | Phase 10 | Pending |
| DRFT-02 | Phase 10 | Pending |
| INAC-01 | Phase 11 | Pending |

**Coverage:**
- v3.0 requirements: 6 total
- Mapped to phases: 6
- Unmapped: 0

---
*Requirements defined: 2026-03-14*
