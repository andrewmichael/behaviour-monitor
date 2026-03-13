# Technology Stack — v1.1 Detection Rebuild

**Domain:** Routine-based anomaly detection in a Home Assistant custom integration
**Researched:** 2026-03-13
**Confidence:** HIGH (core decisions), MEDIUM (CUSUM parameter tuning)
**Scope:** Stack changes needed for v1.1 — routine model, acute detection, drift detection. The existing HA integration shell, sensors, config flow, storage, and Python async approach are validated and out of scope.

---

## Summary Decision

**No new pip dependencies.** The entire routine model, acute detection engine, and drift detection engine can be built from Python stdlib alone. CUSUM drift detection and rolling statistics are well-understood algorithms with compact pure-Python implementations. Adding any library (numpy, scipy, ruptures) would introduce installation friction for HACS users and conflict with the project constraint in `PROJECT.md`.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python stdlib `statistics` | 3.11+ (HA 2024.1.0 ships Python 3.11) | Rolling mean, stdev, NormalDist for routine modeling and z-score for acute detection | Zero install cost, `NormalDist` class provides zscore() and overlap() directly, sufficient precision for behavioral modeling |
| Python stdlib `collections.deque` | stdlib | Fixed-size sliding window for per-entity event history and routine profile | O(1) append/pop, `maxlen` auto-eviction keeps last N observations without manual pruning — ideal for the 4-week rolling window |
| Python stdlib `datetime` / `timedelta` | stdlib | Temporal bucketing (hour-of-day, day-of-week) for routine profiles | Already used throughout codebase; no new import |
| Python stdlib `dataclasses` | stdlib | EntityRoutine, AcuteEvent, DriftEvent data models | Already used in analyzer.py and ml_analyzer.py; consistent pattern |
| `homeassistant.components.recorder` | HA internal | Bootstrap: load 4 weeks of historical state data at startup | The `recorder` dependency is already declared in `manifest.json`; `get_instance()` + `async_add_executor_job()` gives access to history queries |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `homeassistant.helpers.storage.Store` | HA internal | Persist learned routine profiles to `.storage/` JSON | Already used for statistical and ML persistence; same pattern applies to routine profiles |
| `homeassistant.helpers.update_coordinator.DataUpdateCoordinator` | HA internal | Coordinator base class for periodic refresh and sensor push | Already used; rebuilt coordinator inherits from same base |
| `homeassistant.util.dt` | HA internal | Timezone-aware now(), UTC conversion | Already imported in coordinator.py; needed for temporal bucketing |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest-homeassistant-custom-component` | Unit test harness with HA mocks | Already used; all detection logic requires tests per PROJECT.md |
| `unittest.mock` / `freezegun` | Time freezing for deterministic detection tests | Needed for testing temporal-sensitive CUSUM and routine profile logic |

---

## Algorithm Decisions

### Routine Model: Per-Entity Activity Profiles

**What to build:** A profile per entity that tracks expected activity for each hour-of-day × day-of-week slot (168 slots = 7 days × 24 hours). Each slot stores a rolling mean and standard deviation of activity counts using `statistics.mean()` and `statistics.stdev()` over the configured history window.

**Why 168 slots instead of 672:** The existing 672-slot (15-minute) approach was the root cause of sparsity problems. With real human behavior, 15-minute slots accumulate fewer than 3 observations per month, making std_dev unstable. Hour-of-day slots accumulate 4× more data, producing stable distributions within 2 weeks. The PROJECT.md explicitly names this as why buckets are being replaced.

**Data structure:**
```python
from collections import deque
from dataclasses import dataclass, field

@dataclass
class ActivitySlot:
    """Rolling observations for one hour-of-day × day-of-week slot."""
    observations: deque = field(default_factory=lambda: deque(maxlen=56))
    # maxlen=56: 4 weeks × ~14 observations/week per slot (activity count per hour)
```

**Bootstrapping from history:** On coordinator startup, use `recorder.get_instance(hass)` then `instance.async_add_executor_job(get_significant_states, ...)` to load up to `history_window_days` (default 28) of past state history. Replay state changes into the routine model before live monitoring begins. This avoids the cold-start period of the old bucket approach.

### Acute Detection: Z-Score on Rolling Profile

**What to build:** When a new state change arrives, compare it against the current hour-of-day × day-of-week profile for that entity. If the observed activity count falls more than `sensitivity_sigma` standard deviations from the rolling mean, and the profile has at least `MIN_SLOT_OBSERVATIONS` data points, raise an acute event.

**Why z-score here is appropriate:** Unlike the old 672-bucket approach, each slot now has sufficient data (4+ weeks) for stable statistics. The z-score is applied to a well-populated distribution, not sparse buckets. The old code's `float("inf")` z-score from empty buckets cannot happen here because the `MIN_SLOT_OBSERVATIONS` guard is enforced before any comparison.

**Use `statistics.NormalDist`:**
```python
from statistics import NormalDist, mean, stdev

