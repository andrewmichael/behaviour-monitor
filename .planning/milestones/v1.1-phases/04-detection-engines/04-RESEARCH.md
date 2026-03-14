# Phase 4: Detection Engines - Research

**Researched:** 2026-03-13
**Domain:** Pure-Python acute (inactivity + unusual-time) and drift (CUSUM) detectors consuming the Phase 3 RoutineModel API
**Confidence:** HIGH (algorithm design, API surface, test patterns); MEDIUM (CUSUM parameter tuning — flagged in STATE.md; validate against simulation)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Default inactivity multiplier: 3x the learned typical interval per entity
- Sustained evidence requirement: 3 consecutive polling cycles before any acute alert fires
- Inactivity multiplier is a single global setting (per-entity tuning deferred to v2 per NOTIF-02)
- Unusual-time detection: activity in a slot with fewer than MIN_SLOT_OBSERVATIONS (4) events is flagged as unusual — reuses Phase 3's sparse slot guard
- Rich structured result: alert type, severity, confidence, evidence details (expected vs actual values), entity context, timestamp
- 3-tier severity: low (approaching threshold), medium (threshold crossed), high (well beyond threshold, e.g., 5x+ multiplier)
- Human-readable explanation included in result (e.g., "Front door inactive 14h (typical: every 4h, 3.5x threshold)")
- Common base result type with typed detail dicts — acute and drift share fields (entity_id, alert_type, severity, confidence, explanation, timestamp) plus type-specific details
- Minimum evidence window for drift: 3 days of shifted behavior before alerting
- Metric tracked for drift: daily event count (state changes per day per entity)
- Bidirectional CUSUM (detects both increases and decreases in activity)
- Drift sensitivity exposed as simple high/medium/low setting, mapped to pre-tuned CUSUM parameters internally
- routine_reset clears drift accumulator only — baseline history preserved, model adapts naturally
- Single entity_id per call for routine_reset (no "reset all" option)
- No cooldown period — acute alerts unaffected by reset
- Log a WARNING-level message and fire an HA event for logbook visibility on routine_reset

### Claude's Discretion
- Internal CUSUM parameter tuning (k and h values) for each sensitivity level
- Alert result class design and dataclass structure
- Detector class API surface (method signatures, return types)
- Test strategy and fixture design
- How severity thresholds map to multiplier ranges (e.g., low = 2-3x, medium = 3-4x, high = 4x+)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ACUTE-01 | System alerts when no expected activity occurs for a configurable multiplier of the learned typical interval per entity | AcuteDetector.check_inactivity() consuming EntityRoutine.expected_gap_seconds(hour, dow); severity based on actual_elapsed / (threshold * multiplier) ratio |
| ACUTE-02 | System alerts on activity at times that have never or rarely occurred in learned history | AcuteDetector.check_unusual_time() using ActivitySlot.is_sufficient as unusual-time guard; slot.is_sufficient == False means slot is sparse = unusual |
| ACUTE-03 | System requires sustained evidence (multiple consecutive polling cycles) before firing any acute alert — no single-point alerts | Consecutive-cycle counter per entity per alert type; 3 cycles required; counter resets when condition clears |
| DRIFT-01 | System detects persistent changes in daily behavior metrics using CUSUM change point detection | Bidirectional CUSUM on EntityRoutine.daily_activity_rate(date); 3-day minimum evidence window before alerting |
| DRIFT-02 | User can call a routine_reset service to tell the model their routine changed intentionally | routine_reset clears drift accumulator (S_pos, S_neg, days_above_threshold) for entity_id; fires HA event; logs WARNING |
| DRIFT-03 | User can configure drift detection sensitivity in the config flow UI | Sensitivity level (high/medium/low) maps to pre-tuned (k, h) CUSUM parameters in const.py; DriftDetector accepts sensitivity enum at construction |
</phase_requirements>

---

## Summary

Phase 4 produces two new pure-Python files — `acute_detector.py` and `drift_detector.py` — each a self-contained detection engine that consumes the `EntityRoutine` API built in Phase 3. Neither file may import from `homeassistant`; both are fully unit-testable without mocking any HA infrastructure. The coordinator integration (calling detectors, wiring the `routine_reset` service) is deferred to Phase 5.

The `AcuteDetector` checks two conditions per entity per polling cycle: (1) has the entity been silent for longer than `inactivity_multiplier × expected_gap_seconds(current_hour, current_dow)`, and (2) did activity just arrive in a time slot with fewer than `MIN_SLOT_OBSERVATIONS` events? Before producing any alert result, the detector requires 3 consecutive polling cycles of sustained evidence — a per-entity, per-alert-type cycle counter resets when the condition clears. Severity is derived from the ratio of observed gap to threshold.

The `DriftDetector` runs a bidirectional CUSUM on daily activity rates. It accumulates `S_pos` and `S_neg` per entity. When either accumulator exceeds the decision threshold `h` for 3 consecutive days, a drift result is produced. A single `routine_reset(entity_id)` call zeroes both accumulators and the days counter for that entity. The drift detector's CUSUM parameters are tuned per sensitivity level (high/medium/low) mapped from the existing `SENSITIVITY_LOW/MEDIUM/HIGH` constants in `const.py`. The preliminary parameters (k=0.5, h=4.0) are MEDIUM confidence — they must be validated against simulated step-change scenarios during TDD.

Both detectors produce `AlertResult` dataclass instances sharing a common base (entity_id, alert_type, severity, confidence, explanation, timestamp) with type-specific detail dicts. Alert results carry enough context (expected vs. actual values, multiplier ratio, direction) for the Phase 5 coordinator to assemble sensor data and notification messages without querying the detectors again.

