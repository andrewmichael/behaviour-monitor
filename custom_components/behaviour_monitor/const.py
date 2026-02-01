"""Constants for the Behaviour Monitor integration."""

from typing import Final

DOMAIN: Final = "behaviour_monitor"

# Configuration keys
CONF_MONITORED_ENTITIES: Final = "monitored_entities"
CONF_SENSITIVITY: Final = "sensitivity"
CONF_LEARNING_PERIOD: Final = "learning_period"
CONF_ENABLE_NOTIFICATIONS: Final = "enable_notifications"
CONF_ENABLE_ML: Final = "enable_ml"
CONF_RETRAIN_PERIOD: Final = "retrain_period"
CONF_ML_LEARNING_PERIOD: Final = "ml_learning_period"
CONF_CROSS_SENSOR_WINDOW: Final = "cross_sensor_window"
CONF_TRACK_ATTRIBUTES: Final = "track_attributes"
CONF_NOTIFY_SERVICES: Final = "notify_services"

# Sensitivity levels (standard deviations for Z-score)
SENSITIVITY_LOW: Final = "low"
SENSITIVITY_MEDIUM: Final = "medium"
SENSITIVITY_HIGH: Final = "high"

SENSITIVITY_THRESHOLDS: Final = {
    SENSITIVITY_LOW: 3.0,      # 3σ - only flag extreme anomalies
    SENSITIVITY_MEDIUM: 2.0,   # 2σ - flag moderate anomalies
    SENSITIVITY_HIGH: 1.0,     # 1σ - flag any deviation
}

# Isolation Forest contamination (expected anomaly rate)
ML_CONTAMINATION: Final = {
    SENSITIVITY_LOW: 0.01,     # 1% expected anomalies
    SENSITIVITY_MEDIUM: 0.05,  # 5% expected anomalies
    SENSITIVITY_HIGH: 0.10,    # 10% expected anomalies
}

# Default values
DEFAULT_SENSITIVITY: Final = SENSITIVITY_MEDIUM
DEFAULT_LEARNING_PERIOD: Final = 7  # days
DEFAULT_ENABLE_NOTIFICATIONS: Final = True
DEFAULT_ENABLE_ML: Final = True
DEFAULT_RETRAIN_PERIOD: Final = 14  # days (2 weeks)
DEFAULT_ML_LEARNING_PERIOD: Final = 7  # days (minimum time before ML alerts)
DEFAULT_CROSS_SENSOR_WINDOW: Final = 300  # seconds (5 minutes)
DEFAULT_TRACK_ATTRIBUTES: Final = True  # Track attribute changes (not just state)
DEFAULT_NOTIFY_SERVICES: Final = []  # Empty = persistent_notification only

# Storage
STORAGE_KEY: Final = "behaviour_monitor"
STORAGE_VERSION: Final = 2

# Update interval (seconds)
UPDATE_INTERVAL: Final = 60

# Minimum samples required for ML training
MIN_SAMPLES_FOR_ML: Final = 100

# Sensor attributes
ATTR_LAST_UPDATED: Final = "last_updated"
ATTR_MONITORED_ENTITIES: Final = "monitored_entities"
ATTR_LEARNING_PROGRESS: Final = "learning_progress"
ATTR_ANOMALY_DETAILS: Final = "anomaly_details"
ATTR_ML_STATUS: Final = "ml_status"
ATTR_CROSS_SENSOR_PATTERNS: Final = "cross_sensor_patterns"
ATTR_LAST_RETRAIN: Final = "last_retrain"

# Elder care severity levels (based on Z-score)
SEVERITY_NORMAL: Final = "normal"
SEVERITY_MINOR: Final = "minor"
SEVERITY_MODERATE: Final = "moderate"
SEVERITY_SIGNIFICANT: Final = "significant"
SEVERITY_CRITICAL: Final = "critical"

SEVERITY_THRESHOLDS: Final = {
    SEVERITY_MINOR: 1.5,       # 1.5σ
    SEVERITY_MODERATE: 2.5,    # 2.5σ
    SEVERITY_SIGNIFICANT: 3.5, # 3.5σ
    SEVERITY_CRITICAL: 4.5,    # 4.5σ
}

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
