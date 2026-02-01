"""Data update coordinator for Behaviour Monitor."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .analyzer import AnomalyResult, PatternAnalyzer
from .const import (
    CONF_CROSS_SENSOR_WINDOW,
    CONF_ENABLE_ML,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_LEARNING_PERIOD,
    CONF_ML_LEARNING_PERIOD,
    CONF_MONITORED_ENTITIES,
    CONF_NOTIFY_SERVICES,
    CONF_RETRAIN_PERIOD,
    CONF_SENSITIVITY,
    CONF_TRACK_ATTRIBUTES,
    DEFAULT_CROSS_SENSOR_WINDOW,
    DEFAULT_ENABLE_ML,
    DEFAULT_ENABLE_NOTIFICATIONS,
    DEFAULT_LEARNING_PERIOD,
    DEFAULT_ML_LEARNING_PERIOD,
    DEFAULT_NOTIFY_SERVICES,
    DEFAULT_RETRAIN_PERIOD,
    DEFAULT_SENSITIVITY,
    DEFAULT_TRACK_ATTRIBUTES,
    DOMAIN,
    ML_CONTAMINATION,
    SENSITIVITY_THRESHOLDS,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .ml_analyzer import ML_AVAILABLE, MLAnomalyResult, MLPatternAnalyzer, StateChangeEvent

_LOGGER = logging.getLogger(__name__)


class BehaviourMonitorCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for managing behaviour pattern data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

        self._entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self._ml_store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_ml.{entry.entry_id}")
        self._unsubscribe_state_changed: callable | None = None
        self._recent_anomalies: list[AnomalyResult] = []
        self._recent_ml_anomalies: list[MLAnomalyResult] = []
        self._recent_events: list[StateChangeEvent] = []
        self._last_welfare_status: str | None = None
        self._last_notification_time: datetime | None = None
        self._last_notification_type: str | None = None
        self._holiday_mode: bool = False
        self._snooze_until: datetime | None = None

        # Get configuration
        sensitivity_key = entry.data.get(CONF_SENSITIVITY, DEFAULT_SENSITIVITY)
        sensitivity_threshold = SENSITIVITY_THRESHOLDS.get(sensitivity_key, 2.0)
        learning_period = int(entry.data.get(CONF_LEARNING_PERIOD, DEFAULT_LEARNING_PERIOD))

        self._analyzer = PatternAnalyzer(
            sensitivity_threshold=sensitivity_threshold,
            learning_period_days=learning_period,
        )

        # ML configuration - only enable if dependencies are available
        ml_requested = entry.data.get(CONF_ENABLE_ML, DEFAULT_ENABLE_ML)
        self._enable_ml = ml_requested and ML_AVAILABLE

        # Log ML status clearly
        if self._enable_ml:
            _LOGGER.info(
                "Behaviour Monitor: ML features ENABLED (River library available)"
            )
        elif ml_requested and not ML_AVAILABLE:
            _LOGGER.warning(
                "Behaviour Monitor: ML features DISABLED - River library not installed. "
                "Statistical analysis will still work. "
                "To enable ML, install: pip install river"
            )
        else:
            _LOGGER.info(
                "Behaviour Monitor: ML features DISABLED (not requested in config)"
            )

        self._retrain_period_days = int(entry.data.get(CONF_RETRAIN_PERIOD, DEFAULT_RETRAIN_PERIOD))
        self._ml_learning_period_days = int(entry.data.get(CONF_ML_LEARNING_PERIOD, DEFAULT_ML_LEARNING_PERIOD))
        self._cross_sensor_window = int(entry.data.get(CONF_CROSS_SENSOR_WINDOW, DEFAULT_CROSS_SENSOR_WINDOW))

        ml_contamination = ML_CONTAMINATION.get(sensitivity_key, 0.05)
        self._ml_analyzer = MLPatternAnalyzer(
            contamination=ml_contamination,
            cross_sensor_window_seconds=self._cross_sensor_window,
        )

        self._monitored_entities: set[str] = set(
            entry.data.get(CONF_MONITORED_ENTITIES, [])
        )
        self._enable_notifications = entry.data.get(
            CONF_ENABLE_NOTIFICATIONS, DEFAULT_ENABLE_NOTIFICATIONS
        )
        self._track_attributes = entry.data.get(
            CONF_TRACK_ATTRIBUTES, DEFAULT_TRACK_ATTRIBUTES
        )
        self._notify_services: list[str] = entry.data.get(
            CONF_NOTIFY_SERVICES, DEFAULT_NOTIFY_SERVICES
        )

    @property
    def analyzer(self) -> PatternAnalyzer:
        """Get the statistical pattern analyzer."""
        return self._analyzer

    @property
    def ml_analyzer(self) -> MLPatternAnalyzer:
        """Get the ML pattern analyzer."""
        return self._ml_analyzer

    @property
    def monitored_entities(self) -> set[str]:
        """Get the set of monitored entities."""
        return self._monitored_entities

    @property
    def recent_anomalies(self) -> list[AnomalyResult]:
        """Get recent statistical anomalies."""
        return self._recent_anomalies

    @property
    def recent_ml_anomalies(self) -> list[MLAnomalyResult]:
        """Get recent ML anomalies."""
        return self._recent_ml_anomalies

    @property
    def ml_enabled(self) -> bool:
        """Check if ML is enabled."""
        return self._enable_ml

    @property
    def holiday_mode(self) -> bool:
        """Check if holiday mode is enabled."""
        return self._holiday_mode

    @property
    def snooze_until(self) -> datetime | None:
        """Get the snooze until timestamp."""
        return self._snooze_until

    def is_snoozed(self) -> bool:
        """Check if currently snoozed."""
        if self._snooze_until is None:
            return False
        return dt_util.now() < self._snooze_until

    def get_snooze_duration_key(self) -> str:
        """Get the current snooze duration key."""
        from .const import SNOOZE_DURATIONS, SNOOZE_OFF

        if not self.is_snoozed():
            return SNOOZE_OFF

        # Calculate remaining time
        remaining = (self._snooze_until - dt_util.now()).total_seconds()

        # Find closest duration key
        closest_key = SNOOZE_OFF
        min_diff = float("inf")

        for key, duration in SNOOZE_DURATIONS.items():
            if key == SNOOZE_OFF:
                continue
            diff = abs(remaining - duration)
            if diff < min_diff:
                min_diff = diff
                closest_key = key

        return closest_key

    async def async_setup(self) -> None:
        """Set up the coordinator."""
        # Load stored statistical data
        stored_data = await self._store.async_load()
        if stored_data:
            # Handle both old format (direct analyzer dict) and new format (with coordinator state)
            if "analyzer" in stored_data:
                # New format with coordinator state
                analyzer_data = stored_data["analyzer"]
                coordinator_state = stored_data.get("coordinator", {})

                # Restore coordinator state
                last_notif_time = coordinator_state.get("last_notification_time")
                if last_notif_time:
                    dt = datetime.fromisoformat(last_notif_time)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                    self._last_notification_time = dt

                self._last_notification_type = coordinator_state.get("last_notification_type")
                self._last_welfare_status = coordinator_state.get("last_welfare_status")

                # Restore holiday mode
                self._holiday_mode = coordinator_state.get("holiday_mode", False)

                # Restore snooze (check if not expired)
                snooze_until_str = coordinator_state.get("snooze_until")
                if snooze_until_str:
                    snooze_dt = datetime.fromisoformat(snooze_until_str)
                    if snooze_dt.tzinfo is None:
                        snooze_dt = snooze_dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                    # Only restore if not expired
                    if snooze_dt > dt_util.now():
                        self._snooze_until = snooze_dt
                    else:
                        self._snooze_until = None
                        _LOGGER.debug("Snooze expired, not restoring")

                _LOGGER.debug(
                    "Loaded coordinator state: last_notification=%s, last_welfare=%s, holiday_mode=%s, snoozed=%s",
                    self._last_notification_time,
                    self._last_welfare_status,
                    self._holiday_mode,
                    self.is_snoozed(),
                )
            else:
                # Old format - stored_data is the analyzer dict directly
                analyzer_data = stored_data
                _LOGGER.debug("Loaded data in old format (analyzer only)")

            self._analyzer = PatternAnalyzer.from_dict(
                analyzer_data,
                sensitivity_threshold=SENSITIVITY_THRESHOLDS.get(
                    self._entry.data.get(CONF_SENSITIVITY, DEFAULT_SENSITIVITY), 2.0
                ),
                learning_period_days=int(
                    self._entry.data.get(CONF_LEARNING_PERIOD, DEFAULT_LEARNING_PERIOD)
                ),
            )
            _LOGGER.debug(
                "Loaded stored pattern data with %d entities",
                len(self._analyzer.patterns),
            )

        # Load stored ML data
        if self._enable_ml:
            ml_stored_data = await self._ml_store.async_load()
            if ml_stored_data:
                sensitivity_key = self._entry.data.get(CONF_SENSITIVITY, DEFAULT_SENSITIVITY)
                self._ml_analyzer = MLPatternAnalyzer.from_dict(
                    ml_stored_data,
                    contamination=ML_CONTAMINATION.get(sensitivity_key, 0.05),
                    cross_sensor_window_seconds=self._cross_sensor_window,
                )
                _LOGGER.debug(
                    "Loaded ML data with %d events, trained: %s",
                    self._ml_analyzer.sample_count,
                    self._ml_analyzer.is_trained,
                )

                # Retrain if needed
                await self._check_retrain()

        # Subscribe to state changes
        self._unsubscribe_state_changed = self.hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._handle_state_changed
        )

        # Log startup summary
        _LOGGER.info(
            "Behaviour Monitor started: "
            "monitoring %d entities, "
            "ML=%s, "
            "sensitivity=%s, "
            "learning_period=%d days, "
            "notifications=%s, "
            "track_attributes=%s",
            len(self._monitored_entities),
            "ENABLED" if self._enable_ml else "DISABLED",
            self._entry.data.get(CONF_SENSITIVITY, DEFAULT_SENSITIVITY),
            int(self._entry.data.get(CONF_LEARNING_PERIOD, DEFAULT_LEARNING_PERIOD)),
            "ON" if self._enable_notifications else "OFF",
            "ON" if self._track_attributes else "OFF",
        )
        if self._monitored_entities:
            _LOGGER.info("Monitored entities: %s", ", ".join(sorted(self._monitored_entities)))

    async def async_shutdown(self) -> None:
        """Shut down the coordinator."""
        if self._unsubscribe_state_changed:
            self._unsubscribe_state_changed()
            self._unsubscribe_state_changed = None

        # Save data
        await self._save_data()

    async def _save_data(self) -> None:
        """Save pattern data to storage."""
        # Save both analyzer and coordinator state
        storage_data = {
            "analyzer": self._analyzer.to_dict(),
            "coordinator": {
                "last_notification_time": (
                    self._last_notification_time.isoformat()
                    if self._last_notification_time
                    else None
                ),
                "last_notification_type": self._last_notification_type,
                "last_welfare_status": self._last_welfare_status,
                "holiday_mode": self._holiday_mode,
                "snooze_until": (
                    self._snooze_until.isoformat()
                    if self._snooze_until
                    else None
                ),
            },
        }
        await self._store.async_save(storage_data)

        if self._enable_ml:
            await self._ml_store.async_save(self._ml_analyzer.to_dict())

    async def _check_retrain(self) -> None:
        """Check if ML model needs retraining."""
        if not self._enable_ml:
            return

        last_trained = self._ml_analyzer.last_trained
        if last_trained is None:
            # Never trained, try to train
            if self._ml_analyzer.sample_count >= 100:
                _LOGGER.info("Training ML model for the first time")
                self._ml_analyzer.train()
            return

        # Check if retrain period has passed
        retrain_delta = timedelta(days=self._retrain_period_days)
        if dt_util.now() - last_trained > retrain_delta:
            _LOGGER.info(
                "Retraining ML model (last trained: %s, period: %d days)",
                last_trained.isoformat(),
                self._retrain_period_days,
            )
            # Prune old events before retraining
            self._ml_analyzer.prune_old_events(max_age_days=self._retrain_period_days * 2)
            self._ml_analyzer.train()

    async def async_enable_holiday_mode(self) -> None:
        """Enable holiday mode - stops all tracking and learning."""
        self._holiday_mode = True
        await self._save_data()
        _LOGGER.info("Holiday mode enabled - all tracking paused")

    async def async_disable_holiday_mode(self) -> None:
        """Disable holiday mode - resumes normal operation."""
        self._holiday_mode = False
        await self._save_data()
        _LOGGER.info("Holiday mode disabled - tracking resumed")

    async def async_snooze(self, duration_key: str) -> None:
        """Snooze notifications for a specified duration."""
        from .const import SNOOZE_DURATIONS, SNOOZE_LABELS

        duration_seconds = SNOOZE_DURATIONS.get(duration_key, 0)
        if duration_seconds == 0:
            await self.async_clear_snooze()
            return

        self._snooze_until = dt_util.now() + timedelta(seconds=duration_seconds)
        await self._save_data()
        _LOGGER.info(
            "Notifications snoozed for %s until %s",
            SNOOZE_LABELS.get(duration_key, duration_key),
            self._snooze_until.isoformat(),
        )

    async def async_clear_snooze(self) -> None:
        """Clear snooze - resume normal notifications."""
        self._snooze_until = None
        await self._save_data()
        _LOGGER.info("Snooze cleared - notifications resumed")

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        """Handle state change events."""
        # Check if holiday mode is enabled - if so, ignore all state changes
        if self._holiday_mode:
            return

        entity_id = event.data.get("entity_id")

        # Debug: log all state changes to help diagnose issues
        _LOGGER.debug(
            "State change event received: entity=%s, monitored=%s, snoozed=%s",
            entity_id,
            entity_id in self._monitored_entities,
            self.is_snoozed(),
        )

        if entity_id not in self._monitored_entities:
            return

        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        # Only record if the state actually changed (not just attributes)
        if old_state is None or new_state is None:
            _LOGGER.debug(
                "Ignoring %s: old_state=%s, new_state=%s (None state)",
                entity_id,
                old_state,
                new_state,
            )
            return
        if old_state.state == new_state.state:
            if not self._track_attributes:
                _LOGGER.debug(
                    "Ignoring %s: state unchanged (%s -> %s, only attributes changed)",
                    entity_id,
                    old_state.state,
                    new_state.state,
                )
                return
            # Track attribute changes - check if attributes actually changed
            if old_state.attributes == new_state.attributes:
                _LOGGER.debug(
                    "Ignoring %s: no changes (state and attributes identical)",
                    entity_id,
                )
                return
            _LOGGER.debug(
                "Tracking attribute change for %s (state=%s, attributes changed)",
                entity_id,
                new_state.state,
            )

        timestamp = dt_util.now()

        # Check if snoozed
        is_snoozed = self.is_snoozed()

        # During snooze: only track events (for ML history), don't update patterns
        if not is_snoozed:
            # Record in statistical analyzer (updates patterns)
            self._analyzer.record_state_change(entity_id, timestamp)

        # Always record ML events (even when snoozed) to maintain history
        # But don't train the model during snooze
        if self._enable_ml:
            # Track the event but don't call record_event (which trains the model)
            # Instead, just add to recent events
            ml_event = StateChangeEvent(
                entity_id=entity_id,
                timestamp=timestamp,
                old_state=old_state.state,
                new_state=new_state.state,
            )
            self._recent_events.append(ml_event)

            # Keep only recent events
            cutoff = timestamp - timedelta(seconds=self._cross_sensor_window * 2)
            self._recent_events = [e for e in self._recent_events if e.timestamp >= cutoff]

            # Only record in ML analyzer (which updates patterns) if not snoozed
            if not is_snoozed:
                self._ml_analyzer.record_event(
                    entity_id=entity_id,
                    timestamp=timestamp,
                    old_state=old_state.state,
                    new_state=new_state.state,
                )

        snooze_status = " [SNOOZED - patterns not updated]" if is_snoozed else ""
        _LOGGER.info(
            "Behaviour Monitor: Recorded state change for %s: %s -> %s (daily total: %d)%s",
            entity_id,
            old_state.state,
            new_state.state,
            self._analyzer.get_total_daily_count(),
            snooze_status,
        )

        # Trigger an update to refresh sensors
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data and check for anomalies."""
        # Skip anomaly detection if holiday mode or snoozed
        skip_anomaly_detection = self._holiday_mode or self.is_snoozed()

        # Check for statistical anomalies (unless skipped)
        stat_anomalies = [] if skip_anomaly_detection else self._analyzer.check_for_anomalies()

        if stat_anomalies:
            self._recent_anomalies = stat_anomalies

        # Check for ML anomalies (unless skipped)
        ml_anomalies: list[MLAnomalyResult] = []

        if self._enable_ml and not skip_anomaly_detection:
            # Check if we need to retrain
            await self._check_retrain()

            if self._ml_analyzer.is_trained:
                # Check recent events for ML anomalies
                for event in self._recent_events[-10:]:  # Check last 10 events
                    ml_result = self._ml_analyzer.check_anomaly(event)
                    if ml_result:
                        ml_anomalies.append(ml_result)

                # Check for cross-sensor anomalies
                cross_anomalies = self._ml_analyzer.check_cross_sensor_anomalies(
                    self._recent_events
                )
                ml_anomalies.extend(cross_anomalies)

            if ml_anomalies:
                self._recent_ml_anomalies = ml_anomalies

        # Combine anomalies for notifications
        all_anomalies_detected = len(stat_anomalies) > 0 or len(ml_anomalies) > 0

        # Send notifications only after respective learning periods complete
        # Skip notifications if holiday mode or snoozed
        if self._enable_notifications and not skip_anomaly_detection:
            # Determine if any learning is complete
            stat_learning_complete = self._analyzer.is_learning_complete()

            # ML learning requires both sample count AND time elapsed
            ml_learning_complete = False
            if self._enable_ml and self._ml_analyzer.is_trained:
                first_event = self._ml_analyzer.first_event_time
                if first_event is not None:
                    ml_learning_elapsed = dt_util.now() - first_event
                    ml_learning_complete = ml_learning_elapsed >= timedelta(
                        days=self._ml_learning_period_days
                    )

            # Statistical anomaly notifications require statistical learning complete
            if stat_learning_complete and stat_anomalies:
                await self._send_notification(stat_anomalies)

            # ML anomaly notifications require ML trained AND learning period elapsed
            if ml_learning_complete and ml_anomalies:
                await self._send_ml_notification(ml_anomalies)

            # Welfare notifications sent when either learning method is ready
            if stat_learning_complete or ml_learning_complete:
                welfare_status = self._analyzer.get_welfare_status()
                current_welfare = welfare_status.get("status", "ok")
                if current_welfare != self._last_welfare_status:
                    await self._send_welfare_notification(welfare_status)
                    self._last_welfare_status = current_welfare

        # Periodically save data
        await self._save_data()

        # Build data for sensors
        last_activity = self._analyzer.get_last_activity_time()

        # Get cross-sensor patterns
        cross_patterns = []
        if self._enable_ml:
            cross_patterns = self._ml_analyzer.get_strong_patterns(min_strength=0.3)

        # Get elder care data
        welfare_status = self._analyzer.get_welfare_status()
        routine_progress = self._analyzer.get_routine_progress()
        activity_context = self._analyzer.get_time_since_activity_context()
        entity_status = self._analyzer.get_entity_status()

        return {
            "last_activity": last_activity.isoformat() if last_activity else None,
            "activity_score": self._analyzer.calculate_activity_score(),
            "anomaly_detected": all_anomalies_detected,
            "confidence": self._analyzer.get_confidence(),
            "daily_count": self._analyzer.get_total_daily_count(),
            "anomalies": [
                {
                    "entity_id": a.entity_id,
                    "type": a.anomaly_type,
                    "description": a.description,
                    "severity": a.severity,
                    "z_score": round(a.z_score, 2),
                    "source": "statistical",
                }
                for a in stat_anomalies
            ] + [
                {
                    "entity_id": a.entity_id or "cross-sensor",
                    "type": a.anomaly_type,
                    "description": a.description,
                    "source": "ml",
                }
                for a in ml_anomalies
            ],
            "ml_status": {
                "enabled": self._enable_ml,
                "trained": self._ml_analyzer.is_trained if self._enable_ml else False,
                "sample_count": self._ml_analyzer.sample_count if self._enable_ml else 0,
                "last_trained": (
                    self._ml_analyzer.last_trained.isoformat()
                    if self._enable_ml and self._ml_analyzer.last_trained
                    else None
                ),
                "next_retrain": (
                    (self._ml_analyzer.last_trained + timedelta(days=self._retrain_period_days)).isoformat()
                    if self._enable_ml and self._ml_analyzer.last_trained
                    else None
                ),
            },
            "cross_sensor_patterns": cross_patterns,
            # Training time remaining
            "stat_training": self._analyzer.get_training_time_remaining(),
            "ml_training": (
                self._ml_analyzer.get_training_time_remaining(self._ml_learning_period_days)
                if self._enable_ml
                else {"complete": False, "formatted": "ML disabled", "status": "ML disabled"}
            ),
            # Elder care data
            "welfare": welfare_status,
            "routine": routine_progress,
            "activity_context": activity_context,
            "entity_status": entity_status,
            # Notification tracking
            "last_notification": {
                "timestamp": (
                    self._last_notification_time.isoformat()
                    if self._last_notification_time
                    else None
                ),
                "type": self._last_notification_type,
            },
            # Holiday mode and snooze status
            "holiday_mode": self._holiday_mode,
            "snooze_active": self.is_snoozed(),
            "snooze_until": (
                self._snooze_until.isoformat()
                if self._snooze_until
                else None
            ),
        }

    async def _send_notification(self, anomalies: list[AnomalyResult]) -> None:
        """Send a persistent notification for statistical anomalies."""
        if not anomalies:
            return

        notification_id = f"{DOMAIN}_statistical_anomaly"

        # Find highest severity
        severity_order = ["critical", "significant", "moderate", "minor", "normal"]
        highest_severity = "normal"
        for anomaly in anomalies:
            if severity_order.index(anomaly.severity) < severity_order.index(highest_severity):
                highest_severity = anomaly.severity

        severity_emoji = {
            "critical": "🚨",
            "significant": "⚠️",
            "moderate": "⚡",
            "minor": "ℹ️",
            "normal": "",
        }.get(highest_severity, "")

        title = f"{severity_emoji} Behaviour Monitor Alert ({len(anomalies)} sensor{'s' if len(anomalies) > 1 else ''})"

        # Build list of triggered sensors
        triggered_lines = []
        for anomaly in anomalies:
            emoji = {
                "critical": "🚨",
                "significant": "⚠️",
                "moderate": "⚡",
                "minor": "ℹ️",
            }.get(anomaly.severity, "")
            triggered_lines.append(
                f"- {emoji} `{anomaly.entity_id}` - {anomaly.severity} "
                f"(Z: {anomaly.z_score:.1f}, {anomaly.anomaly_type})"
            )

        sensors_text = "\n".join(triggered_lines)

        # Use first anomaly for time reference
        first_anomaly = anomalies[0]

        message = (
            f"**Triggered Sensors:**\n{sensors_text}\n\n"
            f"**Highest Severity:** {highest_severity.upper()}\n\n"
            f"**Time Slot:** {first_anomaly.time_slot}\n\n"
            f"**Detection:** Statistical (Z-score)\n\n"
            f"**Threshold:** {self._analyzer._sensitivity_threshold:.1f}σ\n\n"
            f"**Time:** {first_anomaly.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": title,
                "message": message,
                "notification_id": notification_id,
            },
        )

        # Track notification time
        self._last_notification_time = dt_util.now()
        self._last_notification_type = "statistical"

        _LOGGER.info(
            "Sent notification for %d anomalies (highest severity: %s)",
            len(anomalies),
            highest_severity
        )

        # Also send to mobile device if configured
        await self._send_mobile_notification(
            title=title,
            message=message,
            data={
                "push": {
                    "sound": "default" if highest_severity in ["critical", "significant"] else None,
                    "badge": len(anomalies),
                    "interruption-level": "time-sensitive" if highest_severity == "critical" else "active",
                },
                "group": f"{DOMAIN}_statistical",
            },
        )

    async def _send_ml_notification(self, anomalies: list[MLAnomalyResult]) -> None:
        """Send a persistent notification for ML-detected anomalies."""
        if not anomalies:
            return

        notification_id = f"{DOMAIN}_ml_anomaly"

        title = f"Behaviour Monitor ML Alert ({len(anomalies)} pattern{'s' if len(anomalies) > 1 else ''})"

        # Build list of triggered sensors/patterns
        triggered_lines = []
        all_related = set()

        for anomaly in anomalies:
            entity_name = anomaly.entity_id or "Cross-sensor"
            triggered_lines.append(
                f"- `{entity_name}` - {anomaly.anomaly_type} "
                f"(score: {anomaly.anomaly_score:.2f})"
            )
            if anomaly.related_entities:
                all_related.update(anomaly.related_entities)

        sensors_text = "\n".join(triggered_lines)

        related_text = ""
        if all_related:
            related_text = f"**Related Entities:** {', '.join(sorted(all_related))}\n\n"

        # Use first anomaly for time reference
        first_anomaly = anomalies[0]

        message = (
            f"**Triggered Patterns:**\n{sensors_text}\n\n"
            f"{related_text}"
            f"**Detection:** Machine Learning (Half-Space Trees)\n\n"
            f"**Time:** {first_anomaly.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": title,
                "message": message,
                "notification_id": notification_id,
            },
        )

        # Track notification time
        self._last_notification_time = dt_util.now()
        self._last_notification_type = "ml"

        _LOGGER.info("Sent ML notification for %d anomalies", len(anomalies))

        # Also send to mobile device if configured
        await self._send_mobile_notification(
            title=title,
            message=message,
            data={
                "push": {
                    "sound": "default",
                    "badge": len(anomalies),
                    "interruption-level": "active",
                },
                "group": f"{DOMAIN}_ml",
            },
        )

    async def _send_welfare_notification(self, welfare_status: dict[str, Any]) -> None:
        """Send a notification for welfare status changes."""
        from .const import WELFARE_ALERT, WELFARE_CONCERN

        status = welfare_status.get("status", "ok")
        if status not in [WELFARE_ALERT, WELFARE_CONCERN]:
            return

        notification_id = f"{DOMAIN}_welfare_{status}"

        emoji = "🚨" if status == WELFARE_ALERT else "⚠️"
        title = f"{emoji} Elder Care Welfare {status.replace('_', ' ').title()}"

        reasons = welfare_status.get("reasons", [])
        reasons_text = "\n".join(f"- {r}" for r in reasons)

        routine = welfare_status.get("routine_progress", {})
        activity = welfare_status.get("time_since_activity", {})

        # Get list of triggered sensors (those not in 'normal' status)
        entity_statuses = self._analyzer.get_entity_status()
        triggered_sensors = [
            e for e in entity_statuses
            if e.get("status") in ["alert", "concern", "attention"]
        ]

        triggered_text = ""
        if triggered_sensors:
            triggered_lines = []
            for e in triggered_sensors:
                status_emoji = {"alert": "🚨", "concern": "⚠️", "attention": "ℹ️"}.get(e["status"], "")
                triggered_lines.append(
                    f"- {status_emoji} `{e['entity_id']}` - {e['status']} "
                    f"({e.get('time_since_activity', 'unknown')})"
                )
            triggered_text = f"**Triggered Sensors:**\n" + "\n".join(triggered_lines) + "\n\n"

        message = (
            f"**Status:** {status.upper()}\n\n"
            f"**Summary:** {welfare_status.get('summary', 'Unknown')}\n\n"
            f"**Reasons:**\n{reasons_text}\n\n"
            f"{triggered_text}"
            f"**Recommendation:** {welfare_status.get('recommendation', '')}\n\n"
            f"---\n\n"
            f"**Routine Progress:** {routine.get('progress_percent', 0):.0f}% "
            f"({routine.get('actual_today', 0)} of ~{routine.get('expected_by_now', 0):.0f} expected)\n\n"
            f"**Last Activity:** {activity.get('time_since_formatted', 'Unknown')} "
            f"(usually every {activity.get('typical_interval_formatted', 'Unknown')})\n\n"
            f"**Time:** {dt_util.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": title,
                "message": message,
                "notification_id": notification_id,
            },
        )

        # Track notification time
        self._last_notification_time = dt_util.now()
        self._last_notification_type = "welfare"

        _LOGGER.info("Sent welfare notification: %s - %s", status, welfare_status.get("summary", ""))

        # Also send to mobile device if configured
        await self._send_mobile_notification(
            title=title,
            message=message,
            data={
                "push": {
                    "sound": "default",
                    "badge": 1,
                    "interruption-level": "time-sensitive" if status == WELFARE_ALERT else "active",
                },
                "group": f"{DOMAIN}_welfare",
            },
        )

    async def _send_mobile_notification(
        self, title: str, message: str, data: dict[str, Any] | None = None
    ) -> None:
        """Send notification to mobile devices if configured."""
        if not self._notify_services:
            return

        # Strip markdown formatting for mobile - convert to plain text
        plain_message = message.replace("**", "").replace("`", "").replace("---", "")

        service_data: dict[str, Any] = {
            "title": title.replace("🚨 ", "").replace("⚠️ ", "").replace("⚡ ", "").replace("ℹ️ ", ""),
            "message": plain_message,
        }

        # Add iOS/Android specific data for rich notifications
        if data:
            service_data["data"] = data
        else:
            service_data["data"] = {
                "push": {
                    "sound": "default",
                    "badge": 1,
                },
                "group": DOMAIN,
            }

        for notify_service in self._notify_services:
            # Parse the service name (e.g., "notify.mobile_app_iphone" -> domain="notify", service="mobile_app_iphone")
            service_parts = notify_service.split(".", 1)
            if len(service_parts) != 2:
                _LOGGER.warning(
                    "Invalid notify service format: %s (expected 'notify.service_name')",
                    notify_service,
                )
                continue

            domain, service = service_parts

            try:
                await self.hass.services.async_call(domain, service, service_data)
                _LOGGER.debug("Sent mobile notification via %s", notify_service)
            except Exception as err:
                _LOGGER.warning(
                    "Failed to send mobile notification via %s: %s",
                    notify_service,
                    err,
                )
