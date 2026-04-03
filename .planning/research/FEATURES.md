# Feature Landscape: v4.0 Cross-Entity Correlation & Startup Tier Rehydration

**Domain:** Cross-entity correlation detection and startup tier rehydration for Home Assistant behavior monitoring integration
**Researched:** 2026-04-03
**Milestone:** v4.0
**Scope:** NEW features only. Existing features (per-entity routine learning, acute/drift detection, tier classification, alert suppression, holiday/snooze, config UI through v8) are already shipped.

---

## Table Stakes

Features users expect from a cross-entity correlation system. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Dependencies on Existing | Notes |
|---------|--------------|------------|--------------------------|-------|
| **Auto-discover correlated entity groups** | Users will not manually define which entities co-occur; the system already learns per-entity baselines, so cross-entity learning should also be automatic | High | `RoutineModel._entities`, `_last_seen` dict, `_handle_state_changed` event stream | Core value: learn temporal co-occurrence windows from observed event pairs without user configuration |
| **Expose discovered correlation groups as sensor attributes** | Users need visibility into what the system has learned before they trust alerts from it; correlation groups must be inspectable | Low | Existing `cross_sensor_patterns` list in `_build_sensor_data` is already present but empty (`[]`); populate it | Placeholder already exists in both `_build_sensor_data` and `_build_safe_defaults` at coordinator.py L325 and L338 |
| **Alert on broken correlations** | The payoff feature of correlation detection: entity A fires but expected companion B does not follow within the learned window | Medium | Correlation group data, `AlertResult` infrastructure, existing alert suppression and severity gating | Must integrate with sustained-evidence gating (3 cycles), fire-once-then-throttle, and severity gate. New `AlertType.CORRELATION_BREAK` value. |
| **Startup tier rehydration on first update cycle** | Current gap: `_activity_tier` is a non-serialized field (`init=False`) that defaults to `None` after `EntityRoutine.from_dict()` deserialization. Tiers must be available immediately, not deferred until a side effect triggers them. | Low | `EntityRoutine.classify_tier()`, coordinator `async_setup()` or `_async_update_data` | See detailed analysis in "Startup Tier Rehydration" section below |
| **Correlation window as config parameter** | Users need at least one knob to tune correlation sensitivity (how many seconds apart do events need to be to count as co-occurring) | Low | `config_flow.py` options flow, `const.py` for new config key, config migration v8->v9 | Single integer field, default 120 seconds. Follows established `setdefault` migration pattern. |
| **Config migration v8->v9** | Any new config keys require a migration step so existing installs upgrade cleanly. | Low | Established migration chain (v2->v3->...->v8). Mechanical pattern copy. | Non-negotiable. Every prior milestone has included this. |

---

## Differentiators

Features that go beyond the minimum. Not expected, but valued.

| Feature | Value Proposition | Complexity | Dependencies on Existing | Notes |
|---------|-------------------|------------|--------------------------|-------|
| **Directional correlation (A triggers B, not B triggers A)** | Captures causal ordering: motion sensor triggers light, not light triggers motion. Reduces false correlation alerts by only alerting when the *leading* entity fires without the follower. | Medium | Event timestamp ordering within correlation window | Enriches alert quality. Can be added as a layer on top of bidirectional co-occurrence counting. |
| **Correlation confidence scoring** | Not all co-occurrences are equally reliable. Expose a confidence metric per group so alerts from strong correlations rank higher in severity. | Low | Event count per correlation pair, consistency ratio | Analogous to existing per-entity `confidence()` method; reuse pattern. |
| **Correlation group decay** | Remove stale correlations when behavior changes (new appliance replaces old one, room repurposed). | Low | Recency weighting on co-occurrence counts, analogous to drift detector's exponential decay | Without decay, removed or replaced entities pollute correlation groups indefinitely. |
| **Minimum learning period before correlation alerts fire** | Prevent false correlation alerts during the first days when co-occurrence counts are low and noisy. | Low | Existing `learning_status()` and confidence gate pattern | Analogous to `MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME` gate on acute detection. |

---

## Anti-Features

