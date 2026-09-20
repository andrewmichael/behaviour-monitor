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
    assert m.evaluate(day + timedelta(minutes=6)) == []
    notes = m.evaluate(
        day + timedelta(minutes=20)
    )  # 240s median, 0 mad -> tolerance falls back to window
    assert notes == [] or notes[0].kind == "chain_stall"
    notes = m.evaluate(day + timedelta(minutes=25))
    assert len(notes) == 1
    n = notes[0]
    assert n.cls is AlertClass.STATISTICAL and n.kind == "chain_stall"
    assert n.source == "Bedroom → Bathroom → Kitchen"
    assert n.details == {"missing": "Kitchen", "step": 2}
    # stall persists for its ttl then clears
    assert len(m.evaluate(day + timedelta(minutes=30))) == 1
    assert m.evaluate(day + timedelta(minutes=25 + 61)) == []


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
    m2.prune(date(2026, 12, 1))
    m2.recompute()
    assert m2.chains == []
    assert ChainModel.from_dict({"nope": 1}, CFG).chains == []


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
