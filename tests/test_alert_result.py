"""Tests for alert_result.py shared types — TDD RED phase for Task 1."""

from __future__ import annotations

import pytest


class TestAlertTypeEnum:
    """AlertType enum has the correct values and str serialization."""

    def test_alert_type_inactivity(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertType

        assert AlertType.INACTIVITY == "inactivity"

    def test_alert_type_unusual_time(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertType

        assert AlertType.UNUSUAL_TIME == "unusual_time"

    def test_alert_type_drift(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertType

        assert AlertType.DRIFT == "drift"

    def test_alert_type_is_str(self) -> None:
        """AlertType inherits from str for JSON serialization."""
        from custom_components.behaviour_monitor.alert_result import AlertType

        assert isinstance(AlertType.INACTIVITY, str)


class TestAlertSeverityEnum:
    """AlertSeverity enum has the correct values and str serialization."""

    def test_severity_low(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        assert AlertSeverity.LOW == "low"

    def test_severity_medium(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        assert AlertSeverity.MEDIUM == "medium"

    def test_severity_high(self) -> None:
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        assert AlertSeverity.HIGH == "high"

    def test_severity_is_str(self) -> None:
        """AlertSeverity inherits from str for JSON serialization."""
        from custom_components.behaviour_monitor.alert_result import AlertSeverity

        assert isinstance(AlertSeverity.HIGH, str)


class TestAlertResultDataclass:
    """AlertResult dataclass fields, defaults, and to_dict."""

    def _make_result(self, **kwargs):
        from custom_components.behaviour_monitor.alert_result import (
            AlertResult,
            AlertSeverity,
            AlertType,
        )

        defaults = {
            "entity_id": "sensor.kitchen_motion",
            "alert_type": AlertType.INACTIVITY,
            "severity": AlertSeverity.HIGH,
            "confidence": 0.9,
            "explanation": "No activity for 5 hours (typical: 1 hour)",
            "timestamp": "2024-01-01T00:00:00",
        }
        defaults.update(kwargs)
        return AlertResult(**defaults)

    def test_fields_accessible(self) -> None:
        r = self._make_result()
        assert r.entity_id == "sensor.kitchen_motion"
        assert r.confidence == 0.9

    def test_details_defaults_to_empty_dict(self) -> None:
        r = self._make_result()
        assert r.details == {}

    def test_details_can_be_set(self) -> None:
        r = self._make_result(details={"elapsed_hours": 5.0})
        assert r.details["elapsed_hours"] == 5.0

    def test_to_dict_returns_dict(self) -> None:
        r = self._make_result()
        d = r.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_alert_type_is_string(self) -> None:
        """Enum must be serialized to .value string, not enum object."""
        r = self._make_result()
        d = r.to_dict()
        assert d["alert_type"] == "inactivity"
        assert isinstance(d["alert_type"], str)

    def test_to_dict_severity_is_string(self) -> None:
        r = self._make_result()
        d = r.to_dict()
        assert d["severity"] == "high"
        assert isinstance(d["severity"], str)

    def test_to_dict_all_expected_keys(self) -> None:
        r = self._make_result()
        d = r.to_dict()
        expected_keys = {
            "entity_id",
            "alert_type",
            "severity",
            "confidence",
            "explanation",
            "timestamp",
            "details",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_entity_id_preserved(self) -> None:
        r = self._make_result(entity_id="binary_sensor.front_door")
        d = r.to_dict()
        assert d["entity_id"] == "binary_sensor.front_door"

    def test_to_dict_confidence_preserved(self) -> None:
        r = self._make_result(confidence=0.75)
        d = r.to_dict()
        assert d["confidence"] == 0.75

    def test_to_dict_details_preserved(self) -> None:
        r = self._make_result(details={"ratio": 3.5})
        d = r.to_dict()
        assert d["details"] == {"ratio": 3.5}

    def test_to_dict_unusual_time_type(self) -> None:
        from custom_components.behaviour_monitor.alert_result import (
            AlertSeverity,
            AlertType,
        )

        r = self._make_result(
            alert_type=AlertType.UNUSUAL_TIME, severity=AlertSeverity.LOW
        )
        d = r.to_dict()
        assert d["alert_type"] == "unusual_time"
        assert d["severity"] == "low"


class TestConstDetectionConstants:
    """const.py has the new detection constants added."""

    def test_default_inactivity_multiplier(self) -> None:
        from custom_components.behaviour_monitor.const import (
            DEFAULT_INACTIVITY_MULTIPLIER,
        )

        assert DEFAULT_INACTIVITY_MULTIPLIER == 3.0

    def test_sustained_evidence_cycles(self) -> None:
        from custom_components.behaviour_monitor.const import SUSTAINED_EVIDENCE_CYCLES

        assert SUSTAINED_EVIDENCE_CYCLES == 3

    def test_min_evidence_days(self) -> None:
        from custom_components.behaviour_monitor.const import MIN_EVIDENCE_DAYS

        assert MIN_EVIDENCE_DAYS == 3

    def test_minimum_confidence_for_unusual_time(self) -> None:
        from custom_components.behaviour_monitor.const import (
            MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME,
        )

        assert MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME == 0.3

    def test_cusum_params_has_three_levels(self) -> None:
        from custom_components.behaviour_monitor.const import CUSUM_PARAMS

        assert set(CUSUM_PARAMS.keys()) == {"high", "medium", "low"}

    def test_cusum_params_high(self) -> None:
        from custom_components.behaviour_monitor.const import CUSUM_PARAMS

        assert CUSUM_PARAMS["high"] == (0.25, 2.0)

    def test_cusum_params_medium(self) -> None:
        from custom_components.behaviour_monitor.const import CUSUM_PARAMS

        assert CUSUM_PARAMS["medium"] == (0.5, 4.0)

    def test_cusum_params_low(self) -> None:
        from custom_components.behaviour_monitor.const import CUSUM_PARAMS

        assert CUSUM_PARAMS["low"] == (1.0, 6.0)

    def test_no_ha_imports_in_alert_result(self) -> None:
        """alert_result.py must have zero Home Assistant imports."""
        import subprocess

        result = subprocess.run(
            [
                "grep",
                "-c",
                "homeassistant",
                "custom_components/behaviour_monitor/alert_result.py",
            ],
            capture_output=True,
            text=True,
            cwd="/Users/abourne/Documents/source/behaviour-monitor",
        )
        # grep returns exit code 1 when no matches found
        count = int(result.stdout.strip()) if result.stdout.strip() else 0
        assert count == 0, "alert_result.py must have zero homeassistant imports"