Features to explicitly NOT build in this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **User-defined correlation groups** | Defeats the core value of automatic discovery; adds config UI complexity for a feature most users cannot configure correctly | Auto-discover only; let users inspect via sensor attributes and suppress via holiday/snooze modes |
| **Causal inference (Granger causality, interventional analysis)** | Statistically complex and fragile with small sample sizes; requires long observation windows | Stick with temporal co-occurrence within a window; label it "correlation" not "causation" in all UI text |
| **Cross-entity drift detection (correlation strength changing over weeks)** | Drift detection for single entities already exists via CUSUM; extending to pair-level drift doubles complexity for marginal value in v4.0 | Defer to future milestone; correlation decay handles the simplest case of stale correlations |
| **ML-based correlation discovery (clustering, graph neural networks, FP-growth)** | Violates pure-Python / no-dependency constraint; overkill for a home with 5-30 entities | Pairwise co-occurrence counting with a time window; O(N) per event where N < 100 |
| **Per-pair correlation sensitivity tuning in config UI** | Per-entity sensitivity is already out of scope per PROJECT.md; per-pair is even more granular | Single global correlation window parameter. Per-pair tuning is future work. |
| **Time-of-day scoped correlations** | Morning routine correlations (kettle + kitchen motion) differ from evening (TV + living room motion); slot-aware correlation would extend the 168-slot model to pair-level, causing significant storage and computation increase | Global correlation (any time of day) covers the primary use case. Defer slot-scoped correlation to future milestone. |
| **Real-time streaming correlation engine** | The coordinator already buffers via 60-second polling interval; adding a streaming layer conflicts with the existing DataUpdateCoordinator pattern | Process correlation in `_handle_state_changed` (event recording) and `_run_detection` (alert checking), matching the existing architecture |

---

## Feature Dependencies

```
Startup Tier Rehydration (independent, no dependency on correlation features)
  -- standalone fix, can be done first or in parallel

Correlation Window Config Parameter
  --> Config Migration v8->v9

Auto-discover Correlation Groups
  --> Expose Correlation Groups as Sensor Attributes (requires groups to exist)
  --> Alert on Broken Correlations (requires groups + minimum count threshold)
      --> Correlation Confidence Scoring (enriches alert severity)
      --> Directional Correlation (enriches alert targeting, optional layer)

Correlation Group Decay
  -- can be added independently after groups exist

Minimum Learning Period for Correlations
  -- gates alerting, independent of discovery
```

**Critical path:** Tier Rehydration Fix (parallel) | Correlation Discovery -> Sensor Exposure -> Break Alerting -> Config/Migration

---

## Correlation Discovery Algorithm (Recommended Approach)

