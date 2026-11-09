"""Tests for constants module."""

from custom_components.behaviour_monitor import const


def test_category_keys_cover_all_six_categories_in_order():
    assert list(const.CATEGORY_CONF_KEYS) == [
        "motion",
        "contact",
        "plug",
        "panic",
        "light",
        "other",
    ]
    assert (
        const.CATEGORY_CONF_KEYS["motion"]
        == const.CONF_MOTION_ENTITIES
        == "motion_entities"
    )
    assert const.CATEGORY_CONF_KEYS["other"] == "other_entities"


def test_option_defaults_match_spec():
    assert const.OPTION_DEFAULTS == {
        "motion_debounce_s": 90,
        "plug_margin_w": 5,
        "learning_days": 14,
        "window_days": 28,
        "health_grace_s": 900,
        "attention_min_severity": "medium",
        "chain_window_s": 1800,
        "timing_promote_days": 7,
        "drift_sensitivity": "medium",
    }


def test_versions_and_services():
    assert const.CONFIG_VERSION == 13 and const.STORAGE_VERSION == 11
    assert const.VERSION == "5.0.0"
    assert const.SERVICE_CLEAR_ALERT == "clear_alert"
    assert const.SERVICE_RESET_LEARNING == "reset_learning"
    assert const.SERVICE_TEST_PANIC == "test_panic"
    assert const.SNOOZE_DURATIONS["1_hour"] == 3600


def test_notification_migration_constants():
    assert const.LEGACY_CONF_NOTIFY_SERVICE == "notify_service"
    assert const.ISSUE_NOTIFICATIONS_MOVED == "notifications_moved"
    assert const.BLUEPRINT_URL.startswith(
        "https://github.com/andrewmichael/behaviour-monitor/"
    )
    assert not hasattr(const, "CONF_NOTIFY_SERVICE")
    assert not hasattr(const, "CONF_PUSH_REPEAT_S")
    assert not hasattr(const, "CONF_PUSH_MIN_SEVERITY")


def test_whereabouts_option_keys():
    assert const.CONF_OUTSIDE_DOORS == "outside_doors"
    assert const.CONF_SITTING_APPLIANCES == "sitting_appliances"
    assert const.CONF_BEDROOMS == "bedrooms"
    assert const.LEGACY_CONF_HOUSE_LOW_RATIO == "house_low_ratio"
    assert not hasattr(const, "CONF_HOUSE_LOW_RATIO")