dist = NormalDist(mu=slot_mean, sigma=slot_stdev)
z = dist.zscore(observed_count)
```

`NormalDist` is available in Python 3.8+, confirmed present in all HA 2024.1.0+ environments. No numpy required.

### Drift Detection: CUSUM on Daily Activity Totals

**What to build:** A per-entity CUSUM (Cumulative Sum) control chart that accumulates evidence of sustained shift in daily activity levels. CUSUM is the standard algorithm for this class of problem — it is sensitive to gradual, persistent changes (drift) while being insensitive to one-off spikes (acute events). The two engines are complementary by design.

**Why CUSUM over other approaches:**
- **vs. rolling mean comparison:** A rolling mean comparison detects the same shift but has a detection lag proportional to window size. CUSUM detects shifts in O(1) per new observation.
- **vs. ruptures (PELT):** ruptures requires numpy + scipy as hard dependencies. For a HA custom integration targeting HACS users, pulling in numpy is a significant install burden. The ruptures algorithm is also batch-oriented (processes the whole series), not streaming. CUSUM is a streaming algorithm — one observation per day, detect immediately.
- **vs. River library:** River is being explicitly removed per PROJECT.md. CUSUM needs ~15 lines of pure Python.

**CUSUM implementation shape:**
```python
@dataclass
class CUSUMDetector:
    """One-sided CUSUM for drift detection on daily activity totals."""
    k: float = 0.5          # allowance / reference value (half the expected shift size in sigma units)
    h: float = 4.0          # decision threshold (in sigma units; ~4.0 for ~ARL of 168 one-sided)
    _pos_sum: float = 0.0   # cumulative sum for upward drift
    _neg_sum: float = 0.0   # cumulative sum for downward drift

    def update(self, z_score: float) -> tuple[bool, str]:
        """Update with today's z-score. Returns (drift_detected, direction)."""
        self._pos_sum = max(0, self._pos_sum + z_score - self.k)
        self._neg_sum = max(0, self._neg_sum - z_score - self.k)
        if self._pos_sum > self.h:
            return True, "increase"
        if self._neg_sum > self.h:
            return True, "decrease"
        return False, ""
```

**Parameter rationale:**
- `k=0.5`: Standard choice for detecting a 1-sigma shift in the mean. Balances sensitivity with false alarm rate.
- `h=4.0`: At h=4 with daily observations, average run length (ARL) before false alarm is ~168 days — acceptable for a drift detector that should only fire after sustained behavioral change.
- Both parameters are configurable constants in `const.py`; users should not need to tune them, but they can be exposed as advanced options if needed.

**Confidence:** MEDIUM — the CUSUM formula is verified (Wikipedia, Stackademic article cited below), parameter values k=0.5 and h=4.0 are the textbook defaults for detecting a 1-sigma shift with ARL~168. The mapping of h=4.0 to "days before false alarm" is training knowledge (ARL tables for normal distributions). Phase-level research should validate ARL empirically with simulated home sensor data.

---

## Installation

```bash
# No new pip dependencies required.
# All algorithms use Python stdlib only.

