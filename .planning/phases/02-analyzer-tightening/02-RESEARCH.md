# Phase 2: Analyzer Tightening - Research

**Researched:** 2026-03-13
**Domain:** Statistical and ML anomaly detection — Python, scipy-style z-score math, River streaming ML
**Confidence:** HIGH — all findings derived from direct reading of the actual codebase; no external library research required for core changes

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| STAT-01 | Minimum observation count per time bucket prevents flagging when insufficient data exists (fixes `float("inf")` z-scores from zero-variance buckets) | `check_for_anomalies()` line 440 skips `expected_std==0 and expected_mean==0` but does NOT skip when `expected_std==0 and expected_mean>0`; adding a `bucket.count < MIN_BUCKET_OBSERVATIONS` guard before z-score calculation covers both the inf-score case and the sparse-data case for STAT-02 |
| STAT-02 | Minimum mean activity guard skips anomaly detection for time buckets with near-zero historical activity | Subsumed by the same `bucket.count` guard for STAT-01; alternatively guard on `expected_mean < MIN_MEAN_ACTIVITY`; both guards live in `check_for_anomalies()` |
| STAT-03 | Default sensitivity thresholds raised so Medium sensitivity no longer flags ~4.5% of normal events | `SENSITIVITY_THRESHOLDS[SENSITIVITY_MEDIUM] = 2.0` in `const.py` line 28; raising to 2.5 or 3.0 is a one-line constant change; confirmed STATE.md research flag that existing MEDIUM users are unaffected without migration |
| STAT-04 | Adaptive thresholds adjust per-entity based on historical variance profile (high-variance entities get wider thresholds) | `EntityPattern.day_buckets` already accumulates per-bucket `std_dev`; a per-entity variance multiplier can be computed from the distribution of `bucket.std_dev` values and applied at detection time in `check_for_anomalies()` |
| ML-01 | Cross-sensor correlation thresholds raised — minimum co-occurrence count increased from 10 to a statistically meaningful level | `check_cross_sensor_anomalies()` line 504-505 hardcodes `co_occurrence_count >= 10`; this must become a named constant `MIN_CROSS_SENSOR_OCCURRENCES`; recommended target: 30 |
| ML-02 | ML anomaly score threshold raised to reduce marginal detections | `check_anomaly()` line 473 computes `threshold = 1.0 - self._contamination`; `ML_CONTAMINATION[SENSITIVITY_MEDIUM] = 0.05` gives threshold 0.95; STATE.md flags LOW confidence on exact values — treat as provisional |
| ML-03 | ML score smoothing via exponential moving average reduces noise from single-point spikes | No smoothing exists today; requires a per-entity EMA state dict on `MLPatternAnalyzer`; `score_smoothed = alpha * score + (1 - alpha) * prev_score`; compare smoothed score against threshold |
</phase_requirements>

---

## Summary

Phase 2 makes surgical changes to `analyzer.py` and `ml_analyzer.py` to reduce the volume of raw anomalies that reach the coordinator. Phase 1 added suppression gates at the notification dispatch layer; Phase 2 attacks the root cause — the analyzers produce too many low-quality anomalies in the first place.

The statistical analyzer has two concrete bugs that produce certain false positives: (1) when a time bucket has zero standard deviation but nonzero mean (perfectly consistent entity), the z-score formula produces `float("inf")` for any deviation, instantly flagging the anomaly; (2) when a bucket has too few historical observations (e.g., two Mondays at 3 AM), the standard deviation is statistically meaningless and should not drive anomaly decisions. Both bugs are fixed by a single guard in `check_for_anomalies()` that checks `bucket.count` before entering the z-score path. The default medium sensitivity threshold (2.0 sigma = 4.5% false positive rate on normal data) needs to be raised; 2.5 sigma (1.2% rate) is the standard recommendation for routine variance suppression. STAT-04 (adaptive thresholds) is more complex — it requires computing a per-entity variance coefficient and applying it as a multiplier.

