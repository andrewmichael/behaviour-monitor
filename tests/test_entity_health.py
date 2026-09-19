"""Tests for entity_health: health classification and welfare qualification."""

from __future__ import annotations

import pytest

from custom_components.behaviour_monitor.alert_result import AlertType
from custom_components.behaviour_monitor.const import (
    CONF_BURST_DISCARD_THRESHOLD,
    CONF_PANIC_HEARTBEAT_HOURS,
    CONF_PANIC_TEST_REMINDER_DAYS,
    CONF_STARTUP_GRACE_SECONDS,
    DEFAULT_BURST_DISCARD_THRESHOLD,
    DEFAULT_PANIC_HEARTBEAT_HOURS,
    DEFAULT_PANIC_TEST_REMINDER_DAYS,
    DEFAULT_STARTUP_GRACE_SECONDS,
    HEALTH_MISSING,
    HEALTH_PRESENT,
    HEALTH_UNAVAILABLE,
    PANIC_LOW_BATTERY_PERCENT,
    PANIC_TEST_WINDOW_SECONDS,
    SERVICE_PANIC_TEST,
    WELFARE_BLIND,
    WELFARE_BLIND_RECOMMENDATION,
    WELFARE_DEGRADED,
    WELFARE_DEGRADED_RECOMMENDATION,
)
from custom_components.behaviour_monitor.entity_health import (
    count_by_status,
    qualify_welfare,
    resolve_entity_health,
)


class TestConstants:
    def test_values(self) -> None:
        assert CONF_STARTUP_GRACE_SECONDS == "startup_grace_seconds"
        assert DEFAULT_STARTUP_GRACE_SECONDS == 90
        assert CONF_BURST_DISCARD_THRESHOLD == "burst_discard_threshold"
        assert DEFAULT_BURST_DISCARD_THRESHOLD == 3
        assert CONF_PANIC_HEARTBEAT_HOURS == "panic_heartbeat_hours"
        assert DEFAULT_PANIC_HEARTBEAT_HOURS == 24
        assert CONF_PANIC_TEST_REMINDER_DAYS == "panic_test_reminder_days"
        assert DEFAULT_PANIC_TEST_REMINDER_DAYS == 30
        assert SERVICE_PANIC_TEST == "panic_test"
        assert PANIC_TEST_WINDOW_SECONDS == 120
        assert PANIC_LOW_BATTERY_PERCENT == 20
        assert (HEALTH_PRESENT, HEALTH_UNAVAILABLE, HEALTH_MISSING) == (
            "present",
            "unavailable",
            "missing",
        )
        assert (WELFARE_BLIND, WELFARE_DEGRADED) == ("blind", "degraded")
        assert AlertType.DEVICE_HEALTH.value == "device_health"


class TestResolveEntityHealth:
    def test_present(self) -> None:
        assert (
            resolve_entity_health(["a.b"], {"a.b": "on"}, set())["a.b"]
            == HEALTH_PRESENT
        )

    def test_present_with_empty_state_string(self) -> None:
        # coordinator passes "" for "exists, non-string state" (test doubles)
        assert (
            resolve_entity_health(["a.b"], {"a.b": ""}, set())["a.b"] == HEALTH_PRESENT
        )

    @pytest.mark.parametrize("sv", ["unavailable", "unknown"])
    def test_unavailable_state(self, sv: str) -> None:
        assert (
            resolve_entity_health(["a.b"], {"a.b": sv}, set())["a.b"]
            == HEALTH_UNAVAILABLE
        )

    def test_no_state_but_in_registry_is_unavailable(self) -> None:
        assert (
            resolve_entity_health(["a.b"], {"a.b": None}, {"a.b"})["a.b"]
            == HEALTH_UNAVAILABLE
        )

    def test_no_state_not_in_registry_is_missing(self) -> None:
        assert (
            resolve_entity_health(["a.b"], {"a.b": None}, set())["a.b"]
            == HEALTH_MISSING
        )

    def test_absent_from_states_mapping_is_missing(self) -> None:
        assert resolve_entity_health(["a.b"], {}, set())["a.b"] == HEALTH_MISSING

    def test_returns_entry_for_every_entity(self) -> None:
        out = resolve_entity_health(["a.b", "c.d"], {"a.b": "on"}, set())
        assert out == {"a.b": HEALTH_PRESENT, "c.d": HEALTH_MISSING}


