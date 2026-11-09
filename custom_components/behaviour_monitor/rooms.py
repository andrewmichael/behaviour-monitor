"""Room names for configured entities, shared by the config flow and coordinator."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


def resolve_room(hass: HomeAssistant, entity_id: str) -> tuple[str, str | None]:
    """Resolve a room name, and the area id it came from if it had one.

    The entity's own area wins, then its device's area, then its friendly
    name, then the entity id itself.
    """
    entry = er.async_get(hass).async_get(entity_id)
    area_id = getattr(entry, "area_id", None)
    if not area_id and getattr(entry, "device_id", None):
        device = dr.async_get(hass).async_get(entry.device_id)
        area_id = getattr(device, "area_id", None)
    if area_id:
        area = ar.async_get(hass).async_get_area(area_id)
        if area is not None and getattr(area, "name", None):
            return str(area.name), str(area_id)
    state = hass.states.get(entity_id)
    if state is not None and state.attributes.get("friendly_name"):
        return str(state.attributes["friendly_name"]), None
    return entity_id, None


def display_room(site: str, room: str) -> str:
    """Strip a leading site name so "Test House Kitchen" reads as "Kitchen"."""
    prefix = site.strip().lower()
    low = room.lower()
    if (
        prefix
        and low.startswith(prefix)
        and len(room) > len(prefix)
        and room[len(prefix)].isspace()
    ):
        return room[len(prefix) :].strip()
    return room


def bedroom_suggestions(rooms: Iterable[str]) -> list[str]:
    """The rooms whose name contains "bedroom" (case-insensitive), sorted."""
    return sorted({r for r in rooms if "bedroom" in r.lower()})
