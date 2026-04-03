"""AcuteDetector — inactivity and unusual-time detection engine.

Pure Python stdlib only. Zero Home Assistant imports.
Consumes EntityRoutine from routine_model.py and produces AlertResult objects.

Detection pattern: both check_inactivity and check_unusual_time require
SUSTAINED_EVIDENCE_CYCLES consecutive polling cycles of evidence before
an alert fires. This prevents transient false positives (research Pitfall 2).
"""

from __future__ import annotations

from datetime import datetime

from .alert_result import AlertResult, AlertSeverity, AlertType
from .const import (
    DEFAULT_INACTIVITY_MULTIPLIER,
    DEFAULT_MIN_INACTIVITY_MULTIPLIER,
    DEFAULT_MAX_INACTIVITY_MULTIPLIER,
    MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME,
    SUSTAINED_EVIDENCE_CYCLES,
    TIER_BOOST_FACTOR,
    TIER_FLOOR_SECONDS,
)
from .routine_model import EntityRoutine, format_duration


class AcuteDetector:
    """Detects inactivity and unusual-time anomalies for monitored entities.

    Maintains per-entity cycle counters so that alerts only fire after
    SUSTAINED_EVIDENCE_CYCLES consecutive polling intervals of evidence.
    Counters reset to zero whenever the condition clears.
    """

    def __init__(
        self,
        inactivity_multiplier: float = DEFAULT_INACTIVITY_MULTIPLIER,
        sustained_cycles: int = SUSTAINED_EVIDENCE_CYCLES,
        min_multiplier: float = DEFAULT_MIN_INACTIVITY_MULTIPLIER,
        max_multiplier: float = DEFAULT_MAX_INACTIVITY_MULTIPLIER,
    ) -> None:
        self._inactivity_multiplier = inactivity_multiplier
        self._sustained_cycles = sustained_cycles
        self._min_multiplier = min_multiplier
        self._max_multiplier = max_multiplier

        # Per-entity counters for sustained-evidence requirement
        self._inactivity_cycles: dict[str, int] = {}
        self._unusual_time_cycles: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_inactivity(
        self,
        entity_id: str,
        routine: EntityRoutine,
        now: datetime,
        last_seen: datetime | None,
    ) -> AlertResult | None:
        """Check whether an entity has been inactive for too long.

        Returns AlertResult after SUSTAINED_EVIDENCE_CYCLES consecutive cycles
        where elapsed time >= inactivity_multiplier * expected_gap.
        Returns None and resets counter on any cycle where the condition is not met.

        Args:
            entity_id:  The entity being checked.
            routine:    The entity's learned routine.
            now:        Current datetime (caller-provided for testability).
            last_seen:  When the entity last changed state; None if never seen.
        """
        # Guard: no last_seen means we cannot measure inactivity
        if last_seen is None:
            self._inactivity_cycles[entity_id] = 0
            return None

        # Guard: sparse slot — expected_gap unknown
        expected_gap = routine.expected_gap_seconds(now.hour, now.weekday())
        if expected_gap is None:
            self._inactivity_cycles[entity_id] = 0
            return None

        elapsed = (now - last_seen).total_seconds()
        cv = routine.interval_cv(now.hour, now.weekday())
        if cv is not None:
            raw_scalar = 1.0 + cv
            scalar: float | None = max(
                self._min_multiplier, min(self._max_multiplier, raw_scalar)
            )
            threshold = self._inactivity_multiplier * scalar * expected_gap
        else:
            scalar = None
            threshold = self._inactivity_multiplier * expected_gap

        # Tier-aware boost and floor (DET-01)
        tier = routine.activity_tier
        if tier is not None:
            threshold *= TIER_BOOST_FACTOR[tier]
            threshold = max(threshold, TIER_FLOOR_SECONDS[tier])

        # Condition not met — reset counter
        if elapsed < threshold:
            self._inactivity_cycles[entity_id] = 0
            return None

        # Condition met — increment counter
        current = self._inactivity_cycles.get(entity_id, 0) + 1
        self._inactivity_cycles[entity_id] = current

        # Not enough sustained evidence yet
        if current < self._sustained_cycles:
            return None

        # Enough sustained evidence — produce alert
        # severity_ratio = elapsed / threshold (how many times over the threshold)
        severity_ratio = elapsed / threshold
        severity = self._inactivity_severity(severity_ratio)
        elapsed_fmt = format_duration(elapsed)
        typical_fmt = format_duration(expected_gap)

        return AlertResult(
            entity_id=entity_id,
            alert_type=AlertType.INACTIVITY,
            severity=severity,
            confidence=routine.confidence(now),
            explanation=(
                f"{entity_id}: no activity for {elapsed_fmt} "
                f"(typical interval: {typical_fmt}, "
                f"{severity_ratio:.1f}x over threshold)"
            ),
            timestamp=now.isoformat(),
            details={
                "elapsed_seconds": elapsed,
                "expected_gap_seconds": expected_gap,
                "threshold_seconds": threshold,
                "severity_ratio": severity_ratio,
                "adaptive_scalar": scalar,
                "activity_tier": tier.value if tier is not None else None,
                "elapsed_formatted": elapsed_fmt,
                "typical_formatted": typical_fmt,
            },
        )

    def check_unusual_time(
        self,
        entity_id: str,
        routine: EntityRoutine,
        now: datetime,
    ) -> AlertResult | None:
        """Check whether activity is occurring at an unusual time.

        An unusual-time alert fires when the current slot has insufficient
        observations (sparse slot) AND the routine has enough confidence to
        distinguish "unusual" from "still learning" (research Pitfall 6).

        Returns AlertResult after SUSTAINED_EVIDENCE_CYCLES consecutive cycles
        of unusual-time evidence.
        Returns None and resets counter when condition is not met.

        Args:
            entity_id:  The entity being checked.
            routine:    The entity's learned routine.
            now:        Current datetime.
        """
        slot_index = routine.slot_index(now.hour, now.weekday())
        slot = routine.slots[slot_index]

        # Condition not met: slot is well-known (sufficient observations)
        if slot.is_sufficient:
            self._unusual_time_cycles[entity_id] = 0
            return None

        # Condition not met: confidence too low to distinguish unusual from learning
        confidence = routine.confidence(now)
        if confidence < MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME:
            self._unusual_time_cycles[entity_id] = 0
            return None

        # Condition met — increment counter
        current = self._unusual_time_cycles.get(entity_id, 0) + 1
        self._unusual_time_cycles[entity_id] = current

        # Not enough sustained evidence yet
        if current < self._sustained_cycles:
            return None

        return AlertResult(
            entity_id=entity_id,
            alert_type=AlertType.UNUSUAL_TIME,
            severity=AlertSeverity.LOW,
            confidence=confidence,
            explanation=(
                f"{entity_id}: activity at unusual time "
                f"(slot has insufficient history, "
                f"confidence: {confidence:.2f})"
            ),
            timestamp=now.isoformat(),
            details={
                "slot_index": slot_index,
                "confidence": confidence,
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _inactivity_severity(severity_ratio: float) -> AlertSeverity:
        """Map elapsed/threshold ratio to a severity tier.

        severity_ratio = elapsed / threshold (threshold = multiplier * expected_gap).

        <3.0  -> LOW    (barely over threshold to 3x the threshold)
        3.0–5.0 -> MEDIUM (3x–5x the threshold)
        >=5.0 -> HIGH   (5x+ the threshold)
        """
        if severity_ratio >= 5.0:
            return AlertSeverity.HIGH
        if severity_ratio >= 3.0:
            return AlertSeverity.MEDIUM
        return AlertSeverity.LOW
