# Technology Stack — False Positive Reduction

**Project:** Behaviour Monitor — False Positive Reduction Milestone
**Researched:** 2026-03-13
**Scope:** Techniques and approaches to reduce false positives in the existing dual-analyzer anomaly detection system. No new dependencies required; all recommendations work within the current Python-only, no-external-library-required stack.

---

## Research Method Note

External web search and WebFetch were unavailable for this session. Findings are based on:
1. Deep reading of all four codebase files (`analyzer.py`, `ml_analyzer.py`, `coordinator.py`, `const.py`)
2. Training knowledge on z-score statistics, streaming ML anomaly detection, and notification deduplication patterns
3. Evidence from the code itself — comment annotations in `analyzer.py` show thresholds were already loosened in v2.8.7/v2.8.8 and the specific values reveal where the system is still over-triggering

All recommendations are directly traceable to specific lines in the codebase.

---

## Current Thresholds Inventory

Before recommending changes, the live threshold values (as of the codebase read):

### Statistical Analyzer (`analyzer.py` + `const.py`)

| Threshold | Current Value | Location |
|-----------|--------------|----------|
| Z-score sensitivity — Low | 3.0σ | `const.py:SENSITIVITY_THRESHOLDS` |
| Z-score sensitivity — Medium | 2.0σ | `const.py:SENSITIVITY_THRESHOLDS` |
| Z-score sensitivity — High | 1.0σ | `const.py:SENSITIVITY_THRESHOLDS` |
| Severity: minor | ≥1.5σ | `const.py:SEVERITY_THRESHOLDS` |
| Severity: moderate | ≥2.5σ | `const.py:SEVERITY_THRESHOLDS` |
| Severity: significant | ≥3.5σ | `const.py:SEVERITY_THRESHOLDS` |
| Severity: critical | ≥4.5σ | `const.py:SEVERITY_THRESHOLDS` |
| Entity status: normal→attention | 2.5σ | `analyzer.py:667` (was 1.5) |
| Entity status: attention→concern | 3.5σ | `analyzer.py:668` (was 2.5) |
| Entity status: concern→alert | 4.5σ | `analyzer.py:669` (was 3.5) |
| Welfare: check_recommended trigger | concern_level ≥ 2.0 | `analyzer.py:553` (was 1.5) |
| Welfare: concern trigger | concern_level ≥ 3.5 | `analyzer.py:555` (was 2.5) |
| Welfare: alert trigger | concern_level ≥ 6.0 | `analyzer.py:557` (was 4.0) |
| Routine: on_track threshold | ≥50% | `analyzer.py:618` (was 70%) |
| Routine: below_normal threshold | ≥25% | `analyzer.py:619` (was 40%) |
| Welfare: attention_count trigger | >2 sensors | `analyzer.py:714` (was >1) |

### ML Analyzer (`ml_analyzer.py` + `const.py`)

| Parameter | Current Value | Location |
|-----------|--------------|----------|
| Contamination — Low sensitivity | 0.01 (1%) | `const.py:ML_CONTAMINATION` |
| Contamination — Medium sensitivity | 0.05 (5%) | `const.py:ML_CONTAMINATION` |
| Contamination — High sensitivity | 0.10 (10%) | `const.py:ML_CONTAMINATION` |
| Score threshold | `1.0 - contamination` | `ml_analyzer.py:473` |
| Cross-sensor correlation min strength | 0.5 | `ml_analyzer.py:503` |
| Cross-sensor min co-occurrence | 10 | `ml_analyzer.py:504` |
| Cross-sensor expected window multiplier | 2× avg_time_delta | `ml_analyzer.py:525` |
| Min samples before ML active | 100 | `const.py:MIN_SAMPLES_FOR_ML` |
| HST window_size | 256 | `ml_analyzer.py:163` |
| HST n_trees | 10 | `ml_analyzer.py:133` |
| HST height | 8 | `ml_analyzer.py:133` |

### Coordinator Notification Logic (`coordinator.py`)

