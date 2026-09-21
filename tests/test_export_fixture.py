import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_fixture import anonymise, rows_to_events  # noqa: E402


def test_anonymise_replaces_ids_and_rooms_consistently():
    specs = [
        {
            "entity_id": "binary_sensor.kitchen_motion_2",
            "category": "motion",
            "room": "Biddulph Road Kitchen",
        },
        {
            "entity_id": "sensor.kettle_power",
            "category": "plug",
            "room": "Biddulph Road Kitchen",
        },
        {
            "entity_id": "binary_sensor.hall_panic",
            "category": "panic",
            "room": "Biddulph Road Hall",
        },
    ]
    out, id_map, room_map = anonymise(specs)
    assert (
        out[0]["entity_id"] == "binary_sensor.motion_1"
        and out[1]["entity_id"] == "sensor.plug_1"
    )
    assert out[0]["room"] == out[1]["room"] == "Room 1" and out[2]["room"] == "Room 2"
    assert (
        id_map["sensor.kettle_power"] == "sensor.plug_1"
        and room_map["Biddulph Road Hall"] == "Room 2"
    )


def test_rows_to_events_sorted_and_mapped():
    rows = [
        [
            {
                "entity_id": "a",
                "state": "on",
                "last_changed": "2026-09-10T08:00:00+01:00",
            },
            {
                "entity_id": "a",
                "state": "off",
                "last_changed": "2026-09-10T08:01:00+01:00",
            },
        ],
        [
            {
                "entity_id": "b",
                "state": "12.5",
                "last_changed": "2026-09-10T07:59:00+01:00",
            }
        ],
    ]
    ev = rows_to_events(rows, {"a": "binary_sensor.motion_1", "b": "sensor.plug_1"})
    assert [e["e"] for e in ev] == [
        "sensor.plug_1",
        "binary_sensor.motion_1",
        "binary_sensor.motion_1",
    ]
    assert ev[0]["s"] == "12.5" and ev[1]["t"] == "2026-09-10T08:00:00+01:00"
