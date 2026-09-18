"""Entity health classification and welfare qualification.

Pure Python stdlib only. Zero Home Assistant imports. The coordinator supplies
raw state strings and registry membership; this module decides health and
whether the welfare status may honestly say "ok".
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from typing import Any

from .const import (
    HEALTH_MISSING,
    HEALTH_PRESENT,
    HEALTH_UNAVAILABLE,
    WELFARE_BLIND,
    WELFARE_BLIND_RECOMMENDATION,
    WELFARE_DEGRADED,
    WELFARE_DEGRADED_RECOMMENDATION,
    WELFARE_OK,
)

_UNAVAILABLE_STATES = frozenset({"unavailable", "unknown"})


def resolve_entity_health(
    entity_ids: Iterable[str],
    states: Mapping[str, str | None],
    in_registry: Collection[str],
) -> dict[str, str]:
    """Classify each entity as present / unavailable / missing.

    ``states[eid]`` is the raw state string, ``""`` for an entity that exists
    but whose state is not a string (test doubles), or ``None`` when the entity
    has no state object at all.
    """
    out: dict[str, str] = {}
    for eid in entity_ids:
        sv = states.get(eid)
        if sv is None:
            out[eid] = HEALTH_UNAVAILABLE if eid in in_registry else HEALTH_MISSING
        elif sv in _UNAVAILABLE_STATES:
            out[eid] = HEALTH_UNAVAILABLE
        else:
            out[eid] = HEALTH_PRESENT
    return out


def count_by_status(
    entity_ids: Iterable[str],
    health: Mapping[str, str],
    contributing: Collection[str],
    alerting: Collection[str],
) -> dict[str, int]:
    """Counts the status-summary sensor renders: ok / attention / unavailable / missing."""
    counts = {"ok": 0, "attention": 0, "unavailable": 0, "missing": 0}
    for eid in entity_ids:
        h = health.get(eid, HEALTH_MISSING)
        if h == HEALTH_MISSING:
            counts["missing"] += 1
        elif h == HEALTH_UNAVAILABLE:
            counts["unavailable"] += 1
        elif eid in contributing:
            counts["attention" if eid in alerting else "ok"] += 1
    return counts


def qualify_welfare(
    welfare: dict[str, Any],
    *,
    contributing: list[str],
    expected: list[str],
    missing: list[str],
    unavailable: list[str],
    panic_active: bool,
    device_alerts: bool,
) -> dict[str, Any]:
    """Return a copy of ``welfare`` that never says "ok" from no data.

    Precedence: panic alert > blind > alert/concern/check from alerts >
    degraded > ok. Always adds contributing/expected counts and the missing
    and unavailable id lists.
    """
    out = dict(welfare)
    n_c, n_e = len(contributing), len(expected)
    out["contributing_entities"] = n_c
    out["expected_entities"] = n_e
    out["missing_entities"] = list(missing)
    out["unavailable_entities"] = list(unavailable)
    if panic_active:
        return out
    if n_e > 0 and n_c == 0:
        out["status"] = WELFARE_BLIND
        out["recommendation"] = WELFARE_BLIND_RECOMMENDATION
        out["summary"] = f"blind: 0 of {n_e} entities reporting"
        return out
    if out.get("status") == WELFARE_OK and (n_c < n_e or device_alerts):
        out["status"] = WELFARE_DEGRADED
        out["recommendation"] = WELFARE_DEGRADED_RECOMMENDATION
        out["summary"] = f"degraded: {n_c} of {n_e} entities reporting"
        return out
    out["summary"] = f"{out.get('summary', '')} ({n_c} of {n_e} reporting)"
    return out
