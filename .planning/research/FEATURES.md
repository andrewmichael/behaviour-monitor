# Feature Landscape: v3.1 Activity-Rate Classification & Display Formatting

**Domain:** Home Assistant behaviour monitoring -- activity-rate tiering and display fixes
**Researched:** 2026-03-28
**Milestone:** v3.1
**Scope:** NEW features only. Existing features (CV-adaptive thresholds, sustained evidence gating, fire-once suppression, weekday/weekend drift, recency-weighted baseline, config UI) are already shipped and not re-documented here.

---

## Table Stakes

Features that must ship for the milestone to deliver its stated goal: "eliminate false-positive inactivity alerts on high-frequency entities."

| Feature | Why Expected | Complexity | Dependencies on Existing | Notes |
|---------|-------------|------------|--------------------------|-------|
| **Auto-classify entities into frequency tiers** | Without classification, all entities share the same inactivity multiplier logic. A motion sensor firing 200x/day gets the same threshold math as a door sensor firing 5x/day -- this is the root cause of the false-positive problem on high-frequency entities. | Medium | `EntityRoutine.daily_activity_rate()` and `ActivitySlot.expected_gap_seconds()` already provide the raw data. No new storage schema needed -- classification is derived from existing slot data. | Three tiers (high/medium/low) based on median daily event count across observed days. Recomputed from persisted routine data on startup, at most once per day thereafter. |
| **Tier-appropriate inactivity detection with absolute minimum floor** | Classification alone does nothing -- it must feed different detection parameters. High-frequency entities need an absolute minimum time floor so that a 30-second expected gap does not trigger an alert after 90 seconds (3x multiplier). | Medium | `AcuteDetector.check_inactivity()` currently applies uniform multiplier logic. Must branch on tier. `_min_multiplier` / `_max_multiplier` bounds already exist as scaffolding. | The absolute floor is the critical piece. Arithmetic: 30s gap x 3x multiplier = 90s threshold. No amount of multiplier tuning fixes this without a floor. A floor of ~300s (5 min) prevents this entire class of false positive. |
| **Fix alert display formatting (minutes vs hours)** | Current `acute_detector.py` L122-123 always formats as hours (`{elapsed_hours:.1f}h`). For a high-frequency entity with typical interval 6 minutes, alert reads "typical interval: 0.1h" -- confusing and unprofessional. | Low | `AlertResult.explanation` string in `AcuteDetector.check_inactivity()`. Pure string formatting change. `coordinator.py` L283-288 already handles this correctly for sensor attributes (`ts_fmt`, `typ_fmt`). | Format as seconds when < 60s, minutes when < 1 hour, hours+minutes otherwise. |
| **User override for tier assignment in config UI** | Auto-classification will sometimes misclassify (e.g., motion sensor in rarely-used room classifies as "low" but user knows it is high-frequency by nature). Users need an escape hatch. | Medium | `config_flow.py` options flow, `const.py` for new config keys, config migration v7->v8, `translations/en.json`. Follows established `setdefault` migration pattern. | Global default tier override or per-tier multiplier adjustment. NOT per-entity (explicitly out of scope per PROJECT.md). |
| **Config migration v7->v8** | Any new config keys require a migration step so existing installs upgrade cleanly. | Low | Existing `setdefault` migration pattern (v4->v5, v6->v7) is well-established. Mechanical copy of the pattern. | Non-negotiable. Every prior milestone has included this. |

---

## Differentiators

Features that go beyond the minimum. Not strictly required for the false-positive fix, but add meaningful value at low cost.

