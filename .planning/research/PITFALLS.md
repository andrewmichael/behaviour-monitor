# Domain Pitfalls: Anomaly Detection False Positive Reduction

**Domain:** Home Assistant behavior monitoring / anomaly detection tuning
**Researched:** 2026-03-13
**Sources:** Codebase analysis (analyzer.py, coordinator.py, const.py, ml_analyzer.py) + commit history (v2.8.6–v2.8.8)

---

## Critical Pitfalls

Mistakes that cause rewrites, break user trust, or create welfare safety regressions.

---

### Pitfall 1: Scatter-shot Threshold Bumping Without Root Cause Analysis

**What goes wrong:** Each false positive wave gets met with another round of threshold increases across multiple detection layers simultaneously — z-score thresholds up, routine progress thresholds down, welfare status multipliers loosened, minimum sensor counts raised. The system gets quieter but no one knows *which* change did the work or whether the false positives were statistical, ML, or welfare-driven.

**Why it happens:** Alerts are noisy, the user wants relief fast, so thresholds get bumped wholesale. The commit history shows this pattern explicitly: v2.8.6 loosened time-based thresholds, v2.8.7 + v2.8.8 loosened entity z-score thresholds, routine progress bands, and multi-sensor attention counts — all in quick succession without isolating which layer was responsible.

**Evidence in codebase:** The inline comments in `analyzer.py` preserve a paper trail of successive increases:
- `# was 1.5 — tolerates up to 2x the typical interval`
- `# was 2.5 — wider window before recommending a check`
- `# was 1.5 — more tolerant of minor deviations`
- `# was 70 — more tolerant of routine variance`

Five separate threshold values across three methods have already been bumped. The z-score sensitivity (`SENSITIVITY_LOW = 3.0σ`) is already at maximum coarseness in the existing config.

**Consequences:** You lose the ability to trace alert causation. Future tuning becomes guesswork. You can drift into over-suppression without noticing because no individual change crossed a visible line.

**Prevention:** Before changing any threshold, instrument which detection path (statistical z-score, welfare time-based, welfare routine progress, ML, cross-sensor) produced the most recent batch of false positives. Add per-source counters or log aggregation. Only tune the layer that is causing the problem.

**Detection (warning signs):**
- Multiple threshold changes in the same release without a single root cause named
- "False positives" in the bug report with no mention of which sensor entity or detection path triggered it
- Inline comments accumulating "was X — now Y" annotations across many methods

**Phase mapping:** Address in the diagnosis/instrumentation phase *before* any threshold changes.

---

### Pitfall 2: Suppressing Notifications Without Suppressing Detection

**What goes wrong:** The coordinator tracks `_last_notification_time` and `_last_notification_type` but there is no minimum cooldown window between re-firing the same alert type. Every 60-second `_async_update_data()` call re-evaluates and potentially re-sends if anomalies persist. The `persistent_notification.create` call with a fixed `notification_id` will overwrite the existing notification silently — which looks like deduplication but is actually silent re-fire to mobile devices.

**Why it happens:** The `notification_id` approach deduplicates HA UI notifications but the mobile push path (`_send_mobile_notification`) fires on every detection cycle with no cooldown check. A sustained anomaly (e.g., an entity that is consistently inactive for 2 hours) will generate a mobile push every 60 seconds for the duration.

**Evidence in codebase:** `coordinator.py` lines 560–565: `if stat_learning_complete and stat_anomalies: await self._send_notification(stat_anomalies)` — there is no `if time_since_last_notification > MIN_INTERVAL` guard. `_last_notification_time` is recorded but never read back to gate re-firing.

**Consequences:** The user receives repeated mobile pushes for the same ongoing anomaly. This is the core "flood of false positive notifications" complaint even when detection accuracy itself is acceptable.

**Prevention:** Add a per-type notification cooldown (e.g., 30–60 minutes) before re-sending a notification of the same type. Read `_last_notification_time` and `_last_notification_type` in `_async_update_data()` to gate sends. Distinguish "same anomaly still active" from "new anomaly detected."

**Detection (warning signs):**
- User reports "flood of notifications" for a single event
- `_last_notification_time` is populated in storage but the notification fires again within the next update cycle

**Phase mapping:** Address in the coordinator notification logic phase; this is independent of threshold tuning.

---

### Pitfall 3: Welfare Notifications Fire on Every Status Transition Including Recoveries

**What goes wrong:** The welfare notification logic sends a notification whenever `current_welfare != self._last_welfare_status`. This catches both degradations (ok → concern) and improvements (concern → ok). Recovering back to "ok" fires a notification, then a brief re-check fires "concern" again, producing oscillation.

