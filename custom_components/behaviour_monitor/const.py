"""Constants for the Behaviour Monitor integration."""

from enum import Enum
from typing import Final

from .alert_result import AlertSeverity

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

# New v2.9 config keys
CONF_LEARNING_PERIOD: Final = "learning_period"
CONF_TRACK_ATTRIBUTES: Final = "track_attributes"

# New v4.1 config keys (per-entity overrides of track_attributes)
CONF_TRACK_ATTRIBUTES_INCLUDE: Final = "track_attributes_include"
CONF_TRACK_ATTRIBUTES_EXCLUDE: Final = "track_attributes_exclude"

# New v3.0 config keys
CONF_ALERT_REPEAT_INTERVAL: Final = "alert_repeat_interval"
CONF_MIN_INACTIVITY_MULTIPLIER: Final = "min_inactivity_multiplier"
CONF_MAX_INACTIVITY_MULTIPLIER: Final = "max_inactivity_multiplier"

# New v3.1 config keys
CONF_ACTIVITY_TIER_OVERRIDE: Final = "activity_tier_override"

# New v3.0 defaults
DEFAULT_ALERT_REPEAT_INTERVAL: Final = 240  # minutes (4 hours)
DEFAULT_MIN_INACTIVITY_MULTIPLIER: Final = 1.5
DEFAULT_MAX_INACTIVITY_MULTIPLIER: Final = 10.0

# New v3.1 defaults
DEFAULT_ACTIVITY_TIER_OVERRIDE: Final = "auto"

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
DEFAULT_LEARNING_PERIOD_DAYS: Final = 7  # days
DEFAULT_TRACK_ATTRIBUTES: Final = False

# New v4.1 defaults
DEFAULT_TRACK_ATTRIBUTES_INCLUDE: Final[list[str]] = []  # Entities that always track attributes
DEFAULT_TRACK_ATTRIBUTES_EXCLUDE: Final[list[str]] = []  # Entities that never track attributes

# Legacy v5.0 keys: read by the v11 and v14 migrations only.
CONF_CATEGORY_MOTION: Final = "category_motion"
CONF_CATEGORY_CONTACT: Final = "category_contact"
CONF_CATEGORY_PLUG: Final = "category_plug"
CONF_CATEGORY_LIGHT: Final = "category_light"

# New v5.0 config keys (motion debounce)
CONF_MOTION_DEBOUNCE_SECONDS: Final = "motion_debounce_seconds"
DEFAULT_MOTION_DEBOUNCE_SECONDS: Final = 120  # seconds; 0 disables debounce
# New v5.1 config keys (panic button)
CONF_CATEGORY_PANIC: Final = "category_panic"
CONF_PANIC_RENOTIFY_MINUTES: Final = "panic_renotify_minutes"
# One-shot flag written by the v11 migration; cleared by the coordinator
# after it re-bootstraps motion entities from recorder history.
CONF_REBOOTSTRAP_MOTION: Final = "rebootstrap_motion"

# New v5.1 defaults
DEFAULT_CATEGORY_PANIC: Final[list[str]] = []  # override-list only; never inferred
DEFAULT_PANIC_RENOTIFY_MINUTES: Final = 5  # minutes between re-notifications until acknowledged

# New v5.2 config keys (system integrity)
CONF_STARTUP_GRACE_SECONDS: Final = "startup_grace_seconds"
CONF_BURST_DISCARD_THRESHOLD: Final = "burst_discard_threshold"
CONF_PANIC_HEARTBEAT_HOURS: Final = "panic_heartbeat_hours"
CONF_PANIC_TEST_REMINDER_DAYS: Final = "panic_test_reminder_days"

# New v5.2 defaults
DEFAULT_STARTUP_GRACE_SECONDS: Final = 90  # seconds after setup during which events are ignored; 0 disables
DEFAULT_BURST_DISCARD_THRESHOLD: Final = 3  # distinct entities changing in one second = artifact; 0 disables
DEFAULT_PANIC_HEARTBEAT_HOURS: Final = 24  # hours without a report before a panic device alert; 0 disables
DEFAULT_PANIC_TEST_REMINDER_DAYS: Final = 30  # days without a test press before a reminder; 0 disables
PANIC_TEST_WINDOW_SECONDS: Final = 120
PANIC_LOW_BATTERY_PERCENT: Final = 20

