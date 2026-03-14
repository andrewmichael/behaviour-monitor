"""DriftDetector — CUSUM-based persistent shift detector.

Pure Python stdlib only. Zero Home Assistant imports.
Detects gradual, sustained changes in daily activity rates using the
Cumulative Sum (CUSUM) algorithm, which distinguishes genuine routine
changes from transient noise via an evidence window.

Typical use case: welfare monitoring — e.g., detecting a gradual decline in
kitchen motion over several days that might indicate a health concern.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .alert_result import AlertResult, AlertSeverity, AlertType
from .const import CUSUM_PARAMS, MIN_EVIDENCE_DAYS, SENSITIVITY_MEDIUM
from .routine_model import EntityRoutine


# ---------------------------------------------------------------------------
# CUSUMState
# ---------------------------------------------------------------------------


@dataclass
class CUSUMState:
    """Per-entity CUSUM accumulator state.

    Fields:
        s_pos:               CUSUM statistic for upward drift (S+).
        s_neg:               CUSUM statistic for downward drift (S-).
        days_above_threshold: Consecutive days where S+ or S- exceeds threshold h.
        last_update_date:    ISO date string of the last day check() was called;
                             None if never updated.
    """

    s_pos: float = 0.0
    s_neg: float = 0.0
    days_above_threshold: int = 0
    last_update_date: str | None = None

    def reset(self) -> None:
        """Zero the CUSUM accumulators and consecutive-day counter.

        last_update_date is intentionally preserved so that the idempotency
        guard still functions after a user-initiated routine_reset.
        """
        self.s_pos = 0.0
        self.s_neg = 0.0
        self.days_above_threshold = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "s_pos": self.s_pos,
            "s_neg": self.s_neg,
            "days_above_threshold": self.days_above_threshold,
            "last_update_date": self.last_update_date,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CUSUMState":
        """Restore from a serialized dict."""
        return cls(
            s_pos=float(data.get("s_pos", 0.0)),
            s_neg=float(data.get("s_neg", 0.0)),
            days_above_threshold=int(data.get("days_above_threshold", 0)),
            last_update_date=data.get("last_update_date"),
        )


# ---------------------------------------------------------------------------
# DriftDetector
# ---------------------------------------------------------------------------


class DriftDetector:
    """Bidirectional CUSUM drift detector.

    Detects persistent upward or downward shifts in an entity's daily activity
    rate. An alert fires only after the CUSUM statistic has exceeded the
    detection threshold h for at least MIN_EVIDENCE_DAYS consecutive days,
    preventing transient spikes from producing false alerts.

    Usage:
        detector = DriftDetector(sensitivity="medium")
        result = detector.check(entity_id, routine, today, now)
        if result:
            # Genuine sustained drift detected
            pass
    """

    def __init__(self, sensitivity: str = SENSITIVITY_MEDIUM) -> None:
        params = CUSUM_PARAMS.get(sensitivity)
        if params is None:
            params = CUSUM_PARAMS[SENSITIVITY_MEDIUM]
        self._k, self._h = params
        self._sensitivity = sensitivity if sensitivity in CUSUM_PARAMS else SENSITIVITY_MEDIUM
        self._states: dict[str, CUSUMState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create_state(self, entity_id: str) -> CUSUMState:
        """Return the CUSUMState for entity_id, creating a blank one if needed."""
        if entity_id not in self._states:
            self._states[entity_id] = CUSUMState()
        return self._states[entity_id]

    def reset_entity(self, entity_id: str) -> None:
        """Clear the CUSUM accumulator for a specific entity.

        Does not affect any other entity's state. Safe to call for entities
        that have no recorded state.
        """
        if entity_id in self._states:
            self._states[entity_id].reset()

    def check(
        self,
        entity_id: str,
        routine: EntityRoutine,
        today: date,
        now: datetime,
    ) -> AlertResult | None:
        """Check for drift in entity activity rate using CUSUM.

        Returns an AlertResult if sustained drift is confirmed, or None if:
        - Already processed today (idempotent guard).
        - Insufficient baseline history (< MIN_EVIDENCE_DAYS unique dates).
        - Baseline mean is zero (no events in history — division guard).
        - The CUSUM statistic hasn't exceeded threshold for 3+ consecutive days.

        Args:
            entity_id: The monitored entity identifier.
            routine:   EntityRoutine containing historical event_times data.
            today:     Calendar date to treat as "today" (excluded from baseline).
            now:       Current datetime (used for AlertResult timestamp and confidence).

        Returns:
            AlertResult | None
        """
        state = self.get_or_create_state(entity_id)
        today_iso = today.isoformat()

        # --- Idempotency guard ---
        if state.last_update_date == today_iso:
            return None

        # --- Determine day type ---
        day_type = "weekend" if today.weekday() >= 5 else "weekday"

        # --- Compute baseline rates (day-type-split with recency weighting) ---
        day_type_counts = self._compute_baseline_rates_for_day_type(
            routine, exclude_today=today, day_type=day_type
        )
        if len(day_type_counts) >= MIN_EVIDENCE_DAYS:
            baseline_rates_for_stdev = list(day_type_counts.values())
            baseline_mean = self._compute_weighted_mean(day_type_counts, today)
        else:
            # Fallback: combined pool (all day types)
            all_counts = self._compute_baseline_rates(routine, exclude_today=today)
            if len(all_counts) < MIN_EVIDENCE_DAYS:
                return None
            combined_counts: dict[date, int] = {}
            for dt_type in ("weekday", "weekend"):
                combined_counts.update(
                    self._compute_baseline_rates_for_day_type(
                        routine, exclude_today=today, day_type=dt_type
                    )
                )
            baseline_rates_for_stdev = list(combined_counts.values())
            baseline_mean = self._compute_weighted_mean(combined_counts, today)

        if baseline_mean == 0:
            return None

        # --- Compute baseline stdev ---
        if len(baseline_rates_for_stdev) >= 2:
            try:
                baseline_stdev = statistics.stdev(baseline_rates_for_stdev)
            except statistics.StatisticsError:
                baseline_stdev = 0.0
        else:
            baseline_stdev = 0.0

        # Guard: if stdev is 0, all values are identical — use a small default
        # to avoid infinite z-scores while still allowing CUSUM to detect shifts.
        if baseline_stdev == 0.0:
            baseline_stdev = max(1.0, baseline_mean * 0.1)

        # --- Today's activity rate ---
        today_rate = routine.daily_activity_rate(today)

        # --- Z-score standardisation ---
        z = (today_rate - baseline_mean) / baseline_stdev

        # --- CUSUM update (bidirectional) ---
        state.s_pos = max(0.0, state.s_pos + z - self._k)
        state.s_neg = max(0.0, state.s_neg - z - self._k)

        # --- Evidence accumulation ---
        if state.s_pos > self._h or state.s_neg > self._h:
            state.days_above_threshold += 1
        else:
            state.days_above_threshold = 0

        # --- Mark as processed today ---
        state.last_update_date = today_iso

        # --- Fire alert only after evidence window ---
        if state.days_above_threshold < MIN_EVIDENCE_DAYS:
            return None

        # --- Determine drift direction ---
        direction = "increase" if state.s_pos >= state.s_neg else "decrease"

        # --- Build AlertResult ---
        severity = self._drift_severity(state.days_above_threshold)
        confidence = routine.confidence(now)

        explanation = (
            f"Persistent activity {direction} detected for {entity_id}: "
            f"{state.days_above_threshold} consecutive days of shifted behaviour. "
            f"Baseline rate: {baseline_mean:.1f} events/day, "
            f"today: {today_rate} events/day."
        )

        return AlertResult(
            entity_id=entity_id,
            alert_type=AlertType.DRIFT,
            severity=severity,
            confidence=confidence,
            explanation=explanation,
            timestamp=now.isoformat(),
            details={
                "direction": direction,
                "days_above_threshold": state.days_above_threshold,
                "baseline_rate": round(baseline_mean, 2),
                "today_rate": today_rate,
                "s_pos": round(state.s_pos, 4),
                "s_neg": round(state.s_neg, 4),
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_baseline_rates_for_day_type(
        self,
        routine: EntityRoutine,
        exclude_today: date,
        day_type: str,  # "weekday" or "weekend"
    ) -> dict[date, int]:
        """Return date->count mapping filtered to matching day_type.

        Args:
            routine:      EntityRoutine with populated event_times.
            exclude_today: Calendar date to exclude from baseline (today's data).
            day_type:     "weekday" (Mon-Fri) or "weekend" (Sat-Sun).

        Returns:
            Dict mapping each matching date to its event count.
        """
        is_weekend = day_type == "weekend"
        date_counts: dict[date, int] = {}
        for slot in routine.slots:
            for ts_str in slot.event_times:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    event_date = dt.date()
                except (ValueError, TypeError):
                    continue
                if event_date == exclude_today:
                    continue
                dow = event_date.weekday()
                event_is_weekend = dow >= 5
                if event_is_weekend != is_weekend:
                    continue
                date_counts[event_date] = date_counts.get(event_date, 0) + 1
        return date_counts

    @staticmethod
    def _compute_weighted_mean(
        date_counts: dict[date, int],
        reference_date: date,
        decay_factor: float = 0.95,
    ) -> float:
        """Compute exponentially decay-weighted mean of daily counts.

        Recent dates have weight closer to 1.0; older dates approach 0.
        decay_factor=0.95 halves weight every ~14 days.

        Args:
            date_counts:    Dict mapping event dates to their daily counts.
            reference_date: The date from which age is measured (typically today).
            decay_factor:   Per-day decay multiplier (default 0.95).

        Returns:
            Weighted mean count, or 0.0 if date_counts is empty.
        """
        if not date_counts:
            return 0.0
        total_weight = 0.0
        weighted_sum = 0.0
        for event_date, count in date_counts.items():
            age_days = (reference_date - event_date).days
            weight = decay_factor ** max(0, age_days)
            weighted_sum += count * weight
            total_weight += weight
        if total_weight == 0.0:
            return 0.0
        return weighted_sum / total_weight

    def _compute_baseline_rates(
        self, routine: EntityRoutine, exclude_today: date
    ) -> list[int]:
        """Compute daily event counts from routine event_times, excluding today.

        Scans all slots' event_times deques and groups events by calendar date.
        Returns a list of daily counts (one integer per unique date found).

        Args:
            routine:      EntityRoutine with populated event_times.
            exclude_today: Calendar date to exclude from baseline (today's data).

        Returns:
            List of integer daily event counts; may be empty.
        """
        date_counts: dict[date, int] = {}

        for slot in routine.slots:
            for ts_str in slot.event_times:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    event_date = dt.date()
                except (ValueError, TypeError):
                    continue

                if event_date == exclude_today:
                    continue

                date_counts[event_date] = date_counts.get(event_date, 0) + 1

        return list(date_counts.values())

    @staticmethod
    def _drift_severity(days: int) -> AlertSeverity:
        """Map consecutive days above threshold to an AlertSeverity.

        Tiers:
            < 3 days  -> LOW  (sub-evidence; only reached if guard is bypassed)
            3–6 days  -> MEDIUM
            7+ days   -> HIGH
        """
        if days >= 7:
            return AlertSeverity.HIGH
        if days >= 3:
            return AlertSeverity.MEDIUM
        return AlertSeverity.LOW

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize detector state to a JSON-safe dict."""
        return {
            "sensitivity": self._sensitivity,
            "states": {
                entity_id: state.to_dict()
                for entity_id, state in self._states.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DriftDetector":
        """Restore a DriftDetector from a serialized dict."""
        detector = cls(sensitivity=data.get("sensitivity", SENSITIVITY_MEDIUM))
        for entity_id, state_data in data.get("states", {}).items():
            detector._states[entity_id] = CUSUMState.from_dict(state_data)
        return detector