**Why it happens:** The welfare status is computed from rolling averages and time-since-activity. Near a threshold boundary, small fluctuations in activity timing can cause rapid ok → concern → ok → concern oscillation, each transition triggering a notification.

**Evidence in codebase:** `coordinator.py` lines 571–573: `if current_welfare != self._last_welfare_status: await self._send_welfare_notification(welfare_status)`. No hysteresis, no minimum dwell time. The welfare function itself (`analyzer.py` `get_welfare_status`) uses strict inequalities with no smoothing.

**Consequences:** Repeated welfare alerts for the same marginal borderline case. The user stops trusting welfare alerts entirely, which defeats the core elder care purpose.

**Prevention:** Implement hysteresis: require a status to persist for at least N consecutive update cycles (e.g., 3 × 60s = 3 minutes) before treating it as a confirmed transition. Only notify on confirmed degradations, not on recoveries or oscillations.

**Detection (warning signs):**
- `welfare_concern` and `welfare_ok` notifications in close temporal succession in logs
- `_last_welfare_status` toggling between two values across consecutive saves

**Phase mapping:** Address in welfare notification logic phase alongside cooldown implementation.

---

### Pitfall 4: Zero-Variance Buckets Producing Spurious Infinite Z-Scores

**What goes wrong:** When a time bucket has observations but all observations have the same value (e.g., a sensor that always fires exactly once at 08:15 on Monday), `std_dev` is 0. The analyzer handles `expected_std == 0` with a special case: if actual differs from expected, it assigns `z_score = float("inf")` or `z_score = sensitivity_threshold + 1`, both of which unconditionally trigger an anomaly.

**Why it happens:** The Welford accumulator in `TimeBucket` correctly computes zero variance when all observations are identical. This is statistically accurate but practically wrong for behavior monitoring: a sensor that fires predictably at the same rate is the *most* routine entity, not the most anomalous one.

**Evidence in codebase:** `analyzer.py` lines 444–449:
```python
elif actual != expected_mean:
    # No variance but value differs from expected
    z_score = float("inf") if actual > 0 else self._sensitivity_threshold + 1
```
Any departure from a perfectly consistent entity will produce an infinite z-score and always pass the `z_score > self._sensitivity_threshold` check regardless of how the threshold is configured.

**Consequences:** Highly regular entities (which should be considered the most "normal") become the most likely to generate alerts. Raising the global threshold doesn't fix this because infinity exceeds any finite threshold.

**Prevention:** Apply a minimum std_dev floor (e.g., 0.5 or 1.0 events) when `count >= MIN_OBSERVATIONS` to prevent zero-variance buckets from producing unbounded z-scores. Alternatively, treat zero-variance highly-consistent entities as immune to "unusual inactivity" detection during the first N weeks of operation.

**Detection (warning signs):**
- Alerts consistently come from the same entities, especially those that fire on a very regular schedule
- `z_score: null` or `z_score: Infinity` in anomaly sensor attributes
- Alert description says "expected ~1.0 state changes, got 0" for a rarely-varying sensor

**Phase mapping:** Address in statistical analyzer phase; requires a targeted fix and corresponding test.

---

### Pitfall 5: ML Anomaly Scores Not Normalized Relative to Statistical Alerts

**What goes wrong:** The dual-path architecture fires statistical notifications and ML notifications independently. An event that triggers both paths sends two separate mobile pushes (one from `_send_notification`, one from `_send_ml_notification`) within the same 60-second cycle. The user receives two alerts for one event.

**Why it happens:** There is no cross-path deduplication or correlation. The coordinator checks `stat_anomalies` and `ml_anomalies` independently and sends if either is non-empty, with no "is this the same underlying event?" check.

**Evidence in codebase:** `coordinator.py` lines 560–565: stat notification and ML notification are sent in sequence with no check whether they refer to the same entity at the same time.

**Consequences:** The notification flood is doubled for events that trigger both paths. The user cannot distinguish "two separate problems" from "one problem detected twice."

**Prevention:** Before sending ML notifications, check whether the same entity is already covered by a recent statistical notification. Alternatively, combine both paths into a single notification when they fire within the same update cycle, labelling the detection source.

**Detection (warning signs):**
- Two notifications arrive within seconds of each other naming the same entity
- `last_notification_type` alternates between `"statistical"` and `"ml"` for the same entity within a short window

**Phase mapping:** Address in coordinator notification consolidation phase.

---

## Moderate Pitfalls

---

### Pitfall 6: Learning Period Completing on Atypical Data

