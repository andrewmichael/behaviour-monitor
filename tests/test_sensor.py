"""Tests for the sensor platform."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from custom_components.behaviour_monitor.sensor import (
    BehaviourMonitorSensor,
    SENSOR_DESCRIPTIONS,
    async_setup_entry,
)
from custom_components.behaviour_monitor.coordinator import BehaviourMonitorCoordinator
from custom_components.behaviour_monitor.const import DOMAIN


class TestSensorDescriptions:
    """Tests for sensor value and attribute functions."""

    def test_last_activity_sensor_with_timestamp(self) -> None:
        """Test last_activity sensor with valid timestamp."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "last_activity")
        data = {"last_activity": "2024-01-15T10:30:00"}

        result = sensor.value_fn(data)

        assert isinstance(result, datetime)
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_last_activity_sensor_without_timestamp(self) -> None:
        """Test last_activity sensor without timestamp."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "last_activity")
        data = {}

        result = sensor.value_fn(data)

        assert result is None

    def test_activity_score_sensor(self) -> None:
        """Test activity_score sensor rounding."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "activity_score")
        data = {"activity_score": 75.678}

        result = sensor.value_fn(data)

        assert result == 75.7

    def test_activity_score_sensor_default(self) -> None:
        """Test activity_score sensor with missing data."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "activity_score")
        data = {}

        result = sensor.value_fn(data)

        assert result == 0

    def test_anomaly_detected_sensor_true(self) -> None:
        """Test anomaly_detected sensor when anomaly present."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "anomaly_detected")
        data = {"anomaly_detected": True}

        result = sensor.value_fn(data)

        assert result == "on"

    def test_anomaly_detected_sensor_false(self) -> None:
        """Test anomaly_detected sensor when no anomaly."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "anomaly_detected")
        data = {"anomaly_detected": False}

        result = sensor.value_fn(data)

        assert result == "off"

    def test_anomaly_detected_extra_attrs(self) -> None:
        """Test anomaly_detected sensor extra attributes."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "anomaly_detected")
        coord = MagicMock()
        data = {"anomalies": [{"entity": "sensor.test", "score": -3.5}]}

        result = sensor.extra_attrs_fn(coord, data)

        assert "anomaly_details" in result
        assert len(result["anomaly_details"]) == 1

    def test_baseline_confidence_sensor(self) -> None:
        """Test baseline_confidence sensor."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "baseline_confidence")
        data = {"confidence": 85.432}

        result = sensor.value_fn(data)

        assert result == 85.4

    def test_baseline_confidence_extra_attrs(self) -> None:
        """Test baseline_confidence sensor extra attributes."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "baseline_confidence")
        coord = MagicMock()
        coord.analyzer.is_learning_complete.return_value = True
        data = {
            "confidence": 85.0,
            "ml_status": {
                "enabled": True,
                "trained": True,
                "last_trained": "2024-01-15T10:00:00",
            },
        }

        result = sensor.extra_attrs_fn(coord, data)

        assert result["learning_progress"] == "complete"
        assert result["ml_status"]["enabled"] is True
        assert result["last_retrain"] == "2024-01-15T10:00:00"

    def test_daily_activity_count_sensor(self) -> None:
        """Test daily_activity_count sensor."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "daily_activity_count")
        data = {"daily_count": 42}

        result = sensor.value_fn(data)

        assert result == 42

    def test_daily_activity_count_extra_attrs(self) -> None:
        """Test daily_activity_count sensor extra attributes."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "daily_activity_count")
        coord = MagicMock()
        coord.monitored_entities = {"sensor.test1", "sensor.test2"}
        data = {"daily_count": 42}

        result = sensor.extra_attrs_fn(coord, data)

        assert "monitored_entities" in result
        assert len(result["monitored_entities"]) == 2

    def test_cross_sensor_patterns_sensor(self) -> None:
        """Test cross_sensor_patterns sensor returns stub value 0 (deprecated in v1.1)."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "cross_sensor_patterns")
        data = {
            "cross_sensor_patterns": [
                {"pattern": "A -> B", "strength": 0.8},
                {"pattern": "C -> D", "strength": 0.6},
            ]
        }

        result = sensor.value_fn(data)

        assert result == 0

    def test_cross_sensor_patterns_extra_attrs(self) -> None:
        """Test cross_sensor_patterns sensor extra attributes contain deprecated flag."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "cross_sensor_patterns")
        coord = MagicMock()
        patterns = [{"pattern": "A -> B", "strength": 0.8}]
        data = {"cross_sensor_patterns": patterns}

        result = sensor.extra_attrs_fn(coord, data)

        assert result["deprecated"] is True

    def test_ml_status_sensor_ready(self) -> None:
        """Test ml_status sensor returns stub value (deprecated in v1.1)."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_status")
        data = {
            "ml_training": {"complete": True},
            "ml_status": {"enabled": True, "trained": True},
        }

        result = sensor.value_fn(data)

        assert result == "Removed in v1.1"

    def test_ml_status_sensor_trained_learning(self) -> None:
        """Test ml_status sensor returns stub regardless of training state."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_status")
        data = {
            "ml_training": {"complete": False},
            "ml_status": {"enabled": True, "trained": True},
        }

        result = sensor.value_fn(data)

        assert result == "Removed in v1.1"

    def test_ml_status_sensor_learning(self) -> None:
        """Test ml_status sensor returns stub regardless of learning state."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_status")
        data = {
            "ml_training": {"complete": False},
            "ml_status": {"enabled": True, "trained": False},
        }

        result = sensor.value_fn(data)

        assert result == "Removed in v1.1"

    def test_ml_status_sensor_disabled(self) -> None:
        """Test ml_status sensor returns stub regardless of disabled state."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_status")
        data = {
            "ml_training": {"complete": False},
            "ml_status": {"enabled": False, "trained": False},
        }

        result = sensor.value_fn(data)

        assert result == "Removed in v1.1"

    def test_ml_status_extra_attrs(self) -> None:
        """Test ml_status sensor extra attributes contain deprecated flag."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_status")
        coord = MagicMock()
        coord.ml_analyzer.ml_available = True
        data = {
            "ml_training": {"complete": True, "days_remaining": 0},
            "ml_status": {
                "enabled": True,
                "trained": True,
                "sample_count": 150,
                "last_trained": "2024-01-15T10:00:00",
                "next_retrain": "2024-01-29T10:00:00",
            },
        }

        result = sensor.extra_attrs_fn(coord, data)

        assert result["deprecated"] is True

    def test_welfare_status_sensor(self) -> None:
        """Test welfare_status sensor."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "welfare_status")
        data = {"welfare": {"status": "normal"}}

        result = sensor.value_fn(data)

        assert result == "normal"

    def test_welfare_status_extra_attrs(self) -> None:
        """Test welfare_status sensor extra attributes."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "welfare_status")
        coord = MagicMock()
        data = {
            "welfare": {
                "status": "attention",
                "reasons": ["Low activity"],
                "summary": "Activity below normal",
                "recommendation": "Check in",
                "entity_count_by_status": {"normal": 2, "attention": 1},
            }
        }

        result = sensor.extra_attrs_fn(coord, data)

        assert result["reasons"] == ["Low activity"]
        assert result["summary"] == "Activity below normal"
        assert result["recommendation"] == "Check in"
        assert result["entity_count_by_status"]["attention"] == 1

    def test_routine_progress_sensor(self) -> None:
        """Test routine_progress sensor."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "routine_progress")
        data = {"routine": {"progress_percent": 67.5}}

        result = sensor.value_fn(data)

        assert result == 67.5

    def test_routine_progress_extra_attrs(self) -> None:
        """Test routine_progress sensor extra attributes."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "routine_progress")
        coord = MagicMock()
        data = {
            "routine": {
                "progress_percent": 67.5,
                "expected_by_now": 10,
                "actual_today": 8,
                "expected_full_day": 15,
                "status": "below_normal",
                "summary": "Slightly behind schedule",
            }
        }

        result = sensor.extra_attrs_fn(coord, data)

        assert result["expected_by_now"] == 10
        assert result["actual_today"] == 8
        assert result["expected_full_day"] == 15
        assert result["status"] == "below_normal"

    def test_time_since_activity_sensor(self) -> None:
        """Test time_since_activity sensor."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "time_since_activity")
        data = {"activity_context": {"time_since_formatted": "2 hours"}}

        result = sensor.value_fn(data)

        assert result == "2 hours"

    def test_time_since_activity_extra_attrs(self) -> None:
        """Test time_since_activity sensor extra attributes."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "time_since_activity")
        coord = MagicMock()
        data = {
            "activity_context": {
                "time_since_formatted": "2 hours",
                "time_since_seconds": 7200,
                "typical_interval_seconds": 3600,
                "typical_interval_formatted": "1 hour",
                "concern_level": 1,
                "status": "normal",
                "context": "Within expected range",
            }
        }

        result = sensor.extra_attrs_fn(coord, data)

        assert result["time_since_activity"] == 7200
        assert result["typical_interval"] == 3600
        assert result["concern_level"] == 1

    def test_entity_status_summary_sensor(self) -> None:
        """Test entity_status_summary sensor."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "entity_status_summary")
        data = {
            "welfare": {
                "entity_count_by_status": {
                    "normal": 5,
                    "attention": 1,
                    "concern": 1,
                    "alert": 0,
                }
            }
        }

        result = sensor.value_fn(data)

        assert result == "5 OK, 2 Need Attention"

    def test_entity_status_summary_extra_attrs(self) -> None:
        """Test entity_status_summary sensor extra attributes."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "entity_status_summary")
        coord = MagicMock()
        entity_status = [
            {"entity": "sensor.test1", "status": "normal"},
            {"entity": "sensor.test2", "status": "attention"},
        ]
        data = {"entity_status": entity_status}

        result = sensor.extra_attrs_fn(coord, data)

        assert result["entity_status"] == entity_status

    def test_statistical_training_remaining_sensor(self) -> None:
        """Test statistical_training_remaining sensor."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "statistical_training_remaining")
        data = {"stat_training": {"formatted": "3 days remaining"}}

        result = sensor.value_fn(data)

        assert result == "3 days remaining"

    def test_statistical_training_remaining_extra_attrs(self) -> None:
        """Test statistical_training_remaining sensor extra attributes."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "statistical_training_remaining")
        coord = MagicMock()
        data = {
            "stat_training": {
                "formatted": "3 days remaining",
                "complete": False,
                "days_remaining": 3,
                "days_elapsed": 4,
                "total_days": 7,
                "first_observation": "2024-01-12T10:00:00",
            }
        }

        result = sensor.extra_attrs_fn(coord, data)

        assert result["complete"] is False
        assert result["days_remaining"] == 3
        assert result["days_elapsed"] == 4

    def test_ml_training_remaining_sensor(self) -> None:
        """Test ml_training_remaining sensor returns stub value 'N/A' (deprecated in v1.1)."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_training_remaining")
        data = {"ml_training": {"formatted": "10 days remaining"}}

        result = sensor.value_fn(data)

        assert result == "N/A"

    def test_ml_training_remaining_extra_attrs(self) -> None:
        """Test ml_training_remaining sensor extra attributes contain deprecated flag."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_training_remaining")
        coord = MagicMock()
        data = {
            "ml_training": {
                "formatted": "10 days remaining",
                "complete": False,
                "status": "learning",
                "days_remaining": 10,
                "days_elapsed": 4,
                "total_days": 14,
                "samples_remaining": 50,
                "samples_processed": 50,
                "samples_needed": 100,
                "first_event": "2024-01-11T10:00:00",
            }
        }

        result = sensor.extra_attrs_fn(coord, data)

        assert result["deprecated"] is True

    def test_last_notification_sensor_with_timestamp(self) -> None:
        """Test last_notification sensor with valid timestamp."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "last_notification")
        data = {
            "last_notification": {
                "timestamp": "2024-01-15T12:00:00",
                "type": "anomaly",
            }
        }

        result = sensor.value_fn(data)

        assert isinstance(result, datetime)
        assert result == datetime(2024, 1, 15, 12, 0, 0)

    def test_last_notification_sensor_without_timestamp(self) -> None:
        """Test last_notification sensor without timestamp."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "last_notification")
        data = {}

        result = sensor.value_fn(data)

        assert result is None

    def test_last_notification_extra_attrs(self) -> None:
        """Test last_notification sensor extra attributes."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "last_notification")
        coord = MagicMock()
        data = {
            "last_notification": {
                "timestamp": "2024-01-15T12:00:00",
                "type": "welfare",
            }
        }

        result = sensor.extra_attrs_fn(coord, data)

        assert result["type"] == "welfare"


