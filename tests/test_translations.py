import json
from pathlib import Path

import yaml  # PyYAML ships with Home Assistant; add to requirements-test.txt if missing

from custom_components.behaviour_monitor.const import (
    CATEGORY_CONF_KEYS,
    OPTION_DEFAULTS,
)

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "behaviour_monitor"


def test_translations_cover_every_config_and_option_field():
    t = json.loads((ROOT / "translations" / "en.json").read_text())
    user = t["config"]["step"]["user"]["data"]
    init = t["options"]["step"]["init"]["data"]
    for key in ("site_name", *CATEGORY_CONF_KEYS.values()):
        assert key in user and key in init
    for key in OPTION_DEFAULTS:
        assert key in init
    assert "house_low_ratio" not in init
    for section in ("config", "options"):
        step = t[section]["step"]["whereabouts"]
        assert step["title"]
        assert set(step["data"]) == {"outside_doors", "bedrooms", "sitting_appliances"}
        for sentence in (
            "Doors that lead outside. Don't pick fridge, cupboard or internal "
            "doors: they would hold back fall alerts.",
            "Rooms she sleeps in. Stillness here at night is normal.",
            "Plugs, like a TV, that mean she is sitting nearby when on.",
        ):
            assert sentence in step["description"]
        assert set(t[section]["error"]) >= {
            "no_entities",
            "duplicate_entity",
            "door_not_contact",
            "appliance_not_plug",
        }
    assert set(t["issues"]) >= {
        "assign_categories",
        "device_health",
        "notifications_moved",
    }


def test_services_yaml_lists_every_service():
    s = yaml.safe_load((ROOT / "services.yaml").read_text())
    assert set(s) == {
        "enable_holiday_mode",
        "disable_holiday_mode",
        "snooze",
        "clear_snooze",
        "clear_alert",
        "reset_learning",
        "test_panic",
    }
    assert "entity_id" in s["reset_learning"]["fields"]
