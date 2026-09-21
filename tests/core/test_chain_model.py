from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import AlertClass
from custom_components.behaviour_monitor.core.chain_model import ChainConfig, ChainModel
from custom_components.behaviour_monitor.core.events import (
    ActivityEvent,
    Category,
    EventKind,
)

MON = datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc)
CFG = ChainConfig(min_count=5, lift=1.5)


def _ev(ts: datetime, room: str, eid: str = "x") -> ActivityEvent:
    return ActivityEvent(
        f"binary_sensor.{eid}", Category.MOTION, EventKind.PRESENCE, room, ts
    )


def _morning(m: ChainModel, day: datetime, hop_min: float = 4.0) -> None:
    """Bedroom -> Bathroom -> Kitchen with two kitchen sensors and a filler visit."""
    t = day
    m.record(_ev(t, "Bedroom"))
    t += timedelta(minutes=hop_min)
    m.record(_ev(t, "Bathroom"))
    t += timedelta(minutes=hop_min)
    m.record(_ev(t, "Kitchen", "kmotion"))
    m.record(
        _ev(t + timedelta(seconds=30), "Kitchen", "kettle")
    )  # same room: no new step
    # afternoon noise: kitchen <-> lounge back and forth, outside the window from the morning
    t += timedelta(hours=6)
    m.record(_ev(t, "Lounge"))
    m.record(_ev(t + timedelta(minutes=3), "Kitchen"))


def _trained(days: int = 14) -> ChainModel:
    m = ChainModel(CFG)
    for d in range(days):
        _morning(m, MON + timedelta(days=d))
    m.recompute()
    return m


def test_learns_bedroom_bathroom_kitchen_chain():
    m = _trained()
    names = [c.name for c in m.chains]
    assert "Bedroom → Bathroom → Kitchen" in names
    chain = next(c for c in m.chains if c.name.startswith("Bedroom"))
    assert chain.rooms == ["Bedroom", "Bathroom", "Kitchen"]
    assert chain.hop_stats[0][0] == 240.0  # median hop seconds
    assert len(chain.hop_stats) == 2


def test_chains_are_learned_per_time_bucket():
    """A nightly Bedroom -> Bathroom -> Bedroom trip must not swallow the
    morning Bedroom -> Bathroom -> Kitchen routine, and must not open a run
    for it either."""
    m = ChainModel(CFG)
    for d in range(14):
        day = MON + timedelta(days=d)
        night = day.replace(hour=0, minute=30)
        m.record(_ev(night, "Bedroom"))
        m.record(_ev(night + timedelta(minutes=4), "Bathroom"))
        m.record(_ev(night + timedelta(minutes=8), "Bedroom"))
        _morning(m, day)
    m.recompute()
    chain = next(c for c in m.chains if c.name == "Bedroom → Bathroom → Kitchen")
    assert chain.buckets == {2}  # 06:00-09:00 only
    # a night step into the first room is in bucket 0: no run, so no stall
    night = (MON + timedelta(days=14)).replace(hour=0, minute=30)
    m.record(_ev(night, "Bedroom"))
    assert m.evaluate(night + timedelta(hours=1)) == []


def test_same_room_events_do_not_create_pairs():
    m = _trained()
    assert all("Kitchen → Kitchen" not in c.name for c in m.chains)


def test_completed_run_records_duration_for_the_day():
    m = _trained()
    day = MON + timedelta(days=14)
    _morning(m, day)
    comps = m.completions_for_day(date(2026, 10, 5))
    assert comps["Bedroom → Bathroom → Kitchen"] == 480.0


def test_stall_raises_note_naming_missing_room():
    m = _trained()
    day = MON + timedelta(days=14)
    m.record(_ev(day, "Bedroom"))
    m.record(_ev(day + timedelta(minutes=4), "Bathroom"))
    # 240 s median, 0 mad -> tolerance is max(240, 720, 2 * 1800) = 3600 s,
    # measured from the step into the Bathroom at +4 min
    assert m.evaluate(day + timedelta(minutes=6)) == []
    assert m.evaluate(day + timedelta(minutes=25)) == []
    assert m.evaluate(day + timedelta(minutes=60)) == []
    notes = m.evaluate(day + timedelta(minutes=65))
    assert len(notes) == 1
    n = notes[0]
    assert n.cls is AlertClass.STATISTICAL and n.kind == "chain_stall"
    assert n.source == "Bedroom → Bathroom → Kitchen"
    assert n.details == {"missing": "Kitchen", "step": 2}
    # nothing else happens, so the stall stands until the six-hour safety cap
    assert len(m.evaluate(day + timedelta(minutes=70))) == 1
    assert len(m.evaluate(day + timedelta(hours=3))) == 1
    assert m.evaluate(day + timedelta(minutes=65, hours=6, seconds=60)) == []