The ML analyzer has three independent changes. ML-01 is the simplest: a hardcoded `10` in `check_cross_sensor_anomalies()` needs to become a named constant raised to ~30 co-occurrences. ML-02 raises the contamination value to reduce sensitivity. ML-03 is the most structural: it requires adding per-entity EMA state to the ML analyzer to smooth scores before threshold comparison.

**Primary recommendation:** Implement STAT-01+02 together (same guard), STAT-03 as a pure constant change, STAT-04 as a standalone enhancement, and the three ML changes as one cohesive ML pass.

---

## Standard Stack

### Core (no new dependencies)
| Component | Location | Purpose | Change |
|-----------|----------|---------|--------|
| `analyzer.py` | existing | Statistical detection | Add bucket guards, raise threshold, adaptive multiplier |
| `ml_analyzer.py` | existing | ML streaming detection | Raise cross-sensor count, EMA score smoothing |
| `const.py` | existing | Constants | Add `MIN_BUCKET_OBSERVATIONS`, `MIN_CROSS_SENSOR_OCCURRENCES`, raise `SENSITIVITY_MEDIUM` threshold |
| `pytest` + `conftest.py` | existing | Test framework | Tests added to `tests/test_analyzer.py` and `tests/test_ml_analyzer.py` |

### No New Dependencies
Zero new Python packages. All changes use stdlib math and existing data structures.

---

## Architecture Patterns

### File Change Map
```
custom_components/behaviour_monitor/
├── const.py              # Add 2 new constants; raise SENSITIVITY_MEDIUM threshold
├── analyzer.py           # check_for_anomalies() guard; adaptive multiplier logic
└── ml_analyzer.py        # check_cross_sensor_anomalies() constant; EMA state + smoothing

tests/
├── test_analyzer.py      # New test classes: TestBucketGuards, TestAdaptiveThresholds
└── test_ml_analyzer.py   # New test cases: cross-sensor count guard, EMA smoothing
```

### Pattern 1: Bucket Observation Guard (STAT-01 + STAT-02)

**What:** Before computing a z-score for a time bucket, check that the bucket has enough observations to be statistically meaningful. If not, skip — return no anomaly for this entity/interval.

**When to use:** At the top of the per-entity loop in `check_for_anomalies()`, immediately after fetching `expected_mean, expected_std`.

**Exact location:** `analyzer.py`, `PatternAnalyzer.check_for_anomalies()`, after line 437 (`expected_mean, expected_std = pattern.get_expected_activity(now)`)

**Current code path that causes the bug:**
```python
# analyzer.py line 444-448
if expected_std > 0:
    z_score = abs(actual - expected_mean) / expected_std
elif actual != expected_mean:
    # No variance but value differs from expected  ← THIS IS THE BUG
    z_score = float("inf") if actual > 0 else self._sensitivity_threshold + 1
```
An entity that fires exactly once every Tuesday at 09:00 for 3 weeks has `count=3`, `mean=1.0`, `std_dev=0.0`. The Tuesday it does NOT fire gets `z_score = float("inf")` and is flagged as critical.

**Fix pattern:**
```python
# After fetching mean/std, add this guard:
day_of_week = now.weekday()
interval = _get_interval_index(now)
bucket = pattern.day_buckets[day_of_week][interval]

if bucket.count < MIN_BUCKET_OBSERVATIONS:
    continue  # Not enough data to make a decision
```

The `float("inf")` path then becomes dead code for the normal case; it can be replaced with a capped value (e.g., `self._sensitivity_threshold + 1`) or removed entirely.

### Pattern 2: Raise Default Medium Sensitivity (STAT-03)

**What:** Change `SENSITIVITY_THRESHOLDS[SENSITIVITY_MEDIUM]` from 2.0 to 2.5 in `const.py`.

**Statistical rationale:** At 2.0 sigma, ~4.5% of observations from a normal distribution exceed the threshold (two-tailed). At 2.5 sigma, that drops to ~1.2%. For a system checking 96 intervals/day across multiple entities, 2.0 sigma generates constant noise.

**Exact location:** `const.py` line 28:
```python
SENSITIVITY_THRESHOLDS: Final = {
    SENSITIVITY_LOW: 3.0,
    SENSITIVITY_MEDIUM: 2.5,   # was 2.0 — raises from 4.5% to 1.2% false positive rate
    SENSITIVITY_HIGH: 1.0,
}
```

