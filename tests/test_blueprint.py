"""Pin the shape of the notify blueprint."""

from __future__ import annotations

from pathlib import Path

import yaml

BLUEPRINT = (
    Path(__file__).parent.parent
    / "blueprints"
    / "automation"
    / "behaviour_monitor"
    / "notify.yaml"
)


class _Input:
    def __init__(self, name: str) -> None:
        self.name = name


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor(
    "!input", lambda loader, node: _Input(loader.construct_scalar(node))
)


def _load() -> dict:
    return yaml.load(BLUEPRINT.read_text(encoding="utf-8"), Loader=_Loader)


def _walk(node):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_inputs_and_defaults():
    inputs = _load()["blueprint"]["input"]
    assert set(inputs) == {
        "notify_service",
        "groups",
        "repeat_minutes",
        "send_cleared",
        "panic_action",
    }
    assert "default" not in inputs["notify_service"]
    assert inputs["groups"]["default"] == ["attention"]
    assert inputs["repeat_minutes"]["default"] == 30
    assert inputs["send_cleared"]["default"] is True
    assert inputs["panic_action"]["default"] is True
    sel = inputs["groups"]["selector"]["select"]
    assert sel["multiple"] is True
    assert set(sel["options"]) == {"attention", "information", "health"}
    num = inputs["repeat_minutes"]["selector"]["number"]
    assert (num["min"], num["max"]) == (0, 240)


def test_triggers_and_mode():
    data = _load()
    assert data["mode"] == "parallel"
    assert data["max"] == 20
    triggers = data["triggers"]
    types = {t.get("event_type") for t in triggers if t.get("trigger") == "event"}
    assert "behaviour_monitor_alert" in types
    assert "mobile_app_notification_action" in types


def test_clear_alert_service_call():
    calls = [
        n
        for n in _walk(_load()["actions"])
        if isinstance(n, dict) and n.get("action") == "behaviour_monitor.clear_alert"
    ]
    assert calls
    assert "alert_id" in calls[0]["data"]


def test_wait_matches_id_and_any_type():
    waits = [
        n
        for n in _walk(_load()["actions"])
        if isinstance(n, dict) and "wait_for_trigger" in n
    ]
    assert waits
    for w in waits:
        trig = w["wait_for_trigger"][0]
        assert trig["event_type"] == "behaviour_monitor_alert"
        assert "id" in trig["event_data"]
        # Any same-id event ends the wait (a newer run took over, or cleared)
        assert "type" not in trig["event_data"]