**Primary recommendation:** Build `alert_result.py` (shared types) first, then `acute_detector.py` and `drift_detector.py` in parallel (they have no dependency on each other). Use TDD throughout — write failing tests before implementing each method. Validate CUSUM parameters against simulated 1-sigma and 2-sigma step changes before committing final parameter values.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `dataclasses` | stdlib | `AlertResult`, `AcuteDetail`, `DriftDetail`, `CUSUMState` data models | Established pattern throughout codebase; `to_dict`/`from_dict` for persistence |
| Python stdlib `datetime` | stdlib | Temporal arithmetic (elapsed time, daily rate window) | Already throughout codebase; zero HA dependency |
| Python stdlib `statistics` | 3.11 (HA ships 3.11) | `median()` for expected gap (already used by RoutineModel); available if needed for future z-score support | Zero install cost |
| Python stdlib `math` | stdlib | `max()` implicit; nothing exotic required for CUSUM | stdlib |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `unittest.mock` | stdlib | Mocking `EntityRoutine` in detector unit tests | All detector tests — inject mock routine to test detector logic in isolation |
| `freezegun` | test dep | Time freezing for elapsed-time tests | Tests that exercise inactivity duration calculation; already in test deps |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Bidirectional CUSUM (separate S_pos, S_neg) | Single one-sided CUSUM | Bidirectional catches both activity decrease (welfare concern) and increase (new routine). Single-sided misses increases. |
| Consecutive-cycle counter for sustained evidence | Debounce timer (absolute time) | Cycle counter is simpler: coordinator poll interval can change without breaking the evidence model. Time-based debounce requires storing first-alert timestamps. |
| Severity ratio from multiplier | Fixed z-score thresholds | Multiplier ratio is more interpretable ("3.5x typical gap") than z-score for human-facing explanations. |

**Installation:**
```bash
# No new pip dependencies required.
# Python stdlib only. manifest.json unchanged.
```

---

## Architecture Patterns

### Recommended File Structure

```
custom_components/behaviour_monitor/
├── alert_result.py       # NEW: AlertResult base dataclass, AcuteDetail, DriftDetail, AlertType, AlertSeverity
├── acute_detector.py     # NEW: AcuteDetector — inactivity + unusual-time, zero HA imports
├── drift_detector.py     # NEW: DriftDetector — bidirectional CUSUM, zero HA imports
├── routine_model.py      # EXISTING (Phase 3): EntityRoutine, RoutineModel — read only
└── const.py              # EXTENDED: CUSUM parameter dicts, inactivity multiplier default
```

### Pattern 1: Shared Alert Result Type

**What:** A common `AlertResult` dataclass with mandatory fields shared by both detectors, plus a `details` dict for type-specific evidence. This allows the coordinator to handle all alerts uniformly while preserving type-specific fields for notification construction.

**When to use:** Any time both detector types produce results that the coordinator processes in the same loop.

```python
# alert_result.py — zero HA imports
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

class AlertType(str, Enum):
    INACTIVITY = "inactivity"
    UNUSUAL_TIME = "unusual_time"
    DRIFT = "drift"

class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

@dataclass
class AlertResult:
    """Structured detection result produced by AcuteDetector or DriftDetector."""
    entity_id: str
    alert_type: AlertType
    severity: AlertSeverity
    confidence: float          # 0.0–1.0 from EntityRoutine.confidence()
    explanation: str           # Human-readable: "Front door inactive 14h (typical: every 4h, 3.5x threshold)"
    timestamp: str             # ISO timestamp (UTC)
    details: dict[str, Any] = field(default_factory=dict)
    # details for INACTIVITY: {"elapsed_seconds": float, "threshold_seconds": float, "multiplier_ratio": float}
    # details for UNUSUAL_TIME: {"hour": int, "dow": int, "slot_observations": int}
    # details for DRIFT: {"direction": str, "cusum_score": float, "days_above_threshold": int, "baseline_rate": float, "current_rate": float}

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "timestamp": self.timestamp,
            "details": self.details,
        }
```

### Pattern 2: AcuteDetector — Inactivity Check

**What:** Per-entity, per-condition consecutive-cycle counters stored in dicts. The detector is stateful (holds counters), but state is ephemeral — it resets to zero on HA restart and reaccumulates within 3 polling cycles. No persistence needed.

**When to use:** Called from the coordinator's 60-second `_async_update_data` for inactivity checks. Also called from the `_handle_state_change` callback for unusual-time checks (O(1), safe in callback).