**What goes wrong:** The 7-day default learning period is measured from first observation, not from a representative sample. If the integration is installed during a holiday, a housesitter visit, or an unusually active/inactive week, the baseline patterns encode atypical behavior as "normal." Post-learning period alerts will be calibrated against this skewed baseline forever (unless patterns are reset).

**Why it happens:** `PatternAnalyzer.is_learning_complete()` returns True when `days_elapsed >= learning_period_days` regardless of observation quality or representativeness.

**Evidence in codebase:** `analyzer.py` `get_confidence()` calculates confidence as `days_elapsed / learning_period_days * 100`. No quality signal (e.g., minimum observations per bucket) gates the transition from learning to detection.

**Prevention:** Consider requiring a minimum total observation count in addition to elapsed days before marking learning complete. Document for the user that the learning period should represent a typical week.

**Detection (warning signs):**
- Immediately high false positive rate after learning period completes
- `total_observations` very low despite learning period being marked complete

**Phase mapping:** Relevant to any documentation or configuration guidance work; may also inform a minimum observation threshold gating change.

---

### Pitfall 7: Attribute Tracking Inflating Activity Counts

**What goes wrong:** `CONF_TRACK_ATTRIBUTES = True` by default. Many Home Assistant entities emit frequent attribute changes (e.g., sensor brightness level adjustments, climate setpoint changes, media player volume) without a meaningful state change. Each attribute change increments the same bucket counter used for z-score computation, inflating the expected activity baseline and compressing the z-score sensitivity.

**Why it happens:** The option exists to support entities where meaningful activity shows up in attributes rather than state. But enabling it globally causes high-frequency entities to dominate the bucket statistics.

**Evidence in codebase:** `coordinator.py` `_handle_state_changed()` lines 435–455: attribute tracking is an all-or-nothing toggle applied to all monitored entities uniformly.

**Prevention:** Verify whether `CONF_TRACK_ATTRIBUTES` is enabled. If entities like `media_player.*` or `climate.*` are monitored, attribute tracking likely inflates counts. Consider defaulting to False or adding per-entity attribute tracking control.

**Detection (warning signs):**
- `daily_count` sensor values are unexpectedly high (hundreds per day for entities that rarely change state)
- Buckets with very high means and near-zero std_dev

**Phase mapping:** Relevant to configuration audit phase early in the milestone.

---

### Pitfall 8: Changing Sensitivity Config Without Resetting Learned Patterns

**What goes wrong:** `PatternAnalyzer.from_dict()` accepts a `sensitivity_threshold` parameter that overrides the stored value. However, the *learned patterns themselves* (bucket statistics) are anchored to historical data collected under the previous threshold. Raising the threshold from `MEDIUM (2.0σ)` to `LOW (3.0σ)` makes the detection less sensitive, but the patterns remain unchanged. If the patterns are already sparse or skewed, even a higher threshold may not solve the problem.

**Why it happens:** Threshold and learned data are separate concerns. Changing config reloads the coordinator with new thresholds but reuses existing pattern data transparently.

**Prevention:** When changing sensitivity, evaluate whether existing pattern data is sufficient quality. After a significant threshold change, monitor whether the alert rate drops appropriately — if it does not, the problem may be in pattern data quality rather than threshold value.

**Detection (warning signs):**
- Alert rate unchanged after a sensitivity downgrade
- Pattern data shows very sparse buckets (most buckets count = 0 or 1)

**Phase mapping:** Relevant to any phase involving `CONF_SENSITIVITY` changes.

---

### Pitfall 9: Breaking Automation-Dependent Sensor States

**What goes wrong:** The 14 exposed sensor entities have stable entity_ids that users may reference in automations (e.g., trigger on `sensor.behaviour_monitor_anomaly_detected` becoming `True`). If threshold changes cause the `anomaly_detected` sensor to become perpetually `True` or perpetually `False`, existing automations silently break.

**Why it happens:** The `anomaly_detected` sensor reflects `all_anomalies_detected` which is `True` if either `stat_anomalies` or `ml_anomalies` is non-empty at the last update cycle. Over-suppression means this sensor stays `False` even during genuine anomalies; under-suppression means it stays `True` and automation triggers become meaningless.

**Evidence in codebase:** `coordinator.py` line 541: `all_anomalies_detected = len(stat_anomalies) > 0 or len(ml_anomalies) > 0`. This is set each 60-second cycle and directly exposed via `sensor.py`.

**Prevention:** After any threshold change, verify the `anomaly_detected` sensor behavior over 24–48 hours. Add a test that confirms the sensor value is `False` under normal conditions when using synthetic pattern data calibrated to "typical" behavior.

**Detection (warning signs):**
- `anomaly_detected` sensor stuck in one state
- Automations that previously triggered on anomalies stop firing after a tuning change

