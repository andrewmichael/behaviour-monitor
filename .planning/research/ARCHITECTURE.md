# Architecture Patterns: False Positive Reduction

**Domain:** Anomaly detection false positive reduction in a dual-analyzer Home Assistant integration
**Researched:** 2026-03-13
**Confidence:** HIGH (based on direct codebase analysis)

---

## Recommended Architecture

The existing architecture is sound. No structural changes are needed. False positive reduction is achieved by layering new logic at precisely-defined points in the existing pipeline — not by restructuring components.

The pattern is: **each component owns what it produces, the coordinator owns what gets sent**.

```
StatePoll / EventBus
        |
        v
[coordinator.py: _handle_state_changed()]
  - Gate: holiday mode, entity not monitored, state unchanged
        |
        +---> [analyzer.py: PatternAnalyzer]
        |       - record_state_change()
        |       - check_for_anomalies() → List[AnomalyResult]
        |         * THRESHOLD LIVES HERE: _sensitivity_threshold (Z-score)
        |         * OBSERVATION GATE LIVES HERE: skip if bucket has <N obs
        |
        +---> [ml_analyzer.py: MLPatternAnalyzer]
                - record_event()
                - check_anomaly() → MLAnomalyResult | None
                  * THRESHOLD LIVES HERE: contamination / score threshold
                - check_cross_sensor_anomalies() → List[MLAnomalyResult]
                  * GATE LIVES HERE: min co_occurrence_count, correlation_strength

[coordinator.py: _async_update_data()]
  - Calls both analyzers
  - CONFIDENCE SCORING LIVES HERE: combine/weight results before notify gate
  - DEDUPLICATION LIVES HERE: suppress repeat anomalies within cooldown window
  - NOTIFICATION GATE LIVES HERE: learning complete? snoozed? holiday?
        |
        v
[coordinator.py: _send_notification() / _send_ml_notification() / _send_welfare_notification()]
  - SEVERITY FILTER LIVES HERE: minimum severity to fire notification
  - COOLDOWN LIVES HERE: _last_notification_time guard
```

---

## Component Boundaries

| Component | Owns | Does NOT Own |
|-----------|------|--------------|
| `analyzer.py` | Z-score computation, per-bucket thresholds, severity labels, observation count guards | When to notify, deduplication, cross-run cooldown |
| `ml_analyzer.py` | ML score computation, contamination threshold, cross-sensor pattern gates | When to notify, coordinator-level deduplication |
| `coordinator.py` | Combining results from both analyzers, deduplication, cooldown, notification dispatch, severity filtering | How scores are computed |
| `const.py` | Numeric constants for all thresholds and defaults | Logic |

This boundary means: **the analyzers can be tested in isolation with deterministic threshold inputs, and coordinator-level suppression can be tested by injecting pre-built anomaly lists**.

---

## Where Each False-Positive Reduction Change Lives

### 1. Statistical Analyzer — Z-score threshold floor (`analyzer.py`)

Current `SENSITIVITY_THRESHOLDS`:
- LOW: 3.0σ, MEDIUM: 2.0σ, HIGH: 1.0σ

The MEDIUM setting of 2.0σ flags roughly 5% of normally-distributed observations as anomalous. For a system seeing 96 intervals/day × N entities, this generates substantial noise.

**Recommendation:** Raise MEDIUM to 2.5σ (flags ~1.2%) and LOW to 3.5σ. HIGH stays 1.0σ for users who explicitly want sensitivity. Change location: `const.py` `SENSITIVITY_THRESHOLDS`.

### 2. Statistical Analyzer — Minimum observation count guard (`analyzer.py`)

Current code in `check_for_anomalies()` skips a bucket only when `expected_std == 0 and expected_mean == 0`. A bucket with count=1 has std_dev=0 and mean=1 and will trigger infinite Z-score on any non-1 observation.