| Behaviour | Current State | Location |
|-----------|--------------|----------|
| Notification cooldown | **None** — fires every 60s if anomaly present | `coordinator.py:560-565` |
| Welfare notification dedup | Status-change only | `coordinator.py:571-573` |
| Stat anomaly dedup | **None** — fires every update cycle | `coordinator.py:560-561` |
| ML anomaly dedup | **None** — fires every update cycle | `coordinator.py:564-565` |
| Min severity to notify | **None** — any z > threshold notifies | `coordinator.py:560-561` |

---

## Critical Finding: The Coordinator Has No Notification Cooldown

**This is the single highest-impact false positive source.** The `_async_update_data()` method runs every 60 seconds. Every time it runs and `stat_anomalies` is non-empty, it calls `_send_notification()`. There is no check like "did we already send this notification recently?" for statistical or ML anomalies. `_last_notification_time` is tracked but never consulted before firing.

The welfare notification does check `current_welfare != self._last_welfare_status` — but anomaly notifications have no equivalent guard. An anomaly that persists for 30 minutes fires 30 notifications, one per minute.

---

## Recommended Stack for False Positive Reduction

No new libraries are needed. All techniques operate on pure Python and the existing River dependency.

### Technique 1: Notification Cooldown in Coordinator

**What:** Add a minimum cooldown between notifications of the same type. Check `_last_notification_time` before calling `_send_notification()` and `_send_ml_notification()`.

**Why this works:** The most common false positive scenario is a single genuine anomaly (or spurious one) that fires repeatedly at 60-second intervals. A 15–30 minute cooldown per notification type eliminates the flood without suppressing genuine novel anomalies.

**Where:** `coordinator.py::_async_update_data()` lines 560–565

**Implementation shape:**
```python
NOTIFICATION_COOLDOWN_SECONDS = 1800  # 30 minutes

def _can_notify(self, notification_type: str) -> bool:
    if self._last_notification_time is None:
        return True
    if self._last_notification_type != notification_type:
        return True  # different type — always allow
    elapsed = (dt_util.now() - self._last_notification_time).total_seconds()
    return elapsed >= NOTIFICATION_COOLDOWN_SECONDS
```

**Confidence:** HIGH — this is a direct observation from reading the code. The mechanism to track last notification time already exists; it is simply not consulted.

---

### Technique 2: Minimum Observation Count Gate in PatternAnalyzer

**What:** In `check_for_anomalies()`, skip a bucket if `bucket.count < N` even after the learning period is complete. Currently the code skips buckets where `expected_std == 0 AND expected_mean == 0` — but it does not skip sparse buckets where mean and std_dev are computed from very few data points.

**Why this works:** A TimeBucket with `count=2` will have a wildly unstable std_dev. If those 2 observations both happened to be `1`, the std_dev will be 0 — and any future 15-minute interval with 0 events will trigger the "no variance but value differs" branch at `analyzer.py:447-448`, which hard-codes an infinite z-score. A minimum `count >= 4` (meaning the pattern has been observed at least 4 Mondays at 09:00) prevents these sparse-bucket false positives.

**Where:** `analyzer.py::check_for_anomalies()` after line 441

**Implementation shape:**
```python
day_of_week = now.weekday()
interval = _get_interval_index(now)
bucket = pattern.day_buckets[day_of_week][interval]
if bucket.count < MIN_BUCKET_OBSERVATIONS:
    continue
```

Recommended constant: `MIN_BUCKET_OBSERVATIONS = 4` (4 weeks of observation for a given slot).

**Confidence:** HIGH — the sparse bucket problem is clearly visible in the code. The `float("inf")` z-score at line 448 is the smoking gun: it fires for any bucket that was never zero-activity but the current interval happens to be zero.

---

### Technique 3: Raise Default Sensitivity Level

**What:** Change `DEFAULT_SENSITIVITY` from `SENSITIVITY_MEDIUM` (2.0σ) to `SENSITIVITY_LOW` (3.0σ).