| Feature | Value Proposition | Complexity | Dependencies on Existing | Notes |
|---------|-------------------|------------|--------------------------|-------|
| **Activity tier as sensor attribute** | Expose each entity's computed tier (high/medium/low) as an attribute on the entity status sensor so users can see the classification and debug issues. | Low | `_build_sensor_data()` in `coordinator.py` already builds `entity_status` list with per-entity dicts. Add a `tier` key. | Near-free to implement. Critical for user trust -- if users cannot see what tier an entity was assigned, they cannot understand why alert behavior changed. Strongly recommended. |
| **Shared interval formatting utility** | Extract a single `format_interval(seconds)` function used by both `acute_detector.py` (alert explanations) and `coordinator.py` (sensor attributes). | Low | Currently formatting logic is duplicated: `coordinator.py` L283-288 does `"{h}h {m}m"` / `"{m}m"`, while `acute_detector.py` L113-114 hardcodes `{:.1f}h`. | Good engineering practice. Eliminates duplication and prevents future formatting drift. Could live in a small `formatting.py` util or in `const.py`. |
| **Tier-specific sustained evidence cycles** | High-frequency entities could require more consecutive cycles (e.g., 5 instead of 3) before firing an alert, further reducing false positives for chatty sensors. | Low | `AcuteDetector._sustained_cycles` is already per-instance. Would need to become per-entity or per-tier lookup. | Belt-and-suspenders. The absolute floor alone likely solves 90%+ of false positives. Worth considering only if floor proves insufficient in testing. |
| **Tier transition logging** | Log when an entity's auto-classified tier changes (e.g., motion sensor moves from "high" to "medium" because usage dropped). Helps users understand system behavior. | Low | Debug-level `_LOGGER.info()` call wherever classification runs. | Debug-level only, not a notification. Useful for troubleshooting but not user-facing. |
| **Higher effective multiplier for high-frequency tier** | Apply a tier-specific multiplier boost (e.g., 1.5x the configured multiplier for high-frequency entities) in addition to the absolute floor. | Low | `AcuteDetector.check_inactivity()` -- multiply `self._inactivity_multiplier` by a tier factor before computing threshold. | Useful but secondary to the floor. The floor handles the catastrophic case (90s alerts); the multiplier boost handles the marginal case (5-minute alerts that are still too sensitive). |

---

## Anti-Features

Features to explicitly NOT build in this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Per-entity tier override in config UI** | PROJECT.md explicitly lists "per-entity sensitivity tuning UI" as out of scope. A per-entity dropdown for 20+ entities creates UI complexity and maintenance burden. | Global tier parameters (multiplier overrides per tier or tier boundary thresholds) in the options flow. |
| **ML-based classification** | Hard constraint: pure Python, no external dependencies. Any ML classifier violates this. A simple event-rate heuristic is sufficient and fully interpretable. | Median daily event count with fixed boundaries. Transparent, debuggable, no black box. |
| **Dynamic tier reassignment every cycle** | Reclassifying entities every 60-second polling cycle creates instability -- an entity could oscillate between tiers during quiet hours vs active hours. | Classify on startup from stored routine data, reclassify at most once per day. Tier should be stable over hours/days, not minutes. |
| **Separate notification channels per tier** | Over-engineering. Users already have notification cooldown, severity gating, and fire-once suppression. Tier-based notification routing adds complexity without demonstrated user demand. | Existing severity-based gating handles notification volume. Tier affects detection parameters, not notification routing. |
| **Tier-specific drift detection parameters** | Drift detection (CUSUM) operates on daily activity rates, not inter-event intervals. The false-positive problem is specific to acute inactivity detection. Changing CUSUM parameters per tier adds complexity for no benefit. | Leave drift detection unchanged. The problem being solved is acute inactivity false positives on high-frequency entities only. |
| **Configurable tier boundary thresholds** | Premature. Sensible defaults should work for most users. Adding 2 more config fields (high/low boundary) increases config complexity. | Ship with fixed defaults. Add configurability only if user feedback demonstrates the defaults are wrong for common setups. |

---

## Feature Dependencies

```
Auto-classify entities into tiers
    --> Tier-appropriate inactivity detection (requires tier to branch logic)
    --> Activity tier as sensor attribute (requires tier to expose)
    --> User override for tier (requires tier concept to exist)
    --> Config migration v7->v8 (required if new config keys added)

Fix alert display formatting
    (independent -- no dependency on tier work)
    --> Shared formatting utility (optional extraction, improves code quality)

Config migration v7->v8
    <-- User override for tier (new config keys need migration)
```

**Critical path:** Auto-classify -> Tier-appropriate detection -> Testing. Display formatting is independent and can be done in parallel.

---

## Classification Design

### Tier Definitions

| Tier | Typical Entities | Median Daily Events | Inactivity Behavior |
|------|-----------------|--------------------|--------------------|
| **High** | Motion sensors, power monitors, climate sensors, energy meters | >50/day | Expected gap is seconds to low minutes. Needs absolute minimum floor (e.g., 300s). Without floor, multiplier math produces thresholds of 1-2 minutes -- too short. |
| **Medium** | Door/window sensors, light switches, appliance toggles | 5-50/day | Expected gap is minutes to low hours. Current detection logic works well here. This is the "default" tier -- no parameter changes needed. |
| **Low** | Rarely-used doors, seasonal devices, guest room sensors | <5/day | Expected gap is hours to days. Existing CV-adaptive logic already inflates thresholds for high-variance slots. No special handling needed. |

### Classification Algorithm