**Recommendation:** Add a `MIN_BUCKET_OBSERVATIONS` constant (suggest: 4) and skip the bucket if `bucket.count < MIN_BUCKET_OBSERVATIONS`. This is particularly important for infrequently-used entities in sparse time slots.

Change location: `analyzer.py` `check_for_anomalies()` and `const.py` for the constant.

### 3. Statistical Analyzer — Minimum mean activity guard (`analyzer.py`)

Buckets with very low mean (e.g., mean=0.1) will generate high Z-scores from a single event. A `MIN_MEAN_ACTIVITY_THRESHOLD` (suggest: 0.3 events/interval) guards against anomalies on entities that almost never activate in a given slot.

Change location: `analyzer.py` `check_for_anomalies()` and `const.py` for the constant.

### 4. ML Analyzer — Contamination values (`const.py`)

Current `ML_CONTAMINATION`: LOW=0.01, MEDIUM=0.05, HIGH=0.10. A 5% contamination threshold means the model will flag 5% of all events in steady state.

**Recommendation:** Tighten to LOW=0.005, MEDIUM=0.02, HIGH=0.05. Change location: `const.py` `ML_CONTAMINATION`.

### 5. ML Analyzer — Cross-sensor pattern gates (`ml_analyzer.py`)

Current gate in `check_cross_sensor_anomalies()`: `correlation_strength > 0.5 and co_occurrence_count >= 10`. The `avg_time_delta_seconds * 2` expected window is also very narrow for entities that loosely correlate.

**Recommendation:** Raise the minimum co-occurrence count from 10 to 20, and raise the correlation strength gate from 0.5 to 0.6. Change location: `ml_analyzer.py` `check_cross_sensor_anomalies()`, or extract these to `const.py` constants for testability.

### 6. Coordinator — Notification cooldown (`coordinator.py`)

Current behaviour: `_last_notification_time` is tracked per-type ("statistical", "ml", "welfare") but there is **no per-type cooldown guard in `_async_update_data()`**. Every 60-second update cycle that detects anomalies sends a new notification, even if an identical one was sent one minute ago.

**Recommendation:** Add a per-type cooldown check before `_send_notification()` calls. The cooldown period should be configurable in `const.py` (suggest `NOTIFICATION_COOLDOWN_SECONDS = 1800` — 30 minutes for statistical and ML, shorter for welfare state changes).

Change location: `coordinator.py` `_async_update_data()`, new constant in `const.py`.

### 7. Coordinator — Cross-cycle anomaly deduplication (`coordinator.py`)

Current `_recent_anomalies` is replaced (not appended) each cycle: `self._recent_anomalies = stat_anomalies`. There is no mechanism to detect that the same entity triggered the same anomaly type in the previous N cycles.

**Recommendation:** Add a deduplication set that tracks `(entity_id, anomaly_type, time_slot)` tuples seen in the last M cycles. Only pass anomalies to `_send_notification()` if they are new. Flush the dedup set after the cooldown period. Change location: `coordinator.py`.

### 8. Coordinator — Severity filter before notification (`coordinator.py`)

Current behaviour: any anomaly returned by `check_for_anomalies()` (including severity="minor") triggers a notification. Minor severity corresponds to Z-scores between 1.5σ and 2.5σ — well within normal daily fluctuation.

**Recommendation:** Add a `MIN_NOTIFICATION_SEVERITY` constant (suggest: "moderate") and filter `stat_anomalies` to only notify on anomalies at or above that severity. Expose this as an option in the config flow later if needed. Change location: `coordinator.py` `_async_update_data()`, constant in `const.py`.

### 9. Welfare status — Hysteresis (`coordinator.py`)

Current welfare notification fires whenever `current_welfare != self._last_welfare_status`. This means oscillation between "ok" and "check_recommended" (e.g., caused by a single quiet 15-minute slot) generates a notification on every transition.