**Migration note:** This ONLY affects new installs and users who reconfigure sensitivity. Existing installs with MEDIUM sensitivity continue using whatever value was passed to `PatternAnalyzer.__init__()` at setup time. The coordinator reads sensitivity on startup from `entry.data`; there is no migration path built into Phase 2. Document this limitation.

### Pattern 3: Adaptive Thresholds (STAT-04)

**What:** Compute a per-entity variance coefficient from historical bucket data. Entities with highly variable patterns (high-variance entities like motion sensors) get a wider effective threshold; entities with very consistent patterns (lights on a schedule) retain the base threshold.

**Implementation approach:**
1. Add a method `get_variance_profile(entity_id) -> float` on `PatternAnalyzer` that computes the coefficient of variation (CV = mean std_dev / mean mean) across all non-empty buckets for a given entity.
2. In `check_for_anomalies()`, compute `effective_threshold = self._sensitivity_threshold * variance_multiplier` where `variance_multiplier = max(1.0, min(MAX_VARIANCE_MULTIPLIER, 1.0 + cv))`.
3. Apply `effective_threshold` instead of `self._sensitivity_threshold` in the z-score comparison.

**Constants needed:**
```python
MAX_VARIANCE_MULTIPLIER: Final = 2.0  # Cap at 2x the base threshold
```

**Complexity note:** STAT-04 is the most complex STAT requirement. If it creates test complexity or schedule risk, it should be its own plan wave rather than bundled with STAT-01/02/03.

### Pattern 4: Cross-Sensor Co-occurrence Guard (ML-01)

**What:** Replace hardcoded `10` in `check_cross_sensor_anomalies()` with named constant `MIN_CROSS_SENSOR_OCCURRENCES`.

**Exact location:** `ml_analyzer.py`, `MLPatternAnalyzer.check_cross_sensor_anomalies()`, line ~504:
```python
# Current
strong_patterns = [
    p for p in self._cross_sensor_patterns.values()
    if p.correlation_strength > 0.5 and p.co_occurrence_count >= 10
]

# After
strong_patterns = [
    p for p in self._cross_sensor_patterns.values()
    if p.correlation_strength > 0.5 and p.co_occurrence_count >= MIN_CROSS_SENSOR_OCCURRENCES
]
```

**Recommended value:** 30. At 10 co-occurrences over a 5-minute window, two sensors that happen to fire near each other twice a week would reach threshold in 5 weeks. At 30, it requires ~15 weeks of consistent co-occurrence, which is a statistically meaningful signal for a home environment.

**Constant location:** `const.py`.

### Pattern 5: ML Score EMA Smoothing (ML-03)

**What:** Maintain a per-entity exponential moving average (EMA) of the ML anomaly score. Compare the EMA score (not the raw score) against the threshold.

**State to add to `MLPatternAnalyzer.__init__()`:**
```python
self._score_ema: dict[str, float] = {}  # entity_id -> smoothed score
self._ema_alpha: float = 0.3  # smoothing factor (lower = more smoothing)
```

**EMA update in `check_anomaly()`:**
```python
# After score = self._model.score_one(features)
entity_id = event.entity_id
prev_ema = self._score_ema.get(entity_id, score)
smoothed_score = self._ema_alpha * score + (1 - self._ema_alpha) * prev_ema
self._score_ema[entity_id] = smoothed_score

# Compare smoothed score against threshold
if smoothed_score > threshold:
    ...
```

**Alpha guidance:** 0.3 means a single spike contributes 30% of the new EMA; the previous history contributes 70%. At alpha=0.3, a one-off spike to 0.99 (with a prior EMA of 0.50) produces a smoothed score of `0.3*0.99 + 0.7*0.50 = 0.647` — well below the typical threshold of 0.95. A genuine sustained anomaly (multiple consecutive high scores) rapidly pushes the EMA over threshold.

**EMA state persistence:** The `_score_ema` dict should be included in `to_dict()` / `from_dict()` so it survives HA restarts. Otherwise the first update cycle after a restart always starts with a cold EMA, which can cause false positives.