# New v5.3 config keys (roles + event pipeline)
CONF_EXTERIOR_DOORS: Final = "exterior_doors"
CONF_ROLE_OVERRIDES: Final = "role_overrides"
CONF_DOOR_DEBOUNCE_SECONDS: Final = "door_debounce_seconds"
CONF_RETRIGGER_COLLAPSE_SECONDS: Final = "retrigger_collapse_seconds"
CONF_EXCURSION_WINDOW_SECONDS: Final = "excursion_window_seconds"
CONF_DOOR_OPEN_EXTENDED_SECONDS: Final = "door_open_extended_seconds"
CONF_DOOR_OPEN_PROLONGED_SECONDS: Final = "door_open_prolonged_seconds"
# One-shot flag written by the v14 migration; cleared by the coordinator
# after it re-bootstraps door and appliance entities from recorder history.
CONF_REBOOTSTRAP_ROLES: Final = "rebootstrap_roles"

# New v5.3 defaults
DEFAULT_EXTERIOR_DOORS: Final[list[str]] = []  # door.exterior is never inferred
DEFAULT_ROLE_OVERRIDES: Final = ""  # multiline "entity_id: role-or-kind"
DEFAULT_DOOR_DEBOUNCE_SECONDS: Final = 60  # seconds; 0 disables
DEFAULT_RETRIGGER_COLLAPSE_SECONDS: Final = 5  # seconds; off/on pairs closer than this are noise; 0 disables
DEFAULT_EXCURSION_WINDOW_SECONDS: Final = 60  # seconds; exterior-door events inside this window are one excursion; 0 disables
DEFAULT_DOOR_OPEN_EXTENDED_SECONDS: Final = 15  # open at least this long = "extended"
DEFAULT_DOOR_OPEN_PROLONGED_SECONDS: Final = 120  # open at least this long = "prolonged"

# Storage
STORAGE_KEY: Final = "behaviour_monitor"
STORAGE_VERSION: Final = 14

# Update interval (seconds)
UPDATE_INTERVAL: Final = 60

# Sensor attributes
ATTR_LAST_UPDATED: Final = "last_updated"
ATTR_MONITORED_ENTITIES: Final = "monitored_entities"
ATTR_LEARNING_PROGRESS: Final = "learning_progress"
ATTR_ANOMALY_DETAILS: Final = "anomaly_details"
ATTR_ML_STATUS: Final = "ml_status"
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
WELFARE_BLIND: Final = "blind"  # no monitored entity is reporting
WELFARE_DEGRADED: Final = "degraded"  # some inputs lost or a device-health alert is active

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
SERVICE_ACKNOWLEDGE_PANIC: Final = "acknowledge_panic"
SERVICE_PANIC_TEST: Final = "panic_test"

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

# ---------------------------------------------------------------------------
# Activity-rate tier classification (v3.1)
# ---------------------------------------------------------------------------


