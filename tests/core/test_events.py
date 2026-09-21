from datetime import datetime, timezone

from custom_components.behaviour_monitor.core.events import (
    ACTIVITY_KINDS,
    UNAVAILABLE_STATES,
    ActivityEvent,
    Category,
    EventKind,
    HealthEvent,
)

TS = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)


def test_activity_kinds_are_the_person_signals():
    assert ACTIVITY_KINDS == frozenset(
        {
            EventKind.PRESENCE,
            EventKind.OPEN,
            EventKind.APPLIANCE_ON,
            EventKind.LIGHT_ON,
            EventKind.GENERIC,
        }
    )


def test_activity_event_is_activity_property():
    ev = ActivityEvent(
        "binary_sensor.k", Category.MOTION, EventKind.PRESENCE, "Kitchen", TS
    )
    assert ev.is_activity is True
    off = ActivityEvent(
        "binary_sensor.d",
        Category.CONTACT,
        EventKind.CLOSE,
        "Hall",
        TS,
        duration_s=12.0,
    )
    assert off.is_activity is False
    assert off.duration_s == 12.0


def test_panic_event_defaults_bypass_false_and_health_event_shape():
    ev = ActivityEvent(
        "binary_sensor.p", Category.PANIC, EventKind.PANIC, "Hall", TS, bypass=True
    )
    assert ev.bypass is True
    he = HealthEvent("binary_sensor.p", Category.PANIC, "Hall", TS, available=False)
    assert he.available is False
    assert "unavailable" in UNAVAILABLE_STATES and "unknown" in UNAVAILABLE_STATES
