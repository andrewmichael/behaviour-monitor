"""Data update coordinator for Behaviour Monitor — v1.1 rebuild."""
# Wires RoutineModel, AcuteDetector, DriftDetector into DataUpdateCoordinator.
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .acute_detector import AcuteDetector
from .alert_result import AlertResult, AlertSeverity, AlertType
from .const import (
    CONF_ACTIVITY_TIER_OVERRIDE,
    CONF_ALERT_REPEAT_INTERVAL, CONF_CATEGORY_CONTACT, CONF_CATEGORY_LIGHT,
    CONF_CATEGORY_MOTION, CONF_CATEGORY_PANIC, CONF_CATEGORY_PLUG, CONF_CORRELATION_WINDOW, CONF_DRIFT_SENSITIVITY,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_HISTORY_WINDOW_DAYS, CONF_INACTIVITY_MULTIPLIER, CONF_LEARNING_PERIOD,
    CONF_MAX_INACTIVITY_MULTIPLIER, CONF_MIN_INACTIVITY_MULTIPLIER,
    CONF_MIN_NOTIFICATION_SEVERITY, CONF_MONITORED_ENTITIES, CONF_MOTION_DEBOUNCE_SECONDS,
    CONF_NOTIFICATION_COOLDOWN,
    CONF_NOTIFY_SERVICES, CONF_PANIC_RENOTIFY_MINUTES, CONF_REBOOTSTRAP_MOTION, CONF_TRACK_ATTRIBUTES, CONF_TRACK_ATTRIBUTES_EXCLUDE,
    CONF_TRACK_ATTRIBUTES_INCLUDE,
    ActivityTier,
    DEFAULT_ACTIVITY_TIER_OVERRIDE,
    DEFAULT_ALERT_REPEAT_INTERVAL, DEFAULT_CORRELATION_WINDOW,
    DEFAULT_ENABLE_NOTIFICATIONS, DEFAULT_HISTORY_WINDOW_DAYS,
    DEFAULT_INACTIVITY_MULTIPLIER, DEFAULT_LEARNING_PERIOD_DAYS,
    DEFAULT_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER,
    DEFAULT_MIN_NOTIFICATION_SEVERITY,
    DEFAULT_MOTION_DEBOUNCE_SECONDS,
    DEFAULT_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFY_SERVICES, DEFAULT_PANIC_RENOTIFY_MINUTES, DEFAULT_TRACK_ATTRIBUTES,
    DOMAIN, EntityCategory, SENSITIVITY_MEDIUM, SNOOZE_DURATIONS, SNOOZE_OFF, STORAGE_KEY,
    STORAGE_VERSION, UPDATE_INTERVAL, WELFARE_DEBOUNCE_CYCLES,
)
from .correlation_detector import CorrelationDetector
from .drift_detector import CUSUMState, DriftDetector
from .entity_category import MotionDebouncer, derive_weighted_status, infer_categories
from .panic_monitor import PanicMonitor
from .routine_model import RoutineModel, format_duration, is_binary_state

try:
    from homeassistant.components.recorder import get_instance as recorder_get_instance
    from homeassistant.components.recorder.history import (
        state_changes_during_period as recorder_state_changes_during_period,
    )
except ImportError:  # pragma: no cover
    recorder_get_instance = None  # type: ignore[assignment]
    recorder_state_changes_during_period = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)
_SEV_ORDER = [AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH]
_SEV_GATE = {"minor": AlertSeverity.LOW, "moderate": AlertSeverity.LOW, "significant": AlertSeverity.MEDIUM, "critical": AlertSeverity.HIGH}


def _parse_dt(ts: str) -> datetime | None:
    """Parse ISO timestamp; tz-aware when possible; return None on failure."""
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is not None:
            return dt
        try:
            return dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        except (TypeError, AttributeError):
            return dt
    except (ValueError, TypeError):
        return None


