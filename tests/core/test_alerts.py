from datetime import datetime, timezone

from custom_components.behaviour_monitor.core.alerts import Alert, AlertClass, Severity

TS = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)


def test_severity_ordering_and_bump():
    assert Severity.LOW < Severity.MEDIUM < Severity.HIGH < Severity.CRITICAL
    assert Severity.LOW.bump() is Severity.MEDIUM
    assert Severity.CRITICAL.bump() is Severity.CRITICAL
    assert Severity.HIGH.at_least(Severity.MEDIUM) is True
    assert Severity.LOW.at_least(Severity.MEDIUM) is False


def test_alert_key_and_to_dict():
    a = Alert(
        AlertClass.WELFARE,
        "house",
        "inactivity",
        Severity.MEDIUM,
        "No activity",
        TS,
        {"ratio": 6.2},
    )
    assert a.key == "welfare:house:inactivity"
    d = a.to_dict()
    assert d["class"] == "welfare"
    assert d["severity"] == "medium"
    assert d["raised_at"] == TS.isoformat()
    assert d["details"] == {"ratio": 6.2}