**Constant location:** `ML_EMA_ALPHA: Final = 0.3` in `const.py`.

### Pattern 6: Raise ML Contamination Threshold (ML-02)

**What:** Raise the contamination values in `ML_CONTAMINATION` in `const.py` to reduce the proportion of events flagged as anomalous.

**Current values:**
```python
ML_CONTAMINATION: Final = {
    SENSITIVITY_LOW: 0.01,
    SENSITIVITY_MEDIUM: 0.05,
    SENSITIVITY_HIGH: 0.10,
}
```

**Issue:** `contamination=0.05` means the model is calibrated to expect 5% of events to be anomalies. For a home environment with predictable routines, this is extremely high. River's HalfSpaceTrees uses contamination to compute the detection threshold as `1.0 - contamination`. At 0.05, threshold = 0.95; at 0.02, threshold = 0.98.

**Recommended values (treat as provisional per STATE.md flag):**
```python
ML_CONTAMINATION: Final = {
    SENSITIVITY_LOW: 0.005,   # 0.5% expected anomalies
    SENSITIVITY_MEDIUM: 0.02, # 2% expected anomalies
    SENSITIVITY_HIGH: 0.05,   # 5% (original medium value)
}
```

**Confidence:** LOW on exact values. The STATE.md explicitly flags this: "ML contamination optimal values (LOW: 0.005, MEDIUM: 0.02) are directionally correct but empirically determined — treat as provisional and monitor after Phase 2 ships."

### Anti-Patterns to Avoid

- **Don't change `TimeBucket.std_dev` to return a non-zero floor:** The zero variance case is meaningful information; suppress at detection time, not at data time.
- **Don't raise `HIGH` sensitivity threshold:** HIGH = 1.0 sigma is intentionally aggressive for users who want it. Only MEDIUM changes.
- **Don't share EMA state across entities:** Each entity gets independent EMA; cross-contamination would cause entity B's activity to affect entity A's anomaly score.
- **Don't persist EMA state in the ML events list:** Keep it in a separate dict; the events list is for model replay, not for score history.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| EMA computation | Custom windowed average | Simple alpha formula | EMA is O(1) per update, one line, no library needed |
| Statistical significance of bucket count | Confidence intervals, Bayesian priors | Simple threshold guard on `bucket.count` | The problem is sparse data, not estimation quality; a count gate is sufficient |
| Per-entity adaptive threshold | Per-bucket regression | Coefficient of variation on existing `std_dev` values | `EntityPattern.day_buckets` already has everything needed |

---

## Common Pitfalls

### Pitfall 1: Off-by-one in bucket access within `check_for_anomalies()`
**What goes wrong:** The bucket access for the guard needs to use the same `day_of_week` and `interval` that `get_expected_activity()` uses internally. If the guard computes day/interval differently from the detection code, it guards the wrong bucket.
**Why it happens:** `now = datetime.now(timezone.utc)` is called once at the top of `check_for_anomalies()`; `get_expected_activity(now)` passes `now` through. The guard must also derive day/interval from the same `now`.
**How to avoid:** Access the bucket directly — `pattern.day_buckets[now.weekday()][_get_interval_index(now)]` — using the same `now` already in scope. Alternatively, refactor `get_expected_activity()` to also return `bucket.count`.
**Warning signs:** Tests pass but a bucket with `count=0` still generates anomaly results.

### Pitfall 2: EMA cold-start after HA restart
**What goes wrong:** After restart, `_score_ema` is empty. The first `check_anomaly()` call for each entity initialises EMA to the raw score (`prev_ema = score`). If the first event after restart is a spike, the EMA immediately equals the spike — the smoothing provides no protection for the first event.
**Why it happens:** The EMA dict is not persisted by default.
**How to avoid:** Include `_score_ema` in `to_dict()` / `from_dict()`. If the dict is absent in stored data (old format), fall back to empty dict gracefully.
**Warning signs:** Anomaly fired in first 60 seconds after HA restart on a sensor that hasn't changed.

