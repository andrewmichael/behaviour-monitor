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
CONF_CROSS_SENSOR_WINDOW: Final = "cross_sensor_window"

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
DEFAULT_CROSS_SENSOR_WINDOW: Final = 300  # seconds (5 minutes)

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
