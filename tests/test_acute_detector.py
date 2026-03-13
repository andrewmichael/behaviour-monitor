"""Tests for acute_detector.py — TDD RED/GREEN for Task 2.

Tests cover:
- check_inactivity: sparse slot, no last_seen, below threshold, sustained evidence,
  counter reset, severity tiers
- check_unusual_time: normal slot, low confidence, sustained evidence, counter reset
- Zero HA imports confirmed
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_routine(
    *,
    expected_gap: float | None = 3600.0,
    confidence: float = 0.8,
    slot_is_sufficient: bool = True,
) -> MagicMock:
    """Return a mock EntityRoutine with configurable properties."""
    routine = MagicMock()
    routine.expected_gap_seconds.return_value = expected_gap
    routine.confidence.return_value = confidence

    # Build a mock slot whose is_sufficient matches the parameter
    slot = MagicMock()
    slot.is_sufficient = slot_is_sufficient
    routine.slots = [slot] * 168  # 168 slots
    routine.slot_index.return_value = 0
    return routine


def make_now() -> datetime:
    """Return a fixed UTC datetime for deterministic tests."""
    return datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# check_inactivity
# ---------------------------------------------------------------------------


class TestCheckInactivitySparseSlot:
    """Returns None when expected_gap is None (sparse / insufficient slot)."""

    def test_returns_none_when_no_expected_gap(self) -> None:
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        routine = make_routine(expected_gap=None)
        now = make_now()
        last_seen = datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc)  # 10h ago

        result = detector.check_inactivity("sensor.test", routine, now, last_seen)
        assert result is None


class TestCheckInactivityNoLastSeen:
    """Returns None when last_seen is None."""

    def test_returns_none_when_last_seen_is_none(self) -> None:
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        routine = make_routine(expected_gap=3600.0)
        now = make_now()

        result = detector.check_inactivity("sensor.test", routine, now, None)
        assert result is None


class TestCheckInactivityBelowThreshold:
    """Returns None when elapsed < 3x expected_gap."""

    def test_returns_none_when_below_threshold(self) -> None:
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        # expected_gap = 3600s, threshold = 3x = 10800s
        # elapsed = 5400s (1.5x) — well below threshold
        routine = make_routine(expected_gap=3600.0)
        now = make_now()
        last_seen = datetime(2024, 6, 1, 8, 30, 0, tzinfo=timezone.utc)  # 90 min ago

        result = detector.check_inactivity("sensor.test", routine, now, last_seen)
        assert result is None

    def test_returns_none_at_exactly_threshold_minus_one_second(self) -> None:
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        # expected_gap = 3600s, threshold = 10800s
        # elapsed = 10799s — just under
        routine = make_routine(expected_gap=3600.0)
        now = make_now()
        from datetime import timedelta

        last_seen = now - timedelta(seconds=10799)

        result = detector.check_inactivity("sensor.test", routine, now, last_seen)
        assert result is None


class TestCheckInactivitySustainedEvidence:
    """Cycles 1 and 2 return None; cycle 3 returns AlertResult (ACUTE-03)."""

    def _run_cycles(self, n_cycles: int, elapsed_seconds: float = 15000.0):
        """Run n_cycles of check_inactivity; expected_gap=3600s (threshold=10800s)."""
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        routine = make_routine(expected_gap=3600.0)
        now = make_now()
        from datetime import timedelta

        last_seen = now - timedelta(seconds=elapsed_seconds)  # 4.17x threshold

        results = []
        for _ in range(n_cycles):
            results.append(
                detector.check_inactivity("sensor.test", routine, now, last_seen)
            )
        return results

    def test_cycle_1_returns_none(self) -> None:
        results = self._run_cycles(1)
        assert results[0] is None

    def test_cycle_2_returns_none(self) -> None:
        results = self._run_cycles(2)
        assert results[1] is None

    def test_cycle_3_returns_alert_result(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertResult

        results = self._run_cycles(3)
        assert isinstance(results[2], AlertResult)

    def test_cycle_3_has_correct_entity_id(self) -> None:
        results = self._run_cycles(3)
        assert results[2].entity_id == "sensor.test"

    def test_cycle_3_has_inactivity_type(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertType

        results = self._run_cycles(3)
        assert results[2].alert_type == AlertType.INACTIVITY

    def test_cycle_4_continues_to_return_alert(self) -> None:
        """Alert continues firing on cycle 4+ (sustained condition)."""
        from custom_components.behaviour_monitor.alert_result import AlertResult

        results = self._run_cycles(4)
        assert isinstance(results[3], AlertResult)


class TestCheckInactivityCounterReset:
    """Counter resets when condition clears; fresh 3 cycles needed to re-fire."""

    def test_counter_resets_when_below_threshold(self) -> None:
        """After 3 alert cycles, clear condition, then need 3 more cycles."""
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector
        from custom_components.behaviour_monitor.alert_result import AlertResult
        from datetime import timedelta

        detector = AcuteDetector()
        routine = make_routine(expected_gap=3600.0)
        now = make_now()

        # 3 cycles above threshold (4.17x)
        last_seen_far = now - timedelta(seconds=15000)
        for _ in range(3):
            detector.check_inactivity("sensor.test", routine, now, last_seen_far)

        # Condition clears (elapsed < threshold: 0.5x)
        last_seen_close = now - timedelta(seconds=1800)
        detector.check_inactivity("sensor.test", routine, now, last_seen_close)

        # Back above threshold — cycles 1 and 2 must return None again
        result_1 = detector.check_inactivity("sensor.test", routine, now, last_seen_far)
        result_2 = detector.check_inactivity("sensor.test", routine, now, last_seen_far)
        assert result_1 is None
        assert result_2 is None

        # Cycle 3 re-fires
        result_3 = detector.check_inactivity("sensor.test", routine, now, last_seen_far)
        assert isinstance(result_3, AlertResult)


# ---------------------------------------------------------------------------
# Severity tiers
# ---------------------------------------------------------------------------


class TestCheckInactivitySeverity:
    """Severity is based on elapsed / threshold (threshold = 3x expected_gap).

    LOW:    elapsed is 1x-3x the threshold  (barely exceeds threshold)
    MEDIUM: elapsed is 3x-5x the threshold
    HIGH:   elapsed is 5x+ the threshold

    The plan behavior states: ratio 2.5x -> LOW (2.5x the threshold),
    ratio 3.5x -> MEDIUM, ratio 6x -> HIGH.
    """

    def _fire_alert(self, threshold_ratio: float):
        """Run 3 cycles at the given elapsed/threshold ratio and return the alert.

        threshold_ratio: multiplier relative to (DEFAULT_INACTIVITY_MULTIPLIER * expected_gap).
        """
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector
        from custom_components.behaviour_monitor.const import DEFAULT_INACTIVITY_MULTIPLIER
        from datetime import timedelta

        detector = AcuteDetector()
        expected_gap = 3600.0
        threshold = DEFAULT_INACTIVITY_MULTIPLIER * expected_gap
        routine = make_routine(expected_gap=expected_gap)
        now = make_now()
        last_seen = now - timedelta(seconds=threshold * threshold_ratio)

        result = None
        for _ in range(3):
            result = detector.check_inactivity("sensor.test", routine, now, last_seen)
        return result

    def test_severity_low_at_2_5x_threshold(self) -> None:
        """2.5x the threshold -> LOW severity."""
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        alert = self._fire_alert(2.5)
        assert alert is not None
        assert alert.severity == AlertSeverity.LOW

    def test_severity_medium_at_3_5x_threshold(self) -> None:
        """3.5x the threshold -> MEDIUM severity."""
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        alert = self._fire_alert(3.5)
        assert alert is not None
        assert alert.severity == AlertSeverity.MEDIUM

    def test_severity_high_at_6x_threshold(self) -> None:
        """6x the threshold -> HIGH severity."""
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        alert = self._fire_alert(6.0)
        assert alert is not None
        assert alert.severity == AlertSeverity.HIGH

    def test_severity_boundary_exactly_1x_is_low(self) -> None:
        """Just at the threshold (1x) is LOW."""
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        # Use 1.01x to ensure we're just above threshold
        alert = self._fire_alert(1.01)
        assert alert is not None
        assert alert.severity == AlertSeverity.LOW

    def test_severity_boundary_exactly_3x_is_medium(self) -> None:
        """Exactly 3.0x the threshold is MEDIUM (ratio/threshold >= 3.0 and < 5.0)."""
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        alert = self._fire_alert(3.0)
        assert alert is not None
        assert alert.severity == AlertSeverity.MEDIUM

    def test_severity_boundary_exactly_5x_is_high(self) -> None:
        """Exactly 5.0x the threshold is HIGH (ratio/threshold >= 5.0)."""
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        alert = self._fire_alert(5.0)
        assert alert is not None
        assert alert.severity == AlertSeverity.HIGH


# ---------------------------------------------------------------------------
# check_unusual_time
# ---------------------------------------------------------------------------


class TestCheckUnusualTimeNormalSlot:
    """Returns None when slot.is_sufficient is True (normal active slot)."""

    def test_returns_none_for_sufficient_slot(self) -> None:
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        routine = make_routine(slot_is_sufficient=True, confidence=0.9)
        now = make_now()

        result = detector.check_unusual_time("sensor.test", routine, now)
        assert result is None


class TestCheckUnusualTimeLowConfidence:
    """Returns None when routine.confidence < MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME (0.3)."""

    def test_returns_none_when_confidence_too_low(self) -> None:
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        # sparse slot (not sufficient) BUT confidence below threshold
        routine = make_routine(slot_is_sufficient=False, confidence=0.2)
        now = make_now()

        result = detector.check_unusual_time("sensor.test", routine, now)
        assert result is None

    def test_returns_none_at_exactly_0_29_confidence(self) -> None:
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        routine = make_routine(slot_is_sufficient=False, confidence=0.29)
        now = make_now()

        result = detector.check_unusual_time("sensor.test", routine, now)
        assert result is None


class TestCheckUnusualTimeSustainedEvidence:
    """Unusual-time alert requires 3 consecutive cycles of sparse+confident slot."""

    def _run_cycles(self, n_cycles: int):
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        routine = make_routine(slot_is_sufficient=False, confidence=0.8)
        now = make_now()

        results = []
        for _ in range(n_cycles):
            results.append(detector.check_unusual_time("sensor.test", routine, now))
        return results

    def test_cycle_1_returns_none(self) -> None:
        results = self._run_cycles(1)
        assert results[0] is None

    def test_cycle_2_returns_none(self) -> None:
        results = self._run_cycles(2)
        assert results[1] is None

    def test_cycle_3_returns_alert_result(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertResult

        results = self._run_cycles(3)
        assert isinstance(results[2], AlertResult)

    def test_cycle_3_has_unusual_time_type(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertType

        results = self._run_cycles(3)
        assert results[2].alert_type == AlertType.UNUSUAL_TIME

    def test_cycle_3_entity_id_correct(self) -> None:
        results = self._run_cycles(3)
        assert results[2].entity_id == "sensor.test"


class TestCheckUnusualTimeCounterReset:
    """Counter resets when condition clears (slot becomes sufficient or confidence drops)."""

    def test_counter_resets_when_slot_becomes_sufficient(self) -> None:
        """3 unusual cycles, then slot becomes sufficient — re-fire needs 3 fresh cycles."""
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector
        from custom_components.behaviour_monitor.alert_result import AlertResult

        detector = AcuteDetector()
        routine_sparse = make_routine(slot_is_sufficient=False, confidence=0.8)
        routine_normal = make_routine(slot_is_sufficient=True, confidence=0.8)
        now = make_now()

        # 3 unusual cycles
        for _ in range(3):
            detector.check_unusual_time("sensor.test", routine_sparse, now)

        # Condition clears (slot is now sufficient)
        detector.check_unusual_time("sensor.test", routine_normal, now)

        # Back to sparse — needs 3 more cycles; cycles 1 and 2 must return None
        result_1 = detector.check_unusual_time("sensor.test", routine_sparse, now)
        result_2 = detector.check_unusual_time("sensor.test", routine_sparse, now)
        assert result_1 is None
        assert result_2 is None

        # Cycle 3 re-fires
        result_3 = detector.check_unusual_time("sensor.test", routine_sparse, now)
        assert isinstance(result_3, AlertResult)


# ---------------------------------------------------------------------------
# AlertResult explanation quality
# ---------------------------------------------------------------------------


class TestAlertResultExplanation:
    """AlertResult explanation carries human-readable context."""

    def test_inactivity_explanation_contains_entity_id(self) -> None:
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector
        from datetime import timedelta

        detector = AcuteDetector()
        routine = make_routine(expected_gap=3600.0)
        now = make_now()
        last_seen = now - timedelta(seconds=15000)

        for _ in range(3):
            result = detector.check_inactivity("sensor.kitchen", routine, now, last_seen)

        assert "sensor.kitchen" in result.explanation

    def test_unusual_time_explanation_contains_entity_id(self) -> None:
        from custom_components.behaviour_monitor.acute_detector import AcuteDetector

        detector = AcuteDetector()
        routine = make_routine(slot_is_sufficient=False, confidence=0.8)
        now = make_now()

        result = None
        for _ in range(3):
            result = detector.check_unusual_time("sensor.bathroom", routine, now)

        assert "sensor.bathroom" in result.explanation


# ---------------------------------------------------------------------------
# Zero HA imports
# ---------------------------------------------------------------------------


class TestNoHAImports:
    """acute_detector.py must not import any homeassistant modules."""

    def test_no_homeassistant_imports(self) -> None:
        import subprocess

        result = subprocess.run(
            [
                "grep",
                "-c",
                "homeassistant",
                "custom_components/behaviour_monitor/acute_detector.py",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        count = int(result.stdout.strip()) if result.stdout.strip() else 0
        assert count == 0, "acute_detector.py must have zero homeassistant imports"