class TestBehaviourMonitorSensor:
    """Tests for the BehaviourMonitorSensor class."""

    @pytest.fixture
    def mock_coordinator(self, mock_hass: MagicMock, mock_config_entry: MagicMock) -> MagicMock:
        """Create a mock coordinator."""
        coord = MagicMock(spec=BehaviourMonitorCoordinator)
        coord.data = {
            "last_activity": "2024-01-15T10:30:00",
            "activity_score": 75.5,
            "anomaly_detected": False,
        }
        coord.analyzer = MagicMock()
        coord.analyzer.is_learning_complete.return_value = False
        coord.ml_analyzer = MagicMock()
        coord.ml_analyzer.ml_available = True
        coord.monitored_entities = {"sensor.test1", "sensor.test2"}
        return coord

    def test_sensor_initialization(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test sensor initialization."""
        description = SENSOR_DESCRIPTIONS[0]
        sensor = BehaviourMonitorSensor(mock_coordinator, mock_config_entry, description)

        assert sensor.entity_description == description
        assert sensor.unique_id == f"{mock_config_entry.entry_id}_{description.key}"
        assert sensor.device_info is not None
        assert sensor.device_info["identifiers"] == {(DOMAIN, mock_config_entry.entry_id)}

    def test_sensor_native_value(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test sensor native_value property."""
        description = next(s for s in SENSOR_DESCRIPTIONS if s.key == "activity_score")
        sensor = BehaviourMonitorSensor(mock_coordinator, mock_config_entry, description)

        value = sensor.native_value

        assert value == 75.5

    def test_sensor_native_value_with_no_data(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test sensor native_value property when coordinator has no data."""
        mock_coordinator.data = None
        description = SENSOR_DESCRIPTIONS[0]
        sensor = BehaviourMonitorSensor(mock_coordinator, mock_config_entry, description)

        value = sensor.native_value

        assert value is None

    def test_sensor_extra_state_attributes(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test sensor extra_state_attributes property."""
        mock_coordinator.data = {
            "anomaly_detected": True,
            "anomalies": [{"entity": "sensor.test", "score": -3.5}],
        }
        description = next(s for s in SENSOR_DESCRIPTIONS if s.key == "anomaly_detected")
        sensor = BehaviourMonitorSensor(mock_coordinator, mock_config_entry, description)

        attrs = sensor.extra_state_attributes

        assert attrs is not None
        assert "anomaly_details" in attrs

    def test_sensor_extra_state_attributes_none_when_no_fn(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test extra_state_attributes returns None when no extra_attrs_fn."""
        description = next(s for s in SENSOR_DESCRIPTIONS if s.key == "activity_score")
        sensor = BehaviourMonitorSensor(mock_coordinator, mock_config_entry, description)

        attrs = sensor.extra_state_attributes

        assert attrs is None

    def test_sensor_extra_state_attributes_none_when_no_data(
        self, mock_coordinator: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test extra_state_attributes returns None when no coordinator data."""
        mock_coordinator.data = None
        description = next(s for s in SENSOR_DESCRIPTIONS if s.key == "anomaly_detected")
        sensor = BehaviourMonitorSensor(mock_coordinator, mock_config_entry, description)

        attrs = sensor.extra_state_attributes

        assert attrs is None


class TestAsyncSetupEntry:
    """Tests for the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_creates_all_sensors(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test setup creates all sensor entities."""
        # Setup coordinator in hass.data
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}

        # Mock async_add_entities
        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Verify all sensors were added
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == len(SENSOR_DESCRIPTIONS)

        # Verify all are BehaviourMonitorSensor instances
        for entity in entities:
            assert isinstance(entity, BehaviourMonitorSensor)

    @pytest.mark.asyncio
    async def test_async_setup_entry_uses_coordinator_from_hass_data(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test setup uses coordinator from hass.data."""
        mock_coordinator = MagicMock(spec=BehaviourMonitorCoordinator)
        mock_hass.data = {DOMAIN: {mock_config_entry.entry_id: mock_coordinator}}
        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        entities = async_add_entities.call_args[0][0]
        # Verify the coordinator is passed to all sensors
        assert all(entity.coordinator == mock_coordinator for entity in entities)


class TestDeprecatedSensorStubs:
    """Tests for stub value_fns on deprecated ML sensors."""

    def test_sensor_descriptions_has_14_entries(self) -> None:
        """SENSOR_DESCRIPTIONS tuple must have exactly 14 entries."""
        assert len(SENSOR_DESCRIPTIONS) == 14

    # --- ml_status stub ---

    def test_ml_status_stub_returns_removed_string_with_empty_data(self) -> None:
        """ml_status value_fn returns 'Removed in v1.1' when data is empty."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_status")
        result = sensor.value_fn({})
        assert result == "Removed in v1.1"

    def test_ml_status_stub_returns_removed_string_with_populated_data(self) -> None:
        """ml_status value_fn returns 'Removed in v1.1' regardless of data contents."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_status")
        data = {
            "ml_training": {"complete": True},
            "ml_status": {"enabled": True, "trained": True},
        }
        result = sensor.value_fn(data)
        assert result == "Removed in v1.1"

    def test_ml_status_stub_extra_attrs_has_deprecated_true(self) -> None:
        """ml_status extra_attrs_fn returns dict with deprecated=True."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_status")
        coord = MagicMock()
        result = sensor.extra_attrs_fn(coord, {})
        assert result.get("deprecated") is True

    # --- ml_training_remaining stub ---

    def test_ml_training_remaining_stub_returns_na_with_empty_data(self) -> None:
        """ml_training_remaining value_fn returns 'N/A' when data is empty."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_training_remaining")
        result = sensor.value_fn({})
        assert result == "N/A"

    def test_ml_training_remaining_stub_returns_na_with_populated_data(self) -> None:
        """ml_training_remaining value_fn returns 'N/A' regardless of data contents."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_training_remaining")
        data = {
            "ml_training": {
                "formatted": "10 days remaining",
                "complete": False,
                "days_remaining": 10,
            }
        }
        result = sensor.value_fn(data)
        assert result == "N/A"

    def test_ml_training_remaining_stub_extra_attrs_has_deprecated_true(self) -> None:
        """ml_training_remaining extra_attrs_fn returns dict with deprecated=True."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "ml_training_remaining")
        coord = MagicMock()
        result = sensor.extra_attrs_fn(coord, {})
        assert result.get("deprecated") is True

    # --- cross_sensor_patterns stub ---

    def test_cross_sensor_patterns_stub_returns_zero_with_empty_data(self) -> None:
        """cross_sensor_patterns value_fn returns 0 when data is empty."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "cross_sensor_patterns")
        result = sensor.value_fn({})
        assert result == 0

    def test_cross_sensor_patterns_stub_returns_zero_with_populated_data(self) -> None:
        """cross_sensor_patterns value_fn returns 0 regardless of data contents."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "cross_sensor_patterns")
        data = {
            "cross_sensor_patterns": [
                {"pattern": "A -> B", "strength": 0.8},
                {"pattern": "C -> D", "strength": 0.6},
            ]
        }
        result = sensor.value_fn(data)
        assert result == 0

    def test_cross_sensor_patterns_stub_extra_attrs_has_deprecated_true(self) -> None:
        """cross_sensor_patterns extra_attrs_fn returns dict with deprecated=True."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "cross_sensor_patterns")
        coord = MagicMock()
        result = sensor.extra_attrs_fn(coord, {})
        assert result.get("deprecated") is True

    # --- spot-check non-deprecated sensors still work ---

    def test_last_activity_non_deprecated_still_works(self) -> None:
        """Non-deprecated last_activity sensor still parses timestamps."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "last_activity")
        from datetime import datetime
        data = {"last_activity": "2024-06-01T08:00:00"}
        result = sensor.value_fn(data)
        assert isinstance(result, datetime)

    def test_daily_activity_count_non_deprecated_still_works(self) -> None:
        """Non-deprecated daily_activity_count sensor still returns count."""
        sensor = next(s for s in SENSOR_DESCRIPTIONS if s.key == "daily_activity_count")
        data = {"daily_count": 99}
        result = sensor.value_fn(data)
        assert result == 99
