# Phase 4: Detection Engines - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Build acute (inactivity + unusual-time) and drift (CUSUM) detectors as pure-Python, HA-free classes that consume the RoutineModel API and produce structured alert results. Fully testable without mocking HA infrastructure. Config flow UI changes and sensor wiring are Phase 5 — this phase delivers the detection logic and result types.

</domain>

<decisions>
## Implementation Decisions

### Alert Sensitivity Defaults
- Default inactivity multiplier: 3x the learned typical interval per entity
- Sustained evidence requirement: 3 consecutive polling cycles before any acute alert fires
- Inactivity multiplier is a single global setting (per-entity tuning deferred to v2 per NOTIF-02)
- Unusual-time detection: activity in a slot with fewer than MIN_SLOT_OBSERVATIONS (4) events is flagged as unusual — reuses Phase 3's sparse slot guard

### Alert Output Structure
- Rich structured result: alert type, severity, confidence, evidence details (expected vs actual values), entity context, timestamp
- 3-tier severity: low (approaching threshold), medium (threshold crossed), high (well beyond threshold, e.g., 5x+ multiplier)
- Human-readable explanation included in result (e.g., "Front door inactive 14h (typical: every 4h, 3.5x threshold)")
- Common base result type with typed detail dicts — acute and drift share fields (entity_id, alert_type, severity, confidence, explanation, timestamp) plus type-specific details

### Drift Detection
- Minimum evidence window: 3 days of shifted behavior before alerting
- Metric tracked: daily event count (state changes per day per entity)
- Detects both increases and decreases in activity (bidirectional CUSUM)
- Sensitivity exposed as simple high/medium/low setting, mapped to pre-tuned CUSUM parameters internally

### Routine Reset
- Clears drift accumulator only — baseline history preserved, model adapts naturally as new data arrives
- Single entity_id per call (no "reset all" option)
- No cooldown period — acute alerts unaffected by reset
- Log a WARNING-level message and fire an HA event for logbook visibility

### Claude's Discretion
- Internal CUSUM parameter tuning (k and h values) for each sensitivity level
- Alert result class design and dataclass structure
- Detector class API surface (method signatures, return types)
- Test strategy and fixture design
- How severity thresholds map to multiplier ranges (e.g., low = 2-3x, medium = 3-4x, high = 4x+)

</decisions>

<specifics>
## Specific Ideas

- Welfare monitoring context: 3-day drift window chosen because in welfare scenarios, detecting a change within days matters — a full week is too slow
- The RoutineModel API already provides `expected_gap_seconds(hour, dow)`, `daily_activity_rate(date)`, `confidence(now)`, and `is_sufficient` — detectors should consume these directly
- STATE.md flags CUSUM params (k=0.5, h=4.0) as MEDIUM confidence — validate against simulated scenarios during TDD
- Phase 3 established pure Python stdlib only, no HA imports in detection components

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `routine_model.py`: RoutineModel, EntityRoutine, ActivitySlot — the baseline API these detectors consume
- `routine_model.expected_gap_seconds(hour, dow)`: median inter-event interval for acute inactivity detection
- `routine_model.daily_activity_rate(date)`: daily event count for drift CUSUM input
- `routine_model.is_sufficient` on ActivitySlot: sparse slot guard reusable for unusual-time detection
- `const.py`: severity levels (SEVERITY_LOW/MEDIUM/HIGH), welfare statuses already defined

### Established Patterns
- Pure Python stdlib, zero HA imports (routine_model.py proves the pattern)
- Dataclass-based models with `to_dict`/`from_dict` serialization
- TDD workflow: failing tests first, then implementation
- `MIN_SLOT_OBSERVATIONS = 4` as the sparse slot threshold

### Integration Points
- Detectors will be imported by `coordinator.py` (Phase 5) which calls them each polling cycle
- Alert results will populate `coordinator.data` dict consumed by sensor value_fn lambdas
- `routine_reset` service will be registered in `__init__.py` alongside existing holiday/snooze services
- Drift accumulator state needs serialization for persistence via HA Store

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-detection-engines*
*Context gathered: 2026-03-13*
