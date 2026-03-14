"""Constants for the Behaviour Monitor integration."""

from typing import Final

DOMAIN: Final = "behaviour_monitor"

# Configuration keys
CONF_MONITORED_ENTITIES: Final = "monitored_entities"
CONF_ENABLE_NOTIFICATIONS: Final = "enable_notifications"
CONF_NOTIFY_SERVICES: Final = "notify_services"
CONF_NOTIFICATION_COOLDOWN: Final = "notification_cooldown"
CONF_MIN_NOTIFICATION_SEVERITY: Final = "min_notification_severity"

# New v1.1 config keys
CONF_HISTORY_WINDOW_DAYS: Final = "history_window_days"
CONF_INACTIVITY_MULTIPLIER: Final = "inactivity_multiplier"
CONF_DRIFT_SENSITIVITY: Final = "drift_sensitivity"

# Sensitivity levels
SENSITIVITY_LOW: Final = "low"
SENSITIVITY_MEDIUM: Final = "medium"
SENSITIVITY_HIGH: Final = "high"

# Default values
DEFAULT_ENABLE_NOTIFICATIONS: Final = True
DEFAULT_NOTIFY_SERVICES: Final = []  # Empty = persistent_notification only
DEFAULT_NOTIFICATION_COOLDOWN: Final = 30  # minutes
DEFAULT_MIN_NOTIFICATION_SEVERITY: Final = "significant"

# New v1.1 defaults
DEFAULT_HISTORY_WINDOW_DAYS: Final = 28  # days
DEFAULT_INACTIVITY_MULTIPLIER: Final = 3.0

# Storage
STORAGE_KEY: Final = "behaviour_monitor"
STORAGE_VERSION: Final = 4

# Update interval (seconds)
UPDATE_INTERVAL: Final = 60

# Sensor attributes
ATTR_LAST_UPDATED: Final = "last_updated"
ATTR_MONITORED_ENTITIES: Final = "monitored_entities"
ATTR_LEARNING_PROGRESS: Final = "learning_progress"
ATTR_ANOMALY_DETAILS: Final = "anomaly_details"
ATTR_ML_STATUS: Final = "ml_status"
ATTR_CROSS_SENSOR_PATTERNS: Final = "cross_sensor_patterns"
ATTR_LAST_RETRAIN: Final = "last_retrain"

# Elder care severity levels
SEVERITY_NORMAL: Final = "normal"
SEVERITY_MINOR: Final = "minor"
SEVERITY_MODERATE: Final = "moderate"
SEVERITY_SIGNIFICANT: Final = "significant"
SEVERITY_CRITICAL: Final = "critical"

WELFARE_DEBOUNCE_CYCLES: Final = 3  # consecutive update cycles before welfare notification fires (~3 min at 60s interval)

# Elder care attributes
ATTR_SEVERITY: Final = "severity"
ATTR_TIME_SINCE_ACTIVITY: Final = "time_since_activity"
ATTR_TYPICAL_INTERVAL: Final = "typical_interval"
ATTR_ROUTINE_PROGRESS: Final = "routine_progress"
ATTR_EXPECTED_BY_NOW: Final = "expected_by_now"
ATTR_ACTUAL_TODAY: Final = "actual_today"
ATTR_TREND: Final = "trend"
ATTR_CONSECUTIVE_LOW_DAYS: Final = "consecutive_low_days"
ATTR_ENTITY_STATUS: Final = "entity_status"
ATTR_LAST_ACTIVITY_CONTEXT: Final = "last_activity_context"
ATTR_WELFARE_STATUS: Final = "welfare_status"

# Welfare status levels
WELFARE_OK: Final = "ok"
WELFARE_CHECK: Final = "check_recommended"
WELFARE_CONCERN: Final = "concern"
WELFARE_ALERT: Final = "alert"

# Holiday mode and snooze
ATTR_HOLIDAY_MODE: Final = "holiday_mode"
ATTR_SNOOZE_UNTIL: Final = "snooze_until"
ATTR_SNOOZE_ACTIVE: Final = "snooze_active"

# Snooze duration options
SNOOZE_OFF: Final = "off"
SNOOZE_1_HOUR: Final = "1_hour"
SNOOZE_2_HOURS: Final = "2_hours"
SNOOZE_4_HOURS: Final = "4_hours"
SNOOZE_1_DAY: Final = "1_day"

SNOOZE_DURATIONS: Final = {
    SNOOZE_OFF: 0,
    SNOOZE_1_HOUR: 3600,      # 1 hour in seconds
    SNOOZE_2_HOURS: 7200,     # 2 hours
    SNOOZE_4_HOURS: 14400,    # 4 hours
    SNOOZE_1_DAY: 86400,      # 24 hours
}

SNOOZE_OPTIONS: Final = [
    SNOOZE_OFF,
    SNOOZE_1_HOUR,
    SNOOZE_2_HOURS,
    SNOOZE_4_HOURS,
    SNOOZE_1_DAY,
]

SNOOZE_LABELS: Final = {
    SNOOZE_OFF: "Off",
    SNOOZE_1_HOUR: "1 Hour",
    SNOOZE_2_HOURS: "2 Hours",
    SNOOZE_4_HOURS: "4 Hours",
    SNOOZE_1_DAY: "1 Day",
}

# Services
SERVICE_ENABLE_HOLIDAY_MODE: Final = "enable_holiday_mode"
SERVICE_DISABLE_HOLIDAY_MODE: Final = "disable_holiday_mode"
SERVICE_SNOOZE: Final = "snooze"
SERVICE_CLEAR_SNOOZE: Final = "clear_snooze"
SERVICE_ROUTINE_RESET: Final = "routine_reset"

# ---------------------------------------------------------------------------
# Detection engine constants (v1.1)
# ---------------------------------------------------------------------------

# Number of consecutive polling cycles evidence must persist before an alert fires
SUSTAINED_EVIDENCE_CYCLES: Final = 3

# Minimum days of observations before drift detection activates
MIN_EVIDENCE_DAYS: Final = 3

# Minimum routine confidence before unusual-time alerts fire (Pitfall 6 guard)
MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME: Final = 0.3

# CUSUM parameters (k=allowance, h=threshold) keyed by sensitivity level
# high=(0.25, 2.0): sensitive to small shifts; low=(1.0, 6.0): only large shifts
CUSUM_PARAMS: Final = {
    "high": (0.25, 2.0),
    "medium": (0.5, 4.0),
    "low": (1.0, 6.0),
}