### Pitfall 3: Raising MIN_BUCKET_OBSERVATIONS too high
**What goes wrong:** Setting `MIN_BUCKET_OBSERVATIONS` to 20 means you need 20 weeks of data before Monday-at-3AM is ever checked (one sample per week per bucket). This silently disables detection for low-frequency slots.
**Why it happens:** The bucket is per-day-per-15-minute-slot, not per-day. Rare but legitimate patterns would never accumulate enough samples.
**How to avoid:** Start with `MIN_BUCKET_OBSERVATIONS = 3`. This requires 3 observations before flagging, which at one observation per week means detection starts after 3 weeks — reasonable. Don't go above 5.
**Warning signs:** Entity with 90 days of data is never flagged even for clearly anomalous behaviour at unusual hours.

### Pitfall 4: ML-02 contamination change not applied to coordinator
**What goes wrong:** `ML_CONTAMINATION` in `const.py` is changed but `coordinator.py` already instantiated `MLPatternAnalyzer` with the old contamination at setup time; the new values don't take effect until HA restarts.
**Why it happens:** `coordinator.py` reads `ML_CONTAMINATION` at `__init__` time. Existing installs won't get the new default until they restart HA. This is acceptable (same as STAT-03 sensitivity change) but must be documented.
**How to avoid:** Accept this behaviour; document it in CHANGELOG.

### Pitfall 5: `correlation_strength` formula already includes `log1p(co_occurrence_count) / 5.0`
**What goes wrong:** Assuming the co-occurrence count guard fully controls the threshold. The `correlation_strength` formula already scales by `log1p(count) / 5.0`, which means `count=10` yields a `count_factor` of only `log1p(10)/5 ≈ 0.48`. The `> 0.5` correlation strength filter is ALSO at play.
**Why it happens:** Both filters exist in `check_cross_sensor_anomalies()` — the strength filter AND the count filter. Raising the count minimum will tighten the count filter; the strength filter is unchanged.
**How to avoid:** Raise only the count minimum (ML-01 scope). Do not change the strength threshold simultaneously — isolate the variable.
**Warning signs:** After raising count minimum, no cross-sensor patterns ever trigger because both filters stack.

---

## Code Examples

### STAT-01/02: Bucket guard in `check_for_anomalies()`
```python
# Source: direct code analysis of analyzer.py
# Location: PatternAnalyzer.check_for_anomalies(), inside the entity loop

for entity_id, pattern in self._patterns.items():
    expected_mean, expected_std = pattern.get_expected_activity(now)
    actual = current_interval_activity.get(entity_id, 0)
    time_slot = pattern.get_time_description(now)

    # NEW GUARD: skip buckets without enough historical data
    day_of_week = now.weekday()
    interval = _get_interval_index(now)
    bucket = pattern.day_buckets[day_of_week][interval]
    if bucket.count < MIN_BUCKET_OBSERVATIONS:
        continue

    # Existing: skip if no data at all
    if expected_std == 0 and expected_mean == 0:
        continue

    # Calculate Z-score
    if expected_std > 0:
        z_score = abs(actual - expected_mean) / expected_std
    elif actual != expected_mean:
        z_score = self._sensitivity_threshold + 1  # was float("inf")
    else:
        z_score = 0.0
    ...
```

### ML-03: EMA smoothing in `check_anomaly()`
```python
# Source: direct code analysis of ml_analyzer.py
# Location: MLPatternAnalyzer.check_anomaly()

score = self._model.score_one(features)

# NEW: EMA smoothing to prevent single-spike false positives
entity_id = event.entity_id
prev_ema = self._score_ema.get(entity_id, score)  # cold start: seed with current score
smoothed = self._ema_alpha * score + (1 - self._ema_alpha) * prev_ema
self._score_ema[entity_id] = smoothed

threshold = 1.0 - self._contamination

if smoothed > threshold:  # compare smoothed, not raw
    return MLAnomalyResult(
        ...
        anomaly_score=smoothed,  # report the smoothed score
        ...
    )
return None
```

