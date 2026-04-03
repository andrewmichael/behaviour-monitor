# Technology Stack — v4.0 Cross-Entity Correlation & Startup Tier Rehydration

**Project:** Behaviour Monitor v4.0
**Researched:** 2026-04-03
**Confidence:** HIGH
**Scope:** Stack additions/changes for NEW features only. Existing stack (RoutineModel, AcuteDetector, DriftDetector, config flow v8, storage v8) is validated and unchanged.

---

## Summary Decision

**No new external dependencies.** Both features (cross-entity correlation discovery/break detection, startup tier rehydration) are implementable with Python stdlib modules already in use (`math`, `statistics`, `collections`, `dataclasses`, `itertools`, `datetime`). The correlation engine reads existing `event_times` deques from `ActivitySlot` — no new data collection path is required. The tier rehydration fix is a 1-line logic change.

---

## Recommended Stack

### Core Technologies (Unchanged)

| Technology | Version | Purpose | v4.0 Role |
|------------|---------|---------|-----------|
| Python stdlib `math` | 3.11+ (HA-bundled) | `log2` | PMI calculation for co-occurrence scoring |
| Python stdlib `statistics` | 3.11+ (HA-bundled) | `median` | Median lag computation between correlated pairs |
| Python stdlib `collections` | stdlib | `defaultdict`, `deque` | Co-occurrence counting per time window; bounded event buffers |
| Python stdlib `itertools` | stdlib | `combinations` | Generate entity pairs from monitored list (N*(N-1)/2 pairs) |
| Python stdlib `dataclasses` | stdlib | `@dataclass` | New `CorrelationPair`, `CorrelationGroup` structures |
| Python stdlib `datetime` | stdlib | Timestamp math | Time window membership checks |
| `homeassistant.helpers.storage.Store` | HA-bundled | JSON persistence | Extend existing save dict with correlation state |

### New Internal Components (Zero External Dependencies)

| Component | Location | What It Does | Data Source |
|-----------|----------|-------------|-------------|
| `CorrelationDetector` class | `correlation_detector.py` (new) | Discovers co-occurring entity pairs; detects correlation breaks | Existing `event_times` deques in `ActivitySlot` |
| `CorrelationPair` dataclass | `correlation_detector.py` | Stores PMI score, co-occurrence count, median lag per pair | Computed from `event_times` |
| `AlertType.CORRELATION_BREAK` | `alert_result.py` | New enum value for correlation break alerts | -- |
| Tier rehydration fix | `routine_model.py` | Allow retry when `_activity_tier is None` | Existing `_tier_classified_date` guard |

---

## Algorithm: Co-Occurrence Detection via Temporal PMI

### Why PMI Over Alternatives

Three candidate metrics were evaluated for co-occurrence scoring:

| Metric | Formula | Pros | Cons | Verdict |
|--------|---------|------|------|---------|
| **Raw count** | count(A and B in window) | Simple | Biased toward high-frequency entities; a busy motion sensor "correlates" with everything | Rejected |
| **Jaccard index** | intersection/union of active time slots | Normalized [0,1] | Does not account for base rates; two always-active entities get high Jaccard spuriously | Rejected |
| **Pointwise Mutual Information (PMI)** | log2(P(A,B) / (P(A) * P(B))) | Normalizes for base rates; positive PMI = genuine co-occurrence above chance; works naturally with activity tiers | **Selected** |

**Why PMI is the right fit:**
- Normalizes for entity frequency tiers. A HIGH-tier motion sensor (50 events/day) and a LOW-tier door sensor (4 events/day) that genuinely co-occur will score high. Two HIGH-tier sensors that fire independently will score near zero despite both being very active.
- The math is trivial: `math.log2`, division, counting. All stdlib.
- Computable directly from existing `event_times` deques — no new data recording needed.
- Well-established in co-occurrence literature (NLP, ecology, smart home event mining).

**Confidence: HIGH** — PMI is the standard co-occurrence metric when base-rate normalization matters. Multiple research sources confirm its suitability for event stream co-occurrence.

### PMI Formula for This Domain

```
PMI(A, B) = log2( P(A and B fire within window) / (P(A fires in slot) * P(B fires in slot)) )
```

Where:
- **P(A fires in slot)** = fraction of time slots (168 total) where entity A has events
- **P(B fires in slot)** = fraction of time slots where entity B has events
- **P(A and B fire within window)** = fraction of time slots where both A and B have events within `CO_OCCURRENCE_WINDOW_SECONDS` of each other

