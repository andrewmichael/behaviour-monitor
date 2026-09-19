"""Tests for entity roles: constants, area lookup, override parsing, inference."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from custom_components.behaviour_monitor.alert_result import AlertResult, AlertSeverity, AlertType
from custom_components.behaviour_monitor.const import (
    AREA_ROLE_KEYWORDS,
    CONF_DOOR_DEBOUNCE_SECONDS,
    CONF_DOOR_OPEN_EXTENDED_SECONDS,
    CONF_DOOR_OPEN_PROLONGED_SECONDS,
    CONF_EXCURSION_WINDOW_SECONDS,
    CONF_EXTERIOR_DOORS,
    CONF_REBOOTSTRAP_ROLES,
    CONF_RETRIGGER_COLLAPSE_SECONDS,
    CONF_ROLE_OVERRIDES,
    DEFAULT_DOOR_DEBOUNCE_SECONDS,
    DEFAULT_DOOR_OPEN_EXTENDED_SECONDS,
    DEFAULT_DOOR_OPEN_PROLONGED_SECONDS,
    DEFAULT_EXCURSION_WINDOW_SECONDS,
    DEFAULT_EXTERIOR_DOORS,
    DEFAULT_RETRIGGER_COLLAPSE_SECONDS,
    DEFAULT_ROLE_OVERRIDES,
    DOOR_OPEN_BRIEF,
    DOOR_OPEN_EXTENDED,
    DOOR_OPEN_PROLONGED,
    KIND_WEIGHT,
    ROLE_KINDS,
    WELFARE_ALERT,
    WELFARE_CHECK,
    WELFARE_CONCERN,
    EntityRole,
)
from custom_components.behaviour_monitor.entity_role import (
    derive_weighted_status,
    infer_roles,
    parse_role_overrides,
    role_for_area,
)


class TestRoleConstants:
    def test_role_values(self) -> None:
        assert {r.value for r in EntityRole} == {
            "motion.bathroom", "motion.bedroom", "motion.living", "motion.kitchen",
            "motion.transit", "motion.unassigned", "door.exterior", "door.interior",
            "appliance", "panic", "other",
        }

    @pytest.mark.parametrize(
        ("role", "kind"),
        [
            (EntityRole.MOTION_BATHROOM, "motion"),
            (EntityRole.MOTION_UNASSIGNED, "motion"),
            (EntityRole.DOOR_EXTERIOR, "door"),
            (EntityRole.DOOR_INTERIOR, "door"),
            (EntityRole.APPLIANCE, "appliance"),
            (EntityRole.PANIC, "panic"),
            (EntityRole.OTHER, "other"),
        ],
    )
    def test_kind(self, role: EntityRole, kind: str) -> None:
        assert role.kind == kind

    def test_from_string(self) -> None:
        assert EntityRole.from_string("door.exterior") is EntityRole.DOOR_EXTERIOR
        with pytest.raises(ValueError):
            EntityRole.from_string("door.side")

    def test_kinds_and_weights(self) -> None:
        assert ROLE_KINDS == frozenset({"motion", "door", "appliance", "panic", "other"})
        assert KIND_WEIGHT == {"motion": 1.0, "door": 0.8, "appliance": 0.5, "other": 1.0}

    def test_area_keywords_cover_every_room_role(self) -> None:
        roles = [role for role, _ in AREA_ROLE_KEYWORDS]
        assert roles == [
            EntityRole.MOTION_BATHROOM, EntityRole.MOTION_BEDROOM, EntityRole.MOTION_LIVING,
            EntityRole.MOTION_KITCHEN, EntityRole.MOTION_TRANSIT,
        ]
        for _, keywords in AREA_ROLE_KEYWORDS:
            assert keywords and all(k == k.lower() for k in keywords)

    def test_open_classes(self) -> None:
        assert (DOOR_OPEN_BRIEF, DOOR_OPEN_EXTENDED, DOOR_OPEN_PROLONGED) == ("brief", "extended", "prolonged")

    def test_config_keys_and_defaults(self) -> None:
        assert CONF_EXTERIOR_DOORS == "exterior_doors"
        assert CONF_ROLE_OVERRIDES == "role_overrides"
        assert CONF_DOOR_DEBOUNCE_SECONDS == "door_debounce_seconds"
        assert CONF_RETRIGGER_COLLAPSE_SECONDS == "retrigger_collapse_seconds"
        assert CONF_EXCURSION_WINDOW_SECONDS == "excursion_window_seconds"
        assert CONF_DOOR_OPEN_EXTENDED_SECONDS == "door_open_extended_seconds"
        assert CONF_DOOR_OPEN_PROLONGED_SECONDS == "door_open_prolonged_seconds"
        assert CONF_REBOOTSTRAP_ROLES == "rebootstrap_roles"
        assert DEFAULT_EXTERIOR_DOORS == []
        assert DEFAULT_ROLE_OVERRIDES == ""
        assert DEFAULT_DOOR_DEBOUNCE_SECONDS == 60
        assert DEFAULT_RETRIGGER_COLLAPSE_SECONDS == 5
        assert DEFAULT_EXCURSION_WINDOW_SECONDS == 60
        assert DEFAULT_DOOR_OPEN_EXTENDED_SECONDS == 15
        assert DEFAULT_DOOR_OPEN_PROLONGED_SECONDS == 120


class TestRoleForArea:
    @pytest.mark.parametrize(
        ("name", "role"),
        [
            ("Bathroom", EntityRole.MOTION_BATHROOM),
            ("Downstairs WC", EntityRole.MOTION_BATHROOM),
            ("Master Bedroom", EntityRole.MOTION_BEDROOM),
            ("Living Room", EntityRole.MOTION_LIVING),
            ("Kitchen", EntityRole.MOTION_KITCHEN),
            ("Upstairs Landing", EntityRole.MOTION_TRANSIT),
            ("Garage", EntityRole.MOTION_UNASSIGNED),
            ("", EntityRole.MOTION_UNASSIGNED),
            (None, EntityRole.MOTION_UNASSIGNED),
        ],
    )
    def test_lookup(self, name: str | None, role: EntityRole) -> None:
        assert role_for_area(name) is role

    def test_table_order_wins_on_double_match(self) -> None:
        # "bed" (bedroom) and "bathroom" both match; bathroom is earlier in the table
        assert role_for_area("Bedroom Bathroom") is EntityRole.MOTION_BATHROOM


class TestParseRoleOverrides:
    def test_parses_roles_kinds_comments_and_blanks(self) -> None:
        text = "\n".join([
            "# exterior doors are listed separately",
            "",
            "binary_sensor.pir_hall: motion.transit",
            "  Binary_Sensor.Study : motion  ",
            "switch.lamp: appliance",
        ])
        assert parse_role_overrides(text) == {
            "binary_sensor.pir_hall": "motion.transit",
            "binary_sensor.study": "motion",
            "switch.lamp": "appliance",
        }

    def test_empty(self) -> None:
        assert parse_role_overrides("") == {}
        assert parse_role_overrides("\n  \n") == {}

    @pytest.mark.parametrize(
        "line",
        [
            "binary_sensor.pir",                 # no colon
            "binary_sensor.pir: motion.garage",  # unknown role
            "binary_sensor.pir: contact",        # old category name is not a kind
            "pir: motion",                       # entity id needs a domain
            "binary_sensor.sos: panic",          # panic only via the panic list
            "binary_sensor.pir: ",               # empty value
        ],
    )
    def test_rejects_bad_lines(self, line: str) -> None:
        with pytest.raises(ValueError) as exc:
            parse_role_overrides("ok.entity: appliance\n" + line)
        assert "line 2" in str(exc.value)

    def test_rejects_duplicate_entity(self) -> None:
        with pytest.raises(ValueError) as exc:
            parse_role_overrides("a.b: motion\na.b: appliance")
        assert "line 2" in str(exc.value)


class TestInferRoles:
    def _infer(self, entity_ids, **kw):
        base = dict(panic=(), exterior_doors=(), overrides={}, device_classes={}, area_names={}, numeric_entities=())
        base.update(kw)
        return infer_roles(entity_ids, **base)

    def test_numeric_is_other_even_when_overridden(self) -> None:
        r = self._infer(["sensor.lux"], overrides={"sensor.lux": "motion.kitchen"}, numeric_entities={"sensor.lux"})
        assert r["sensor.lux"] is EntityRole.OTHER

    def test_panic_list_beats_override(self) -> None:
        r = self._infer(["binary_sensor.sos"], panic=["binary_sensor.sos"], overrides={"binary_sensor.sos": "appliance"})
        assert r["binary_sensor.sos"] is EntityRole.PANIC

    def test_full_role_override_beats_everything_below(self) -> None:
        r = self._infer(
            ["binary_sensor.x"],
            overrides={"binary_sensor.x": "motion.kitchen"},
            device_classes={"binary_sensor.x": "door"},
            area_names={"binary_sensor.x": "Bathroom"},
        )
        assert r["binary_sensor.x"] is EntityRole.MOTION_KITCHEN

    def test_exterior_list(self) -> None:
        r = self._infer(["binary_sensor.front"], exterior_doors=["binary_sensor.front"], device_classes={"binary_sensor.front": "door"})
        assert r["binary_sensor.front"] is EntityRole.DOOR_EXTERIOR

    def test_kind_override_lets_area_fill_room(self) -> None:
        r = self._infer(["sensor.presence"], overrides={"sensor.presence": "motion"}, area_names={"sensor.presence": "Kitchen"})
        assert r["sensor.presence"] is EntityRole.MOTION_KITCHEN

    def test_kind_override_door_is_interior(self) -> None:
        r = self._infer(["sensor.x"], overrides={"sensor.x": "door"})
        assert r["sensor.x"] is EntityRole.DOOR_INTERIOR

    @pytest.mark.parametrize(
        ("eid", "dc", "area", "role"),
        [
            ("binary_sensor.a", "motion", "Bathroom", EntityRole.MOTION_BATHROOM),
            ("binary_sensor.b", "occupancy", "Bedroom", EntityRole.MOTION_BEDROOM),
            ("binary_sensor.c", "presence", None, EntityRole.MOTION_UNASSIGNED),
            ("binary_sensor.d", "door", "Kitchen", EntityRole.DOOR_INTERIOR),
            ("binary_sensor.e", "window", None, EntityRole.DOOR_INTERIOR),
            ("binary_sensor.f", "garage_door", None, EntityRole.DOOR_INTERIOR),
            ("switch.g", "outlet", None, EntityRole.APPLIANCE),
            ("switch.h", None, None, EntityRole.APPLIANCE),
            ("light.i", None, "Kitchen", EntityRole.APPLIANCE),
            ("sensor.j", None, "Kitchen", EntityRole.OTHER),
            ("binary_sensor.k", "smoke", None, EntityRole.OTHER),
        ],
    )
    def test_device_class_and_domain(self, eid, dc, area, role) -> None:
        r = self._infer([eid], device_classes={eid: dc}, area_names={eid: area})
        assert r[eid] is role

    def test_every_entity_gets_a_role(self) -> None:
        r = self._infer(["a.b", "c.d"])
        assert set(r) == {"a.b", "c.d"}


def _alert(entity_id: str, severity: AlertSeverity, alert_type: AlertType = AlertType.INACTIVITY) -> AlertResult:
    return AlertResult(
        entity_id=entity_id, alert_type=alert_type, severity=severity, confidence=1.0,
        explanation="x", timestamp=datetime.now(timezone.utc).isoformat(), details={},
    )


class TestDeriveWeightedStatus:
    roles = {
        "binary_sensor.pir": EntityRole.MOTION_LIVING,
        "binary_sensor.door": EntityRole.DOOR_INTERIOR,
        "switch.kettle": EntityRole.APPLIANCE,
    }

    def test_motion_high_is_alert(self) -> None:
        assert derive_weighted_status([_alert("binary_sensor.pir", AlertSeverity.HIGH)], self.roles)[0] == WELFARE_ALERT

    def test_door_high_is_alert(self) -> None:
        assert derive_weighted_status([_alert("binary_sensor.door", AlertSeverity.HIGH)], self.roles)[0] == WELFARE_ALERT

    def test_appliance_high_is_concern(self) -> None:
        assert derive_weighted_status([_alert("switch.kettle", AlertSeverity.HIGH)], self.roles)[0] == WELFARE_CONCERN

    def test_unknown_entity_weighs_as_other(self) -> None:
        assert derive_weighted_status([_alert("sensor.x", AlertSeverity.MEDIUM)], self.roles)[0] == WELFARE_CONCERN

    def test_max_not_sum(self) -> None:
        alerts = [_alert("switch.kettle", AlertSeverity.HIGH), _alert("switch.kettle", AlertSeverity.HIGH)]
        assert derive_weighted_status(alerts, self.roles)[0] == WELFARE_CONCERN

    def test_panic_and_correlation_ignored(self) -> None:
        alerts = [
            _alert("binary_sensor.pir", AlertSeverity.HIGH, AlertType.PANIC),
            _alert("binary_sensor.pir", AlertSeverity.HIGH, AlertType.CORRELATION_BREAK),
        ]
        assert derive_weighted_status(alerts, self.roles)[0] == WELFARE_CHECK
