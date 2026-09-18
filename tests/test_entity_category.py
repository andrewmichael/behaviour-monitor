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
from custom_components.behaviour_monitor.alert_result import (
    AlertResult,
    AlertSeverity,
    AlertType,
)
from custom_components.behaviour_monitor.entity_category import (
    MotionDebouncer,
    derive_weighted_status,
    infer_categories,
)


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
        return infer_categories([entity_id], overrides, device_classes, numeric)[
            entity_id
        ]

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


T0 = datetime(2026, 9, 18, 10, 0, 0)


class TestMotionDebouncer:
    def test_rising_edge_counts(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0) is True

    def test_off_transition_never_counts(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "on", "off", T0) is False
        # even when nothing has been counted yet
        assert d.should_count("binary_sensor.pir", True, None, "off", T0) is False

    def test_on_to_on_is_not_a_rising_edge(self) -> None:
        d = MotionDebouncer(0)
        assert d.should_count("binary_sensor.pir", True, "on", "on", T0) is False

    def test_second_edge_inside_window_dropped(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0) is True
        assert (
            d.should_count(
                "binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=119)
            )
            is False
        )

    def test_edge_at_exactly_window_counts(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0) is True
        assert (
            d.should_count(
                "binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=120)
            )
            is True
        )

    def test_dropped_edge_does_not_extend_window(self) -> None:
        d = MotionDebouncer(120)
        d.should_count("binary_sensor.pir", True, "off", "on", T0)
        d.should_count(
            "binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=100)
        )  # dropped
        # 120s after the *counted* edge, not the dropped one
        assert (
            d.should_count(
                "binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=120)
            )
            is True
        )

    def test_zero_window_counts_every_rising_edge(self) -> None:
        d = MotionDebouncer(0)
        assert d.should_count("binary_sensor.pir", True, "off", "on", T0) is True
        assert (
            d.should_count(
                "binary_sensor.pir", True, "off", "on", T0 + timedelta(seconds=1)
            )
            is True
        )

    def test_none_old_state_counts_as_rising_edge(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, None, "on", T0) is True

    def test_non_motion_always_counts(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.door", False, "on", "off", T0) is True
        assert d.should_count("binary_sensor.door", False, "off", "off", T0) is True
        assert (
            d.should_count(
                "binary_sensor.door", False, "off", "on", T0 + timedelta(seconds=1)
            )
            is True
        )

    def test_entities_are_independent(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.a", True, "off", "on", T0) is True
        assert (
            d.should_count(
                "binary_sensor.b", True, "off", "on", T0 + timedelta(seconds=1)
            )
            is True
        )

    def test_state_is_case_insensitive(self) -> None:
        d = MotionDebouncer(120)
        assert d.should_count("binary_sensor.pir", True, "OFF", "On", T0) is True


def _alert(
    entity_id: str,
    severity: AlertSeverity,
    alert_type: AlertType = AlertType.INACTIVITY,
) -> AlertResult:
    return AlertResult(
        entity_id=entity_id,
        alert_type=alert_type,
        severity=severity,
        confidence=0.9,
        explanation=f"{entity_id} test",
        timestamp=T0.isoformat(),
    )


class TestDeriveWeightedStatus:
    @pytest.mark.parametrize(
        ("category", "severity", "expected"),
        [
            (EntityCategory.MOTION, AlertSeverity.HIGH, "alert"),
            (EntityCategory.MOTION, AlertSeverity.MEDIUM, "concern"),
            (EntityCategory.MOTION, AlertSeverity.LOW, "check_recommended"),
            (EntityCategory.OTHER, AlertSeverity.HIGH, "alert"),
            (EntityCategory.OTHER, AlertSeverity.MEDIUM, "concern"),
            (EntityCategory.OTHER, AlertSeverity.LOW, "check_recommended"),
            (EntityCategory.CONTACT, AlertSeverity.HIGH, "alert"),
            (EntityCategory.CONTACT, AlertSeverity.MEDIUM, "concern"),
            (EntityCategory.CONTACT, AlertSeverity.LOW, "check_recommended"),
            (EntityCategory.PLUG, AlertSeverity.HIGH, "concern"),
            (EntityCategory.PLUG, AlertSeverity.MEDIUM, "check_recommended"),
            (EntityCategory.PLUG, AlertSeverity.LOW, "check_recommended"),
            (EntityCategory.LIGHT, AlertSeverity.HIGH, "concern"),
            (EntityCategory.LIGHT, AlertSeverity.MEDIUM, "check_recommended"),
            (EntityCategory.LIGHT, AlertSeverity.LOW, "check_recommended"),
        ],
    )
    def test_single_alert_matrix(
        self, category: EntityCategory, severity: AlertSeverity, expected: str
    ) -> None:
        status, _ = derive_weighted_status([_alert("x.y", severity)], {"x.y": category})
        assert status == expected

    def test_max_not_sum(self) -> None:
        alerts = [_alert(f"switch.p{i}", AlertSeverity.HIGH) for i in range(5)]
        cats = {a.entity_id: EntityCategory.PLUG for a in alerts}
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "concern"

    def test_strongest_alert_wins(self) -> None:
        alerts = [
            _alert("switch.p", AlertSeverity.HIGH),
            _alert("binary_sensor.m", AlertSeverity.MEDIUM),
        ]
        cats = {
            "switch.p": EntityCategory.PLUG,
            "binary_sensor.m": EntityCategory.MOTION,
        }
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "concern"
        alerts.append(_alert("binary_sensor.m2", AlertSeverity.HIGH))
        cats["binary_sensor.m2"] = EntityCategory.MOTION
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "alert"

    def test_unknown_entity_defaults_to_other_weight(self) -> None:
        status, _ = derive_weighted_status(
            [_alert("sensor.unknown", AlertSeverity.HIGH)], {}
        )
        assert status == "alert"

    def test_correlation_breaks_ignored(self) -> None:
        alerts = [
            _alert("binary_sensor.m", AlertSeverity.HIGH, AlertType.CORRELATION_BREAK),
            _alert("switch.p", AlertSeverity.LOW),
        ]
        cats = {
            "binary_sensor.m": EntityCategory.MOTION,
            "switch.p": EntityCategory.PLUG,
        }
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "check_recommended"

    def test_recommendations(self) -> None:
        _, rec = derive_weighted_status([_alert("x.y", AlertSeverity.HIGH)], {})
        assert rec == "Immediate welfare check recommended."
        _, rec = derive_weighted_status([_alert("x.y", AlertSeverity.MEDIUM)], {})
        assert rec == "Schedule a welfare check soon."
        _, rec = derive_weighted_status([_alert("x.y", AlertSeverity.LOW)], {})
        assert rec == "Monitor closely."


class TestPanicCategory:
    def test_constants(self) -> None:
        from custom_components.behaviour_monitor.const import (
            CONF_CATEGORY_PANIC,
            CONF_PANIC_RENOTIFY_MINUTES,
            DEFAULT_CATEGORY_PANIC,
            DEFAULT_PANIC_RENOTIFY_MINUTES,
            SERVICE_ACKNOWLEDGE_PANIC,
            WELFARE_PANIC_RECOMMENDATION,
        )

        assert EntityCategory.PANIC.value == "panic"
        assert AlertType.PANIC.value == "panic"
        assert CONF_CATEGORY_PANIC == "category_panic"
        assert DEFAULT_CATEGORY_PANIC == []
        assert CONF_PANIC_RENOTIFY_MINUTES == "panic_renotify_minutes"
        assert DEFAULT_PANIC_RENOTIFY_MINUTES == 5
        assert SERVICE_ACKNOWLEDGE_PANIC == "acknowledge_panic"
        assert WELFARE_PANIC_RECOMMENDATION == "Panic button pressed. Respond now."

    def test_panic_only_from_override_list(self) -> None:
        eid = "binary_sensor.sos"
        assert infer_categories([eid], {EntityCategory.PANIC: [eid]}, {})[eid] is EntityCategory.PANIC

    @pytest.mark.parametrize("dc", ["safety", "problem", "motion", None])
    def test_panic_never_inferred_from_device_class(self, dc: str | None) -> None:
        eid = "binary_sensor.sos"
        assert infer_categories([eid], {}, {eid: dc})[eid] is not EntityCategory.PANIC

    def test_weighted_status_skips_panic_alerts(self) -> None:
        alerts = [_alert("binary_sensor.sos", AlertSeverity.HIGH, AlertType.PANIC), _alert("switch.p", AlertSeverity.LOW)]
        cats = {"binary_sensor.sos": EntityCategory.PANIC, "switch.p": EntityCategory.PLUG}
        status, _ = derive_weighted_status(alerts, cats)
        assert status == "check_recommended"

    def test_unknown_category_weight_defaults_to_one(self) -> None:
        # a non-panic alert on a PANIC-category entity must not KeyError
        alerts = [_alert("binary_sensor.sos", AlertSeverity.HIGH)]
        status, _ = derive_weighted_status(alerts, {"binary_sensor.sos": EntityCategory.PANIC})
        assert status == "alert"