### STAT-04: Per-entity variance multiplier
```python
# Source: design based on existing EntityPattern.day_buckets structure

def _get_variance_multiplier(self, pattern: EntityPattern) -> float:
    """Compute adaptive threshold multiplier based on entity variance profile."""
    from .const import MAX_VARIANCE_MULTIPLIER
    stds = []
    means = []
    for day_buckets in pattern.day_buckets.values():
        for bucket in day_buckets:
            if bucket.count >= MIN_BUCKET_OBSERVATIONS and bucket.mean > 0:
                stds.append(bucket.std_dev)
                means.append(bucket.mean)
    if not means:
        return 1.0
    avg_mean = sum(means) / len(means)
    avg_std = sum(stds) / len(stds)
    cv = avg_std / avg_mean if avg_mean > 0 else 0.0
    multiplier = 1.0 + cv
    return max(1.0, min(MAX_VARIANCE_MULTIPLIER, multiplier))
```

---

## State of the Art

| Old Behaviour | New Behaviour | When Changed | Impact |
|---------------|---------------|--------------|--------|
| Zero-variance bucket → `float("inf")` z-score | Zero-variance with sparse data → skipped | Phase 2 | Eliminates guaranteed false positives for consistent entities |
| Any bucket with observations → checked | Only buckets with `count >= 3` → checked | Phase 2 | Eliminates weak-data false positives |
| MEDIUM sensitivity = 2.0 sigma | MEDIUM sensitivity = 2.5 sigma | Phase 2 | Reduces false positive rate from 4.5% to 1.2% |
| Uniform threshold per entity | Per-entity variance-scaled threshold | Phase 2 | High-variance entities tolerate more deviation |
| ML cross-sensor: 10 co-occurrences minimum | 30 co-occurrences minimum | Phase 2 | Requires more evidence before pattern triggers |
| ML raw score vs threshold | EMA-smoothed score vs threshold | Phase 2 | Single-interval spikes no longer trigger |
| ML MEDIUM contamination = 5% | ML MEDIUM contamination = 2% | Phase 2 | Fewer marginal detections |

---

## Open Questions

1. **Exact value for `MIN_BUCKET_OBSERVATIONS`**
   - What we know: 3 requires 3 observations per slot before checking; for a once-per-week slot that's 3 weeks of data before that slot is checked
   - What's unclear: Whether 3 is the right tradeoff between data quality and detection responsiveness
   - Recommendation: Start with 3; make it a named constant so it can be tuned without code changes

2. **Whether STAT-04 (adaptive thresholds) warrants its own plan wave**
   - What we know: STAT-01/02/03 are straightforward; STAT-04 adds a `_get_variance_multiplier()` helper and modifies the detection loop
   - What's unclear: Test complexity of STAT-04 vs the other items
   - Recommendation: Planner should bundle STAT-01/02/03 in one wave and STAT-04 + ML changes in a second wave

