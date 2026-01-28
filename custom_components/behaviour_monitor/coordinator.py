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

from .analyzer import AnomalyResult, PatternAnalyzer
from .const import (
    CONF_CROSS_SENSOR_WINDOW,
    CONF_ENABLE_ML,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_LEARNING_PERIOD,
    CONF_MONITORED_ENTITIES,
    CONF_RETRAIN_PERIOD,
    CONF_SENSITIVITY,
    DEFAULT_CROSS_SENSOR_WINDOW,
    DEFAULT_ENABLE_ML,
    DEFAULT_ENABLE_NOTIFICATIONS,
    DEFAULT_LEARNING_PERIOD,
    DEFAULT_RETRAIN_PERIOD,
    DEFAULT_SENSITIVITY,
    DOMAIN,
    ML_CONTAMINATION,
    SENSITIVITY_THRESHOLDS,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .ml_analyzer import MLAnomalyResult, MLPatternAnalyzer, StateChangeEvent

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

        # Get configuration
        sensitivity_key = entry.data.get(CONF_SENSITIVITY, DEFAULT_SENSITIVITY)
        sensitivity_threshold = SENSITIVITY_THRESHOLDS.get(sensitivity_key, 2.0)
        learning_period = int(entry.data.get(CONF_LEARNING_PERIOD, DEFAULT_LEARNING_PERIOD))

        self._analyzer = PatternAnalyzer(
            sensitivity_threshold=sensitivity_threshold,
            learning_period_days=learning_period,
        )

        # ML configuration
        self._enable_ml = entry.data.get(CONF_ENABLE_ML, DEFAULT_ENABLE_ML)
        self._retrain_period_days = int(entry.data.get(CONF_RETRAIN_PERIOD, DEFAULT_RETRAIN_PERIOD))
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

    async def async_setup(self) -> None:
        """Set up the coordinator."""
        # Load stored statistical data
        stored_data = await self._store.async_load()
        if stored_data:
            self._analyzer = PatternAnalyzer.from_dict(
                stored_data,
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

    async def async_shutdown(self) -> None:
        """Shut down the coordinator."""
        if self._unsubscribe_state_changed:
            self._unsubscribe_state_changed()
            self._unsubscribe_state_changed = None

        # Save data
        await self._save_data()

    async def _save_data(self) -> None:
        """Save pattern data to storage."""
        await self._store.async_save(self._analyzer.to_dict())

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
        if datetime.now() - last_trained > retrain_delta:
            _LOGGER.info(
                "Retraining ML model (last trained: %s, period: %d days)",
                last_trained.isoformat(),
                self._retrain_period_days,
            )
            # Prune old events before retraining
            self._ml_analyzer.prune_old_events(max_age_days=self._retrain_period_days * 2)
            self._ml_analyzer.train()

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        """Handle state change events."""
        entity_id = event.data.get("entity_id")
        if entity_id not in self._monitored_entities:
            return

        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        # Only record if the state actually changed (not just attributes)
        if old_state is None or new_state is None:
            return
        if old_state.state == new_state.state:
            return

        timestamp = datetime.now()

        # Record in statistical analyzer
        self._analyzer.record_state_change(entity_id, timestamp)

        # Record in ML analyzer
        if self._enable_ml:
            self._ml_analyzer.record_event(
                entity_id=entity_id,
                timestamp=timestamp,
                old_state=old_state.state,
                new_state=new_state.state,
            )

            # Track recent events for cross-sensor analysis
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

        _LOGGER.debug(
            "Recorded state change for %s: %s -> %s",
            entity_id,
            old_state.state,
            new_state.state,
        )

        # Trigger an update to refresh sensors
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data and check for anomalies."""
        # Check for statistical anomalies
        stat_anomalies = self._analyzer.check_for_anomalies()

        if stat_anomalies:
            self._recent_anomalies = stat_anomalies

        # Check for ML anomalies
        ml_anomalies: list[MLAnomalyResult] = []

        if self._enable_ml:
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

        if self._enable_notifications:
            for anomaly in stat_anomalies:
                await self._send_notification(anomaly)
            for ml_anomaly in ml_anomalies:
                await self._send_ml_notification(ml_anomaly)

        # Periodically save data
        await self._save_data()

        # Build data for sensors
        last_activity = self._analyzer.get_last_activity_time()

        # Get cross-sensor patterns
        cross_patterns = []
        if self._enable_ml:
            cross_patterns = self._ml_analyzer.get_strong_patterns(min_strength=0.3)

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
        }

    async def _send_notification(self, anomaly: AnomalyResult) -> None:
        """Send a persistent notification for a statistical anomaly."""
        notification_id = f"{DOMAIN}_{anomaly.entity_id}_{anomaly.anomaly_type}"

        title = "Behaviour Monitor Alert"
        if anomaly.anomaly_type == "unusual_activity":
            title = "Unusual Activity Detected"
        elif anomaly.anomaly_type == "unusual_inactivity":
            title = "Unusual Inactivity Detected"

        message = (
            f"**Entity:** `{anomaly.entity_id}`\n\n"
            f"**Time Slot:** {anomaly.time_slot}\n\n"
            f"**Details:** {anomaly.description}\n\n"
            f"**Z-Score:** {anomaly.z_score:.2f} "
            f"(threshold: {self._analyzer._sensitivity_threshold:.1f})\n\n"
            f"**Detection:** Statistical (Z-score)\n\n"
            f"**Time:** {anomaly.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
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

        _LOGGER.info("Sent notification for anomaly: %s", anomaly.description)

    async def _send_ml_notification(self, anomaly: MLAnomalyResult) -> None:
        """Send a persistent notification for an ML-detected anomaly."""
        entity_part = anomaly.entity_id or "cross_sensor"
        notification_id = f"{DOMAIN}_ml_{entity_part}_{anomaly.anomaly_type}"

        title = "Behaviour Monitor ML Alert"
        if anomaly.anomaly_type == "isolation_forest":
            title = "Unusual Pattern Detected (ML)"
        elif anomaly.anomaly_type == "missing_correlation":
            title = "Missing Expected Activity"
        elif anomaly.anomaly_type == "unexpected_correlation":
            title = "Unexpected Activity Pattern"

        related = ""
        if anomaly.related_entities:
            related = f"**Related Entities:** {', '.join(anomaly.related_entities)}\n\n"

        message = (
            f"**Entity:** `{anomaly.entity_id or 'Cross-sensor pattern'}`\n\n"
            f"{related}"
            f"**Details:** {anomaly.description}\n\n"
            f"**ML Score:** {anomaly.anomaly_score:.3f}\n\n"
            f"**Detection:** Machine Learning ({anomaly.anomaly_type})\n\n"
            f"**Time:** {anomaly.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
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

        _LOGGER.info("Sent ML notification for anomaly: %s", anomaly.description)
