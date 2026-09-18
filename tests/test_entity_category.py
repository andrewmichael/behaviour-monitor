"""Tests for entity_category: inference, motion debounce, weighted welfare."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.behaviour_monitor.const import (
    CATEGORY_WEIGHT,
    CONF_CATEGORY_CONTACT,
    CONF_CATEGORY_LIGHT,
    CONF_CATEGORY_MOTION,
    CONF_CATEGORY_PLUG,
    CONF_MOTION_DEBOUNCE_SECONDS,
    CONF_REBOOTSTRAP_MOTION,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
    SEVERITY_POINTS,
    WELFARE_ALERT_SCORE,
    WELFARE_CONCERN_SCORE,
    EntityCategory,
)
from custom_components.behaviour_monitor.alert_result import AlertSeverity


class TestConstants:
    def test_enum_values(self) -> None:
        assert EntityCategory.MOTION.value == "motion"
        assert EntityCategory.CONTACT.value == "contact"
        assert EntityCategory.PLUG.value == "plug"
        assert EntityCategory.LIGHT.value == "light"
        assert EntityCategory.OTHER.value == "other"

    def test_config_keys(self) -> None:
        assert CONF_CATEGORY_MOTION == "category_motion"
        assert CONF_CATEGORY_CONTACT == "category_contact"
        assert CONF_CATEGORY_PLUG == "category_plug"
        assert CONF_CATEGORY_LIGHT == "category_light"
        assert CONF_MOTION_DEBOUNCE_SECONDS == "motion_debounce_seconds"
        assert CONF_REBOOTSTRAP_MOTION == "rebootstrap_motion"
        assert DEFAULT_MOTION_DEBOUNCE_SECONDS == 120

    def test_weights_and_thresholds(self) -> None:
        assert CATEGORY_WEIGHT[EntityCategory.MOTION] == 1.0
        assert CATEGORY_WEIGHT[EntityCategory.CONTACT] == 0.8
        assert CATEGORY_WEIGHT[EntityCategory.OTHER] == 1.0
        assert CATEGORY_WEIGHT[EntityCategory.PLUG] == 0.5
        assert CATEGORY_WEIGHT[EntityCategory.LIGHT] == 0.5
        assert SEVERITY_POINTS[AlertSeverity.LOW] == 1
        assert SEVERITY_POINTS[AlertSeverity.MEDIUM] == 2
        assert SEVERITY_POINTS[AlertSeverity.HIGH] == 3
        assert WELFARE_ALERT_SCORE == 2.25
        assert WELFARE_CONCERN_SCORE == 1.25