class BehaviourMonitorStore(Store):  # type: ignore[type-arg]
    """Store whose persisted schema is version-tolerant.

    Every reader of the persisted dict uses .get() with defaults, so data written
    by any earlier STORAGE_VERSION loads unchanged. Without this override Home
    Assistant raises NotImplementedError on a major-version mismatch.
    """

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        return old_data


class BehaviourMonitorCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator wiring RoutineModel + AcuteDetector + DriftDetector."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=UPDATE_INTERVAL))
        self._entry = entry
        d = entry.data
        self._monitored_entities: list[str] = list(d.get(CONF_MONITORED_ENTITIES, []))
        self._history_window_days: int = int(d.get(CONF_HISTORY_WINDOW_DAYS, DEFAULT_HISTORY_WINDOW_DAYS))
        self._enable_notifications: bool = d.get(CONF_ENABLE_NOTIFICATIONS, DEFAULT_ENABLE_NOTIFICATIONS)
        self._notify_services: list[str] = list(d.get(CONF_NOTIFY_SERVICES, DEFAULT_NOTIFY_SERVICES))
        self._notification_cooldown: int = int(d.get(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN))
        self._min_notification_severity: str = d.get(CONF_MIN_NOTIFICATION_SEVERITY, DEFAULT_MIN_NOTIFICATION_SEVERITY)
        self._learning_period_days: int = int(d.get(CONF_LEARNING_PERIOD, DEFAULT_LEARNING_PERIOD_DAYS))
        self._track_attributes: bool = bool(d.get(CONF_TRACK_ATTRIBUTES, DEFAULT_TRACK_ATTRIBUTES))
        self._track_attributes_include: frozenset[str] = frozenset(d.get(CONF_TRACK_ATTRIBUTES_INCLUDE) or [])
        self._track_attributes_exclude: frozenset[str] = frozenset(d.get(CONF_TRACK_ATTRIBUTES_EXCLUDE) or [])
        self._category_overrides: dict[EntityCategory, list[str]] = {
            EntityCategory.MOTION: list(d.get(CONF_CATEGORY_MOTION) or []),
            EntityCategory.CONTACT: list(d.get(CONF_CATEGORY_CONTACT) or []),
            EntityCategory.PLUG: list(d.get(CONF_CATEGORY_PLUG) or []),
            EntityCategory.LIGHT: list(d.get(CONF_CATEGORY_LIGHT) or []),
            EntityCategory.PANIC: list(d.get(CONF_CATEGORY_PANIC) or []),
        }
        self._motion_debounce_seconds: int = int(d.get(CONF_MOTION_DEBOUNCE_SECONDS, DEFAULT_MOTION_DEBOUNCE_SECONDS))
        self._categories: dict[str, EntityCategory] = {}
        self._debouncer = MotionDebouncer(self._motion_debounce_seconds)
        self._panic_renotify_minutes: int = int(d.get(CONF_PANIC_RENOTIFY_MINUTES, DEFAULT_PANIC_RENOTIFY_MINUTES))
        self._panic_monitor = PanicMonitor()
        self._routine_model = RoutineModel(self._learning_period_days)
        self._acute_detector = AcuteDetector(
            float(d.get(CONF_INACTIVITY_MULTIPLIER, DEFAULT_INACTIVITY_MULTIPLIER)),
            min_multiplier=float(d.get(CONF_MIN_INACTIVITY_MULTIPLIER, DEFAULT_MIN_INACTIVITY_MULTIPLIER)),
            max_multiplier=float(d.get(CONF_MAX_INACTIVITY_MULTIPLIER, DEFAULT_MAX_INACTIVITY_MULTIPLIER)),
        )
        self._drift_detector = DriftDetector(d.get(CONF_DRIFT_SENSITIVITY, SENSITIVITY_MEDIUM))
        self._correlation_detector = CorrelationDetector(
            co_occurrence_window_seconds=int(
                d.get(CONF_CORRELATION_WINDOW, DEFAULT_CORRELATION_WINDOW)
            ),
        )
        self._last_seen: dict[str, datetime] = {}
        self._notification_cooldowns: dict[str, datetime] = {}
        self._alert_repeat_interval: int = int(d.get(CONF_ALERT_REPEAT_INTERVAL, DEFAULT_ALERT_REPEAT_INTERVAL))
        self._activity_tier_override: str = str(d.get(CONF_ACTIVITY_TIER_OVERRIDE, DEFAULT_ACTIVITY_TIER_OVERRIDE))
        self._alert_suppression: dict[str, datetime] = {}
        self._holiday_mode = False
        self._snooze_until: datetime | None = None
        self._today_count = 0
        self._today_date: date | None = None
        self._last_notification_info: dict[str, Any] = {"timestamp": None, "type": None}
        self._welfare_debounce: dict[str, int] = {}
        self._current_welfare_status = "ok"
        self._store = BehaviourMonitorStore(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self._unsub_state_changed: Any = None

    @property
    def monitored_entities(self) -> list[str]:
        return self._monitored_entities

    @property
    def holiday_mode(self) -> bool:
        return self._holiday_mode

    @property
    def snooze_until(self) -> datetime | None:
        return self._snooze_until

    def is_snoozed(self) -> bool:
        return self._snooze_until is not None and dt_util.now() < self._snooze_until

    @property
    def panic_active(self) -> list[str]:
        return [eid for eid, _, _ in self._panic_monitor.active()]

    @property
    def panic_unacknowledged(self) -> list[str]:
        return self._panic_monitor.unacknowledged()

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored:
            if "routine_model" in stored:
                self._routine_model = RoutineModel.from_dict(stored["routine_model"])
            for eid, sd in stored.get("cusum_states", {}).items():
                self._drift_detector._states[eid] = CUSUMState.from_dict(sd)
            if "correlation_state" in stored:
                self._correlation_detector = CorrelationDetector.from_dict(
                    stored["correlation_state"]
                )
                # Purge correlation state for entities no longer monitored
                monitored_set = set(self._monitored_entities)
                stale_entities = [
                    eid for eid in list(self._correlation_detector._entity_event_counts)
                    if eid not in monitored_set
                ]
                for eid in stale_entities:
                    self._correlation_detector.remove_entity(eid)
            if "panic_state" in stored:
                self._panic_monitor = PanicMonitor.from_dict(stored["panic_state"])
            c = stored.get("coordinator", {})
            self._holiday_mode = c.get("holiday_mode", False)
            if (sn := c.get("snooze_until")) and (sdt := _parse_dt(sn)):
                now = dt_util.now()
                now = now.replace(tzinfo=sdt.tzinfo) if now.tzinfo is None and sdt.tzinfo is not None else now
                self._snooze_until = sdt if sdt > now else None
            self._last_seen = {e: dt for e, ts in c.get("last_seen", {}).items() if (dt := _parse_dt(ts))}
            self._last_notification_info = c.get("last_notification_info", {"timestamp": None, "type": None})
            self._notification_cooldowns = {k: dt for k, ts in c.get("notification_cooldowns", {}).items() if (dt := _parse_dt(ts))}
            self._alert_suppression = {k: dt for k, ts in c.get("alert_suppression", {}).items() if (dt := _parse_dt(ts))}
        # Categories must be inferred from restored data before either bootstrap path.
        self._refresh_categories()
        if stored:
            if self._entry.data.get(CONF_REBOOTSTRAP_MOTION, False):
                await self._rebootstrap_motion_entities()
        elif not self._routine_model._entities:
            await self._bootstrap_from_recorder()
            await self._save_data()
        self._unsub_state_changed = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed)

    async def async_shutdown(self) -> None:
        if self._unsub_state_changed:
            self._unsub_state_changed()
            self._unsub_state_changed = None
        await self._save_data()

    async def _save_data(self) -> None:
        await self._store.async_save({
            "routine_model": self._routine_model.to_dict(),
            "cusum_states": {e: s.to_dict() for e, s in self._drift_detector._states.items()},
            "correlation_state": self._correlation_detector.to_dict(),
            "panic_state": self._panic_monitor.to_dict(),
            "coordinator": {
                "holiday_mode": self._holiday_mode,
                "snooze_until": self._snooze_until.isoformat() if self._snooze_until else None,
                "last_seen": {e: dt.isoformat() for e, dt in self._last_seen.items()},
                "last_notification_info": self._last_notification_info,
                "notification_cooldowns": {k: v.isoformat() for k, v in self._notification_cooldowns.items()},
                "alert_suppression": {k: v.isoformat() for k, v in self._alert_suppression.items()},
            },
        })

    def _registry_device_classes(self) -> dict[str, str | None]:
        """Return entity-registry device class per monitored entity (None if unknown)."""
        out: dict[str, str | None] = {}
        try:
            registry = er.async_get(self.hass)
        except Exception:  # noqa: BLE001
            return {eid: None for eid in self._monitored_entities}
        for eid in self._monitored_entities:
            entry = registry.async_get(eid)
            dc: Any = None
            if entry is not None:
                dc = entry.device_class or entry.original_device_class
            out[eid] = dc if isinstance(dc, str) else None
        return out

    def _refresh_categories(self) -> None:
        """Rebuild the entity -> category map from overrides, registry and model."""
        numeric: set[str] = set()
        for eid in self._monitored_entities:
            r = self._routine_model._entities.get(eid)
            if r is not None:
                if not r.is_binary:
                    numeric.add(eid)
                continue
            state = self.hass.states.get(eid)
            sv = getattr(state, "state", None)
            if isinstance(sv, str) and sv not in ("unavailable", "unknown") and not is_binary_state(sv):
                numeric.add(eid)
        self._categories = infer_categories(
            self._monitored_entities,
            self._category_overrides,
            self._registry_device_classes(),
            numeric,
        )

    def _tracks_attributes(self, entity_id: str) -> bool:
        """Return whether attribute-only changes count as activity for this entity.

        Per-entity overrides take precedence over the global setting: an entity in
        the exclude list never tracks attributes, one in the include list always
        does, and everything else follows the global track_attributes toggle.
        """
        if entity_id in self._track_attributes_exclude:
            return False
        if entity_id in self._track_attributes_include:
            return True
        return self._track_attributes

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        eid: str = event.data.get("entity_id", "")
        if eid not in self._monitored_entities:
            return
        ns = event.data.get("new_state")
        if ns is None:
            return
        if self._categories.get(eid) is EntityCategory.PANIC:
            self._handle_panic_event(eid, event.data.get("old_state"), ns)
            return
        old_state = event.data.get("old_state")
        if not self._tracks_attributes(eid):
            if old_state is not None and old_state.state == ns.state:
                return
        now, sv = dt_util.now(), str(ns.state)
        self._last_seen[eid] = now
        old_sv = None if old_state is None else str(old_state.state)
        is_motion = self._categories.get(eid) is EntityCategory.MOTION
        if not self._debouncer.should_count(eid, is_motion, old_sv, sv, now):
            return
        self._routine_model.record(entity_id=eid, timestamp=now, state_value=sv, is_binary=is_binary_state(sv))
        self._correlation_detector.record_event(eid, now, self._last_seen)
        if self._today_date != now.date():
            self._today_count, self._today_date = 0, now.date()
        self._today_count += 1
        self.hass.async_create_task(self.async_request_refresh())

    def _handle_panic_event(self, eid: str, old_state: Any, new_state: Any) -> None:
        """Panic entities bypass learning entirely: press notifies now, release clears."""
        sv = str(new_state.state).lower()
        old_sv = None if old_state is None else str(old_state.state).lower()
        now = dt_util.now()
        if sv == "on" and old_sv != "on":
            if self._panic_monitor.press(eid, now):
                self.hass.async_create_task(self._async_panic_pressed([eid], now))
        elif sv == "off" and self._panic_monitor.is_active(eid):
            self._panic_monitor.release(eid)
            self.hass.async_create_task(
                self._save_fire_refresh(f"{DOMAIN}_panic_released", {"entity_id": eid})
            )

    async def _async_panic_pressed(self, entity_ids: list[str], now: datetime) -> None:
        await self._send_panic_notification(entity_ids, now)
        await self._save_fire_refresh(f"{DOMAIN}_panic_pressed", {"entity_ids": entity_ids})

    async def _send_panic_notification(self, entity_ids: list[str], now: datetime) -> None:
        """Send a panic notification. Ignores every suppression on purpose."""
        lines = []
        for eid in entity_ids:
            since = self._panic_monitor.active_since(eid)
            elapsed = (now - since).total_seconds() if since is not None else 0.0
            when = "just now" if elapsed < 60 else f"{format_duration(elapsed)} ago"
            lines.append(f"- PANIC: {eid} pressed {when}")
        title, msg = "Behaviour Monitor: PANIC", "\n".join(lines)
        await self.hass.services.async_call(
            "persistent_notification", "create",
            {"title": title, "message": msg, "notification_id": "behaviour_monitor_panic"},
        )
        for svc in self._notify_services:
            parts = svc.split(".", 1)
            if len(parts) == 2:
                await self.hass.services.async_call(parts[0], parts[1], {"title": title, "message": msg})
        self._last_notification_info = {"timestamp": now.isoformat(), "type": "panic"}

    async def async_acknowledge_panic(self, entity_id: str | None = None) -> None:
        """Acknowledge one or all active panics; stops re-notification until release."""
        changed = self._panic_monitor.acknowledge(dt_util.now(), entity_id)
        if changed:
            await self._save_fire_refresh(f"{DOMAIN}_panic_acknowledged", {"entity_ids": changed})

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()
        if self._today_date != now.date():
            self._today_count = 0
            self._today_date = now.date()
            for r in self._routine_model._entities.values():
                r.classify_tier(now)
            if self._activity_tier_override != "auto":
                override_tier = ActivityTier(self._activity_tier_override)
                for r in self._routine_model._entities.values():
                    r._activity_tier = override_tier
            self._correlation_detector.recompute()
        if self._holiday_mode or self.is_snoozed():
            return self._build_safe_defaults()
        try:
            alerts = self._run_detection(now)
            await self._handle_alerts(alerts, now)
            return self._build_sensor_data(alerts, now)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Coordinator update error — returning safe defaults")
            return self._build_safe_defaults()

    def _run_detection(self, now: datetime) -> list[AlertResult]:
        alerts: list[AlertResult] = []
        d = now.date()
        for eid in self._monitored_entities:
            if (r := self._routine_model._entities.get(eid)) is None:
                continue
            alerts.extend(x for x in (
                self._acute_detector.check_inactivity(eid, r, now, self._last_seen.get(eid)),
                self._acute_detector.check_unusual_time(eid, r, now),
                self._drift_detector.check(eid, r, d, now),
            ) if x is not None)
        # Correlation break detection
        for eid in self._monitored_entities:
            alerts.extend(
                self._correlation_detector.check_breaks(eid, now, self._last_seen)
            )
        return alerts

    async def _handle_alerts(self, alerts: list[AlertResult], now: datetime) -> None:
        # Clear suppression entries whose condition has resolved (key not in current alerts)
        current_keys = {f"{a.entity_id}|{a.alert_type.value}" for a in alerts}
        for key in list(self._alert_suppression):
            if key not in current_keys:
                del self._alert_suppression[key]

        if not self._enable_notifications or not alerts:
            return
        gate = _SEV_GATE.get(self._min_notification_severity, AlertSeverity.MEDIUM)
        def _ok(a: AlertResult) -> bool:
            key = f"{a.entity_id}|{a.alert_type.value}"
            last = self._alert_suppression.get(key)
            sup_ok = last is None or (now - last).total_seconds() / 60 >= self._alert_repeat_interval
            sev_ok = _SEV_ORDER.index(a.severity) >= _SEV_ORDER.index(gate)
            return sup_ok and sev_ok
        notifiable = [a for a in alerts if _ok(a)]
        drift_ok = [a for a in notifiable if a.alert_type == AlertType.DRIFT]
        acute_ok = [a for a in notifiable if a.alert_type != AlertType.DRIFT]
        new_status = self._derive_welfare(alerts)["status"]
        if new_status != self._current_welfare_status:
            cnt = self._welfare_debounce.get(new_status, 0) + 1
            self._welfare_debounce[new_status] = cnt
            drift_ok = drift_ok if cnt >= WELFARE_DEBOUNCE_CYCLES else []
            if cnt >= WELFARE_DEBOUNCE_CYCLES:
                self._welfare_debounce[new_status] = 0
                self._current_welfare_status = new_status
        else:
            self._welfare_debounce = {}
        to_send = acute_ok + drift_ok
        if not to_send:
            return
        await self._send_notification(to_send)
        for a in to_send:
            self._alert_suppression[f"{a.entity_id}|{a.alert_type.value}"] = now
            self._notification_cooldowns[f"{a.entity_id}|{a.alert_type.value}"] = now
        self._last_notification_info = {"timestamp": now.isoformat(), "type": to_send[0].alert_type.value}

    async def _send_notification(self, alerts: list[AlertResult]) -> None:
        title = f"Behaviour Monitor: {len(alerts)} alert(s)"
        msg = "\n".join(f"- [{a.severity.value.upper()}] {a.explanation}" for a in alerts)
        await self.hass.services.async_call(
            "persistent_notification", "create",
            {"title": title, "message": msg, "notification_id": "behaviour_monitor"},
        )
        for svc in self._notify_services:
            parts = svc.split(".", 1)
            if len(parts) == 2:
                await self.hass.services.async_call(parts[0], parts[1], {"title": title, "message": msg})

    def _derive_welfare(self, alerts: list[AlertResult]) -> dict[str, Any]:
        if not alerts:
            return {"status": "ok", "reasons": [], "summary": "No active alerts", "recommendation": "", "entity_count_by_status": {}}
        # Exclude correlation breaks from welfare escalation (per D-03)
        welfare_alerts = [a for a in alerts if a.alert_type != AlertType.CORRELATION_BREAK]
        if not welfare_alerts:
            return {"status": "ok", "reasons": [], "summary": "No active alerts", "recommendation": "", "entity_count_by_status": {}}
        st, rec = derive_weighted_status(welfare_alerts, self._categories)
        cnt: dict[str, int] = {}
        for a in welfare_alerts:
            cnt[a.entity_id] = cnt.get(a.entity_id, 0) + 1
        return {"status": st, "reasons": [a.explanation for a in welfare_alerts],
                "summary": f"{len(welfare_alerts)} active alert(s): {st}", "recommendation": rec, "entity_count_by_status": cnt}

    def _build_sensor_data(self, alerts: list[AlertResult], now: datetime) -> dict[str, Any]:
        last_activity = max(self._last_seen.values()).isoformat() if self._last_seen else None
        conf = self._routine_model.overall_confidence(now) * 100.0
        ls = self._routine_model.learning_status(now)
        today, hrs = now.date(), now.hour + now.minute / 60.0
        rates = [r.daily_activity_rate(today) for eid in self._monitored_entities if (r := self._routine_model._entities.get(eid))]
        exp_full, exp_now = sum(rates), sum(int(r * hrs / 24.0) for r in rates)
        pct = min(100, int(self._today_count / exp_now * 100)) if exp_now else 0
        rstatus = "on_track" if self._today_count >= exp_now * 0.7 else "below_expected"
        tsec = typ_sec = concern = 0; ts_fmt = typ_fmt = "Unknown"; ctx_st = "unknown"
        if self._last_seen:
            most = max(self._last_seen.values())
            tsec = int((now - most).total_seconds())
            ts_fmt = f"{format_duration(tsec)} ago"
            best_r = self._routine_model._entities.get(max(self._last_seen, key=lambda e: self._last_seen[e]))
            if best_r and (gap := best_r.expected_gap_seconds(now.hour, now.weekday())):
                typ_sec = int(gap); typ_fmt = format_duration(typ_sec); concern = min(10, int(tsec / gap))
            ctx_st = "active" if tsec < 3600 else "inactive"
        obs_list = [er.first_observation for er in self._routine_model._entities.values() if er.first_observation]
        first_obs = min(obs_list) if obs_list else None
        days_el = max(0, int((now - fdt).total_seconds() / 86400)) if first_obs and (fdt := _parse_dt(first_obs)) else None
        complete = ls == "ready"
        days_rem = max(0, self._history_window_days - days_el) if days_el is not None else None
        stat_fmt = "Complete" if complete else (f"{days_rem} day(s) remaining" if days_rem is not None else "Learning...")
        return {
            "last_activity": last_activity, "activity_score": round(conf, 1), "anomaly_detected": bool(alerts),
            "anomalies": [a.to_dict() for a in alerts], "confidence": round(conf, 1), "daily_count": self._today_count,
            "welfare": self._derive_welfare(alerts),
            "routine": {"progress_percent": pct, "expected_by_now": exp_now, "actual_today": self._today_count,
                        "expected_full_day": exp_full, "status": rstatus,
                        "summary": f"{self._today_count} of ~{exp_full} expected activities"},
            "activity_context": {"time_since_formatted": ts_fmt, "time_since_seconds": tsec,
                                 "typical_interval_seconds": typ_sec, "typical_interval_formatted": typ_fmt,
                                 "concern_level": concern, "status": ctx_st, "context": ts_fmt},
            "entity_status": [
                {
                    "entity_id": e,
                    "status": "active" if e in self._last_seen else "unknown",
                    "last_seen": self._last_seen[e].isoformat() if e in self._last_seen else None,
                    "activity_tier": r.activity_tier.value if (r := self._routine_model._entities.get(e)) and r.activity_tier else None,
                    "category": self._categories.get(e, EntityCategory.OTHER).value,
                    "correlated_with": self._correlation_detector.get_correlated_entities(e),
                }
                for e in self._monitored_entities
            ],
            "stat_training": {"complete": complete, "formatted": stat_fmt, "days_remaining": days_rem,
                              "days_elapsed": days_el, "total_days": self._history_window_days, "first_observation": first_obs},
            "ml_status": {"enabled": False}, "cross_sensor_patterns": self._correlation_detector.get_correlation_groups(),
            "last_notification": self._last_notification_info, "holiday_mode": self._holiday_mode,
            "snooze_active": self.is_snoozed(), "snooze_until": self._snooze_until.isoformat() if self._snooze_until else None,
            "learning_status": ls, "baseline_confidence": round(conf, 1),
        }

    def _build_safe_defaults(self) -> dict[str, Any]:
        return {"last_activity": None, "activity_score": 0.0, "anomaly_detected": False, "anomalies": [],
                "confidence": 0.0, "daily_count": self._today_count, "entity_status": [],
                "welfare": {"status": "ok", "reasons": [], "summary": "No active alerts", "recommendation": "", "entity_count_by_status": {}},
                "routine": {"progress_percent": 0, "expected_by_now": 0, "actual_today": 0, "expected_full_day": 0, "status": "unknown", "summary": "Suppressed"},
                "activity_context": {"time_since_formatted": "Unknown", "time_since_seconds": None, "typical_interval_seconds": None, "typical_interval_formatted": "Unknown", "concern_level": 0, "status": "unknown", "context": ""},
                "stat_training": {"complete": False, "formatted": "Unknown", "days_remaining": None, "days_elapsed": None, "total_days": self._history_window_days, "first_observation": None},
                "ml_status": {"enabled": False}, "cross_sensor_patterns": [], "last_notification": self._last_notification_info,
                "holiday_mode": self._holiday_mode, "snooze_active": self.is_snoozed(), "snooze_until": self._snooze_until.isoformat() if self._snooze_until else None,
                "learning_status": "inactive", "baseline_confidence": 0.0}

    async def _save_fire_refresh(self, event: str, data: dict | None = None) -> None:
        await self._save_data(); self.hass.bus.async_fire(event, data or {}); await self.async_request_refresh()

    async def async_enable_holiday_mode(self) -> None:
        self._holiday_mode = True; await self._save_fire_refresh(f"{DOMAIN}_holiday_mode_enabled")

    async def async_disable_holiday_mode(self) -> None:
        self._holiday_mode = False; await self._save_fire_refresh(f"{DOMAIN}_holiday_mode_disabled")

    def get_snooze_duration_key(self) -> str:
        if not self.is_snoozed(): return SNOOZE_OFF
        rem = (self._snooze_until - dt_util.now()).total_seconds()
        return min((k for k in SNOOZE_DURATIONS if k != SNOOZE_OFF), key=lambda k: abs(rem - SNOOZE_DURATIONS[k]), default=SNOOZE_OFF)

    async def async_snooze(self, duration_key: str) -> None:
        secs = SNOOZE_DURATIONS.get(duration_key, 0)
        self._snooze_until = dt_util.now() + timedelta(seconds=secs) if secs > 0 else None
        await self._save_fire_refresh(f"{DOMAIN}_snooze_set")

    async def async_clear_snooze(self) -> None:
        self._snooze_until = None
        await self._save_fire_refresh(f"{DOMAIN}_snooze_cleared")

    async def async_routine_reset(self, entity_id: str) -> None:
        self._drift_detector.reset_entity(entity_id)
        _LOGGER.warning("Routine reset for %s — CUSUM cleared", entity_id)
        await self._save_fire_refresh(f"{DOMAIN}_routine_reset", {"entity_id": entity_id})

    async def _bootstrap_from_recorder(self, entity_ids: list[str] | None = None) -> None:
        """Replay recorder history into the routine model, debouncing motion entities.

        Uses a private MotionDebouncer so replay never disturbs live debounce state.
        A skipped unavailable/unknown state resets the edge-detection ``prev`` value,
        matching live handling: on -> unavailable -> on is a rising edge.
        """
        if recorder_get_instance is None or recorder_state_changes_during_period is None:
            _LOGGER.warning("Behaviour Monitor: recorder unavailable, skipping bootstrap")
            return
        targets = list(entity_ids) if entity_ids is not None else list(self._monitored_entities)
        debouncer = MotionDebouncer(self._motion_debounce_seconds)
        try:
            instance = recorder_get_instance(self.hass)
            if instance is None:
                return
            end, start = dt_util.now(), dt_util.now() - timedelta(days=self._history_window_days)
            for eid in targets:
                if self._categories.get(eid) is EntityCategory.PANIC:
                    continue
                is_motion = self._categories.get(eid) is EntityCategory.MOTION
                prev: str | None = None
                try:
                    for sl in (await instance.async_add_executor_job(
                        recorder_state_changes_during_period, self.hass, start, end, [eid], False,
                    )).values():
                        for s in sl:
                            if s.state in ("unavailable", "unknown"):
                                prev = None
                                continue
                            sv = str(s.state)
                            if debouncer.should_count(eid, is_motion, prev, sv, s.last_changed):
                                self._routine_model.record(eid, s.last_changed, sv, is_binary_state(sv))
                            prev = sv
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Could not load recorder history for %s", eid)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Behaviour Monitor: recorder bootstrap failed", exc_info=True)

    async def _rebootstrap_motion_entities(self) -> None:
        """One-shot after the v11 migration: rebuild motion routines with debounce.

        Drops the learned routine and correlation counts for every motion-category
        entity, replays recorder history for those entities, saves, then clears
        the rebootstrap_motion flag on the config entry. CUSUM drift state and
        last_seen are kept.
        """
        motion = [e for e in self._monitored_entities if self._categories.get(e) is EntityCategory.MOTION]
        for eid in motion:
            self._routine_model._entities.pop(eid, None)
            self._correlation_detector.remove_entity(eid)
        if motion:
            await self._bootstrap_from_recorder(entity_ids=motion)
            _LOGGER.info("Behaviour Monitor: re-bootstrapped %d motion entities with debounce", len(motion))
        await self._save_data()
        new_data = {k: v for k, v in self._entry.data.items() if k != CONF_REBOOTSTRAP_MOTION}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
