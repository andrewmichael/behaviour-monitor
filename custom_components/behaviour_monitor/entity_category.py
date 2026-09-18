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


# ---------------------------------------------------------------------------
# Motion debounce
# ---------------------------------------------------------------------------


class MotionDebouncer:
    """Decide whether a motion-sensor event should count as activity.

    For motion entities only rising edges (not-on -> on) count, and only when
    at least ``window_seconds`` have elapsed since the last counted edge for
    that entity. Non-motion entities always count. State is in-memory only;
    after a restart the first rising edge always counts.
    """

    def __init__(self, window_seconds: int) -> None:
        self._window = timedelta(seconds=max(0, int(window_seconds)))
        self._last_counted: dict[str, datetime] = {}

    def should_count(
        self,
        entity_id: str,
        is_motion: bool,
        old_state: str | None,
        new_state: str,
        timestamp: datetime,
    ) -> bool:
        """Return True if this event should be recorded as activity."""
        if not is_motion:
            return True
        if new_state.lower() != "on":
            return False
        if old_state is not None and old_state.lower() == "on":
            return False
        last = self._last_counted.get(entity_id)
        if last is not None and timestamp - last < self._window:
            return False
        self._last_counted[entity_id] = timestamp
        return True


# ---------------------------------------------------------------------------
# Weighted welfare
# ---------------------------------------------------------------------------

_RECOMMENDATION = {
    WELFARE_ALERT: "Immediate welfare check recommended.",
    WELFARE_CONCERN: "Schedule a welfare check soon.",
    WELFARE_CHECK: "Monitor closely.",
}


def alert_score(alert: AlertResult, categories: Mapping[str, EntityCategory]) -> float:
    """Severity points times the category weight of the alert's entity."""
    category = categories.get(alert.entity_id, EntityCategory.OTHER)
    return SEVERITY_POINTS[alert.severity] * CATEGORY_WEIGHT[category]


def derive_weighted_status(
    alerts: Iterable[AlertResult],
    categories: Mapping[str, EntityCategory],
) -> tuple[str, str]:
    """Return (welfare status, recommendation) from the highest-scoring alert.

    Correlation-break alerts are ignored. The maximum score is used, not the
    sum, so several weak alerts from automated devices cannot compound.
    Callers must handle the no-alert case themselves; with no scoring alerts
    this returns the check_recommended tier.
    """
    top = 0.0
    for alert in alerts:
        if alert.alert_type == AlertType.CORRELATION_BREAK:
            continue
        top = max(top, alert_score(alert, categories))
    if top >= WELFARE_ALERT_SCORE:
        status = WELFARE_ALERT
    elif top >= WELFARE_CONCERN_SCORE:
        status = WELFARE_CONCERN
    else:
        status = WELFARE_CHECK
    return status, _RECOMMENDATION[status]