**Why this works:** For a home activity monitor, 2.0σ means ~5% of all observations will be flagged as anomalous under a normal distribution. In a home with moderate routine variation, that is far too sensitive. 3.0σ reduces theoretical flag rate to ~0.3%. The existing "Low" label is confusing (low sensitivity = high threshold) but the threshold value 3.0 is correct.

**Where:** `const.py:DEFAULT_SENSITIVITY`

**Note:** This is a default for new installs only. Existing users must reconfigure via the UI or reset the config entry. Consider renaming the sensitivity levels to reduce confusion: "Low" → "Cautious", "Medium" → "Standard", "High" → "Sensitive".

**Confidence:** HIGH — standard statistical reasoning. 2σ is the wrong default for a system generating notifications.

---

### Technique 4: Minimum Z-Score for Notification (Severity Gate)

**What:** Only send statistical anomaly notifications when the highest severity is at least "moderate" (≥2.5σ). Currently any anomaly above `_sensitivity_threshold` (including minor ones at 2.0σ) fires a notification.

**Why this works:** There is already a full severity classification system (`SEVERITY_THRESHOLDS`). It is currently only used for display, not for notification gating. A "minor" anomaly at 2.0σ is informational — it should update the sensor state but not fire a push notification.

**Where:** `coordinator.py::_async_update_data()` line 560, and `coordinator.py::_send_notification()`

**Implementation shape:**
```python
# Only notify if highest severity is at least moderate
notifiable_anomalies = [
    a for a in stat_anomalies
    if a.severity in ("moderate", "significant", "critical")
]
if stat_learning_complete and notifiable_anomalies:
    await self._send_notification(notifiable_anomalies)
```

**Confidence:** HIGH — the severity system exists specifically for this purpose and is unused in the notification path.

---

### Technique 5: Raise ML Contamination Threshold for Medium Sensitivity

**What:** Change `ML_CONTAMINATION[SENSITIVITY_MEDIUM]` from 0.05 to 0.02.

**Why this works:** `contamination=0.05` means the HST score threshold is `1.0 - 0.05 = 0.95`. River's HalfSpaceTrees produces scores in [0, 1] where scores cluster near 0 for normal data and near 1 for anomalous data. At 0.95, the model flags the top 5% of all scored events. In a streaming home sensor context, 5% is far too high — sensors fire frequently and normal variation is substantial. Setting contamination to 0.02 raises the threshold to 0.98, flagging only the top 2% of anomalous events.

**Where:** `const.py:ML_CONTAMINATION`

Recommended values:
```python
ML_CONTAMINATION: Final = {
    SENSITIVITY_LOW: 0.005,    # 0.5% — only extreme outliers
    SENSITIVITY_MEDIUM: 0.02,  # 2% — was 5%
    SENSITIVITY_HIGH: 0.05,    # 5% — was 10%
}
```

**Confidence:** MEDIUM — the threshold mathematics are correct (training knowledge), but optimal contamination values for home sensors are domain-specific. The direction (lower) is definitely right; exact values need empirical validation.

---

### Technique 6: Require Consecutive Anomalous Intervals Before Notifying

**What:** Add a consecutive-interval counter to `PatternAnalyzer`. Only raise a notification-worthy anomaly if the same entity has been anomalous for N consecutive 60-second update cycles.

**Why this works:** Transient one-interval anomalies (brief noise bursts, momentary sensor glitches, single unusually-timed activation) should be suppressed. A genuine anomaly — real unusual inactivity, for example — persists across multiple intervals. Requiring 2–3 consecutive detections before flagging eliminates one-off spikes entirely.

**Where:** `coordinator.py` — track a `dict[str, int]` of consecutive anomaly counts per entity. Reset to 0 when entity returns to normal.