**Interpretation:**
- PMI > 0: entities co-occur more than chance
- PMI > 1.0: 2x more likely than chance (minimum threshold for "correlated")
- PMI > 2.0: 4x more likely than chance (strong association)

### Data Structures

```python
@dataclass
class CorrelationPair:
    """Learned co-occurrence relationship between two entities."""
    entity_a: str
    entity_b: str
    pmi_score: float            # PMI value (> 0 = positive correlation)
    co_occurrence_count: int    # Raw count of co-occurrences in window
    total_slots_checked: int    # Denominator for probabilities
    median_lag_seconds: float   # Typical time offset between A and B firing
    last_computed: str          # ISO timestamp of last recomputation
```

Follows existing codebase pattern: pure Python dataclass with `to_dict()`/`from_dict()` serialization.

**No `CorrelationGroup` dataclass is needed initially.** Groups are simply entity pairs with PMI above threshold. Exposing them as a list of pairs in `cross_sensor_patterns` is sufficient for v4.0. Group clustering can come later if users need it.

### Constants

```python
CO_OCCURRENCE_WINDOW_SECONDS: int = 300  # 5 minutes
MIN_CO_OCCURRENCES: int = 10             # Minimum pair observations before scoring
PMI_THRESHOLD: float = 1.0              # PMI > 1.0 = 2x more likely than chance
```

**Window rationale:** Smart home events that are causally related (motion triggers light, door opens then hallway motion fires) typically occur within 1-5 minutes. 300 seconds captures the vast majority of causal chains while excluding coincidental overlap.

**MIN_CO_OCCURRENCES rationale:** Prevents premature pair creation from insufficient data. With 28 days of history and 168 slots, 10 co-occurrences means the pair fires together in at least ~6% of its active slots — a reasonable minimum for statistical significance.

All constants are internal (not user-facing config). They live in `const.py` following the existing `TIER_BOUNDARY_HIGH` / `TIER_BOUNDARY_LOW` pattern.

### Computation Strategy: Batch Daily, Not Real-Time

**Do NOT compute correlations on every state change.** Reasons:
1. `_handle_state_changed` must stay fast (it triggers `async_request_refresh`)
2. PMI requires scanning all event_times — O(slots x events) per entity pair
3. Correlations are stable day-to-day properties

**Instead:** Recompute correlations once per day, in the existing daily block in `_async_update_data()`:

```python
if self._today_date != now.date():
    self._today_count = 0
    self._today_date = now.date()
    for r in self._routine_model._entities.values():
        r.classify_tier(now)
    # NEW: recompute correlation pairs daily
    self._correlation_detector.recompute(self._routine_model, now)
```

This mirrors the proven daily-recomputation pattern from `classify_tier()`.

**Confidence: HIGH** — Follows established coordinator pattern. No new scheduling mechanism.

### Computational Complexity

With N monitored entities (typical: 10-50):
- Pairs to check: N*(N-1)/2 = 45 (N=10) to 1,225 (N=50)
- Per pair: scan event_times across 168 slots, compare timestamps within window
- Each slot has at most 56 timestamps (deque maxlen)
- Worst case: 1,225 pairs x 168 slots x 56 timestamps = ~11.5M comparisons
- In practice much less (most slots are empty for most entities)
- Easily sub-second on any hardware running Home Assistant

**Why NOT graph-based community detection:** At N<50, the complete pair enumeration is trivial. Graph algorithms (Louvain, etc.) require NetworkX or similar, violating the no-dependency constraint, and add complexity unnecessary at this scale.

---

## Algorithm: Correlation Break Detection

When a learned correlation breaks, the detection follows the existing sustained-evidence pattern from `AcuteDetector`:

1. Entity A fires (state change observed in `_handle_state_changed`)
2. Coordinator records the timestamp
3. On the next update cycle (60s), check: did entity B fire within `CO_OCCURRENCE_WINDOW_SECONDS` of entity A?
4. If not, increment a sustained-evidence counter for this pair
5. Fire `AlertType.CORRELATION_BREAK` only after `SUSTAINED_EVIDENCE_CYCLES` (3) consecutive missed co-occurrences

**Why sustained evidence, not single-miss:** A single missed co-occurrence is normal noise. Someone might open the door without turning on the hallway light occasionally. Three consecutive misses of a learned strong correlation (PMI > 1.0) is genuinely unusual.

### New AlertType

```python
class AlertType(str, Enum):
    INACTIVITY = "inactivity"
    UNUSUAL_TIME = "unusual_time"
    DRIFT = "drift"
    CORRELATION_BREAK = "correlation_break"  # NEW
```