The research literature on smart home co-occurrence mining (CoPMiner, temporal pattern mining via Allen's temporal relations, FP-growth) targets large-scale datasets with hundreds of sensor types and thousands of events per second. For a home with 5-30 monitored entities and events measured in dozens per hour, a much simpler approach is appropriate and correct.

**Pairwise co-occurrence counting with a time window:**

1. On each state change event for entity A at time T (in `_handle_state_changed`), scan `_last_seen` for all other monitored entities B where `T - last_seen[B] < correlation_window` (default 120s).
2. Increment `co_occurrence_count[frozenset({A, B})]` (unordered pair for bidirectional; can add ordered pair tracking later for directionality).
3. Track `total_events[A]` (total state changes per entity) separately.
4. Correlation strength for pair {A, B} = `co_occurrence_count[{A, B}] / min(total_events[A], total_events[B])`. Using `min` means the pair strength reflects what fraction of the *less active* entity's events are accompanied by the other.
5. Pairs with strength above a threshold (e.g., 0.5) and minimum count (e.g., 10 co-occurrences) are declared correlated.

**Complexity:** O(N) per event where N = number of monitored entities (scan `_last_seen`). For N < 100 this is trivially fast -- sub-microsecond.

**Architecture:** Create a `CorrelationTracker` class in a new `correlation_tracker.py` file. Pure Python, zero HA imports, independently testable -- matching the pattern of `RoutineModel`, `AcuteDetector`, `DriftDetector`. Wire into coordinator via `_handle_state_changed` (recording) and `_run_detection` (alert generation). Serialize co-occurrence counts into existing `.storage` file alongside routine_model and cusum_states.

**Alert generation:** In `_run_detection`, for each entity that has been seen recently (within the last correlation window), check if its correlated partners have also been seen. If entity A fired but correlated entity B has not fired within the window, produce an `AlertResult` with `AlertType.CORRELATION_BREAK`. Apply sustained-evidence gating (3 consecutive cycles without the partner firing).

**Confidence:** MEDIUM -- algorithm design is straightforward but thresholds (window size, minimum count, strength threshold) will need tuning against real household data. The 120-second default window and 0.5 strength threshold are reasonable starting points based on typical smart home entity behavior (motion triggers light within seconds, door open triggers hallway motion within 30 seconds).

---

## Startup Tier Rehydration (Detailed Analysis)

### The Problem As Stated

From PROJECT.md: "Fix startup tier rehydration -- classify tiers on first update cycle, not just at midnight."

### Code Analysis

`_activity_tier` on `EntityRoutine` is declared with `field(default=None, init=False, repr=False)` (routine_model.py L245-246). This means after `EntityRoutine.from_dict()` deserialization, `_activity_tier` is always `None` regardless of the entity's data richness. Similarly, `_tier_classified_date` starts as `None`.

In `coordinator.py` `_async_update_data()` (L180-190):
```python
if self._today_date != now.date():
    self._today_count = 0
    self._today_date = now.date()
    for r in self._routine_model._entities.values():
        r.classify_tier(now)
    if self._activity_tier_override != "auto":
        ...
```

On first call after startup, `self._today_date` is `None`, so `None != date(2026, 4, 3)` is `True`. The guard triggers, and `classify_tier(now)` is called for all entities.

Inside `classify_tier()` (routine_model.py L381-423):
- Confidence gate: returns early if `confidence(now) < 0.8`. After deserialization of a mature entity with `first_observation` set, `confidence()` returns a value based on elapsed days vs `history_window_days` -- this should be >= 0.8 for any entity with 22+ days of data (given default 28-day window).
- Once-per-day guard: `_tier_classified_date == now.date()` is `None == date(...)` = `False`, so this does NOT short-circuit.
- Result: `classify_tier()` should successfully classify tiers on first `_async_update_data` call.

### So What Is The Actual Bug?

The stated gap is valid but the mechanism is more subtle than "tiers only classify at midnight." Possible actual failure modes:

1. **Race between `async_setup` and first `_async_update_data`**: If sensors render before the first coordinator update completes, they see `_activity_tier = None` in `entity_status` attributes. The fix is to classify tiers in `async_setup()` after data restoration, before the first coordinator update cycle.

2. **Entities not meeting the 0.8 confidence threshold**: Newer entities (< 22 days old with 28-day window) will have `None` tiers even after `classify_tier()`. This is by design but means tiers are absent for a significant learning period.

3. **`_async_update_data` not called immediately**: The DataUpdateCoordinator's first call is scheduled by HA, not called synchronously during setup. There is a window between `async_setup()` completing and the first `_async_update_data()` running where sensors are live but tiers are `None`.

### Recommended Fix

Move tier classification to `async_setup()` after data restoration, making it explicit and immediate:

```python
async def async_setup(self) -> None:
    stored = await self._store.async_load()
    if stored:
        # ... existing restoration code ...
    elif not self._routine_model._entities:
        await self._bootstrap_from_recorder()
        await self._save_data()

    # Rehydrate tiers immediately after data restoration
    now = dt_util.now()
    for r in self._routine_model._entities.values():
        r.classify_tier(now)
    if self._activity_tier_override != "auto":
        override_tier = ActivityTier(self._activity_tier_override)
        for r in self._routine_model._entities.values():
            r._activity_tier = override_tier

    self._unsub_state_changed = self.hass.bus.async_listen(...)
```

This is defensive and documents intent clearly. The date-change guard in `_async_update_data` still handles daily reclassification. **Complexity: Low.**

---

## MVP Recommendation

**Must ship (table stakes for v4.0):**

1. **Startup tier rehydration** -- Low complexity, standalone bug fix. Classify tiers in `async_setup()` after data restoration. Independent of correlation work.

2. **Auto-discover correlated entity groups** -- Core feature. New `CorrelationTracker` pure-Python class. Pairwise co-occurrence counting with configurable time window. Wire into coordinator's state change handler and detection loop.

3. **Expose discovered groups as sensor attributes** -- Low complexity once groups exist. Populate the existing empty `cross_sensor_patterns` list in `_build_sensor_data`.

4. **Alert on broken correlations** -- The payoff feature. New `AlertType.CORRELATION_BREAK`. Sustained-evidence gating. Integration with existing alert suppression and severity gating.

5. **Correlation window config parameter + migration v8->v9** -- Single integer field, follows established pattern.

**Strongly recommended (low-cost, high-value):**

6. **Correlation confidence scoring** -- Low complexity, improves alert quality.
7. **Minimum learning period for correlation alerts** -- Prevents false alerts during ramp-up.
8. **Correlation group decay** -- Prevents stale groups from accumulating.

**Defer to future milestone:**

- **Time-of-day scoped correlations**: High complexity, marginal initial value. Global correlations cover the primary use case.
- **Directional correlation**: Medium complexity enrichment. Bidirectional is sufficient for v4.0.
- **Cross-entity drift detection**: CUSUM extension adds complexity without proportional value.

---

## Confidence Assessment

| Finding | Confidence | Basis |
|---------|-----------|-------|
| Pairwise co-occurrence counting is sufficient for home-scale entities | HIGH | Direct analysis: 5-30 entities means at most ~435 pairs. FP-growth/graph algorithms are overkill. |
| 120-second default correlation window is reasonable | MEDIUM | Typical smart home latencies (motion->light, door->hallway) are 1-30 seconds. 120s accommodates slower chains. Needs real-world validation. |
| Correlation strength threshold of 0.5 is reasonable | LOW | No empirical data for this specific use case. Threshold selection will need tuning. |
| `CorrelationTracker` as separate pure-Python class is correct architecture | HIGH | Follows established pattern (RoutineModel, AcuteDetector, DriftDetector). HA-free, independently testable. |
| Tier rehydration fix in `async_setup()` is correct | HIGH | Direct code analysis of coordinator lifecycle. Eliminates race between setup and first update. |
| `cross_sensor_patterns` placeholder already exists | HIGH | Direct code inspection: coordinator.py L325 and L338. |
| Sustained-evidence gating applies to correlation alerts | HIGH | Existing pattern proven across inactivity and unusual-time detection. Same rationale applies. |
| Config migration v8->v9 is needed | HIGH | Every milestone with new config keys has required migration. Established pattern. |

---

## Sources

- Direct code analysis: `coordinator.py`, `routine_model.py`, `acute_detector.py`, `const.py`, `sensor.py` in existing codebase (HIGH confidence)
- [Mining Correlation Patterns among Appliances in Smart Home Environment](https://link.springer.com/chapter/10.1007/978-3-319-06605-9_19) -- CoPMiner algorithm for appliance correlation patterns
- [Activity Pattern Mining using Temporal Relationships in a Smart Home](https://ieeexplore.ieee.org/document/6583073/) -- temporal relations improve pattern discovery accuracy
- [Temporal Pattern Discovery for Anomaly Detection in a Smart Home](https://ieeexplore.ieee.org/document/4449955) -- Allen temporal relations applied to smart home anomaly detection
- [On Co-occurrence Pattern Discovery from Spatio-temporal Event Stream](https://link.springer.com/chapter/10.1007/978-3-642-41154-0_29) -- sliding window co-occurrence algorithms
- [HA Community: Entity correlation with ML](https://community.home-assistant.io/t/automatically-switch-entities-based-on-past-observations-learning-entity-correlations-with-machine-learning/976268) -- existing HA custom integration for entity correlation (ML-based, different approach)
- [Restoring An Entity on Home Assistant Restart](https://aarongodfrey.dev/programming/restoring-an-entity-in-home-assistant/) -- HA entity state restoration patterns
- [Significant Correlation Pattern Mining in Smart Homes](https://www.academia.edu/105265564/Significant_Correlation_Pattern_Mining_in_Smart_Homes) -- correlation pattern mining methodologies