**Implementation shape:**
```python
# In coordinator state
self._consecutive_anomaly_counts: dict[str, int] = {}

# In _async_update_data(), after checking stat_anomalies
confirmed_anomalies = []
anomalous_entity_ids = {a.entity_id for a in stat_anomalies}
for anomaly in stat_anomalies:
    self._consecutive_anomaly_counts[anomaly.entity_id] = (
        self._consecutive_anomaly_counts.get(anomaly.entity_id, 0) + 1
    )
    if self._consecutive_anomaly_counts[anomaly.entity_id] >= MIN_CONSECUTIVE_ANOMALIES:
        confirmed_anomalies.append(anomaly)
# Reset counts for entities that are no longer anomalous
for entity_id in list(self._consecutive_anomaly_counts.keys()):
    if entity_id not in anomalous_entity_ids:
        self._consecutive_anomaly_counts[entity_id] = 0
```

Recommended constant: `MIN_CONSECUTIVE_ANOMALIES = 2` (anomaly must persist for at least 2 minutes).

**Confidence:** HIGH — consecutive confirmation is a standard noise-reduction pattern for threshold-based alerting systems. No statistical assumptions required.

---

### Technique 7: Cross-Sensor Anomaly Tightening

**What:** Raise the minimum `co_occurrence_count` threshold for cross-sensor patterns to trigger missing-correlation anomalies from 10 to 20, and raise the expected window multiplier from 2× to 3×.

**Why this works:** With only 10 co-occurrences, the `avg_time_delta_seconds` is a rough estimate. The `expected_window` is `avg_time_delta * 2` — so if sensors A and B typically fire within 30s of each other, the system will raise an anomaly if B hasn't fired within 60s of A. That 60s window is unrealistically tight for home sensors. Using `3×` and requiring 20 co-occurrences gives a much more stable baseline.

**Where:** `ml_analyzer.py::check_cross_sensor_anomalies()` lines 503-504 and 525-526

**Specific changes:**
```python
# Line 503-504: raise both thresholds
strong_patterns = [
    p for p in self._cross_sensor_patterns.values()
    if p.correlation_strength > 0.6  # was 0.5
    and p.co_occurrence_count >= 20  # was 10
]

# Line 525: wider expected window
expected_window = timedelta(seconds=pattern.avg_time_delta_seconds * 3)  # was 2
```

**Confidence:** HIGH — directly traceable to the code. 10 co-occurrences is too few for a stable correlation estimate; 2× is too tight for a window.

---

## What NOT to Do

### Do NOT lower the learning period below 7 days

The 672 buckets (7 days × 96 intervals) exist to give the system one observation per time slot per day-of-week. With fewer than 7 days of data, many buckets will have 0 or 1 observations. The infinite z-score problem (Technique 2) gets dramatically worse with shorter learning periods. The `MIN_BUCKET_OBSERVATIONS` gate (Technique 2) mitigates this, but the learning period should stay at 7+ days minimum.

### Do NOT tune sensitivity thresholds per-entity without a UI

Per-entity sensitivity is listed as out-of-scope in PROJECT.md and for good reason. The config entry stores a single sensitivity key. Adding per-entity overrides would require a schema migration, a new UI flow, and substantial coordinator changes. Global tuning achieves most of the benefit with far less complexity.

### Do NOT add exponential backoff to welfare notifications

Welfare notifications are already deduplicated by status change (line 571-573). Adding backoff would mean a sustained `WELFARE_CONCERN` status stops generating alerts if not resolved — dangerous for the elder care use case. The current status-change-only trigger is correct; do not change it.

### Do NOT increase `window_size` on HalfSpaceTrees to reduce false positives

Counter-intuitive: a larger `window_size` makes HST *more* sensitive to recent changes because it weights recent data more heavily. The `window_size=256` is appropriate. Reducing false positives on HST comes from the contamination threshold (Technique 5), not from HST hyperparameters.

### Do NOT require both analyzers to agree before notifying

Requiring both statistical AND ML to agree would cause true positive misses. The statistical analyzer excels at "unusual for this time slot" (unusual_inactivity) while ML excels at "unusual feature pattern" (unusual sequences). They catch different things. The right approach is to raise the bar for each independently (Techniques 1-6), not to AND them together.

---

## Recommended Implementation Priority

