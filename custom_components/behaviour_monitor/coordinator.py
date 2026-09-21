"""Thin Home Assistant shell around core.engine.Engine."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .config_flow import entity_specs_from_data
from .const import (
    CONF_NOTIFY_SERVICE,
    CONF_SITE_NAME,
    DOMAIN,
    EVENT_LOGBOOK,
    ISSUE_HEALTH_PREFIX,
    OPTION_DEFAULTS,
    SAVE_DEBOUNCE_S,
    SNOOZE_DURATIONS,
    SNOOZE_OFF,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .core.alert_router import DeliveryAction
from .core.engine import SCHEMA_VERSION, Engine, EngineConfig, EntitySpec
from .core.events import UNAVAILABLE_STATES, Category

try:
    from homeassistant.components.recorder import get_instance as recorder_get_instance
    from homeassistant.components.recorder.history import (
        state_changes_during_period as recorder_state_changes_during_period,
    )
except ImportError:  # pragma: no cover
    recorder_get_instance = None  # type: ignore[assignment]
    recorder_state_changes_during_period = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)


class _EngineStore(Store[dict[str, Any]]):
    """Store that throws away anything written by an older schema.

    The v4 integration wrote its learned patterns under the same key at store
    version 10. None of it maps onto the engine's models, so the only honest
    migration is to discard it and learn again from recorder history.
    Without this override Home Assistant calls Store._async_migrate_func,
    which raises NotImplementedError and fails setup on every upgrade.
    """

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        _LOGGER.info(
            "Discarding Behaviour Monitor store version %s.%s; learned state from "
            "before v5 cannot be migrated and will be rebuilt from history",
            old_major_version,
            old_minor_version,
        )
        return {}


class BehaviourMonitorCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Translate Home Assistant into Engine calls and Engine actions into HA."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self._entry = entry
        self._site: str = str(entry.data.get(CONF_SITE_NAME, "Behaviour Monitor"))
        self._notify_service: str = str(entry.data.get(CONF_NOTIFY_SERVICE, ""))
        options = {**OPTION_DEFAULTS, **entry.options}
        self._config = EngineConfig.from_options(options)
        self._specs, self._area_ids = self._resolve_specs()
        self._engine = Engine(self._config, self._specs)
        self._store = _EngineStore(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        self._pending: list[tuple[DeliveryAction, datetime]] = []
        self._unsubs: list[Any] = []
        self._last_notification: dict[str, Any] = {"timestamp": None, "kind": None}
        self._saver = Debouncer(
            hass,
            _LOGGER,
            cooldown=SAVE_DEBOUNCE_S,
            immediate=False,
            function=self._save,
        )

    # ----------------------------------------------------------- properties

    @property
    def site_name(self) -> str:
        return self._site

    @property
    def entity_specs(self) -> list[EntitySpec]:
        return list(self._specs)

    @property
    def holiday_mode(self) -> bool:
        return self._engine.holiday

    @property
    def snooze_until(self) -> datetime | None:
        return self._engine.snooze_until

    @property
    def last_notification(self) -> dict[str, Any]:
        return dict(self._last_notification)

    def is_snoozed(self) -> bool:
        return self._engine.is_snoozed(dt_util.now())

    def get_snooze_duration_key(self) -> str:
        until = self._engine.snooze_until
        if until is None or not self.is_snoozed():
            return SNOOZE_OFF
        remaining = (until - dt_util.now()).total_seconds()
        return min(
            (k for k in SNOOZE_DURATIONS if k != SNOOZE_OFF),
            key=lambda k: abs(remaining - SNOOZE_DURATIONS[k]),
        )

    def display_room(self, room: str) -> str:
        """Strip a leading site name so "Test House Kitchen" reads as "Kitchen"."""
        prefix = self._site.strip().lower()
        low = room.lower()
        if (
            prefix
            and low.startswith(prefix)
            and len(room) > len(prefix)
            and room[len(prefix)].isspace()
        ):
            return room[len(prefix) :].strip()
        return room

    # ---------------------------------------------------------------- rooms

    def _resolve_specs(self) -> tuple[list[EntitySpec], dict[str, str | None]]:
        """Build the entity specs and remember which area each room came from."""
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        specs: list[EntitySpec] = []
        area_ids: dict[str, str | None] = {}
        for entity_id, category in entity_specs_from_data(self._entry.data):
            room, area_id = self._room_for(entity_id, ent_reg, dev_reg, area_reg)
            specs.append(EntitySpec(entity_id, Category(category), room))
            area_ids[entity_id] = area_id
        return specs, area_ids

    def _room_for(
        self, entity_id: str, ent_reg: Any, dev_reg: Any, area_reg: Any
    ) -> tuple[str, str | None]:
        """Resolve a room name, and the area id it came from if it had one."""
        entry = ent_reg.async_get(entity_id)
        area_id = getattr(entry, "area_id", None)
        if not area_id and getattr(entry, "device_id", None):
            device = dev_reg.async_get(entry.device_id)
            area_id = getattr(device, "area_id", None)
        if area_id:
            area = area_reg.async_get_area(area_id)
            if area is not None and getattr(area, "name", None):
                return str(area.name), str(area_id)
        state = self.hass.states.get(entity_id)
        if state is not None and state.attributes.get("friendly_name"):
            return str(state.attributes["friendly_name"]), None
        return entity_id, None

    async def _async_registry_updated(self, event: Any) -> None:
        """Re-resolve rooms, telling a renamed area apart from a moved entity.

        Ruling P6: rename_room rewrites every chain and routine keyed on the
        old room, which is right when an area was renamed and catastrophic
        when one sensor was moved to another area, because it would merge two
        rooms' learning. The area id is what distinguishes them: same id and a
        new name is a rename, a new id is a move.
        """
        new_specs, new_area_ids = self._resolve_specs()
        old_rooms = {s.entity_id: s.room for s in self._specs}
        for spec in new_specs:
            entity_id = spec.entity_id
            if old_rooms.get(entity_id, spec.room) == spec.room:
                continue
            old_area = self._area_ids.get(entity_id)
            if old_area is not None and old_area == new_area_ids.get(entity_id):
                self._engine.rename_room(old_rooms[entity_id], spec.room)
            # A move, or a room that never came from an area, changes only this
            # entity; set_entities below updates its room in place and the
            # room-keyed chains are left alone.
        self._specs = new_specs
        self._area_ids = new_area_ids
        self._engine.set_entities(self._specs)
        await self._saver.async_call()

    # ------------------------------------------------------------- lifecycle

    async def async_setup(self) -> None:
        try:
            stored = await self._store.async_load()
        except Exception:  # noqa: BLE001
            # A corrupt or unreadable store must not stop the integration
            # loading; starting from nothing is always recoverable.
            _LOGGER.exception("Could not read stored state; starting fresh")
            stored = None
        all_ids = [s.entity_id for s in self._specs]
        if stored and isinstance(stored, dict) and "engine" in stored:
            # from_dict silently hands back a blank engine on a schema it does
            # not know. Left to itself that reads as "restored fine", every
            # entity counts as known, and bootstrap is skipped, so the site
            # starts from nothing with no history behind it.
            saved_schema = stored["engine"].get("schema")
            if saved_schema != SCHEMA_VERSION:
                _LOGGER.info(
                    "Stored engine schema %s is not %s; relearning from history",
                    saved_schema,
                    SCHEMA_VERSION,
                )
                stored = None
        if stored and isinstance(stored, dict) and "engine" in stored:
            try:
                self._engine = Engine.from_dict(
                    stored["engine"], self._config, self._specs
                )
                self._last_notification = stored.get(
                    "last_notification", self._last_notification
                )
                known = set(stored.get("entity_ids", []))
                new_ids = [eid for eid in all_ids if eid not in known]
            except Exception:  # noqa: BLE001
                # A store written by a half-finished version, or hand-edited,
                # must cost us the learning and nothing more.
                _LOGGER.exception("Stored engine state unusable; starting fresh")
                self._engine = Engine(self._config, self._specs)
                new_ids = all_ids
        else:
            new_ids = all_ids
        if new_ids:
            try:
                await self._bootstrap_entities(new_ids)
            except Exception:  # noqa: BLE001
                # recorder_get_instance raises KeyError when the recorder is
                # not loaded at all. Running without history is a slower
                # start, not a failed setup.
                _LOGGER.exception("Could not replay history; learning from now on")
            await self._save()
        self._schedule_flush()
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed)
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._async_registry_updated
            )
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                ar.EVENT_AREA_REGISTRY_UPDATED, self._async_registry_updated
            )
        )
        # Assigning an area to a device re-rooms every entity on it without
        # touching the entity registry, so this is the only event that fires.
        self._unsubs.append(
            self.hass.bus.async_listen(
                dr.EVENT_DEVICE_REGISTRY_UPDATED, self._async_registry_updated
            )
        )

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        # Stop both timers before the last save, so nothing can fire against a
        # coordinator that has already been unloaded.
        self._saver.async_shutdown()
        await super().async_shutdown()
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "site": self._site,
                "entity_ids": [s.entity_id for s in self._specs],
                "engine": self._engine.to_dict(),
                "last_notification": self._last_notification,
            }
        )

    async def _bootstrap_entities(self, entity_ids: list[str]) -> None:
        if (
            recorder_get_instance is None
            or recorder_state_changes_during_period is None
        ):
            _LOGGER.warning("Recorder unavailable; skipping bootstrap")
            return
        instance = recorder_get_instance(self.hass)
        if instance is None:
            return
        end = dt_util.now()
        start = end - timedelta(days=self._config.window_days)
        # state_changes_during_period takes one entity_id string, not a list,
        # and attributes are never read here.
        fetch = partial(recorder_state_changes_during_period, no_attributes=True)
        for entity_id in entity_ids:
            try:
                rows = await instance.async_add_executor_job(
                    fetch,
                    self.hass,
                    start,
                    end,
                    entity_id,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Could not load recorder history for %s", entity_id)
                continue
            prev: str | None = None
            for state in rows.get(entity_id, []):
                if state.state in UNAVAILABLE_STATES:
                    # learn_only does not suppress record_health, so replaying
                    # these would report outages that ended weeks ago. Drop
                    # prev too: the next real row is a first sighting, not a
                    # transition back from a dropout.
                    prev = None
                    continue
                ts = dt_util.as_local(state.last_changed)
                self._engine.handle_state(
                    entity_id, prev, state.state, ts, learn_only=True
                )
                prev = state.state
        # The router has already recorded these as opened and pushed, so
        # dropping them here would lose the alert for good.
        self._pending.extend((action, end) for action in self._engine.poll(end))

    # ----------------------------------------------------------------- events

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        entity_id = event.data.get("entity_id", "")
        if entity_id not in {s.entity_id for s in self._specs}:
            return
        new = event.data.get("new_state")
        if new is None:
            return
        old = event.data.get("old_state")
        now = dt_util.now()
        actions = self._engine.handle_state(
            entity_id, old.state if old else None, str(new.state), now
        )
        if actions:
            self._pending.extend((a, now) for a in actions)
            self.hass.async_create_task(self._flush_actions())
        self.hass.async_create_task(self._saver.async_call())

    def _schedule_flush(self) -> None:
        """Deliver anything queued outside the state-change path."""
        if self._pending:
            self.hass.async_create_task(self._flush_actions())

    async def _flush_actions(self) -> None:
        pending, self._pending = self._pending, []
        for action, when in pending:
            await self._perform([action], when)
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()
        try:
            actions = self._engine.poll(now)
            await self._perform(actions, now)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Engine poll failed")
        snapshot = self._engine.snapshot(now)
        snapshot["site"] = self._site
        snapshot["last_notification"] = dict(self._last_notification)
        snapshot["display_rooms"] = {
            s.room: self.display_room(s.room) for s in self._specs
        }
        return snapshot

    # --------------------------------------------------------------- delivery

    async def _perform(self, actions: list[DeliveryAction], now: datetime) -> None:
        for act in actions:
            alert = act.alert
            text = self._render(alert.explanation)
            if act.action == "push":
                await self._push(f"{self._site} welfare", text)
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": f"{self._site} welfare",
                        "message": text,
                        "notification_id": self._notification_id(),
                    },
                )
                self._last_notification = {
                    "timestamp": now.isoformat(),
                    "kind": alert.kind,
                }
            elif act.action == "push_clear":
                await self._push(f"{self._site} welfare", f"Cleared: {text}")
                await self.hass.services.async_call(
                    "persistent_notification",
                    "dismiss",
                    {"notification_id": self._notification_id()},
                )
            elif act.action == "repair_create":
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    self._issue_id(alert.key),
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="device_health",
                    translation_placeholders={"site": self._site, "message": text},
                )
            elif act.action == "repair_delete":
                ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(alert.key))
            elif act.action == "log":
                self.hass.bus.async_fire(
                    EVENT_LOGBOOK,
                    {"name": self._site, "message": text, "domain": DOMAIN},
                )

    def _notification_id(self) -> str:
        return f"{DOMAIN}_{self._entry.entry_id}_welfare"

    def _issue_id(self, key: str) -> str:
        return f"{ISSUE_HEALTH_PREFIX}{self._entry.entry_id}_{key}"

    def _render(self, text: str) -> str:
        for spec in sorted(self._specs, key=lambda s: -len(s.room)):
            display = self.display_room(spec.room)
            if display != spec.room:
                text = text.replace(spec.room, display)
        return text

    async def _push(self, title: str, message: str) -> None:
        if "." not in self._notify_service:
            return
        domain, service = self._notify_service.split(".", 1)
        await self.hass.services.async_call(
            domain, service, {"title": title, "message": message}
        )

    # --------------------------------------------------------------- controls

    async def _after_control(self) -> None:
        await self._save()
        await self.async_request_refresh()

    async def async_enable_holiday_mode(self) -> None:
        self._engine.holiday = True
        await self._after_control()

    async def async_disable_holiday_mode(self) -> None:
        self._engine.holiday = False
        await self._after_control()

    async def async_snooze(self, duration_key: str) -> None:
        seconds = SNOOZE_DURATIONS.get(duration_key, 0)
        self._engine.snooze_until = (
            dt_util.now() + timedelta(seconds=seconds) if seconds > 0 else None
        )
        await self._after_control()

    async def async_clear_snooze(self) -> None:
        self._engine.snooze_until = None
        await self._after_control()

    async def async_acknowledge(self) -> None:
        now = dt_util.now()
        self._engine.acknowledge(now)
        await self._perform(self._engine.poll(now), now)
        await self._after_control()

    async def async_reset_learning(self, entity_id: str | None = None) -> None:
        self._engine.reset(entity_id)
        ids = [entity_id] if entity_id else [s.entity_id for s in self._specs]
        await self._bootstrap_entities(ids)
        self._schedule_flush()
        await self._after_control()

    async def async_test_panic(self) -> None:
        """Send a test push. The alert is self-acknowledging and has its own
        source, so a real panic open at the time is neither replaced nor
        acknowledged; the next poll clears only the test alert."""
        now = dt_util.now()
        await self._perform(self._engine.submit_test(now), now)
        await self._after_control()
