# Feature Landscape: Anomaly Detection False Positive Reduction

**Domain:** Home monitoring / anomaly detection notification tightening
**Researched:** 2026-03-13
**Confidence note:** Research tools unavailable. Analysis based on thorough code review of all five source files (analyzer.py, ml_analyzer.py, coordinator.py, const.py, project context) combined with established anomaly detection literature from training knowledge. All claims grounded in what exists vs. what the literature recommends. Flagged where uncertainty exists.

---

## Existing Baseline (What Already Exists)

Before categorizing what to build, it is important to record what false-positive mitigations are already present:

| Mechanism | Location | How It Helps |
|-----------|----------|--------------|
| Learning period gate | `PatternAnalyzer.is_learning_complete()` | No notifications until pattern baseline exists |
| Z-score threshold | `PatternAnalyzer._sensitivity_threshold` | Only flag if deviation exceeds N standard deviations |
| Sensitivity level (Low/Med/High) | `const.py SENSITIVITY_THRESHOLDS` | User-selectable: 1σ / 2σ / 3σ |
| Zero-variance time slot skip | `check_for_anomalies()` line 441 | Skip buckets with no historical variance at all |
| Holiday mode | `coordinator._holiday_mode` | Full suppression during holidays |
| Snooze | `coordinator._snooze_until` | Temporary suppression (1h–1d) |
| Welfare status change-only | `coordinator._async_update_data()` line 571 | Only notify on welfare status _transitions_ |
| ML sample minimum | `MIN_SAMPLES_FOR_ML = 100` | ML won't fire until it has learned enough |
| ML time gate | `ml_learning_period_days` | ML won't fire until time elapsed even if samples met |
| Attribute-only change skip | `_handle_state_changed()` | `track_attributes=False` skips non-state changes |

**Critical observation:** There is currently NO notification cooldown for statistical anomalies. The welfare status notification is dedup'd by status-change, but `_send_notification()` and `_send_ml_notification()` have no cooldown — they fire on every 60-second coordinator update cycle that detects anomalies. This is the most likely cause of alert floods.

---

## Table Stakes

Features that anomaly detection systems must have to be considered non-spammy. Missing any of these makes the system unusable in practice.

| Feature | Why Expected | Complexity | Currently Present? | Notes |
|---------|--------------|------------|--------------------|-------|
| **Notification cooldown (per type)** | Prevents re-alerting on the same ongoing anomaly every 60s | Low | NO — critical gap | The coordinator's 60s update cycle re-sends notifications every cycle. Needs minimum N minutes between same-type alerts. |
| **Minimum observation count per time bucket** | Z-score on a bucket with count=1 or count=2 produces wildly unstable estimates | Low | Partial — only checks std_dev==0 | Need a hard floor: skip detection on buckets with fewer than N observations (e.g. 3–5) |
| **Anomaly deduplication (same entity, same direction)** | If `light.living_room` was already flagged unusual-activity this interval, don't re-flag it 60s later | Low | NO | Track (entity_id, anomaly_type, time_slot) tuples; suppress repeat within same interval |
| **Learning period gate** | Don't alert before baseline is established | Low | YES | Already implemented correctly |
| **Adjustable sensitivity thresholds** | Users have wildly different environments; one-size fits none | Low | YES | 1σ/2σ/3σ available; default 2σ may be too low for noisy sensors |
| **Zero-variance slot suppression** | Bucket mean=0, std=0 means the slot has never fired — a single event produces infinite effective Z-score | Low | Partial — only `expected_std==0 and expected_mean==0` branch; the `float('inf')` branch still fires anomalies | The `z_score = float("inf")` branch on line 448 fires for any first-ever event in a slot after learning complete — very spammy |

---

## Differentiators

Features that go beyond the minimum, adding meaningfully to detection quality and trustworthiness.