class TestCountByStatus:
    def test_counts(self) -> None:
        health = {
            "a": "present",
            "b": "present",
            "c": "unavailable",
            "d": "missing",
            "p": "present",
        }
        # p is a panic entity: present but not contributing
        counts = count_by_status(
            ["a", "b", "c", "d", "p"], health, contributing=["a", "b"], alerting=["b"]
        )
        assert counts == {"ok": 1, "attention": 1, "unavailable": 1, "missing": 1}

    def test_empty(self) -> None:
        assert count_by_status([], {}, [], []) == {
            "ok": 0,
            "attention": 0,
            "unavailable": 0,
            "missing": 0,
        }


def _welfare(status: str) -> dict:
    return {
        "status": status,
        "reasons": ["r"],
        "summary": "s",
        "recommendation": "rec",
        "alert_count_by_entity": {},
    }


class TestQualifyWelfare:
    def test_ok_all_reporting_gets_suffix_and_counts(self) -> None:
        w = qualify_welfare(
            _welfare("ok"),
            contributing=["a", "b"],
            expected=["a", "b"],
            missing=[],
            unavailable=[],
            panic_active=False,
            device_alerts=False,
        )
        assert w["status"] == "ok"
        assert w["summary"].endswith("(2 of 2 reporting)")
        assert w["contributing_entities"] == 2 and w["expected_entities"] == 2
        assert w["missing_entities"] == [] and w["unavailable_entities"] == []

    def test_blind_when_nothing_contributes(self) -> None:
        w = qualify_welfare(
            _welfare("ok"),
            contributing=[],
            expected=["a", "b"],
            missing=["a"],
            unavailable=["b"],
            panic_active=False,
            device_alerts=False,
        )
        assert w["status"] == WELFARE_BLIND
        assert w["recommendation"] == WELFARE_BLIND_RECOMMENDATION
        assert w["summary"] == "blind: 0 of 2 entities reporting"
        assert w["reasons"] == ["r"]  # kept

    def test_blind_outranks_ordinary_alert(self) -> None:
        w = qualify_welfare(
            _welfare("alert"),
            contributing=[],
            expected=["a"],
            missing=["a"],
            unavailable=[],
            panic_active=False,
            device_alerts=False,
        )
        assert w["status"] == WELFARE_BLIND

    def test_panic_outranks_blind(self) -> None:
        w = qualify_welfare(
            _welfare("alert"),
            contributing=[],
            expected=["a"],
            missing=["a"],
            unavailable=[],
            panic_active=True,
            device_alerts=False,
        )
        assert w["status"] == "alert"
        assert w["recommendation"] == "rec"

    def test_degraded_on_partial_loss_when_ok(self) -> None:
        w = qualify_welfare(
            _welfare("ok"),
            contributing=["a"],
            expected=["a", "b"],
            missing=["b"],
            unavailable=[],
            panic_active=False,
            device_alerts=False,
        )
        assert w["status"] == WELFARE_DEGRADED
        assert w["recommendation"] == WELFARE_DEGRADED_RECOMMENDATION
        assert w["summary"] == "degraded: 1 of 2 entities reporting"

    def test_ordinary_alert_outranks_degraded(self) -> None:
        w = qualify_welfare(
            _welfare("concern"),
            contributing=["a"],
            expected=["a", "b"],
            missing=["b"],
            unavailable=[],
            panic_active=False,
            device_alerts=False,
        )
        assert w["status"] == "concern"
        assert w["summary"].endswith("(1 of 2 reporting)")

    def test_device_alert_degrades_ok(self) -> None:
        w = qualify_welfare(
            _welfare("ok"),
            contributing=["a"],
            expected=["a"],
            missing=[],
            unavailable=[],
            panic_active=False,
            device_alerts=True,
        )
        assert w["status"] == WELFARE_DEGRADED

    def test_no_expected_entities_stays_ok(self) -> None:
        w = qualify_welfare(
            _welfare("ok"),
            contributing=[],
            expected=[],
            missing=[],
            unavailable=[],
            panic_active=False,
            device_alerts=False,
        )
        assert w["status"] == "ok"
        assert w["summary"].endswith("(0 of 0 reporting)")

    def test_input_dict_not_mutated(self) -> None:
        src = _welfare("ok")
        qualify_welfare(
            src,
            contributing=[],
            expected=["a"],
            missing=["a"],
            unavailable=[],
            panic_active=False,
            device_alerts=False,
        )
        assert src["status"] == "ok"