class ActivityTier(Enum):
    """Frequency tier for entity activity classification."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Tier boundary thresholds (events per day)
# >= TIER_BOUNDARY_HIGH -> HIGH tier
# <= TIER_BOUNDARY_LOW  -> LOW tier
# between -> MEDIUM tier
TIER_BOUNDARY_HIGH: Final = 24
TIER_BOUNDARY_LOW: Final = 4

# Absolute minimum inactivity floor per tier (seconds)
# Prevents sub-minute alert thresholds on high-frequency entities
TIER_FLOOR_SECONDS: Final = {
    ActivityTier.HIGH: 3600,  # 1 hour — conservative floor for chatty sensors
    ActivityTier.MEDIUM: 1800,  # 30 minutes
    ActivityTier.LOW: 0,  # no floor — use multiplier arithmetic as-is
}

# Multiplier boost factor per tier (applied on top of user's inactivity_multiplier)
TIER_BOOST_FACTOR: Final = {
    ActivityTier.HIGH: 2.0,  # double the effective multiplier for chatty sensors
    ActivityTier.MEDIUM: 1.0,  # no boost
    ActivityTier.LOW: 1.0,  # no boost
}

# ---------------------------------------------------------------------------
# Cross-entity correlation (v4.0)
# ---------------------------------------------------------------------------

# Config key for user-facing correlation time window
CONF_CORRELATION_WINDOW: Final = "correlation_window"

# Default correlation window in seconds (per D-03: 120s = 2 minutes)
DEFAULT_CORRELATION_WINDOW: Final = 120

# Internal correlation constants (not user-facing config)
# Minimum co-occurrences before a pair is considered for correlation
MIN_CO_OCCURRENCES: Final = 10

# PMI threshold — pairs with PMI > this are considered correlated
# PMI > 1.0 means 2x more likely than chance (medium-confidence, tunable)
PMI_THRESHOLD: Final[float] = 1.0

# ---------------------------------------------------------------------------
# Entity categories, motion debounce and weighted welfare (v5.0)
# ---------------------------------------------------------------------------

# Entity-registry device classes that map to each category
MOTION_DEVICE_CLASSES: Final = frozenset({"motion", "occupancy", "presence"})
CONTACT_DEVICE_CLASSES: Final = frozenset({"door", "window", "opening", "garage_door"})
PLUG_DEVICE_CLASSES: Final = frozenset({"outlet", "plug"})

# ---------------------------------------------------------------------------
# Entity roles and event pipeline (v5.3)
# ---------------------------------------------------------------------------


class EntityRole(Enum):
    """Semantic role of a monitored entity. The part before the dot is its kind."""

    MOTION_BATHROOM = "motion.bathroom"
    MOTION_BEDROOM = "motion.bedroom"
    MOTION_LIVING = "motion.living"
    MOTION_KITCHEN = "motion.kitchen"
    MOTION_TRANSIT = "motion.transit"
    MOTION_UNASSIGNED = "motion.unassigned"  # motion sensor with no recognised area
    DOOR_EXTERIOR = "door.exterior"  # exterior-door list only; never inferred
    DOOR_INTERIOR = "door.interior"  # default for every contact class, windows included
    APPLIANCE = "appliance"
    PANIC = "panic"  # panic list only; instant alert, no learning
    OTHER = "other"

    @property
    def kind(self) -> str:
        return self.value.split(".", 1)[0]

    @classmethod
    def from_string(cls, value: str) -> "EntityRole":
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"unknown role: {value!r}") from None


ROLE_KINDS: Final = frozenset({"motion", "door", "appliance", "panic", "other"})

# Interim welfare weight per kind until v5.4 entropy weighting.
KIND_WEIGHT: Final[dict[str, float]] = {
    "motion": 1.0,
    "door": 0.8,
    "appliance": 0.5,
    "other": 1.0,
}

# Lower-case substrings of a Home Assistant area name that place a motion
# sensor in a room role. First hit in table order wins. English only; other
# languages use the role override map.
AREA_ROLE_KEYWORDS: Final[tuple[tuple[EntityRole, tuple[str, ...]], ...]] = (
    (EntityRole.MOTION_BATHROOM, ("bathroom", "toilet", "ensuite", "en-suite", "shower", "wc", "loo", "cloakroom")),
    (EntityRole.MOTION_BEDROOM, ("bedroom", "bed")),
    (EntityRole.MOTION_LIVING, ("living", "lounge", "sitting", "dining", "study", "office", "conservatory", "snug")),
    (EntityRole.MOTION_KITCHEN, ("kitchen", "utility", "pantry")),
    (EntityRole.MOTION_TRANSIT, ("hall", "landing", "stairs", "stairway", "corridor", "porch", "entrance", "passage")),
)

# Door open-duration classes (pipeline stage 3)
DOOR_OPEN_BRIEF: Final = "brief"
DOOR_OPEN_EXTENDED: Final = "extended"
DOOR_OPEN_PROLONGED: Final = "prolonged"

# Severity points multiplied by KIND_WEIGHT to score an alert.
SEVERITY_POINTS: Final = {
    AlertSeverity.LOW: 1,
    AlertSeverity.MEDIUM: 2,
    AlertSeverity.HIGH: 3,
}

WELFARE_ALERT_SCORE: Final[float] = 2.25
WELFARE_CONCERN_SCORE: Final[float] = 1.25
# Recommendation text when any panic button is active
WELFARE_PANIC_RECOMMENDATION: Final = "Panic button pressed. Respond now."
WELFARE_BLIND_RECOMMENDATION: Final = "No monitored entities are reporting. Check sensors and the integration options."
WELFARE_DEGRADED_RECOMMENDATION: Final = "Some monitored entities are not reporting."

# Entity health classification (v5.2)
HEALTH_PRESENT: Final = "present"
HEALTH_UNAVAILABLE: Final = "unavailable"
HEALTH_MISSING: Final = "missing"