**Recommendation:** Add a welfare status debounce: only send a welfare notification if the new status has persisted for N consecutive update cycles (suggest N=3, configurable via `WELFARE_STATUS_DEBOUNCE_CYCLES` in `const.py`). Implement by tracking `_welfare_status_candidate` and `_welfare_status_candidate_count` on the coordinator.

Change location: `coordinator.py` `_async_update_data()`.

---

## Data Flow: False-Positive Reduction Decision Points

```
60-second tick
    |
    v
check_for_anomalies()
    |
    +--> [GATE 1] bucket.count < MIN_BUCKET_OBSERVATIONS → skip  [analyzer.py]
    +--> [GATE 2] expected_mean < MIN_MEAN_ACTIVITY_THRESHOLD → skip  [analyzer.py]
    +--> [GATE 3] z_score <= sensitivity_threshold → skip  [analyzer.py]
    |
    v
AnomalyResult list (with severity labels)
    |
    v
[GATE 4] filter to severity >= MIN_NOTIFICATION_SEVERITY  [coordinator.py]
    |
    v
[GATE 5] dedup: (entity_id, anomaly_type, time_slot) seen recently? → skip  [coordinator.py]
    |
    v
[GATE 6] last_notification_time + cooldown > now? → skip  [coordinator.py]
    |
    v
_send_notification()
```

```
60-second tick
    |
    v
check_anomaly() for recent events
    |
    +--> [GATE A] score <= (1 - contamination) → skip  [ml_analyzer.py]
    |
    v
check_cross_sensor_anomalies()
    |
    +--> [GATE B] co_occurrence_count < 20 → skip  [ml_analyzer.py]
    +--> [GATE C] correlation_strength <= 0.6 → skip  [ml_analyzer.py]
    |
    v
MLAnomalyResult list
    |
    v
[GATE D] cooldown: last ML notification + cooldown > now? → skip  [coordinator.py]
    |
    v
_send_ml_notification()
```