# manifest.json: no changes needed.
# "requirements": []  remains empty.
# "dependencies": ["recorder"]  already present.
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Pure Python CUSUM (stdlib only) | `ruptures` library (PELT algorithm) | Use ruptures if you need offline batch analysis across the full history series with multiple change points. Not appropriate here — streaming, one observation per update cycle. Also requires numpy + scipy. |
| `statistics.NormalDist` zscore | Manual z-score formula `(x - mu) / sigma` | Equivalent — use NormalDist when you also need `overlap()` or `cdf()` for additional profile comparisons. Either is fine. |
| Hour-of-day × day-of-week slots (168) | 15-minute slots (672 buckets, existing approach) | Use 672 if your sensor population is large enough that each 15-minute slot gets 5+ observations per week. For typical residential monitoring, 672 is too sparse. |
| Bootstrap from HA recorder history | Cold-start (learn from scratch) | Cold-start is simpler to implement but creates a learning dead zone of 4 weeks where acute detection cannot fire. Recorder bootstrap eliminates this entirely for existing installations. |
| Single coordinator for both engines | Separate coordinators per engine | Separate coordinators add complexity with no benefit — both engines process the same state change events and share entity configuration. A single coordinator with two internal detectors is the correct HA pattern. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `ruptures` | Requires numpy + scipy. Batch-oriented, not streaming. Overkill for per-entity daily drift detection. Adds HACS install friction. | Pure Python CUSUM (15 lines, zero deps) |
| `numpy` / `scipy` | Not in HA core requirements.txt. Installing from a custom integration causes conflicts with HA's own scipy if HA ever bundles it, and creates 60-200MB of install overhead. Home Assistant's custom integration guidance explicitly says not to duplicate core requirements. | `statistics` module for all numerical operations |
| `river` (River ML) | Being explicitly removed per PROJECT.md. Routine-based detection makes it redundant. | CUSUM for drift, z-score on rolling profile for acute events |
| `scikit-learn` (IsolationForest, etc.) | Batch-oriented. Would require full history reload for each retrain. Cannot produce streaming detections on state change events. | CUSUM + rolling profile — both are truly streaming |
| Raw SQLAlchemy queries on HA DB | Direct DB access is fragile across HA schema changes (recorder schema has changed multiple times). HA's internal recorder API (`get_significant_states`) is the stable interface. | `homeassistant.components.recorder.history` internal API |
| Global numpy-style arrays for history | Would require numpy. Python `list` or `collections.deque` with `maxlen` is sufficient for the rolling window sizes needed (≤56 observations per slot). | `collections.deque(maxlen=N)` |

---

## Stack Patterns by Variant

**If the monitored entity is binary (motion sensor, door contact, switch):**
- Track activity count per slot: number of ON→OFF transitions in the hour window
- Acute detection: compare transition count to profile distribution (z-score)
- Drift detection: CUSUM on daily transition count z-score

**If the monitored entity is numeric (climate setpoint, power meter):**
- Track value distribution per slot: mean of numeric values during the hour window
- Acute detection: compare current mean to profile distribution (z-score)
- Drift detection: CUSUM on daily mean value z-score

**If the history window has fewer than `MIN_SLOT_OBSERVATIONS` for a slot:**
- Skip detection for that slot entirely — do not emit an acute event
- Recommended `MIN_SLOT_OBSERVATIONS = 4` (4 weeks minimum before that slot is reliable)
- CUSUM resets automatically when the profile is insufficient (no input → no drift signal)

**If the HA recorder history is unavailable at startup (recorder not running):**
- Fall back to cold-start: begin accumulating from live events only
- Log a warning; detection will be suppressed until `MIN_SLOT_OBSERVATIONS` is met
- Do not block integration setup

---

## Version Compatibility

| Component | Requires | Notes |
|-----------|----------|-------|
| `statistics.NormalDist` | Python 3.8+ | Available in all HA 2024.1.0+ environments (ships Python 3.11) |
| `collections.deque(maxlen=N)` | Python 2.6+ | No concern |
| `homeassistant.components.recorder.history` | HA 2024.1.0+ | API has been stable since HA 2023.x; `get_significant_states` is used by the built-in history_stats integration, confirming it is a supported internal interface |
| `homeassistant.helpers.storage.Store` | HA 2021.x+ | Unchanged; already used in v1.0 |

---

## Sources

- [Python docs: statistics.NormalDist](https://docs.python.org/3/library/statistics.html) — confirmed zscore() method, Python 3.8+, HIGH confidence
- [PyPI: ruptures](https://pypi.org/project/ruptures/) — confirmed numpy + scipy required, rules out use in HA custom integration, HIGH confidence
- [The CUSUM Algorithm — Stackademic](https://blog.stackademic.com/the-cusum-algorithm-all-the-essential-information-you-need-with-python-examples-f6a5651bf2e5) — CUSUM formula and parameters verified, MEDIUM confidence (blog source)
- [CUSUM — Wikipedia](https://en.wikipedia.org/wiki/CUSUM) — algorithm definition and ARL tables, HIGH confidence
- [GitHub: deepcharles/ruptures](https://github.com/deepcharles/ruptures) — confirmed scipy>=0.19.1 required dependency, HIGH confidence
- [HA Developer Docs: Integration manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/) — confirmed requirements array installs via pip; custom integrations must not duplicate core requirements, HIGH confidence
- [HA Recorder component](https://www.home-assistant.io/integrations/recorder/) — confirmed `recorder` is already a declared dependency; internal history API is used by built-in integrations, HIGH confidence
- Existing codebase (`coordinator.py`, `analyzer.py`, `ml_analyzer.py`) — confirmed current stdlib-only pattern and HA API usage, HIGH confidence

---

*Stack research for: Behaviour Monitor v1.1 Detection Rebuild*
*Researched: 2026-03-13*
