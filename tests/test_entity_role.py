"""Tests for entity roles: constants, area lookup, override parsing, inference."""

from __future__ import annotations

import pytest

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
    EntityRole,
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