| Priority | Technique | Effort | Expected Impact |
|----------|-----------|--------|-----------------|
| 1 | Notification cooldown (Technique 1) | 30 min | Eliminates repeat-fire floods — immediate dramatic reduction |
| 2 | Minimum severity gate (Technique 4) | 20 min | Eliminates minor-severity notification spam |
| 3 | Minimum bucket observations (Technique 2) | 45 min | Eliminates sparse-bucket infinite z-score triggers |
| 4 | Raise default sensitivity (Technique 3) | 5 min | Reduces ongoing rate for new installs |
| 5 | Consecutive anomaly confirmation (Technique 6) | 60 min | Eliminates transient one-interval noise |
| 6 | ML contamination tuning (Technique 5) | 10 min | Reduces ML false positive rate |
| 7 | Cross-sensor window tightening (Technique 7) | 20 min | Reduces missing-correlation false positives |

**Techniques 1 and 4 together should eliminate the majority of the flood without touching any thresholds or requiring model changes.** The remaining techniques are progressive refinements.

---

## Supporting Libraries / New Dependencies

**None required.** All techniques are pure Python logic changes within the existing four files. No new packages in `manifest.json`.

The existing optional River dependency (`river 0.19.0+`) already provides all ML capability needed. The HalfSpaceTrees model parameters (`n_trees`, `height`, `window_size`) are already constructor-injectable in `MLPatternAnalyzer.__init__()`.

---

## Alternatives Considered

| Alternative | Why Not Recommended |
|-------------|---------------------|
| Replace z-score with IQR (interquartile range) | IQR is less affected by outliers but doesn't naturally produce a normalized score. The existing severity classification and sensor output depend on z-scores. Migration cost is high; benefit is low given the bucket sparsity problem is the root cause. |
| Add EWMA (exponentially weighted moving average) smoothing | Would smooth out noisy buckets but adds complexity to `TimeBucket`. The minimum observation count gate (Technique 2) achieves the same goal more simply. |
| Replace HalfSpaceTrees with Isolation Forest | River's `HalfSpaceTrees` is the recommended streaming anomaly detector in the River library. Isolation Forest is batch-oriented (scikit-learn). The codebase correctly uses HST for streaming; don't replace it. |
| Add dynamic threshold adjustment (adaptive thresholds) | Adaptive thresholds (e.g., adjusting sensitivity based on time of day) add significant complexity. The bucket-based approach already implicitly handles time-of-day variation — the real problem is sparse buckets, not insufficient bucket granularity. |

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Notification cooldown (Technique 1) | HIGH | Direct code observation — `_last_notification_time` is stored but never checked before sending stat/ML alerts |
| Sparse bucket infinite z-score (Technique 2) | HIGH | `float("inf")` at `analyzer.py:448` is directly visible in code |
| Default sensitivity (Technique 3) | HIGH | Statistical reasoning: 2σ flags 5% of normal data |
| Severity gate for notifications (Technique 4) | HIGH | Severity system exists but is not used in notification path |
| ML contamination tuning (Technique 5) | MEDIUM | Direction is correct; exact values need empirical testing |
| Consecutive confirmation (Technique 6) | HIGH | Standard alerting pattern; no false assumptions |
| Cross-sensor window tightening (Technique 7) | HIGH | 10 co-occurrences and 2× window directly visible as insufficient |

---

## Sources

- `/custom_components/behaviour_monitor/analyzer.py` — direct code analysis (all techniques)
- `/custom_components/behaviour_monitor/ml_analyzer.py` — direct code analysis (Techniques 5, 7)
- `/custom_components/behaviour_monitor/coordinator.py` — direct code analysis (Technique 1, 4)
- `/custom_components/behaviour_monitor/const.py` — threshold inventory
- Training knowledge: z-score statistics, River HalfSpaceTrees documentation (knowledge cutoff August 2025), streaming anomaly detection patterns

*External verification via River official docs and WebSearch was unavailable this session. Techniques 1, 2, 4, 6, and 7 are grounded entirely in the codebase and are independent of any external source. Technique 5 (contamination values) and Technique 3 (exact default threshold value) would benefit from validation against River's current documentation.*