def test_stall_clears_on_next_step():
    m = _trained()
    day = MON + timedelta(days=14)
    m.record(_ev(day, "Bedroom"))
    m.record(_ev(day + timedelta(minutes=4), "Bathroom"))
    assert len(m.evaluate(day + timedelta(minutes=65))) == 1
    # the person moved, so the stalled routine is moot well before the cap
    m.record(_ev(day + timedelta(minutes=70), "Lounge"))
    assert m.evaluate(day + timedelta(minutes=71)) == []


def test_clear_runs_drops_open_runs_and_stalls():
    m = _trained()
    day = MON + timedelta(days=14)
    m.record(_ev(day, "Bedroom"))
    m.record(_ev(day + timedelta(minutes=4), "Bathroom"))
    m.clear_runs()
    assert m.evaluate(day + timedelta(days=10)) == []


def test_rename_room_keeps_counts():
    m = _trained()
    m.rename_room("Bathroom", "Washroom")
    m.recompute()
    assert any(c.rooms == ["Bedroom", "Washroom", "Kitchen"] for c in m.chains)


def test_round_trip_and_prune():
    m = _trained()
    m2 = ChainModel.from_dict(m.to_dict(), CFG)
    assert [c.name for c in m2.chains] == [c.name for c in m.chains]
    # buckets decide whether a step opens a run, so they must survive the trip
    assert [c.buckets for c in m2.chains] == [c.buckets for c in m.chains]
    assert m2.to_dict()["steps_into"] == m.to_dict()["steps_into"]
    assert m2.to_dict()["total_steps"] == m.to_dict()["total_steps"]
    # and the restored model still tracks a live run through to completion
    day = MON + timedelta(days=14)
    _morning(m2, day)
    assert m2.completions_for_day(date(2026, 10, 5))[
        "Bedroom → Bathroom → Kitchen"
    ] == (480.0)
    m2.prune(date(2026, 12, 1))
    m2.recompute()
    assert m2.chains == []
    assert ChainModel.from_dict({"nope": 1}, CFG).chains == []


def test_prune_decrements_step_counts():
    """Step counts are the lift denominator, so they must age out too."""
    m = _trained()
    before = m.to_dict()
    assert before["total_steps"]["2"] > 0
    m.prune(MON.date() + timedelta(days=7))
    after = m.to_dict()
    assert after["total_steps"]["2"] < before["total_steps"]["2"]
    m.prune(MON.date() + timedelta(days=99))
    assert m.to_dict()["steps_into"] == [] and m.to_dict()["total_steps"] == {}


def test_from_dict_tolerates_pre_bucket_store():
    """A store written before chains were bucketed loads as a fresh model."""
    old = {
        "pairs": [{"a": "X", "b": "Y", "count": 3, "hops": []}],
        "steps_into": {"X": 3},
        "total_steps": 3,
        "chains": [],
    }
    m = ChainModel.from_dict(old, CFG)
    assert m.chains == []
    assert m.to_dict()["pairs"] == [] and m.to_dict()["total_steps"] == {}


def test_prune_keeps_counts_exact_when_hops_overflow():
    m = ChainModel(CFG)
    day_starts = [MON + timedelta(days=d) for d in range(5)]
    for day_start in day_starts:
        for i in range(50):
            t = day_start + timedelta(minutes=i * 3)
            m.record(_ev(t, "Bedroom"))
            m.record(_ev(t + timedelta(minutes=1), "Bathroom"))
            m.record(_ev(t + timedelta(minutes=2), "Lounge"))
    m.recompute()

    def _pair_count() -> int:
        """Bedroom -> Bathroom across every time bucket it was seen in."""
        return sum(
            sum(p["days"].values())
            for p in m.to_dict()["pairs"]
            if p["a"] == "Bedroom" and p["b"] == "Bathroom"
        )

    assert _pair_count() == 250
    m.prune(day_starts[2].date())
    assert _pair_count() == 150
    m.prune(day_starts[-1].date() + timedelta(days=1))
    assert _pair_count() == 0