**Confidence: HIGH** — Directly extends existing enum. No architectural novelty.

### Break Detection State

```python
# Per-pair break tracking (in CorrelationDetector)
_break_cycles: dict[tuple[str, str], int]  # (entity_a, entity_b) -> consecutive miss count
_pending_checks: dict[str, datetime]       # entity_id -> when it fired, awaiting companion
```

The `_pending_checks` dict is populated in the coordinator's `_handle_state_changed` callback (O(1) dict insert) and evaluated in `_run_detection` (O(pairs) lookup). This is the only real-time overhead — a dict insert per state change.

---

## Startup Tier Rehydration Fix

### Problem Analysis

`classify_tier()` has a once-per-day guard:
```python
if self._tier_classified_date == now.date():
    return
```

On startup, `_tier_classified_date` is `None` (not persisted), so the first call works. The coordinator calls `classify_tier()` inside the daily date-change block, which fires on first update since `_today_date` starts as `None`.

**The actual gap:** If `confidence < 0.8` at startup (fresh install or short history), `classify_tier()` sets `_activity_tier = None` and sets `_tier_classified_date = now.date()`. Once set, it won't retry until tomorrow — even if confidence crosses 0.8 during the day as new events arrive.

### Fix

One-line change in `classify_tier()`:

```python
# Allow retry when currently unclassified, even if already attempted today
if self._tier_classified_date == now.date() and self._activity_tier is not None:
    return
```

**Cost:** At most one extra median computation per entity per day (for entities that never reach 0.8 confidence). Negligible.

**Stack impact: None.** No new modules, no new data structures, no new dependencies.

**Confidence: HIGH** — Direct code analysis. The fix is a conditional guard refinement.

---

## Integration Points with Existing Architecture

### New File: `correlation_detector.py`

Following the established one-detector-per-file pattern:
- `acute_detector.py` — inactivity + unusual-time
- `drift_detector.py` — CUSUM drift
- **`correlation_detector.py`** — co-occurrence discovery + break detection

Pure Python, zero HA imports. Takes `RoutineModel` and entity state as input. Produces `AlertResult` objects. Serializable via `to_dict()`/`from_dict()`.

### Coordinator Wiring (`coordinator.py`)

```
Changes needed:
  1. Import CorrelationDetector
  2. Instantiate in __init__
  3. Daily recompute in date-change block
  4. Check breaks in _run_detection loop
  5. Track pending co-occurrence checks from _handle_state_changed
  6. Add correlation state to _save_data() / async_setup() persistence
  7. Populate cross_sensor_patterns in _build_sensor_data()
```

### Sensor Data

The existing `cross_sensor_patterns: []` placeholder in both `_build_sensor_data()` and `_build_safe_defaults()` is the natural home for correlation data. No new sensor entity IDs needed — this populates the existing attribute.

```python
"cross_sensor_patterns": [
    {
        "entities": [pair.entity_a, pair.entity_b],
        "pmi_score": round(pair.pmi_score, 2),
        "co_occurrence_count": pair.co_occurrence_count,
        "median_lag_seconds": round(pair.median_lag_seconds, 1),
    }
    for pair in self._correlation_detector.learned_pairs
]
```

### Persistence

Add to the existing `_save_data()` dict:
```python
"correlation": self._correlation_detector.to_dict()
```

Follows the existing pattern alongside `routine_model` and `cusum_states` keys. The `async_setup()` loader handles a missing `"correlation"` key gracefully (empty state = no learned correlations yet, same as first boot).

### Config Flow

**No new config options for v4.0.** The co-occurrence window, PMI threshold, and minimum co-occurrence count are internal constants. User-facing tuning can come later if needed.

### Config Migration

**No migration needed.** The correlation detector state is additive (absent = no learned correlations). STORAGE_VERSION stays at 8 since no schema change is required — the loader simply ignores missing keys.

---

## What NOT to Add

