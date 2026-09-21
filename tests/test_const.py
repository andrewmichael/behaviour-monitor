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
        "push_repeat_s": 1800,
        "push_min_severity": "medium",
        "house_low_ratio": 3,
        "chain_window_s": 1800,
        "timing_promote_days": 7,
        "drift_sensitivity": "medium",
    }


def test_versions_and_services():
    assert const.CONFIG_VERSION == 11 and const.STORAGE_VERSION == 11
    assert const.VERSION == "5.0.0"
    assert const.SERVICE_ACKNOWLEDGE == "acknowledge"
    assert const.SERVICE_RESET_LEARNING == "reset_learning"
    assert const.SERVICE_TEST_PANIC == "test_panic"
    assert const.SNOOZE_DURATIONS["1_hour"] == 3600
