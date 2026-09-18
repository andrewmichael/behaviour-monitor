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
from custom_components.behaviour_monitor.entity_category import infer_categories


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


class TestInferCategories:
    def _infer(self, entity_id: str, **kw) -> EntityCategory:
        overrides = kw.pop("overrides", {})
        device_classes = kw.pop("device_classes", {})
        numeric = kw.pop("numeric", ())
        return infer_categories([entity_id], overrides, device_classes, numeric)[entity_id]

    @pytest.mark.parametrize("dc", ["motion", "occupancy", "presence"])
    def test_motion_device_classes(self, dc: str) -> None:
        eid = "binary_sensor.hall"
        assert self._infer(eid, device_classes={eid: dc}) is EntityCategory.MOTION

    @pytest.mark.parametrize("dc", ["door", "window", "opening", "garage_door"])
    def test_contact_device_classes(self, dc: str) -> None:
        eid = "binary_sensor.front"
        assert self._infer(eid, device_classes={eid: dc}) is EntityCategory.CONTACT

    @pytest.mark.parametrize("dc", ["outlet", "plug"])
    def test_plug_device_classes(self, dc: str) -> None:
        eid = "switch.kettle"
        assert self._infer(eid, device_classes={eid: dc}) is EntityCategory.PLUG

    def test_switch_domain_fallback(self) -> None:
        eid = "switch.lamp_socket"
        assert self._infer(eid, device_classes={eid: None}) is EntityCategory.PLUG

    def test_light_domain_fallback(self) -> None:
        eid = "light.kitchen"
        assert self._infer(eid, device_classes={eid: None}) is EntityCategory.LIGHT

    def test_unknown_device_class_and_domain_is_other(self) -> None:
        eid = "binary_sensor.smoke"
        assert self._infer(eid, device_classes={eid: "smoke"}) is EntityCategory.OTHER

    def test_missing_from_registry_uses_domain(self) -> None:
        # entity not present in device_classes mapping at all
        assert self._infer("switch.yaml_defined") is EntityCategory.PLUG
        assert self._infer("sensor.yaml_defined") is EntityCategory.OTHER

    def test_override_beats_device_class(self) -> None:
        eid = "binary_sensor.hall"
        cat = self._infer(
            eid,
            overrides={EntityCategory.CONTACT: [eid]},
            device_classes={eid: "motion"},
        )
        assert cat is EntityCategory.CONTACT

    def test_light_override(self) -> None:
        eid = "switch.strip"
        cat = self._infer(eid, overrides={EntityCategory.LIGHT: [eid]})
        assert cat is EntityCategory.LIGHT

    def test_numeric_entity_forced_to_other(self) -> None:
        eid = "sensor.lux"
        cat = self._infer(
            eid,
            overrides={EntityCategory.MOTION: [eid]},
            device_classes={eid: "motion"},
            numeric=[eid],
        )
        assert cat is EntityCategory.OTHER

    def test_returns_entry_for_every_entity(self) -> None:
        result = infer_categories(
            ["binary_sensor.a", "light.b", "sensor.c"],
            {},
            {"binary_sensor.a": "motion"},
        )
        assert result == {
            "binary_sensor.a": EntityCategory.MOTION,
            "light.b": EntityCategory.LIGHT,
            "sensor.c": EntityCategory.OTHER,
        }