3. **ML-02 contamination values — correctness**
   - What we know: STATE.md flags this as "directionally correct but empirically determined"
   - What's unclear: Whether 0.02 for MEDIUM is correct without field data
   - Recommendation: Ship as provisional; add a comment in const.py that these are tunable

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (see `pytest.ini`) |
| Config file | `/Users/abourne/Documents/source/behaviour-monitor/pytest.ini` |
| Quick run command | `python -m pytest tests/test_analyzer.py tests/test_ml_analyzer.py -v --tb=short` |
| Full suite command | `make test` (runs `python -m pytest tests/ -v`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STAT-01 | Zero-variance bucket with `count < MIN_BUCKET_OBSERVATIONS` is skipped — no anomaly result | unit | `python -m pytest tests/test_analyzer.py::TestBucketGuards::test_sparse_bucket_skipped -x` | ❌ Wave 0 |
| STAT-01 | Zero-variance bucket that previously produced `float("inf")` z-score is skipped | unit | `python -m pytest tests/test_analyzer.py::TestBucketGuards::test_no_inf_z_score -x` | ❌ Wave 0 |
| STAT-02 | Near-zero mean bucket with sparse count is skipped | unit | `python -m pytest tests/test_analyzer.py::TestBucketGuards::test_near_zero_mean_skipped -x` | ❌ Wave 0 |
| STAT-03 | `SENSITIVITY_THRESHOLDS[SENSITIVITY_MEDIUM]` equals 2.5 (not 2.0) | unit | `python -m pytest tests/test_analyzer.py::TestSensitivityConstants::test_medium_threshold_raised -x` | ❌ Wave 0 |
| STAT-04 | High-variance entity gets a wider effective threshold than a low-variance entity | unit | `python -m pytest tests/test_analyzer.py::TestAdaptiveThresholds -x` | ❌ Wave 0 |
| STAT-04 | Variance multiplier is capped at `MAX_VARIANCE_MULTIPLIER` | unit | `python -m pytest tests/test_analyzer.py::TestAdaptiveThresholds::test_multiplier_capped -x` | ❌ Wave 0 |
| ML-01 | Pattern with < `MIN_CROSS_SENSOR_OCCURRENCES` is excluded from strong_patterns | unit | `python -m pytest tests/test_ml_analyzer.py::TestCrossSensorGuard::test_low_count_excluded -x` | ❌ Wave 0 |
| ML-02 | `ML_CONTAMINATION[SENSITIVITY_MEDIUM]` equals 0.02 | unit | `python -m pytest tests/test_ml_analyzer.py::TestMLContaminationConstants::test_medium_contamination_raised -x` | ❌ Wave 0 |
| ML-03 | Single-spike score below smoothed threshold does not produce anomaly result | unit | `python -m pytest tests/test_ml_analyzer.py::TestEMASmoothing::test_spike_suppressed -x` | ❌ Wave 0 |
| ML-03 | Sustained high score (multiple consecutive intervals) does produce anomaly result | unit | `python -m pytest tests/test_ml_analyzer.py::TestEMASmoothing::test_sustained_anomaly_detected -x` | ❌ Wave 0 |
| ML-03 | EMA state is included in `to_dict()` / `from_dict()` round-trip | unit | `python -m pytest tests/test_ml_analyzer.py::TestEMASmoothing::test_ema_serialization -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_analyzer.py tests/test_ml_analyzer.py -v --tb=short`
- **Per wave merge:** `make test`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_analyzer.py::TestBucketGuards` class — covers STAT-01, STAT-02
- [ ] `tests/test_analyzer.py::TestSensitivityConstants` class — covers STAT-03
- [ ] `tests/test_analyzer.py::TestAdaptiveThresholds` class — covers STAT-04
- [ ] `tests/test_ml_analyzer.py::TestCrossSensorGuard` class — covers ML-01
- [ ] `tests/test_ml_analyzer.py::TestMLContaminationConstants` class — covers ML-02
- [ ] `tests/test_ml_analyzer.py::TestEMASmoothing` class — covers ML-03

Note: `conftest.py` already handles HA mocking. No new fixtures needed. Framework install is present (`pytest.ini` exists, `requirements-dev.txt` includes pytest).

---

## Sources

### Primary (HIGH confidence)
- Direct reading of `custom_components/behaviour_monitor/analyzer.py` — all statistical detection logic
- Direct reading of `custom_components/behaviour_monitor/ml_analyzer.py` — all ML detection logic
- Direct reading of `custom_components/behaviour_monitor/const.py` — all constants
- Direct reading of `custom_components/behaviour_monitor/coordinator.py` — Phase 1 suppression state
- Direct reading of `.planning/STATE.md` — accumulated decisions and research flags
- Direct reading of `.planning/REQUIREMENTS.md` — requirement definitions

### Secondary (MEDIUM confidence)
- Statistical claim: "2.5 sigma = 1.2% false positive rate on normal data" — standard z-table result; well-established, not project-specific

### Tertiary (LOW confidence)
- ML contamination target values (0.02 for MEDIUM) — empirically suggested in STATE.md research flag, not derived from River documentation or field data. Treat as provisional.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all changes are in existing files, no new dependencies
- Architecture: HIGH — all patterns derived from direct code reading; no assumptions
- STAT pitfalls: HIGH — derived from reading actual bug in `check_for_anomalies()` line 448
- ML pitfalls: HIGH for EMA cold-start and correlation formula; MEDIUM for contamination values
- Contamination values: LOW — empirically suggested, not validated

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable codebase; no active development on main branch)
