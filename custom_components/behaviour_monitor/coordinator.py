"""Data update coordinator for Behaviour Monitor — v1.1 rebuild."""
# Wires RoutineModel, AcuteDetector, DriftDetector into DataUpdateCoordinator.
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .acute_detector import AcuteDetector
from .alert_result import AlertResult, AlertSeverity, AlertType
from .const import (
    CONF_DRIFT_SENSITIVITY, CONF_ENABLE_NOTIFICATIONS, CONF_HISTORY_WINDOW_DAYS,
    CONF_INACTIVITY_MULTIPLIER, CONF_MIN_NOTIFICATION_SEVERITY, CONF_MONITORED_ENTITIES,
    CONF_NOTIFICATION_COOLDOWN, CONF_NOTIFY_SERVICES,
    DEFAULT_ENABLE_NOTIFICATIONS, DEFAULT_HISTORY_WINDOW_DAYS, DEFAULT_INACTIVITY_MULTIPLIER,
    DEFAULT_MIN_NOTIFICATION_SEVERITY, DEFAULT_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFY_SERVICES,
    DOMAIN, SENSITIVITY_MEDIUM, SNOOZE_DURATIONS, SNOOZE_OFF, STORAGE_KEY, STORAGE_VERSION,
    UPDATE_INTERVAL, WELFARE_DEBOUNCE_CYCLES,
)
from .drift_detector import CUSUMState, DriftDetector
from .routine_model import RoutineModel, is_binary_state

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
        self._routine_model = RoutineModel(self._history_window_days)
        self._acute_detector = AcuteDetector(float(d.get(CONF_INACTIVITY_MULTIPLIER, DEFAULT_INACTIVITY_MULTIPLIER)))
        self._drift_detector = DriftDetector(d.get(CONF_DRIFT_SENSITIVITY, SENSITIVITY_MEDIUM))
        self._last_seen: dict[str, datetime] = {}
        self._notification_cooldowns: dict[str, datetime] = {}
        self._holiday_mode = False
        self._snooze_until: datetime | None = None
        self._today_count = 0
        self._today_date: date | None = None
        self._last_notification_info: dict[str, Any] = {"timestamp": None, "type": None}
        self._welfare_debounce: dict[str, int] = {}
        self._current_welfare_status = "ok"
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self._unsub_state_changed: Any = None
        # Shim: sensor.py accesses coord.analyzer.is_learning_complete() — removed in Plan 03
        self.analyzer = type("_S", (), {"is_learning_complete": lambda s, rm=self._routine_model: rm.learning_status() == "ready"})()

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

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored:
            if "routine_model" in stored:
                self._routine_model = RoutineModel.from_dict(stored["routine_model"])
            for eid, sd in stored.get("cusum_states", {}).items():
                self._drift_detector._states[eid] = CUSUMState.from_dict(sd)
            c = stored.get("coordinator", {})
            self._holiday_mode = c.get("holiday_mode", False)
            if (sn := c.get("snooze_until")) and (sdt := _parse_dt(sn)):
                now = dt_util.now()
                now = now.replace(tzinfo=sdt.tzinfo) if now.tzinfo is None and sdt.tzinfo is not None else now
                self._snooze_until = sdt if sdt > now else None
            self._last_seen = {e: dt for e, ts in c.get("last_seen", {}).items() if (dt := _parse_dt(ts))}
            self._last_notification_info = c.get("last_notification_info", {"timestamp": None, "type": None})
            self._notification_cooldowns = {k: dt for k, ts in c.get("notification_cooldowns", {}).items() if (dt := _parse_dt(ts))}
        elif not self._routine_model._entities:
            await self._bootstrap_from_recorder()
        self._unsub_state_changed = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed)

    async def async_shutdown(self) -> None:
        if self._unsub_state_changed:
            self._unsub_state_changed()
        await self._save_data()

    async def _save_data(self) -> None:
        await self._store.async_save({
            "routine_model": self._routine_model.to_dict(),
            "cusum_states": {e: s.to_dict() for e, s in self._drift_detector._states.items()},
            "coordinator": {
                "holiday_mode": self._holiday_mode,
                "snooze_until": self._snooze_until.isoformat() if self._snooze_until else None,
                "last_seen": {e: dt.isoformat() for e, dt in self._last_seen.items()},
                "last_notification_info": self._last_notification_info,
                "notification_cooldowns": {k: v.isoformat() for k, v in self._notification_cooldowns.items()},
            },
        })

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        eid: str = event.data.get("entity_id", "")
        if eid not in self._monitored_entities:
            return
        ns = event.data.get("new_state")
        if ns is None:
            return
        now, sv = dt_util.now(), str(ns.state)
        self._routine_model.record(entity_id=eid, timestamp=now, state_value=sv, is_binary=is_binary_state(sv))
        self._last_seen[eid] = now
        if self._today_date != now.date():
            self._today_count, self._today_date = 0, now.date()
        self._today_count += 1
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()
        if self._today_date != now.date():
            self._today_count = 0
            self._today_date = now.date()
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
        return alerts

    async def _handle_alerts(self, alerts: list[AlertResult], now: datetime) -> None:
        if not self._enable_notifications or not alerts:
            return
        gate = _SEV_GATE.get(self._min_notification_severity, AlertSeverity.MEDIUM)
        def _ok(a: AlertResult) -> bool:
            last = self._notification_cooldowns.get(f"{a.entity_id}|{a.alert_type.value}")
            cd_ok = last is None or (now - last).total_seconds() / 60 >= self._notification_cooldown
            sev_ok = _SEV_ORDER.index(a.severity) >= _SEV_ORDER.index(gate)
            return cd_ok and sev_ok
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
        sevs = [a.severity for a in alerts]
        if AlertSeverity.HIGH in sevs:
            st, rec = "alert", "Immediate welfare check recommended."
        elif AlertSeverity.MEDIUM in sevs:
            st, rec = "concern", "Schedule a welfare check soon."
        else:
            st, rec = "check_recommended", "Monitor closely."
        cnt: dict[str, int] = {}
        for a in alerts:
            cnt[a.entity_id] = cnt.get(a.entity_id, 0) + 1
        return {"status": st, "reasons": [a.explanation for a in alerts],
                "summary": f"{len(alerts)} active alert(s): {st}", "recommendation": rec, "entity_count_by_status": cnt}

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
            h, m = tsec // 3600, (tsec % 3600) // 60
            ts_fmt = f"{h}h {m}m ago" if h else f"{m}m ago"
            best_r = self._routine_model._entities.get(max(self._last_seen, key=lambda e: self._last_seen[e]))
            if best_r and (gap := best_r.expected_gap_seconds(now.hour, now.weekday())):
                typ_sec = int(gap); gh, gm = typ_sec // 3600, (typ_sec % 3600) // 60
                typ_fmt = f"{gh}h {gm}m" if gh else f"{gm}m"; concern = min(10, int(tsec / gap))
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
            "entity_status": [{"entity_id": e, "status": "active" if e in self._last_seen else "unknown",
                                "last_seen": self._last_seen[e].isoformat() if e in self._last_seen else None}
                               for e in self._monitored_entities],
            "stat_training": {"complete": complete, "formatted": stat_fmt, "days_remaining": days_rem,
                              "days_elapsed": days_el, "total_days": self._history_window_days, "first_observation": first_obs},
            "ml_status": {"enabled": False}, "cross_sensor_patterns": [],
            "last_notification": self._last_notification_info, "holiday_mode": self._holiday_mode,
            "snooze_active": self.is_snoozed(), "snooze_until": self._snooze_until.isoformat() if self._snooze_until else None,
            "ml_status_stub": "Removed in v1.1", "ml_training_stub": "N/A", "cross_sensor_stub": 0,
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
                "ml_status_stub": "Removed in v1.1", "ml_training_stub": "N/A", "cross_sensor_stub": 0, "learning_status": "inactive", "baseline_confidence": 0.0}

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

    async def _bootstrap_from_recorder(self) -> None:
        if recorder_get_instance is None or recorder_state_changes_during_period is None:
            _LOGGER.warning("Behaviour Monitor: recorder unavailable, skipping bootstrap")
            return
        try:
            instance = recorder_get_instance(self.hass)
            if instance is None:
                return
            end, start = dt_util.now(), dt_util.now() - timedelta(days=self._history_window_days)
            for eid in self._monitored_entities:
                try:
                    for sl in (await instance.async_add_executor_job(
                        recorder_state_changes_during_period, self.hass, start, end, [eid], False,
                    )).values():
                        for s in sl:
                            if s.state not in ("unavailable", "unknown"):
                                self._routine_model.record(eid, s.last_changed, s.state, is_binary_state(s.state))
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Could not load recorder history for %s", eid)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Behaviour Monitor: recorder bootstrap failed", exc_info=True)