```
60-second tick
    |
    v
get_welfare_status()
    |
    v
[GATE E] welfare_status == last_welfare_status? → skip  [coordinator.py — existing]
    |
    v
[GATE F] new status persisted for < N cycles? → increment candidate count, skip  [coordinator.py — new]
    |
    v
_send_welfare_notification()
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Threshold logic in the coordinator

**What:** Moving Z-score comparison or anomaly scoring into `_async_update_data()` instead of keeping it in the analyzers.

**Why bad:** The analyzers are tested independently and expose clean `check_for_anomalies()` / `check_anomaly()` APIs. Duplicating or moving threshold logic into the coordinator breaks that testability.

**Instead:** The coordinator receives a `List[AnomalyResult]` and applies only coordinator-level concerns (dedup, cooldown, severity filter).

### Anti-Pattern 2: Per-entity notification filtering in the coordinator

**What:** Tracking per-entity cooldowns (e.g., "don't notify about light.kitchen again for 2 hours") in the coordinator.

**Why bad:** Per-entity state is complex to persist and test. The dedup mechanism (Gate 5) already handles the "same entity, same slot, same type" case.

**Instead:** Use the global per-notification-type cooldown as the primary suppression mechanism. Per-entity tuning is explicitly out of scope for this milestone.

### Anti-Pattern 3: Changing the `_async_update_data()` return shape

**What:** Adding new keys to the data dict, or changing types of existing keys, in order to expose new debug information.

**Why bad:** Sensor entities bind to specific keys in the data dict via `value_fn` in `sensor.py`. Changing existing keys will silently break sensors. Adding new keys is safe only if sensors are updated consistently.

**Instead:** If new diagnostic data is needed (e.g., "notifications suppressed by cooldown"), add it as a new key with a corresponding sensor entity or as an attribute on an existing sensor. Do not remove or rename existing keys.

### Anti-Pattern 4: Raising the statistical learning period to reduce false positives

**What:** Increasing `DEFAULT_LEARNING_PERIOD` from 7 to 21+ days to ensure more data before detection starts.

**Why bad:** The learning period gate already prevents notifications during learning. The false positives are occurring after learning completes. More learning time does not fix structural issues with minimum observation guards or threshold values.

**Instead:** Apply observation count guards (Gate 1, Gate 2) so sparse-data buckets are silenced regardless of learning period completion.

---

## Implementation Order

The changes have clear dependencies and should be built in this sequence:

### Phase 1: Threshold and guard changes (purely additive, lowest risk)

1. `const.py` — Raise `SENSITIVITY_THRESHOLDS` MEDIUM and LOW values
2. `const.py` — Raise `ML_CONTAMINATION` MEDIUM and LOW values
3. `const.py` — Add `MIN_BUCKET_OBSERVATIONS`, `MIN_MEAN_ACTIVITY_THRESHOLD`, `MIN_CROSS_SENSOR_OCCURRENCES`, `MIN_CROSS_SENSOR_STRENGTH`
4. `analyzer.py` — Add observation count and mean guards to `check_for_anomalies()`
5. `ml_analyzer.py` — Raise cross-sensor gates to use new constants

**Tests:** All five changes are exercised through existing `check_for_anomalies()` and `check_cross_sensor_anomalies()` test paths. Tests need to be updated to verify the new guard conditions.

### Phase 2: Coordinator suppression logic (new state, higher risk)

6. `const.py` — Add `NOTIFICATION_COOLDOWN_SECONDS`, `MIN_NOTIFICATION_SEVERITY`, `WELFARE_STATUS_DEBOUNCE_CYCLES`
7. `coordinator.py` — Add per-type cooldown guard in `_async_update_data()` before each `_send_*` call
8. `coordinator.py` — Add severity filter gate before `_send_notification()` for statistical anomalies
9. `coordinator.py` — Add anomaly dedup set and cycle tracking
10. `coordinator.py` — Add welfare status debounce (`_welfare_status_candidate`, `_welfare_status_candidate_count`)

**Tests:** These require coordinator-level tests that inject anomaly lists and verify notification suppression. The coordinator tests in `test_coordinator.py` will need new scenarios for each gate.

**Reason for this order:** Phase 1 changes reduce the raw volume of anomalies produced by the analyzers. Phase 2 changes suppress notifications for anomalies that slip through. Doing Phase 2 first would mask Phase 1 issues and make it harder to verify that the threshold changes are actually working.

---

## Scalability Considerations

This integration runs on a single Home Assistant instance with typically 1–20 monitored entities. Scale is not a concern. The primary non-functional concern is **latency**: all processing runs on the HA event loop and must be fast enough not to block it.

| Concern | Current approach | Risk |
|---------|-----------------|------|
| Anomaly check latency | Synchronous loop over N entities × bucket lookup | Low — O(N) with small N |
| Dedup set memory | Tracking (entity, type, slot) tuples per cycle | Negligible — bounded by entity count |
| Cooldown state persistence | Stored in coordinator, persisted to JSON | None — already done for `_last_notification_time` |
| Welfare debounce state | 2 new fields on coordinator | None — small, add to `_save_data()` / `async_setup()` |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Component boundaries | HIGH | Directly read from source; boundaries are clear and stable |
| Where thresholds live | HIGH | `const.py` + respective analyzer; confirmed by code |
| Where notification logic lives | HIGH | `_async_update_data()` in coordinator; confirmed by code |
| Dedup/cooldown gap | HIGH | Confirmed absence of cooldown guard in current code |
| Recommended threshold values | MEDIUM | Values are evidence-based (statistical theory) but need live calibration against real data |
| Welfare debounce approach | MEDIUM | Standard technique; specific cycle count needs empirical validation |

---

## Sources

- Direct analysis of `coordinator.py`, `analyzer.py`, `ml_analyzer.py`, `const.py` (2026-03-13)
- `.planning/PROJECT.md` and `.planning/codebase/ARCHITECTURE.md`
- Standard anomaly detection literature: Z-score threshold trade-offs, notification deduplication patterns
