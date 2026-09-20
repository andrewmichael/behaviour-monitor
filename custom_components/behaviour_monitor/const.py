"""Constants for the Behaviour Monitor integration (v5)."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "behaviour_monitor"
VERSION: Final = "5.0.0"
CONFIG_VERSION: Final = 11
STORAGE_KEY: Final = "behaviour_monitor"
STORAGE_VERSION: Final = 11
UPDATE_INTERVAL: Final = 60  # seconds
SAVE_DEBOUNCE_S: Final = 30

# Setup-step config keys
CONF_SITE_NAME: Final = "site_name"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_MOTION_ENTITIES: Final = "motion_entities"
CONF_CONTACT_ENTITIES: Final = "contact_entities"
CONF_PLUG_ENTITIES: Final = "plug_entities"
CONF_PANIC_ENTITIES: Final = "panic_entities"
CONF_LIGHT_ENTITIES: Final = "light_entities"
CONF_OTHER_ENTITIES: Final = "other_entities"

CATEGORY_CONF_KEYS: Final[dict[str, str]] = {
    "motion": CONF_MOTION_ENTITIES,
    "contact": CONF_CONTACT_ENTITIES,
    "plug": CONF_PLUG_ENTITIES,
    "panic": CONF_PANIC_ENTITIES,
    "light": CONF_LIGHT_ENTITIES,
    "other": CONF_OTHER_ENTITIES,
}

# Options-step keys (names match EngineConfig.from_options)
CONF_MOTION_DEBOUNCE_S: Final = "motion_debounce_s"
CONF_PLUG_MARGIN_W: Final = "plug_margin_w"
CONF_LEARNING_DAYS: Final = "learning_days"
CONF_WINDOW_DAYS: Final = "window_days"
CONF_HEALTH_GRACE_S: Final = "health_grace_s"
CONF_PUSH_REPEAT_S: Final = "push_repeat_s"
CONF_PUSH_MIN_SEVERITY: Final = "push_min_severity"
CONF_HOUSE_LOW_RATIO: Final = "house_low_ratio"
CONF_CHAIN_WINDOW_S: Final = "chain_window_s"
CONF_TIMING_PROMOTE_DAYS: Final = "timing_promote_days"
CONF_DRIFT_SENSITIVITY: Final = "drift_sensitivity"

OPTION_DEFAULTS: Final[dict[str, int | str]] = {
    CONF_MOTION_DEBOUNCE_S: 90,
    CONF_PLUG_MARGIN_W: 5,
    CONF_LEARNING_DAYS: 14,
    CONF_WINDOW_DAYS: 28,
    CONF_HEALTH_GRACE_S: 900,
    CONF_PUSH_REPEAT_S: 1800,
    CONF_PUSH_MIN_SEVERITY: "medium",
    CONF_HOUSE_LOW_RATIO: 3,
    CONF_CHAIN_WINDOW_S: 1800,
    CONF_TIMING_PROMOTE_DAYS: 7,
    CONF_DRIFT_SENSITIVITY: "medium",
}

SEVERITY_OPTIONS: Final = ["low", "medium", "high", "critical"]
SENSITIVITY_OPTIONS: Final = ["low", "medium", "high"]

# Legacy (v10) key kept only for migration
LEGACY_CONF_MONITORED_ENTITIES: Final = "monitored_entities"

# Snooze
SNOOZE_OFF: Final = "off"
SNOOZE_DURATIONS: Final = {
    SNOOZE_OFF: 0,
    "1_hour": 3600,
    "2_hours": 7200,
    "4_hours": 14400,
    "1_day": 86400,
}
SNOOZE_OPTIONS: Final = list(SNOOZE_DURATIONS)
SNOOZE_LABELS: Final = {
    SNOOZE_OFF: "Off",
    "1_hour": "1 Hour",
    "2_hours": "2 Hours",
    "4_hours": "4 Hours",
    "1_day": "1 Day",
}

# Services
SERVICE_ENABLE_HOLIDAY_MODE: Final = "enable_holiday_mode"
SERVICE_DISABLE_HOLIDAY_MODE: Final = "disable_holiday_mode"
SERVICE_SNOOZE: Final = "snooze"
SERVICE_CLEAR_SNOOZE: Final = "clear_snooze"
SERVICE_ACKNOWLEDGE: Final = "acknowledge"
SERVICE_RESET_LEARNING: Final = "reset_learning"
SERVICE_TEST_PANIC: Final = "test_panic"

# Repair issue ids
ISSUE_ASSIGN_CATEGORIES: Final = "assign_categories"
ISSUE_HEALTH_PREFIX: Final = "health_"

# Events
EVENT_LOGBOOK: Final = "logbook_entry"