1. For each entity, compute `daily_activity_rate()` across the last 7-14 observed days (use the day-of-week slots already stored in `EntityRoutine`).
2. Take the **median** daily count (not mean -- robust to outlier days like a party or a sick day).
3. Apply fixed boundaries: >50 = high, 5-50 = medium, <5 = low.
4. Classify on startup from persisted routine data. Reclassify at most once per day (e.g., at midnight or on config reload).
5. Store tier assignment in memory only (derived from existing data, no new persistence needed).

Median is consistent with existing `expected_gap_seconds()` which already uses median inter-event intervals.

### High-Frequency Inactivity Detection Changes

Two changes to `AcuteDetector.check_inactivity()` for high-frequency tier:

1. **Absolute minimum floor**: Regardless of computed threshold, never alert unless gap exceeds a minimum duration (default 300s / 5 minutes). This is the primary fix -- it makes it mathematically impossible to get sub-minute inactivity alerts.
2. **Optional multiplier boost**: Apply a tier-specific multiplier factor (e.g., 1.5x) on top of the user-configured multiplier for high-frequency entities. Secondary to the floor.

### Display Formatting Logic

```python
def format_interval(seconds: float) -> str:
    """Format a time interval for human display."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}h {m}m" if m else f"{h}h"
```

This matches the pattern already used in `coordinator.py` L283-288. Extract as shared utility, apply to `AcuteDetector` alert explanations (replacing hardcoded `{:.1f}h` format).

---

## MVP Recommendation

**Must ship (table stakes):**
1. Auto-classify entities into frequency tiers -- foundation for everything else
2. Tier-appropriate inactivity detection with absolute minimum floor -- the actual false-positive fix
3. Fix alert display formatting -- low effort, high visibility improvement
4. Config migration for any new keys

**Strongly recommended (low-cost, high-value):**
5. Activity tier as sensor attribute -- near-free, critical for debuggability and user trust
6. Shared interval formatting utility -- prevents code duplication

**Defer:**
- Configurable tier thresholds: ship with sensible defaults, add configurability only if users request it
- Tier-specific sustained evidence cycles: belt-and-suspenders; floor likely sufficient
- Per-entity tier override: explicitly out of scope per PROJECT.md
- Higher effective multiplier for high tier: secondary to floor; add only if floor alone proves insufficient

---

## Confidence Assessment

| Finding | Confidence | Basis |
|---------|-----------|-------|
| Tiered classification solves false positives | HIGH | Direct arithmetic analysis of existing `check_inactivity()`: uniform multiplier + tiny expected gaps = absurdly short thresholds |
| Three tiers (high/medium/low) sufficient | MEDIUM | Common pattern in IoT monitoring literature; no evidence more tiers adds value here |
| Absolute minimum floor is critical fix | HIGH | Arithmetic proof: 30s gap x 3x multiplier = 90s threshold. No multiplier tuning fixes this without a floor |
| Median daily count as classification metric | HIGH | `daily_activity_rate()` already exists; median robust to outlier days; consistent with existing median-based gap |
| Display formatting as minutes when < 1h | HIGH | Direct code inspection: `acute_detector.py` L122-123 hardcodes hours; `coordinator.py` already does the right thing |
| Tier boundaries (50/5 events/day) | LOW | Reasonable defaults but no empirical validation yet. May need adjustment after real-world testing |
| No drift detection changes needed | HIGH | CUSUM operates on daily rates, not inter-event intervals; the false-positive problem is acute-detection-specific |

---

## Sources

- Direct code analysis: `acute_detector.py`, `coordinator.py`, `routine_model.py`, `const.py` in existing codebase (HIGH confidence)
- [HA Community: Debouncing binary sensors](https://community.home-assistant.io/t/debouncing-binary-sensory/111833) -- community patterns for high-frequency binary sensor handling
- [HA Community: Filtering motion detection](https://community.home-assistant.io/t/filtering-motion-detected/590359) -- real-world false positive complaints
- [Effective Anomaly Detection by Integrating Event Time Intervals](https://www.sciencedirect.com/science/article/pii/S1877050922015757) -- time-interval-based anomaly detection with frequency awareness
- [IoT anomaly detection methods survey](https://www.sciencedirect.com/science/article/pii/S2542660522000622) -- adaptive threshold approaches for heterogeneous sensor types
- [Activity and Anomaly Detection in Smart Home survey](https://link.springer.com/chapter/10.1007/978-3-319-21671-3_9) -- frequency-based activity classification patterns in smart homes
- [Home Assistant Statistics integration](https://www.home-assistant.io/integrations/statistics/) -- HA's own approach to sensor data frequency handling