**Phase mapping:** Must be verified after every threshold change as an acceptance criterion.

---

## Minor Pitfalls

---

### Pitfall 10: ML Contamination Parameter Mismatch

**What goes wrong:** `ML_CONTAMINATION` sets the Half-Space Tree's expected anomaly rate. At `SENSITIVITY_MEDIUM`, contamination is 5% — meaning the model expects 5% of events to be anomalous. If the actual anomaly rate in real data is much lower (e.g., 0.1%), the contamination setting causes the model to classify too many normal events as anomalies.

**Prevention:** When reducing false positives from the ML path, reduce `ML_CONTAMINATION[SENSITIVITY_LOW]` from 1% toward 0.1–0.5%, not just the z-score threshold.

**Detection (warning signs):**
- ML-only false positives that do not correspond to statistical anomalies
- High `anomaly_score` values in ML results for entities during clearly normal periods

**Phase mapping:** Address in ML analyzer tuning phase.

---

### Pitfall 11: Cross-Sensor Window Causing Spurious Correlation

**What goes wrong:** `DEFAULT_CROSS_SENSOR_WINDOW = 300` seconds means any two entities that both change state within 5 minutes are considered potentially correlated. In a busy home with many sensors, a 5-minute window can produce spurious correlations between unrelated entities (e.g., a temperature sensor and a door sensor both happen to fire within the same 5-minute window frequently).

**Prevention:** Validate that `cross_sensor_patterns` in sensor attributes reflect genuine behavioral correlations (e.g., "door sensor fires before motion sensor") rather than statistical coincidence. Reduce the window to 60–120 seconds for tighter correlation detection.

**Detection (warning signs):**
- Many cross-sensor patterns with unrelated entity pairs showing high correlation strength
- Cross-sensor anomalies firing for entity pairs that have no logical behavioral relationship

**Phase mapping:** Address in cross-sensor correlation tuning if ML is in scope.

---

### Pitfall 12: Test Coverage Gaps After Threshold Changes

**What goes wrong:** Tests currently assert specific behaviors at specific thresholds. After changing constants in `const.py` (e.g., `SEVERITY_THRESHOLDS`, `SENSITIVITY_THRESHOLDS`), tests that use hardcoded z-score values may silently pass while no longer covering the intended boundary.

**Prevention:** For every threshold value changed, verify that at least one test exercises the exact boundary. Prefer parameterized tests that derive expected results from the constants rather than hardcoding numeric values.

**Detection (warning signs):**
- Tests pass after a constant change but the live behavior differs from test expectations
- Tests reference literal z-score values (e.g., `assert result.z_score > 2.0`) rather than `SENSITIVITY_THRESHOLDS["medium"]`

**Phase mapping:** Enforce as part of every implementation phase's acceptance criteria.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| Statistical threshold tuning | Pitfall 1 (scatter-shot), Pitfall 4 (zero-variance) | Diagnose by source first; add std_dev floor |
| Coordinator notification logic | Pitfall 2 (no cooldown), Pitfall 5 (dual-path duplicate) | Add per-type cooldown; consolidate multi-path notifications |
| Welfare status tuning | Pitfall 3 (oscillation), Pitfall 1 (scatter-shot) | Add hysteresis; tune welfare independently from z-score |
| ML analyzer tuning | Pitfall 5 (dual-path), Pitfall 10 (contamination), Pitfall 11 (cross-sensor) | Reduce contamination; verify cross-sensor window |
| Any threshold change | Pitfall 9 (automation regression) | Verify anomaly_detected sensor behavior post-change |
| Initial config audit | Pitfall 7 (attribute tracking), Pitfall 8 (patterns vs threshold mismatch) | Review track_attributes; assess pattern data quality |
| Learning period / baseline | Pitfall 6 (atypical baseline) | Document representative learning requirement |
| Test maintenance | Pitfall 12 (test gaps) | Tie test assertions to constants, not literals |

---

## Sources

- `custom_components/behaviour_monitor/analyzer.py` — inline threshold comments preserving change history (HIGH confidence)
- `custom_components/behaviour_monitor/coordinator.py` — notification send logic, absence of cooldown guards (HIGH confidence)
- `custom_components/behaviour_monitor/const.py` — `SENSITIVITY_THRESHOLDS`, `ML_CONTAMINATION`, `DEFAULT_CROSS_SENSOR_WINDOW` (HIGH confidence)
- Git commits v2.8.6–v2.8.8 — documented threshold progression and motivations (HIGH confidence)
- Domain knowledge: z-score anomaly detection, Half-Space Trees, HA integration patterns (MEDIUM confidence — training data, not externally verified)
