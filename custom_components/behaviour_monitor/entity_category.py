"""Entity categorisation, motion debounce and weighted welfare scoring.

Pure Python stdlib only. Zero Home Assistant imports. The coordinator supplies
registry device classes and numeric-ness so this module stays testable in
isolation.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from datetime import datetime, timedelta

from .alert_result import AlertResult, AlertType
from .const import (
    CATEGORY_WEIGHT,
    CONTACT_DEVICE_CLASSES,
    MOTION_DEVICE_CLASSES,
    PLUG_DEVICE_CLASSES,
    SEVERITY_POINTS,
    WELFARE_ALERT,
    WELFARE_ALERT_SCORE,
    WELFARE_CHECK,
    WELFARE_CONCERN,
    WELFARE_CONCERN_SCORE,
    EntityCategory,
)

# ---------------------------------------------------------------------------
# Category inference
# ---------------------------------------------------------------------------

_DOMAIN_FALLBACK: dict[str, EntityCategory] = {
    "switch": EntityCategory.PLUG,
    "light": EntityCategory.LIGHT,
}


def _category_for_device_class(device_class: str | None) -> EntityCategory | None:
    if device_class is None:
        return None
    if device_class in MOTION_DEVICE_CLASSES:
        return EntityCategory.MOTION
    if device_class in CONTACT_DEVICE_CLASSES:
        return EntityCategory.CONTACT
    if device_class in PLUG_DEVICE_CLASSES:
        return EntityCategory.PLUG
    return None


def infer_categories(
    entity_ids: Iterable[str],
    overrides: Mapping[EntityCategory, Iterable[str]],
    device_classes: Mapping[str, str | None],
    numeric_entities: Collection[str] = (),
) -> dict[str, EntityCategory]:
    """Return a category for every entity id.

    Precedence: numeric entities are always OTHER; then override lists; then
    the entity-registry device class; then a domain fallback (switch -> PLUG,
    light -> LIGHT); otherwise OTHER.
    """
    override_lookup: dict[str, EntityCategory] = {}
    for category, ids in overrides.items():
        for eid in ids:
            override_lookup[eid] = category

    result: dict[str, EntityCategory] = {}
    for eid in entity_ids:
        if eid in numeric_entities:
            result[eid] = EntityCategory.OTHER
            continue
        if eid in override_lookup:
            result[eid] = override_lookup[eid]
            continue
        from_dc = _category_for_device_class(device_classes.get(eid))
        if from_dc is not None:
            result[eid] = from_dc
            continue
        domain = eid.split(".", 1)[0]
        result[eid] = _DOMAIN_FALLBACK.get(domain, EntityCategory.OTHER)
    return result