**Severity mapping (Claude's discretion):**
- `low`: 2.0x–3.0x typical gap (approaching threshold; not yet at alert level but worth surfacing)
- `medium`: 3.0x–5.0x typical gap (threshold crossed)
- `high`: >5.0x typical gap (well beyond threshold)

```python
# acute_detector.py — zero HA imports
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .alert_result import AlertResult, AlertType, AlertSeverity
from .routine_model import EntityRoutine, MIN_SLOT_OBSERVATIONS

DEFAULT_INACTIVITY_MULTIPLIER: float = 3.0
SUSTAINED_EVIDENCE_CYCLES: int = 3

class AcuteDetector:
    """Detects inactivity anomalies and unusual-time activity.

    Stateless with respect to the RoutineModel. Maintains only per-entity
    consecutive-cycle counters for the sustained-evidence requirement (ACUTE-03).
    """

    def __init__(
        self,
        inactivity_multiplier: float = DEFAULT_INACTIVITY_MULTIPLIER,
        sustained_cycles: int = SUSTAINED_EVIDENCE_CYCLES,
    ) -> None:
        self._multiplier = inactivity_multiplier
        self._required_cycles = sustained_cycles
        # Per-entity inactivity cycle counters
        self._inactivity_cycles: dict[str, int] = {}
        # Per-entity unusual-time cycle counters (keyed by entity_id)
        self._unusual_time_cycles: dict[str, int] = {}

    def check_inactivity(
        self,
        entity_id: str,
        routine: EntityRoutine,
        now: datetime,
        last_seen: datetime | None,
    ) -> AlertResult | None:
        """Check if entity has been silent beyond the inactivity threshold.

        Returns AlertResult if sustained evidence requirement is met, else None.
        Resets cycle counter when condition clears.
        """
        hour = now.hour
        dow = now.weekday()
        expected_gap = routine.expected_gap_seconds(hour, dow)

        if expected_gap is None:
            # Insufficient data — sparse slot guard
            self._inactivity_cycles[entity_id] = 0
            return None

        if last_seen is None:
            self._inactivity_cycles[entity_id] = 0
            return None

        elapsed = (now - last_seen).total_seconds()
        threshold = expected_gap * self._multiplier

        if elapsed < threshold:
            # Condition cleared — reset counter
            self._inactivity_cycles[entity_id] = 0
            return None

        # Condition active — increment counter
        self._inactivity_cycles[entity_id] = self._inactivity_cycles.get(entity_id, 0) + 1

        if self._inactivity_cycles[entity_id] < self._required_cycles:
            return None  # Not yet sustained

        ratio = elapsed / threshold
        severity = self._inactivity_severity(ratio)
        elapsed_h = elapsed / 3600
        typical_h = expected_gap / 3600

        return AlertResult(
            entity_id=entity_id,
            alert_type=AlertType.INACTIVITY,
            severity=severity,
            confidence=routine.confidence(now),
            explanation=(
                f"{entity_id} inactive {elapsed_h:.1f}h "
                f"(typical: every {typical_h:.1f}h, {ratio:.1f}x threshold)"
            ),
            timestamp=now.isoformat(),
            details={
                "elapsed_seconds": elapsed,
                "threshold_seconds": threshold,
                "expected_gap_seconds": expected_gap,
                "multiplier_ratio": ratio,
            },
        )

    def check_unusual_time(
        self,
        entity_id: str,
        routine: EntityRoutine,
        now: datetime,
    ) -> AlertResult | None:
        """Check if activity just occurred at an unusual time slot.

        Unusual = the current (hour, dow) slot has fewer than MIN_SLOT_OBSERVATIONS.
        Returns AlertResult if sustained evidence requirement is met, else None.
        """
        hour = now.hour
        dow = now.weekday()
        slot_idx = routine.slot_index(hour, dow)
        slot = routine.slots[slot_idx]

        if slot.is_sufficient:
            # Normal slot — condition cleared
            self._unusual_time_cycles[entity_id] = 0
            return None

        obs_count = len(slot.event_times) + slot.numeric_count
        self._unusual_time_cycles[entity_id] = (
            self._unusual_time_cycles.get(entity_id, 0) + 1
        )

        if self._unusual_time_cycles[entity_id] < self._required_cycles:
            return None

        return AlertResult(
            entity_id=entity_id,
            alert_type=AlertType.UNUSUAL_TIME,
            severity=AlertSeverity.MEDIUM,
            confidence=routine.confidence(now),
            explanation=(
                f"{entity_id} active at unusual time "
                f"(hour={hour}, dow={dow}, only {obs_count} prior observations)"
            ),
            timestamp=now.isoformat(),
            details={
                "hour": hour,
                "dow": dow,
                "slot_observations": obs_count,
                "min_observations": MIN_SLOT_OBSERVATIONS,
            },
        )

    @staticmethod
    def _inactivity_severity(ratio: float) -> AlertSeverity:
        if ratio >= 5.0:
            return AlertSeverity.HIGH
        if ratio >= 3.0:
            return AlertSeverity.MEDIUM
        return AlertSeverity.LOW
```

### Pattern 3: DriftDetector — Bidirectional CUSUM

**What:** Per-entity `CUSUMState` dataclass holding `S_pos`, `S_neg`, `days_above_threshold` counter. Updated once per coordinator poll cycle (daily rate is computed from `EntityRoutine.daily_activity_rate(today)`). Alert fires when `days_above_threshold >= min_evidence_days`.

**CUSUM formula:**
```
S_pos = max(0, S_pos + z - k)
S_neg = max(0, S_neg - z - k)
drift detected when S_pos > h OR S_neg > h
```

where `z = (today_rate - baseline_rate) / baseline_stdev` (or raw delta if stdev unknown).

**Parameter rationale (MEDIUM confidence — validate with simulation):**

| Sensitivity | k | h | ARL (approx) | Min days at 1-sigma shift to trigger |
|-------------|---|---|--------------|--------------------------------------|
| high | 0.25 | 2.0 | ~35 days | ~2-3 days |
| medium | 0.5 | 4.0 | ~168 days | ~4-5 days |
| low | 1.0 | 6.0 | ~800 days | ~8-10 days |

The 3-day minimum evidence window is layered on top of CUSUM — even if `S_pos > h` on day 1, `days_above_threshold` must reach 3 before an alert fires.

```python
# drift_detector.py — zero HA imports
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from .alert_result import AlertResult, AlertType, AlertSeverity
from .routine_model import EntityRoutine

# CUSUM parameters by sensitivity level
# (k=allowance, h=decision threshold)
CUSUM_PARAMS: dict[str, tuple[float, float]] = {
    "high":   (0.25, 2.0),
    "medium": (0.5,  4.0),
    "low":    (1.0,  6.0),
}

DEFAULT_SENSITIVITY: str = "medium"
MIN_EVIDENCE_DAYS: int = 3

@dataclass
class CUSUMState:
    """Per-entity CUSUM accumulator state."""
    s_pos: float = 0.0          # Cumulative sum for upward drift
    s_neg: float = 0.0          # Cumulative sum for downward drift
    days_above_threshold: int = 0
    last_update_date: str | None = None  # ISO date string (YYYY-MM-DD)

    def reset(self) -> None:
        """Clear accumulators — called by routine_reset service."""
        self.s_pos = 0.0
        self.s_neg = 0.0
        self.days_above_threshold = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "s_pos": self.s_pos,
            "s_neg": self.s_neg,
            "days_above_threshold": self.days_above_threshold,
            "last_update_date": self.last_update_date,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CUSUMState":
        obj = cls()
        obj.s_pos = float(data.get("s_pos", 0.0))
        obj.s_neg = float(data.get("s_neg", 0.0))
        obj.days_above_threshold = int(data.get("days_above_threshold", 0))
        obj.last_update_date = data.get("last_update_date")
        return obj


class DriftDetector:
    """Bidirectional CUSUM drift detector on daily activity rates.

    Processes one day's data per entity per coordinator poll cycle.
    Maintains per-entity CUSUMState — must be persisted across HA restarts.
    """

    def __init__(
        self,
        sensitivity: str = DEFAULT_SENSITIVITY,
        min_evidence_days: int = MIN_EVIDENCE_DAYS,
    ) -> None:
        if sensitivity not in CUSUM_PARAMS:
            sensitivity = DEFAULT_SENSITIVITY
        self._k, self._h = CUSUM_PARAMS[sensitivity]
        self._min_evidence_days = min_evidence_days
        self._states: dict[str, CUSUMState] = {}

    def get_or_create_state(self, entity_id: str) -> CUSUMState:
        if entity_id not in self._states:
            self._states[entity_id] = CUSUMState()
        return self._states[entity_id]

    def reset_entity(self, entity_id: str) -> None:
        """Clear drift accumulator for entity (routine_reset service handler)."""
        state = self.get_or_create_state(entity_id)
        state.reset()

    def check(
        self,
        entity_id: str,
        routine: EntityRoutine,
        today: date,
        now: datetime,
    ) -> AlertResult | None:
        """Run one CUSUM step for entity_id. Returns AlertResult or None."""
        state = self.get_or_create_state(entity_id)

        # Skip if already processed today
        today_str = today.isoformat()
        if state.last_update_date == today_str:
            return None

        state.last_update_date = today_str

        # Compute baseline: mean daily rate over all days in history
        # Use daily_activity_rate for today and estimate z-score relative to baseline
        baseline_rates = self._compute_baseline_rates(routine, today)
        if len(baseline_rates) < self._min_evidence_days:
            # Insufficient history for drift detection
            return None

        baseline_mean = mean(baseline_rates)
        if baseline_mean == 0:
            return None

        today_rate = float(routine.daily_activity_rate(today))
        # Simple z-score: normalize by baseline mean (use mean as proxy for scale)
        # More robust: use stdev of baseline_rates if available
        from statistics import stdev as _stdev
        try:
            baseline_std = _stdev(baseline_rates) if len(baseline_rates) >= 2 else baseline_mean
        except Exception:
            baseline_std = baseline_mean
        if baseline_std == 0:
            baseline_std = 1.0

        z = (today_rate - baseline_mean) / baseline_std

        # Bidirectional CUSUM update
        state.s_pos = max(0.0, state.s_pos + z - self._k)
        state.s_neg = max(0.0, state.s_neg - z - self._k)

        if state.s_pos > self._h or state.s_neg > self._h:
            state.days_above_threshold += 1
        else:
            state.days_above_threshold = 0

        if state.days_above_threshold < self._min_evidence_days:
            return None

        direction = "increase" if state.s_pos > state.s_neg else "decrease"
        cusum_score = max(state.s_pos, state.s_neg)
        severity = self._drift_severity(state.days_above_threshold)

        return AlertResult(
            entity_id=entity_id,
            alert_type=AlertType.DRIFT,
            severity=severity,
            confidence=routine.confidence(now),
            explanation=(
                f"{entity_id} shows sustained {direction} in activity "
                f"({state.days_above_threshold} days above threshold; "
                f"baseline: {baseline_mean:.1f}/day, today: {today_rate:.0f}/day)"
            ),
            timestamp=now.isoformat(),
            details={
                "direction": direction,
                "cusum_score": cusum_score,
                "days_above_threshold": state.days_above_threshold,
                "baseline_rate": baseline_mean,
                "current_rate": today_rate,
            },
        )

    def _compute_baseline_rates(
        self, routine: EntityRoutine, exclude_today: date
    ) -> list[float]:
        """Compute per-day rates from routine history, excluding today."""
        # Collect all unique dates from event_times across all slots
        seen_dates: dict[str, int] = {}
        for slot in routine.slots:
            for ts_str in slot.event_times:
                try:
                    from datetime import datetime as _dt
                    d = _dt.fromisoformat(ts_str).date()
                    if d != exclude_today:
                        d_str = d.isoformat()
                        seen_dates[d_str] = seen_dates.get(d_str, 0) + 1
                except (ValueError, TypeError):
                    pass
        return [float(v) for v in seen_dates.values()]

    @staticmethod
    def _drift_severity(days: int) -> AlertSeverity:
        if days >= 7:
            return AlertSeverity.HIGH
        if days >= 3:
            return AlertSeverity.MEDIUM
        return AlertSeverity.LOW

    def to_dict(self) -> dict[str, Any]:
        """Serialize CUSUM states for persistence."""
        return {
            entity_id: state.to_dict()
            for entity_id, state in self._states.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], sensitivity: str = DEFAULT_SENSITIVITY) -> "DriftDetector":
        detector = cls(sensitivity=sensitivity)
        for entity_id, state_data in data.items():
            detector._states[entity_id] = CUSUMState.from_dict(state_data)
        return detector
```

### Anti-Patterns to Avoid

- **Calling drift detection inside `_handle_state_change` callback:** CUSUM requires iterating all event_times across all slots (O(n) over history). This must run in `_async_update_data`, not the synchronous callback.
- **Importing from `homeassistant` in detector files:** Breaks the HA-free contract, requiring HA mocks in every test. All HA interactions belong in the coordinator.
- **Firing an alert on the first cycle above threshold:** Violates ACUTE-03. Always check `consecutive_cycles >= required_cycles` before producing a result.
- **Persisting ephemeral acute counter state:** Acute cycle counters should NOT be persisted — they represent intra-session transient evidence. On HA restart, counters reset to zero; 3 cycles = 3 minutes before an alert re-fires, which is fine.
- **Persisting DriftDetector state as raw Python objects:** Use `to_dict`/`from_dict` with JSON primitives. The coordinator wraps this in the existing Store.
- **Using a fixed daily rate threshold instead of z-score:** Daily rates vary wildly across entities (a motion sensor fires 100x/day; a front door fires 5x/day). Z-score normalizes by entity baseline, making the CUSUM threshold `h` entity-agnostic.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CUSUM algorithm | Custom moving average + percentage threshold | Standard CUSUM (S_pos, S_neg, k, h) | CUSUM is ~10 lines; has proven ARL guarantees; percentage thresholds fail for near-zero baseline rates |
| Severity mapping | Inline if/elif chains duplicated in each method | `_inactivity_severity()` / `_drift_severity()` static methods | Testable in isolation; single source of truth |
| Baseline rate computation | Raw SQL or scanning all entities in HA state machine | `EntityRoutine.daily_activity_rate(date)` — already built in Phase 3 | Phase 3 API is tested; re-implementing duplicates logic and introduces bugs |
| Alert deduplication / cooldown | State in AcuteDetector or DriftDetector | Phase 5 coordinator / NotificationManager responsibility | Detectors produce results; coordinator decides whether to notify. Mixing concerns forces HA into detector tests. |
| Human-readable elapsed formatting | Complex time formatting utility | f-string arithmetic in the `explanation` field | Simple enough inline; `elapsed_h = elapsed / 3600` is sufficient |

**Key insight:** Detectors are pure computation — they receive inputs and return results. They do not decide whether to send notifications, store history, or interact with HA. That discipline is what makes them HA-free and testable.

---

## Common Pitfalls

### Pitfall 1: Firing on First Cycle (Missing ACUTE-03)
**What goes wrong:** Alert fires immediately on the first polling cycle the condition is true. A transient sensor dropout (entity temporarily unavailable → available) produces a spurious inactivity alert.
**Why it happens:** Developer forgets the 3-cycle counter; implements direct threshold comparison.
**How to avoid:** Every `check_*` method increments and reads `_*_cycles[entity_id]`; returns `None` until count reaches `required_cycles`. Write a test: single cycle → no result; two cycles → no result; three cycles → result.
**Warning signs:** Tests with a single `check_inactivity()` call return a result.

### Pitfall 2: Not Resetting Cycle Counter When Condition Clears
**What goes wrong:** Entity resumes activity. On next poll, `elapsed < threshold`. Counter still at 3. When entity goes inactive again briefly, alert fires immediately on the next cycle instead of requiring 3 fresh cycles.
**Why it happens:** Condition-cleared path returns early without zeroing the counter.
**How to avoid:** Every code path that determines "condition not met" must set `self._*_cycles[entity_id] = 0` before returning `None`.
**Warning signs:** Test scenario "condition clears then returns" fires alert on first recurrence.

### Pitfall 3: CUSUM ARL Too Low at Medium Sensitivity
**What goes wrong:** At default h=4.0 and daily observation, drift alerts fire after 1 week of slightly elevated activity during a holiday. Users see false positives and disable drift detection.
**Why it happens:** h=4.0 has ARL ~168 in theory, but home sensor data is not Gaussian — daily rates are count-based (Poisson-ish) and weekend/weekday differences create structural non-stationarity.
**How to avoid:** Validate parameters against simulated step changes during TDD. Test scenario: stable 14 days, then +1-sigma shift — alert should fire within 3-7 days, not on day 1. Adjust `h` upward if simulation shows false-positives.
**Warning signs:** Unit test with 3-day smooth signal at exactly 1-sigma above baseline triggers alert on day 1.

### Pitfall 4: Baseline Rate of Zero Causes Division Error
**What goes wrong:** An entity that has been silent for days has `baseline_mean = 0`. Z-score computation divides by zero. DriftDetector crashes. Coordinator `_async_update_data` fails. All sensors go unavailable.
**Why it happens:** Not guarding the denominator when baseline mean is 0.
**How to avoid:** Guard `if baseline_mean == 0: return None` before computing z-score. An entity with zero baseline rate cannot drift meaningfully — CUSUM would always show infinity. Return None and wait for the model to accumulate more data.
**Warning signs:** No test for entity with all-zero daily_activity_rate history.

### Pitfall 5: DriftDetector State Not Persisted — Accumulator Lost on Restart
**What goes wrong:** S_pos accumulates over 5 days, reaching the threshold. HA restarts for update. S_pos resets to 0. Detection never fires because it resets before reaching the evidence window.
**Why it happens:** Drift detector state is only in memory; `to_dict()` / `from_dict()` not implemented, or coordinator doesn't call them.
**How to avoid:** `DriftDetector.to_dict()` must be included in the coordinator's store save; `from_dict()` called on load. Write an integration test: accumulate 3 days, serialize, restore, verify days_above_threshold is preserved.
**Warning signs:** `CUSUMState` has no `to_dict`/`from_dict`; DriftDetector test suite has no round-trip serialization test.

### Pitfall 6: Unusual-Time Detection Fires on Normal Rare Events
**What goes wrong:** Front door at 2am is unusual. But so is the thermostat at a rare hour if the entity has only 2 observations total (not yet learned). Alert fires during the learning phase when any slot is sparse.
**Why it happens:** `slot.is_sufficient == False` means BOTH "never seen before" AND "just started learning." Both cases look identical to the detector.
**How to avoid:** Gate unusual-time detection on `EntityRoutine.confidence(now) >= MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME`. A suggested threshold: confidence >= 0.3 (at least ~8 days of data). Below this, the model hasn't learned enough to call anything unusual.
**Warning signs:** Test with a freshly-created EntityRoutine (zero history) fires unusual-time alert.

---

## Code Examples

Verified patterns drawing from Phase 3 established conventions:

### Accessing the RoutineModel API (Phase 3 delivered)
```python
# Source: routine_model.py — EntityRoutine public API
from custom_components.behaviour_monitor.routine_model import EntityRoutine

# In AcuteDetector.check_inactivity():
expected_gap: float | None = routine.expected_gap_seconds(hour=now.hour, dow=now.weekday())
# Returns None when slot has < MIN_SLOT_OBSERVATIONS (4) events

# In DriftDetector.check():
daily_count: int = routine.daily_activity_rate(target_date=today)
# Returns count of state changes recorded on that exact calendar date

# In either detector:
confidence: float = routine.confidence(now=now)
# Returns 0.0–1.0 based on observation history vs history_window_days
```

### Bidirectional CUSUM Step (10 lines, zero dependencies)
```python
# Source: STACK.md research (CUSUM formula, k/h parameters); Wikipedia CUSUM article
def _cusum_step(
    s_pos: float, s_neg: float, z: float, k: float
) -> tuple[float, float]:
    """One CUSUM update step. Returns updated (S_pos, S_neg)."""
    new_s_pos = max(0.0, s_pos + z - k)
    new_s_neg = max(0.0, s_neg - z - k)
    return new_s_pos, new_s_neg
```

### Consecutive-Cycle Counter Pattern (ACUTE-03)
```python
# Source: Architecture decision (04-CONTEXT.md — sustained evidence requirement)
def check_inactivity(self, entity_id: str, routine, now, last_seen) -> AlertResult | None:
    # ... compute threshold ...

    if elapsed < threshold:
        self._inactivity_cycles[entity_id] = 0  # CRITICAL: reset on clear
        return None

    count = self._inactivity_cycles.get(entity_id, 0) + 1
    self._inactivity_cycles[entity_id] = count

    if count < self._required_cycles:
        return None  # Accumulating evidence — not yet sustained

    # Produce result
    ...
```

### Unusual-Time Slot Check (Reusing Phase 3's Sparse Slot Guard)
```python
# Source: routine_model.py ActivitySlot.is_sufficient (Phase 3)
# is_sufficient == False means slot has < MIN_SLOT_OBSERVATIONS events
slot = routine.slots[routine.slot_index(hour=now.hour, dow=now.weekday())]
if slot.is_sufficient:
    return None  # Normal time — no alert
# else: unusual time — accumulate evidence cycles
```

### CUSUMState Serialization (Persistence Pattern)
```python
# Source: Established project pattern (to_dict/from_dict on all persisted dataclasses)
@dataclass
class CUSUMState:
    s_pos: float = 0.0
    s_neg: float = 0.0
    days_above_threshold: int = 0
    last_update_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "s_pos": self.s_pos,
            "s_neg": self.s_neg,
            "days_above_threshold": self.days_above_threshold,
            "last_update_date": self.last_update_date,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CUSUMState":
        obj = cls()
        obj.s_pos = float(data.get("s_pos", 0.0))
        obj.s_neg = float(data.get("s_neg", 0.0))
        obj.days_above_threshold = int(data.get("days_above_threshold", 0))
        obj.last_update_date = data.get("last_update_date")
        return obj
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Detection in coordinator (entangled with HA wiring) | Pure-Python detector classes, HA-free | v1.1 architecture decision | Detectors fully unit-testable; coordinator tests verify orchestration only |
| Fixed-threshold anomaly ("no motion for 2h") | Multiplier of learned typical interval | v1.1 | Alert fires at 3× the entity's own baseline — works for both active (every 30min) and quiet (every 4h) entities |
| River ML (Half-Space Trees) for drift | Bidirectional CUSUM on daily rates | v1.1 (River removed) | No external dependency; interpretable output; streaming algorithm |
| Z-score on 672 sparse buckets | Entity-specific baseline via 168 slots | v1.1 | Sufficient data per slot; z-score is valid; no more `float("inf")` from empty buckets |

**Deprecated/outdated:**
- River `HalfSpaceTrees`: removed from codebase in Phase 3. Do not reference.
- `PatternAnalyzer` z-score approach: deleted. AcuteDetector replaces it using RoutineModel data.
- Fixed welfare thresholds (2h, 4h hard-coded): replaced by multiplier of learned baseline.

---

## Open Questions

1. **CUSUM baseline normalization — z-score vs raw delta**
   - What we know: Using z-score (normalize by baseline stdev) makes `h` entity-agnostic. Raw delta requires entity-specific `h` values.
   - What's unclear: Baseline stdev computed from daily rates may be unstable for quiet entities with few events (e.g., front door: 3 events/day average, stdev approaches 0). Division by near-zero stdev amplifies CUSUM updates — false positives for quiet entities.
   - Recommendation: Clamp minimum stdev to `max(baseline_std, 1.0)` before z-score calculation. Alternatively, use raw delta with `k = baseline_mean * 0.25` (25% of baseline as allowance). Validate both approaches with TDD simulations.

2. **Confidence gate for unusual-time detection**
   - What we know: `slot.is_sufficient == False` catches both genuinely unusual times AND not-yet-learned slots.
   - What's unclear: At what confidence level is the model mature enough to flag unusual times?
   - Recommendation: Gate unusual-time detection on `routine.confidence(now) >= 0.3` (approximately 8+ days of data). Below this, all sparse slots are "learning" not "unusual." Document this in the detector.

3. **Drift detector baseline computation strategy**
   - What we know: `EntityRoutine.daily_activity_rate(date)` counts events on a specific calendar date from the slot deque. Building a baseline requires calling this for many historical dates.
   - What's unclear: Iterating across 28 days × all slots per entity per CUSUM step may be O(28 × 168 × 56) per entity — too slow for the 60s poll cycle with many entities.
   - Recommendation: Cache `_compute_baseline_rates()` result per entity per day (compute once, reuse across the poll cycle). Or maintain a rolling list of recent daily rates alongside the CUSUM state. Validate performance with 15-entity test before committing.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (asyncio_mode=auto per pytest.ini) |
| Config file | `pytest.ini` (project root) |
| Quick run command | `venv/bin/python -m pytest tests/test_acute_detector.py tests/test_drift_detector.py -x -q` |
| Full suite command | `venv/bin/python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACUTE-01 | Entity inactive 3× typical gap → no alert (cycle 1 and 2) | unit | `pytest tests/test_acute_detector.py::TestInactivityDetection::test_no_alert_before_sustained -x` | ❌ Wave 0 |
| ACUTE-01 | Entity inactive 3× typical gap → alert fires on cycle 3 | unit | `pytest tests/test_acute_detector.py::TestInactivityDetection::test_alert_fires_at_cycle_3 -x` | ❌ Wave 0 |
| ACUTE-01 | Sparse slot (< MIN_SLOT_OBSERVATIONS) → no inactivity alert regardless of elapsed time | unit | `pytest tests/test_acute_detector.py::TestInactivityDetection::test_sparse_slot_no_alert -x` | ❌ Wave 0 |
| ACUTE-01 | Condition clears → cycle counter resets → requires 3 fresh cycles | unit | `pytest tests/test_acute_detector.py::TestInactivityDetection::test_counter_resets_on_clear -x` | ❌ Wave 0 |
| ACUTE-01 | Severity: 2.5× → low; 4× → medium; 6× → high | unit | `pytest tests/test_acute_detector.py::TestInactivityDetection::test_severity_mapping -x` | ❌ Wave 0 |
| ACUTE-01 | AlertResult.explanation contains elapsed hours and multiplier ratio | unit | `pytest tests/test_acute_detector.py::TestInactivityDetection::test_explanation_format -x` | ❌ Wave 0 |
| ACUTE-02 | Activity in sparse slot + 3 cycles → unusual_time alert | unit | `pytest tests/test_acute_detector.py::TestUnusualTimeDetection::test_alert_fires_sparse_slot -x` | ❌ Wave 0 |
| ACUTE-02 | Activity in sufficient slot → no unusual_time alert | unit | `pytest tests/test_acute_detector.py::TestUnusualTimeDetection::test_no_alert_sufficient_slot -x` | ❌ Wave 0 |
| ACUTE-02 | Confidence gate: low confidence model → no unusual_time alert | unit | `pytest tests/test_acute_detector.py::TestUnusualTimeDetection::test_no_alert_low_confidence -x` | ❌ Wave 0 |
| ACUTE-03 | Single observation → no alert (inactivity) | unit | `pytest tests/test_acute_detector.py::TestInactivityDetection::test_no_alert_before_sustained -x` | ❌ Wave 0 |
| ACUTE-03 | Single observation → no alert (unusual_time) | unit | `pytest tests/test_acute_detector.py::TestUnusualTimeDetection::test_no_alert_single_cycle -x` | ❌ Wave 0 |
| DRIFT-01 | Stable baseline → CUSUM does not fire for 28 days | unit | `pytest tests/test_drift_detector.py::TestCUSUM::test_stable_no_alert -x` | ❌ Wave 0 |
| DRIFT-01 | 1-sigma upward shift → alert fires within 3-7 days (validate params) | unit | `pytest tests/test_drift_detector.py::TestCUSUM::test_upward_shift_fires -x` | ❌ Wave 0 |
| DRIFT-01 | 1-sigma downward shift → alert fires with direction="decrease" | unit | `pytest tests/test_drift_detector.py::TestCUSUM::test_downward_shift_fires -x` | ❌ Wave 0 |
| DRIFT-01 | Fewer than min_evidence_days history → no alert | unit | `pytest tests/test_drift_detector.py::TestCUSUM::test_insufficient_history_no_alert -x` | ❌ Wave 0 |
| DRIFT-01 | days_above_threshold < 3 → no alert even if S > h | unit | `pytest tests/test_drift_detector.py::TestCUSUM::test_min_evidence_window -x` | ❌ Wave 0 |
| DRIFT-01 | CUSUMState to_dict/from_dict round-trip preserves all fields | unit | `pytest tests/test_drift_detector.py::TestCUSUMState::test_serialization_round_trip -x` | ❌ Wave 0 |
| DRIFT-02 | routine_reset clears S_pos, S_neg, days_above_threshold | unit | `pytest tests/test_drift_detector.py::TestRoutineReset::test_reset_clears_accumulator -x` | ❌ Wave 0 |
| DRIFT-02 | routine_reset does not affect other entities | unit | `pytest tests/test_drift_detector.py::TestRoutineReset::test_reset_isolated_to_entity -x` | ❌ Wave 0 |
| DRIFT-02 | Acute detector unaffected by routine_reset | unit | `pytest tests/test_drift_detector.py::TestRoutineReset::test_acute_unaffected -x` | ❌ Wave 0 |
| DRIFT-03 | DriftDetector(sensitivity="high") uses k=0.25, h=2.0 | unit | `pytest tests/test_drift_detector.py::TestSensitivity::test_high_sensitivity_params -x` | ❌ Wave 0 |
| DRIFT-03 | DriftDetector(sensitivity="low") uses k=1.0, h=6.0 | unit | `pytest tests/test_drift_detector.py::TestSensitivity::test_low_sensitivity_params -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `venv/bin/python -m pytest tests/test_acute_detector.py tests/test_drift_detector.py tests/test_routine_model.py -x -q`
- **Per wave merge:** `venv/bin/python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_acute_detector.py` — new file; all AcuteDetector tests; pure Python, zero HA mocking required
- [ ] `tests/test_drift_detector.py` — new file; all DriftDetector + CUSUMState tests; pure Python, zero HA mocking required
- [ ] `custom_components/behaviour_monitor/alert_result.py` — AlertResult, AlertType, AlertSeverity dataclasses (must exist before detectors import from it)
- [ ] `custom_components/behaviour_monitor/acute_detector.py` — AcuteDetector class
- [ ] `custom_components/behaviour_monitor/drift_detector.py` — DriftDetector + CUSUMState classes
- [ ] `const.py` additions: `CUSUM_PARAMS` dict, `DEFAULT_INACTIVITY_MULTIPLIER = 3.0`, `SUSTAINED_EVIDENCE_CYCLES = 3`, `MIN_DRIFT_EVIDENCE_DAYS = 3`, `CONF_INACTIVITY_MULTIPLIER`, `CONF_DRIFT_SENSITIVITY`

*(No new test infrastructure required — existing `conftest.py` and pytest setup sufficient. Detector tests import only from the new pure-Python modules.)*

---

## Sources

### Primary (HIGH confidence)
- `/Users/abourne/Documents/source/behaviour-monitor/custom_components/behaviour_monitor/routine_model.py` — EntityRoutine public API: `expected_gap_seconds(hour, dow)`, `daily_activity_rate(date)`, `confidence(now)`, `slot_index(hour, dow)`, `slots` list, `ActivitySlot.is_sufficient`; serialization pattern
- `/Users/abourne/Documents/source/behaviour-monitor/.planning/phases/04-detection-engines/04-CONTEXT.md` — locked decisions: multiplier=3×, sustained_cycles=3, unusual_time via sparse slot guard, drift min_evidence=3 days, bidirectional CUSUM, routine_reset behavior
- `/Users/abourne/Documents/source/behaviour-monitor/.planning/research/STACK.md` — CUSUM formula and preliminary parameters (k=0.5, h=4.0) with MEDIUM confidence label; algorithm rationale
- `/Users/abourne/Documents/source/behaviour-monitor/.planning/research/ARCHITECTURE.md` — component boundaries, HA-free constraint, two-timescale data flow (callback for acute, poll for drift), data flow diagrams
- `/Users/abourne/Documents/source/behaviour-monitor/tests/conftest.py` — test infrastructure: HA module mocking approach, existing fixtures; pure-Python tests need no HA mocking

### Secondary (MEDIUM confidence)
- [Wikipedia: CUSUM](https://en.wikipedia.org/wiki/CUSUM) — bidirectional formula, ARL table, standard k/h parameter choices
- [Stackademic: The CUSUM Algorithm](https://blog.stackademic.com/the-cusum-algorithm-all-the-essential-information-you-need-with-python-examples-f6a5651bf2e5) — Python implementation examples; verified against Wikipedia formula
- `/Users/abourne/Documents/source/behaviour-monitor/.planning/STATE.md` — explicit flag: "CUSUM params (k=0.5, h=4.0) are MEDIUM confidence — validate against simulated scenarios during TDD"

### Tertiary (LOW confidence — validate during implementation)
- CUSUM parameter sensitivity table (k, h → ARL → days to detection) derived from training knowledge of CUSUM ARL tables for normal distributions. Actual ARL for Poisson-distributed daily sensor event counts will differ — validate empirically in TDD.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib only, zero new deps; established project pattern
- Algorithm design (CUSUM, cycle counter): HIGH — formula verified from Wikipedia + STACK.md; implementation pattern clear
- Alert result type design: HIGH — dataclass pattern established in project; shared base with type-specific details is straightforward
- CUSUM parameters (k, h per sensitivity level): MEDIUM — textbook defaults; actual home sensor data is non-Gaussian; STATE.md explicitly flags this
- Baseline rate computation performance: LOW — O(history) per entity per poll cycle; untested at scale; open question flagged

**Research date:** 2026-03-13
**Valid until:** 2026-06-13 (90 days; pure Python algorithms; no external library versioning concerns)
