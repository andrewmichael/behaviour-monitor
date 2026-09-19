"""Entity roles: inference from areas, device classes and overrides; weighted welfare.

Pure Python stdlib only. Zero Home Assistant imports. The coordinator supplies
registry device classes, area names and numeric-ness so this module stays
testable in isolation.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping

from .alert_result import AlertResult, AlertType
from .const import (
    AREA_ROLE_KEYWORDS,
    CONTACT_DEVICE_CLASSES,
    KIND_WEIGHT,
    MOTION_DEVICE_CLASSES,
    PLUG_DEVICE_CLASSES,
    ROLE_KINDS,
    SEVERITY_POINTS,
    WELFARE_ALERT,
    WELFARE_ALERT_SCORE,
    WELFARE_CHECK,
    WELFARE_CONCERN,
    WELFARE_CONCERN_SCORE,
    EntityRole,
)

_DOMAIN_KIND: dict[str, str] = {"switch": "appliance", "light": "appliance"}
_OVERRIDE_VALUES: frozenset[str] = frozenset(
    {r.value for r in EntityRole if r is not EntityRole.PANIC}
    | (ROLE_KINDS - {"panic"})
)


# ---------------------------------------------------------------------------
# Area lookup
# ---------------------------------------------------------------------------


def role_for_area(area_name: str | None) -> EntityRole:
    """Map a Home Assistant area name to a motion room role, or MOTION_UNASSIGNED."""
    if not area_name:
        return EntityRole.MOTION_UNASSIGNED
    name = area_name.lower()
    for role, keywords in AREA_ROLE_KEYWORDS:
        if any(k in name for k in keywords):
            return role
    return EntityRole.MOTION_UNASSIGNED


# ---------------------------------------------------------------------------
# Override map
# ---------------------------------------------------------------------------


def parse_role_overrides(text: str) -> dict[str, str]:
    """Parse ``entity_id: role-or-kind`` lines. Blank lines and ``#`` comments are ignored.

    Raises ``ValueError`` naming the 1-based offending line. ``panic`` is not
    accepted (use the panic list); an entity may appear only once.
    """
    out: dict[str, str] = {}
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"line {n}: expected 'entity_id: role'")
        eid, value = (part.strip().lower() for part in line.split(":", 1))
        if "." not in eid or not eid.split(".", 1)[1]:
            raise ValueError(f"line {n}: {eid!r} is not an entity id")
        if value not in _OVERRIDE_VALUES:
            raise ValueError(f"line {n}: {value!r} is not a role or kind")
        if eid in out:
            raise ValueError(f"line {n}: {eid} appears more than once")
        out[eid] = value
    return out


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def _kind_for_device_class(device_class: str | None) -> str | None:
    if device_class is None:
        return None
    if device_class in MOTION_DEVICE_CLASSES:
        return "motion"
    if device_class in CONTACT_DEVICE_CLASSES:
        return "door"
    if device_class in PLUG_DEVICE_CLASSES:
        return "appliance"
    return None


def infer_roles(
    entity_ids: Iterable[str],
    panic: Iterable[str],
    exterior_doors: Iterable[str],
    overrides: Mapping[str, str],
    device_classes: Mapping[str, str | None],
    area_names: Mapping[str, str | None],
    numeric_entities: Collection[str] = (),
) -> dict[str, EntityRole]:
    """Return a role for every entity id (spec §1.2 precedence)."""
    panic_set = set(panic)
    exterior = set(exterior_doors)
    result: dict[str, EntityRole] = {}
    for eid in entity_ids:
        if eid in numeric_entities:
            result[eid] = EntityRole.OTHER
            continue
        if eid in panic_set:
            result[eid] = EntityRole.PANIC
            continue
        override = overrides.get(eid)
        if override is not None and override not in ROLE_KINDS:
            result[eid] = EntityRole.from_string(override)
            continue
        if eid in exterior:
            result[eid] = EntityRole.DOOR_EXTERIOR
            continue
        kind = override
        if kind is None:
            kind = _kind_for_device_class(device_classes.get(eid))
        if kind is None:
            kind = _DOMAIN_KIND.get(eid.split(".", 1)[0])
        if kind == "motion":
            result[eid] = role_for_area(area_names.get(eid))
        elif kind == "door":
            result[eid] = EntityRole.DOOR_INTERIOR
        elif kind == "appliance":
            result[eid] = EntityRole.APPLIANCE
        else:
            result[eid] = EntityRole.OTHER
    return result


# ---------------------------------------------------------------------------
# Weighted welfare
# ---------------------------------------------------------------------------

_RECOMMENDATION = {
    WELFARE_ALERT: "Immediate welfare check recommended.",
    WELFARE_CONCERN: "Schedule a welfare check soon.",
    WELFARE_CHECK: "Monitor closely.",
}


def _alert_score(alert: AlertResult, roles: Mapping[str, EntityRole]) -> float:
    """Severity points times the kind weight of the alert's entity."""
    kind = roles.get(alert.entity_id, EntityRole.OTHER).kind
    return SEVERITY_POINTS[alert.severity] * KIND_WEIGHT.get(kind, 1.0)


def derive_weighted_status(
    alerts: Iterable[AlertResult],
    roles: Mapping[str, EntityRole],
) -> tuple[str, str]:
    """Return (welfare status, recommendation) from the highest-scoring alert.

    Correlation-break and panic alerts are ignored; panic is handled by the
    coordinator ahead of weighted scoring. The maximum score is used, not the
    sum, so several weak alerts from automated devices cannot compound.
    With no scoring alerts this returns the check_recommended tier.
    """
    top = 0.0
    for alert in alerts:
        if alert.alert_type in (AlertType.CORRELATION_BREAK, AlertType.PANIC):
            continue
        top = max(top, _alert_score(alert, roles))
    if top >= WELFARE_ALERT_SCORE:
        status = WELFARE_ALERT
    elif top >= WELFARE_CONCERN_SCORE:
        status = WELFARE_CONCERN
    else:
        status = WELFARE_CHECK
    return status, _RECOMMENDATION[status]
