# Phase 1: Coordinator Suppression - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Add notification cooldown, deduplication, severity gate, and welfare hysteresis in `coordinator.py`. This phase only changes notification dispatch logic — detection algorithms are unchanged. Anomalies below the notification gate still update sensor state (visible to automations), they just don't fire push notifications.

</domain>

<decisions>
## Implementation Decisions

### Cooldown behavior
- Per-entity cooldown (Entity A's cooldown does not block Entity B's alerts)
- Default cooldown: 30 minutes
- Cooldown is configurable via config flow options UI (new option field)
- Cooldown resets when the anomaly clears (entity returns to normal) — if entity goes anomalous again after clearing, treat as new event

### Severity gate level
- Configurable minimum severity level for push notifications via config flow options UI
- Default: significant (3.5σ) — very quiet by default, users can lower to moderate if desired
- Anomalies below the severity gate update sensor state but do NOT trigger push notifications — users can still build HA automations on sensor values

### Deduplication strategy
- Dedup key: entity_id + anomaly_type — different anomaly types on the same entity are separate alerts
- Ongoing anomalies (same entity+type persisting across update cycles) are suppressed until cooldown expires

### Cross-path notification merge
- When both statistical and ML paths flag the same entity in the same cycle, merge into a single notification

### Welfare debounce
- Debounce applies in both directions (escalation and de-escalation)
- Cycle count before notification at Claude's discretion (research suggests 3-5 cycles / 3-5 minutes)

### Claude's Discretion
- Cross-path notification merge implementation details
- Welfare debounce cycle count (within 3-5 cycle range suggested by research)
- Exact config flow UI labels and descriptions for new options
- How to persist per-entity cooldown state (in-memory dict vs coordinator store)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_last_notification_time` / `_last_notification_type`: Already tracked in coordinator but never consulted before sending — extend to per-entity tracking
- Severity system in `const.py`: Full 5-level severity (normal/minor/moderate/significant/critical) with z-score thresholds already defined — just need a gate check
- `_last_welfare_status`: Already tracks previous welfare state — extend with consecutive cycle counter

### Established Patterns
- Config options follow `CONF_` prefix pattern in `const.py`, `DEFAULT_` for defaults
- Config flow uses `vol.Optional()` with defaults from `const.py`
- Coordinator state persisted via `_save_data()` to `.storage/` JSON files
- All notification methods: `_send_notification()`, `_send_ml_notification()`, `_send_welfare_notification()`

### Integration Points
- `_async_update_data()` at lines ~561-573: Where stat/ML/welfare notifications are dispatched — cooldown and severity checks insert here
- `config_flow.py`: Add new options for cooldown duration and minimum severity
- `const.py`: New constants for defaults (CONF_NOTIFICATION_COOLDOWN, CONF_MIN_NOTIFICATION_SEVERITY, DEFAULT_NOTIFICATION_COOLDOWN, DEFAULT_MIN_NOTIFICATION_SEVERITY)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-coordinator-suppression*
*Context gathered: 2026-03-13*
