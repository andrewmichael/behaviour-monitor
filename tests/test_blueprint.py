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
    assert data["max"] == 200
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


def test_panic_button_skips_test_alerts():
    variables = [
        n["push_data"]
        for n in _walk(_load()["actions"])
        if isinstance(n, dict) and "push_data" in n
    ]
    assert variables
    assert "trigger.event.data.test" in variables[0]


def _repeat_branch() -> list:
    choose = _load()["actions"][0]["choose"]
    return next(
        c["sequence"]
        for c in choose
        if any("'opened'" in str(x.get("value_template", "")) for x in c["conditions"])
    )


def test_repeat_only_for_published_groups_and_int_interval():
    gate = next(n for n in _repeat_branch() if isinstance(n, dict) and "if" in n)
    templates = [c["value_template"] for c in gate["if"]]
    assert "{{ repeat_minutes | int(0) > 0 }}" in templates
    assert any("['attention', 'information']" in t for t in templates)
    assert "float" not in str(_load()["actions"])
    waits = [
        n
        for n in _walk(_load()["actions"])
        if isinstance(n, dict) and "wait_for_trigger" in n
    ]
    assert all("| int(" in w["timeout"]["minutes"] for w in waits)


def test_open_check_before_the_wait_and_before_every_repeat_push():
    gate = next(n for n in _repeat_branch() if isinstance(n, dict) and "if" in n)
    then = gate["then"]
    # Look the alert up first, and stop if it already closed.
    live = then[0]["variables"]["live"]
    assert "states.sensor" in live and "alert_id" in live and "snoozed" in live
    assert "'attention', 'information'" in live
    assert then[1]["if"][0]["value_template"] == (
        "{{ live == 'closed' and not real_panic | bool }}"
    )
    assert then[1]["then"] == [{"stop": "Alert closed"}]
    loop = then[2]["repeat"]["sequence"]
    assert "wait_for_trigger" in loop[0]
    after_wait = loop[1]["then"]
    # The same lookup runs again before every repeat push.
    assert after_wait[0]["variables"]["live"] == live
    assert after_wait[1]["then"] == [{"stop": "Alert closed"}]
    push = after_wait[2]
    # While snoozed only a panic repeats.
    assert push["if"][0]["value_template"] == "{{ live == 'open' or kind == 'panic' }}"
    assert isinstance(push["then"][0]["action"], _Input)


def test_a_real_panic_is_never_stopped_by_a_sensor_miss():
    """A late or unavailable sensor must not end a real panic after one push.

    Only a same-id event (cleared, or a newer run) ends a real panic's run;
    the closed check still applies to test alerts and every other kind.
    """
    seq = _repeat_branch()
    variables = next(n["variables"] for n in seq if "variables" in n)
    real = variables["real_panic"]
    assert "kind == 'panic'" in real and "not trigger.event.data.test" in real
    gate = next(n for n in seq if isinstance(n, dict) and "if" in n)
    then = gate["then"]
    stop_checks = [then[1]] + [
        n
        for n in then[2]["repeat"]["sequence"][1]["then"]
        if isinstance(n, dict) and n.get("then") == [{"stop": "Alert closed"}]
    ]
    assert len(stop_checks) == 2
    for check in stop_checks:
        assert check["if"][0]["value_template"] == (
            "{{ live == 'closed' and not real_panic | bool }}"
        )
    # Snooze still never silences a panic.
    push = then[2]["repeat"]["sequence"][1]["then"][-1]
    assert push["if"][0]["value_template"] == "{{ live == 'open' or kind == 'panic' }}"