| Feature | Value Proposition | Complexity | Currently Present? | Notes |
|---------|-------------------|------------|--------------------|-------|
| **Confidence-weighted thresholds** | A bucket with 3 observations warrants a higher Z-score threshold than one with 50. Scale threshold by sqrt(n) or use Student's t instead of Gaussian | Medium | NO | Improves precision for low-count buckets without requiring full minimum-count gating |
| **Per-interval adaptive baseline** | Detect bucket-level drift over weeks (e.g. user's schedule has shifted) via exponentially weighted moving average on bucket means | Medium | NO | Current buckets accumulate forever; a slow schedule shift will always look anomalous |
| **Seasonal/day-type awareness** | Bank holidays, seasonal patterns (summer vs. winter); currently all Tuesdays treated identically regardless of school terms | High | NO (holiday mode is manual) | Out of scope for this milestone given constraint on complexity; flag for later |
| **Cross-analyzer agreement requirement** | Only notify when BOTH statistical AND ML flag the same entity/window | Medium | NO | Requires both analyzers enabled; reduces false positives significantly when both active |
| **Severity minimum for notifications** | Only send notifications for moderate/significant/critical severity; suppress minor | Low | NO — all severities notify | Trivially implementable: add a `min_notification_severity` config option |
| **Burst detection suppression** | N anomalies in M minutes on the same entity → suppress after first, flag as "ongoing pattern" | Medium | NO | Prevents a single sticky situation (door left open, sensor malfunction) from spamming |
| **Missing correlation confidence gate** | Cross-sensor "missing correlation" anomalies require `correlation_strength > 0.7` AND `co_occurrence_count >= 20` before firing; current threshold is 0.5/10 which fires prematurely | Low | Partial — threshold exists at 0.5/10 but too loose | Easy win: raise thresholds |
| **Inactivity anomalies require stronger evidence** | Unusual-inactivity is often a false positive (entity simply didn't fire in a quiet period). Require higher Z-score multiplier for inactivity vs. activity | Low | NO — symmetric thresholds | Add `inactivity_z_multiplier` config (e.g. 1.5x) |

---

## Anti-Features

Features to explicitly NOT build during this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Per-entity sensitivity tuning UI** | Adds config complexity; users won't know correct values; PROJECT.md explicitly calls this out of scope | Tune global thresholds to sane defaults; power users can write HA automations |
| **User feedback / thumbs-up / thumbs-down to adjust thresholds** | Requires a feedback loop UI, persistent feedback storage, and logic to adjust per-bucket thresholds; weeks of work for uncertain gain | Use static threshold improvements with better defaults |
| **Anomaly scoring aggregation dashboard** | Visualization work is cosmetic; the problem is too many alerts, not a lack of dashboards | Focus on suppression logic, not display logic |
| **Daily digest / summary mode** | PROJECT.md explicitly out of scope for this milestone | Defer |
| **New anomaly detection algorithms** | Scope is reducing noise from existing detectors, not adding new detectors | Stay with Z-score and Half-Space Trees; tune them |
| **Seasonal/calendar awareness** | High complexity (DST, holidays, school terms, regional calendars); adds new dependencies | Manual holiday mode is sufficient for now |
| **ML model interpretability / explanation** | Half-Space Trees are not interpretable by design; adding SHAP-style explanations would require algorithm replacement | Keep descriptions as human-readable strings |

---

## Feature Dependencies

```
Notification cooldown (per type)
  → Required before: burst detection suppression (cooldown is the simpler subset)

Minimum observation count per time bucket
  → Required before: confidence-weighted thresholds (both address same bucket sparsity problem;
    start with min-count gate as simpler approach)

Cross-analyzer agreement requirement
  → Depends on: both ML and statistical analyzers being enabled
  → Requires: a way to correlate statistical and ML results by entity + time window

Inactivity Z-score multiplier
  → Depends on: anomaly_type distinction already exists (unusual_activity vs unusual_inactivity)
  → No upstream dependencies; can be done standalone

Severity minimum for notifications
  → Standalone; no dependencies
  → Should be implemented before other changes to establish a floor
```

---

## Analysis: Root Causes of Current False Positive Flood

Based on code review, ranked by likely impact:

### 1. No notification cooldown (HIGH IMPACT)
`_send_notification()` is called every 60-second coordinator cycle that produces any anomaly. An anomaly that persists for 10 minutes generates 10 notifications. There is no `_last_notification_time` check in `_send_notification()` even though `_last_notification_time` is tracked — the value is stored but never used to suppress repeat alerts.

### 2. Infinite Z-score on first event in any slot (HIGH IMPACT)
`analyzer.py` line 448: when `expected_std == 0` but `actual != expected_mean`, sets `z_score = float("inf")`. After the 7-day learning period, every time bucket in every day/interval has `count=1` (seen once in the training week). After learning is "complete" but the second week starts, any new event in a slot where only one observation was recorded in the training period will have `std_dev=0` and trigger `float("inf")` z-score → definite anomaly.

### 3. Sensitivity threshold too low for medium sensitivity (MEDIUM IMPACT)
`SENSITIVITY_MEDIUM = 2.0` (2σ). For a normally distributed process, 2σ means 4.5% of observations are flagged as anomalies by design. With 96 intervals/day × N entities, this produces many events daily even at "normal" operation.

### 4. Cross-sensor missing correlation fires too eagerly (MEDIUM IMPACT)
Threshold `correlation_strength > 0.5` and `co_occurrence_count >= 10` is low. With 10 co-occurrences over a week, correlation estimates are noisy and the 0.5 threshold allows weak correlations to fire "missing correlation" alerts.

### 5. Inactivity detection symmetry (LOW-MEDIUM IMPACT)
Unusual inactivity is detected at the same threshold as unusual activity. But inactivity is naturally more variable (people have occasional atypical days), producing more false positives than activity detection.

---

## MVP Recommendation for False Positive Reduction

Prioritize in this order:

1. **Notification cooldown** — prevent re-alerting on same ongoing anomaly (implement `last_stat_notification_time` and `last_ml_notification_time` with configurable cooldown, default 15–30 min)
2. **Minimum observation floor** — require at least 3–5 observations in a bucket before checking anomalies (eliminates the `float("inf")` z-score problem)
3. **Severity minimum** — only notify on moderate+ severity (eliminates minor noise at threshold boundary)
4. **Raise ML cross-sensor correlation thresholds** — change from 0.5/10 to 0.7/20
5. **Inactivity asymmetric threshold** — apply 1.5x multiplier to inactivity z-score threshold

Defer:
- Confidence-weighted thresholds: high explanatory value but more complex; do min-observation floor first
- Cross-analyzer agreement: useful but requires both analyzers active and correlation logic
- Adaptive baselines: significant architecture change; not needed to solve the immediate flood

---

## Sources

- Code review: `custom_components/behaviour_monitor/analyzer.py`, `ml_analyzer.py`, `coordinator.py`, `const.py` (2026-03-13)
- Project context: `.planning/PROJECT.md` (2026-03-13)
- Architecture context: `.planning/codebase/ARCHITECTURE.md` (2026-03-13)
- Domain knowledge: Z-score anomaly detection, notification system design, streaming ML thresholds — HIGH confidence for well-established statistical and system design principles; MEDIUM confidence for specific threshold values (require empirical validation in this specific use case)
- External research: Unavailable (web search tools denied) — recommendations rely on codebase analysis and established domain knowledge
