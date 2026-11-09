"""Thin Home Assistant shell around core.engine.Engine."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_STATE_CHANGED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
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
    CONF_BEDROOMS,
    CONF_SITE_NAME,
    DOMAIN,
    EVENT_ALERT,
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
from .rooms import bedroom_suggestions, display_room, resolve_room

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


# The poll saves the store at most this often, keeping the last poll time
# fresh for the poll-gap check after an unclean shutdown.
POLL_SAVE_EVERY = timedelta(minutes=5)


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
        self._specs, self._area_ids = self._resolve_specs()
        options = {**OPTION_DEFAULTS, **entry.options}
        if options.get(CONF_BEDROOMS) is None:
            # Unset bedrooms are the rooms named "bedroom"; none of them means
            # the night rules apply to every room.
            options[CONF_BEDROOMS] = bedroom_suggestions(s.room for s in self._specs)
        self._config = EngineConfig.from_options(options)
        self._engine = Engine(self._config, self._specs)
        self._store = _EngineStore(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        self._pending: list[tuple[DeliveryAction, datetime]] = []
        self._unsubs: list[Any] = []
        # Until Home Assistant has started, alert events are held here and
        # fired in order once it has, so automations are listening for them.
        self._started = True
        self._held_events: list[dict[str, Any]] = []
        self._started_unsub: Any = None
        self._last_save: datetime | None = None
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
        return display_room(self._site, room)

    # ---------------------------------------------------------------- rooms

    def _resolve_specs(self) -> tuple[list[EntitySpec], dict[str, str | None]]:
        """Build the entity specs and remember which area each room came from."""
        specs: list[EntitySpec] = []
        area_ids: dict[str, str | None] = {}
        for entity_id, category in entity_specs_from_data(self._entry.data):
            room, area_id = resolve_room(self.hass, entity_id)
            specs.append(EntitySpec(entity_id, Category(category), room))
            area_ids[entity_id] = area_id
        return specs, area_ids

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
        renamed: dict[str, str] = {}
        for spec in new_specs:
            entity_id = spec.entity_id
            if old_rooms.get(entity_id, spec.room) == spec.room:
                continue
            old_area = self._area_ids.get(entity_id)
            if old_area is not None and old_area == new_area_ids.get(entity_id):
                self._engine.rename_room(old_rooms[entity_id], spec.room)
                renamed[old_rooms[entity_id]] = spec.room
            # A move, or a room that never came from an area, changes only this
            # entity; set_entities below updates its room in place and the
            # room-keyed chains are left alone.
        self._specs = new_specs
        self._area_ids = new_area_ids
        self._engine.set_entities(self._specs)
        await self._saver.async_call()
        self._rename_bedrooms(renamed)

    def _rename_bedrooms(self, renamed: dict[str, str]) -> None:
        """Carry a renamed area over into the bedrooms option.

        Unset bedrooms are left unset, and the entry reloads when the rooms
        named "bedroom" change, so they are worked out again. Updating the
        entry reloads it too, which is acceptable for a rename.
        """
        bedrooms = self._entry.options.get(CONF_BEDROOMS)
        if bedrooms is None:
            named = frozenset(bedroom_suggestions(s.room for s in self._specs))
            if named != self._config.whereabouts.bedrooms:
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self._entry.entry_id)
                )
            return
        if not any(room in renamed for room in bedrooms):
            return
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={
                **self._entry.options,
                CONF_BEDROOMS: [renamed.get(room, room) for room in bedrooms],
            },
        )

    # ------------------------------------------------------------- lifecycle

    async def async_setup(self) -> None:
        # Hold events while the stores and history load; whether Home
        # Assistant has started is decided again at the end of setup.
        self._started = self.hass.state is CoreState.running
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
        # No await between reading the state and acting on it: if
        # homeassistant_started fired during the awaits above, a listener
        # registered now would never run and events would be held for good.
        if self.hass.state is CoreState.running:
            # Already up (a reload, or it started while we loaded): release
            # anything held and remind for what automations may have lost.
            self._on_started()
        else:
            self._started_unsub = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._async_ha_started
            )

    async def _async_ha_started(self, _event: Any) -> None:
        # A listen_once listener is gone once it has fired; unsubscribing it
        # again at shutdown would make Home Assistant log an error.
        self._started_unsub = None
        self._on_started()

    def _on_started(self) -> None:
        """Fire the events held during startup, then the restart reminders."""
        self._started = True
        held, self._held_events = self._held_events, []
        # Held alerts and restart reminders are looked up on the sensor too.
        self._publish(dt_util.now())
        for payload in held:
            self.hass.bus.async_fire(EVENT_ALERT, payload)
        self._fire_restart_reminders({p["id"] for p in held})

    def _fire_restart_reminders(self, announced: set[str]) -> None:
        """One reminder per open attention alert not already announced.

        An alert queued for delivery but not yet performed will be announced
        as opened shortly, so it is skipped too.
        """
        skip = set(announced)
        skip.update(
            a.alert_id for a, _ in self._pending if a.action == "event" and a.alert_id
        )
        for act in self._engine.reminders("restart"):
            if act.alert_id not in skip:
                self.hass.bus.async_fire(EVENT_ALERT, self._event_payload(act))

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._started_unsub is not None:
            self._started_unsub()
            self._started_unsub = None
        # Stop both timers before the last save, so nothing can fire against a
        # coordinator that has already been unloaded.
        self._saver.async_shutdown()
        await super().async_shutdown()
        await self._save()

    async def _save(self) -> None:
        self._last_save = dt_util.now()
        await self._store.async_save(
            {
                "site": self._site,
                "entity_ids": [s.entity_id for s in self._specs],
                "engine": self._engine.to_dict(),
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
        # Every entity's rows are fetched before any is replayed, then merged
        # by time: the whereabouts model drops events older than its current
        # interval, so replaying one entity after another would teach it from
        # the first entity only.
        replay: list[tuple[datetime, str, str | None, str]] = []
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
                replay.append((ts, entity_id, prev, state.state))
                prev = state.state
        # sorted is stable, so rows at the same instant keep entity order.
        for ts, entity_id, prev, new in sorted(replay, key=lambda r: r[0]):
            self._engine.handle_state(entity_id, prev, new, ts, learn_only=True)
        # The router has already recorded these as opened, so dropping them
        # here would lose their events for good.
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
        if self._started and any(a.action == "event" for a, _ in pending):
            self._publish(dt_util.now())
        for action, when in pending:
            await self._perform([action], when, publish=False)
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()
        try:
            actions = self._engine.poll(now)
            # The snapshot returned below is written to the entities before
            # Home Assistant runs any automation these events trigger.
            await self._perform(actions, now, publish=False)
            # The last poll time decides whether a restart was a gap worth
            # restarting the stillness clock for, so it must not go stale
            # in the store while nothing changes.
            if self._last_save is None or now - self._last_save >= POLL_SAVE_EVERY:
                await self._save()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Engine poll failed")
        return self._build_snapshot(now)

    def _build_snapshot(self, now: datetime) -> dict[str, Any]:
        snapshot = self._engine.snapshot(now)
        snapshot["site"] = self._site
        snapshot["display_rooms"] = {
            s.room: self.display_room(s.room) for s in self._specs
        }
        return snapshot

    def _publish(self, now: datetime) -> None:
        """Put the current snapshot on the entities straight away.

        Called before an alert event is fired outside the poll: the blueprint
        looks the id up on the Welfare Status sensor as soon as the event
        arrives, and async_request_refresh can be held up to 10 s by its
        debouncer. A failure here must never stop the event going out.
        """
        try:
            self.async_set_updated_data(self._build_snapshot(now))
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not publish the snapshot before an alert")

    # --------------------------------------------------------------- delivery

    async def _perform(
        self, actions: list[DeliveryAction], now: datetime, publish: bool = True
    ) -> None:
        """Deliver actions. Outside the poll, publish first if any is an event."""
        if publish and self._started and any(a.action == "event" for a in actions):
            self._publish(now)
        for act in actions:
            alert = act.alert
            if act.action == "event":
                payload = self._event_payload(act)
                if self._started:
                    self.hass.bus.async_fire(EVENT_ALERT, payload)
                else:
                    self._held_events.append(payload)
            elif act.action == "repair_create":
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    self._issue_id(alert.key),
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="device_health",
                    translation_placeholders={
                        "site": self._site,
                        "message": self._render(alert.explanation),
                    },
                )
            elif act.action == "repair_delete":
                ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(alert.key))
            elif act.action == "log":
                self.hass.bus.async_fire(
                    EVENT_LOGBOOK,
                    {
                        "name": self._site,
                        "message": self._render(alert.explanation),
                        "domain": DOMAIN,
                    },
                )

    def _event_payload(self, act: DeliveryAction) -> dict[str, Any]:
        alert = act.alert
        payload: dict[str, Any] = {
            "entry_id": self._entry.entry_id,
            "site": self._site,
            "type": act.event,
            "id": act.alert_id,
            "group": act.group,
            "class": alert.cls.value,
            "kind": alert.kind,
            "severity": alert.severity.value,
            "source": alert.source,
            "room": alert.details.get("room"),
            "message": self._render(alert.explanation),
            "raised_at": alert.raised_at.isoformat(),
            "test": act.test,
        }
        if act.event == "reminder":
            payload["reason"] = act.reason
        if act.cleared_by is not None:
            payload["cleared_by"] = act.cleared_by
        return payload

    def _issue_id(self, key: str) -> str:
        return f"{ISSUE_HEALTH_PREFIX}{self._entry.entry_id}_{key}"

    def _render(self, text: str) -> str:
        for spec in sorted(self._specs, key=lambda s: -len(s.room)):
            display = self.display_room(spec.room)
            if display != spec.room:
                text = text.replace(spec.room, display)
        return text

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

    async def async_clear_alert(self, alert_id: str | None) -> bool:
        """Clear one open panic by id, or every open panic without one.

        Returns True when anything was cleared. Other welfare alerts close on
        their own, so an id that is not an open panic clears nothing. The
        service warns when no site owns the id, so this stays quiet: with
        several sites, every site but one is expected to miss.
        """
        now = dt_util.now()
        actions = self._engine.clear_panic(alert_id, now)
        if not actions:
            return False
        await self._perform(actions, now)
        await self._after_control()
        return True

    async def async_reset_learning(self, entity_id: str | None = None) -> None:
        self._engine.reset(entity_id)
        ids = [entity_id] if entity_id else [s.entity_id for s in self._specs]
        await self._bootstrap_entities(ids)
        self._schedule_flush()
        await self._after_control()

    async def async_test_panic(self) -> None:
        """Open a test alert and fire its event. It has its own source, so a
        real panic open at the time is untouched; the next poll clears only
        the test alert."""
        now = dt_util.now()
        await self._perform(self._engine.submit_test(now), now)
        await self._after_control()