| Temptation | Why Not | Do Instead |
|------------|---------|------------|
| NetworkX for graph analysis | Violates no-dependency constraint; overkill for N<50 entities | `itertools.combinations` + dict-based pair tracking |
| numpy/scipy for matrix operations | Violates no-dependency constraint; PMI is trivial arithmetic | `math.log2` + division |
| Real-time correlation updates on every event | Unnecessary complexity; `_handle_state_changed` must stay fast | Daily batch recompute, same as tier classification |
| User-configurable co-occurrence window | Premature optimization of UX; start with 300s constant | Internal constant in `const.py`; make configurable later if needed |
| New sensor entity IDs for correlations | Violates sensor stability constraint; adds to entity count | Populate existing `cross_sensor_patterns` attribute |
| Storing raw co-occurrence events separately | Wasteful duplication; existing `event_times` deques contain all needed data | Read from existing `ActivitySlot.event_times` |
| Config flow changes for correlation settings | Premature; no evidence users need to tune this | Internal constants first |
| CorrelationGroup dataclass | Over-engineering; pairs are sufficient for v4.0 | List of `CorrelationPair` objects |
| Separate .storage file for correlation data | Adds complexity; established pattern is single dict | Extend existing `_save_data()` dict |
| sklearn mutual_info_score | External dependency; PMI is 3 lines of arithmetic | `math.log2(p_ab / (p_a * p_b))` |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Co-occurrence metric | PMI | Jaccard index | Jaccard ignores base rates; high-frequency entities spuriously correlate |
| Co-occurrence metric | PMI | Raw count + threshold | Biased by entity frequency; motion sensors "correlate" with everything |
| Computation timing | Daily batch | Real-time per-event | Unnecessary overhead; correlations stable day-to-day |
| Break detection | Sustained-evidence counter (3 cycles) | Single-miss alert | Single misses too noisy; follows proven AcuteDetector pattern |
| Data storage | Extend existing Store dict | Separate .storage file | Unnecessary complexity; single-dict pattern established |
| Pair enumeration | `itertools.combinations` | Manual nested loops | `combinations` is cleaner, correct, and stdlib |
| Tier rehydration | Conditional guard refinement | Periodic retry timer | Timer adds complexity; guard refinement is simpler and sufficient |

---

## Installation

No changes. No new packages.

```bash
# manifest.json: "requirements": [] remains empty
# No pip install changes
make dev-setup
source venv/bin/activate
make test
```

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| No new dependencies | HIGH | All features use stdlib modules already imported in the codebase |
| PMI as co-occurrence metric | HIGH | Well-established; normalizes for base rates; trivial implementation |
| Daily batch computation | HIGH | Follows proven `classify_tier()` pattern; correlations are stable |
| Sustained-evidence break detection | HIGH | Identical pattern to `AcuteDetector._inactivity_cycles` |
| Tier rehydration fix | HIGH | Direct code analysis; 1-line conditional refinement |
| CO_OCCURRENCE_WINDOW (300s) | MEDIUM | Reasonable for smart home causal chains; may need tuning with real data |
| PMI_THRESHOLD (1.0) | MEDIUM | Standard "2x above chance" cutoff; may need adjustment per deployment |
| MIN_CO_OCCURRENCES (10) | MEDIUM | Balances data sufficiency vs. responsiveness; may need tuning |
| Computational performance at N=50 | HIGH | Worst-case 11.5M comparisons; sub-second on any HA hardware |

---

## Sources

- [A Framework for Event Co-occurrence Detection in Event Streams (arXiv)](https://arxiv.org/pdf/1603.09012) — temporal co-occurrence framework with window-based detection
- [Mining Correlation Patterns among Appliances in Smart Home Environment (Springer)](https://link.springer.com/chapter/10.1007/978-3-319-06605-9_19) — CoPMiner algorithm for appliance correlation patterns
- [Pointwise Mutual Information in NLP (ListenData)](https://www.listendata.com/2022/06/pointwise-mutual-information-pmi.html) — PMI formula and interpretation
- [PMI Calculation (Dev Genius)](https://blog.devgenius.io/pointwise-mutual-information-calculation-00d9a64be7ab) — practical PMI computation guidance
- [Temporal Pattern Discovery for Anomaly Detection in Smart Home (ResearchGate)](https://www.researchgate.net/publication/4317368_Temporal_pattern_discovery_for_anomaly_detection_in_a_smart_home) — temporal patterns for smart home anomaly detection
- [A Method for Temporal Event Correlation (IEEE)](https://ieeexplore.ieee.org/document/8717853) — temporal similarity for event correlation
- [A Better Index for Analysis of Co-occurrence (Science Advances)](https://www.science.org/doi/10.1126/sciadv.abj9204) — comparison of co-occurrence indices
- Codebase analysis: `routine_model.py`, `coordinator.py`, `acute_detector.py`, `drift_detector.py`, `alert_result.py`, `const.py`

---

*Stack research for: Behaviour Monitor v4.0 Cross-Entity Correlation & Startup Tier Rehydration*
*Researched: 2026-04-03*
