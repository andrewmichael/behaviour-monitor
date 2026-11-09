"""Wires normaliser, models, health, drift and router. Drives on a supplied clock."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .alert_router import AlertRouter, DeliveryAction, RouterConfig
from .alerts import Alert, AlertClass, Severity
from .chain_model import ChainConfig, ChainModel
from .drift_detector import DriftConfig, DriftDetector
from .entity_routine import EntityRoutineModel, RoutineConfig
from .events import ActivityEvent, Category, HealthEvent
from .health_tracker import HealthConfig, HealthTracker
from .house_model import HouseConfig, HouseModel
from .normaliser import Normaliser, NormaliserConfig
from .slots import confidence, iso_day
from .whereabouts import Whereabouts, WhereaboutsConfig

# 2: chain pairs, steps and chains are keyed by three-hour time bucket,
# so a store written by schema 1 carries no usable chain learning.
# 3: whereabouts replaces the house inactivity alert; its learning comes
# from history, so the store is relearned from the recorder.
SCHEMA_VERSION = 3
# A poll gap this long may hide movement, so the stillness clock restarts.
POLL_GAP = timedelta(minutes=30)


def _no_gap(entity_id: str) -> float | None:
    """Stand-in for longest_gap while the models are still learning."""
    return None


@dataclass(frozen=True)
class EntitySpec:
    entity_id: str
    category: Category
    room: str


@dataclass(frozen=True)
class EngineConfig:
    normaliser: NormaliserConfig = field(default_factory=NormaliserConfig)
    house: HouseConfig = field(default_factory=HouseConfig)
    routine: RoutineConfig = field(default_factory=RoutineConfig)
    chain: ChainConfig = field(default_factory=ChainConfig)
    drift: DriftConfig = field(default_factory=DriftConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    whereabouts: WhereaboutsConfig = field(default_factory=WhereaboutsConfig)
    learning_days: int = 14
    window_days: int = 28

    @classmethod
    def from_options(cls, o: dict[str, Any]) -> "EngineConfig":
        ld = int(o.get("learning_days", 14))
        wd = int(o.get("window_days", 28))
        return cls(
            normaliser=NormaliserConfig(
                motion_debounce_s=float(o.get("motion_debounce_s", 90)),
                plug_margin_w=float(o.get("plug_margin_w", 5)),
            ),
            house=HouseConfig(learning_days=ld, window_days=wd),
            routine=RoutineConfig(learning_days=ld, window_days=wd),
            chain=ChainConfig(
                window_s=float(o.get("chain_window_s", 1800)),
                learning_days=ld,
                window_days=wd,
            ),
            drift=DriftConfig(
                sensitivity=str(o.get("drift_sensitivity", "medium")), window_days=wd
            ),
            health=HealthConfig(grace_s=float(o.get("health_grace_s", 900))),
            router=RouterConfig(
                attention_min_severity=Severity(
                    str(o.get("attention_min_severity", "medium"))
                ),
                timing_promote_days=int(o.get("timing_promote_days", 7)),
            ),
            whereabouts=WhereaboutsConfig(
                outside_doors=frozenset(o.get("outside_doors") or ()),
                sitting_appliances=frozenset(o.get("sitting_appliances") or ()),
                bedrooms=(
                    frozenset(o["bedrooms"]) if o.get("bedrooms") is not None else None
                ),
            ),
            learning_days=ld,
            window_days=wd,
        )


class Engine:
    def __init__(self, config: EngineConfig, entities: list[EntitySpec]) -> None:
        self._cfg = config
        self._specs: dict[str, EntitySpec] = {}
        self._normaliser = Normaliser(config.normaliser)
        self._house = HouseModel(config.house)
        self._routines = EntityRoutineModel(config.routine)
        self._chains = ChainModel(config.chain)
        self._drift = DriftDetector(config.drift)
        self._health = HealthTracker(config.health)
        self._router = AlertRouter(config.router)
        self._where = Whereabouts(config.whereabouts)
        self._last_poll: datetime | None = None
        self._holiday = False
        self._holiday_just_ended = False
        self._snooze_until: datetime | None = None
        self._last_poll_day: date | None = None
        self._first_observation: datetime | None = None
        self._today_count = 0
        self._today: date | None = None
        self._last_stat: list[Alert] = []
        self._degraded = False
        self.set_entities(entities)

    # ------------------------------------------------------------ entities

    def set_entities(self, entities: list[EntitySpec]) -> tuple[set[str], set[str]]:
        new = {s.entity_id: s for s in entities}
        added = set(new) - set(self._specs)
        removed = set(self._specs) - set(new)
        for eid in removed:
            self._routines.remove(eid)
            self._health.remove(eid)
            self._normaliser.forget(eid)
            self._drift.remove_prefix(f"count:{eid}")
            self._drift.remove_prefix(f"open:{eid}")
            self._drift.remove_prefix(f"dwell:{eid}")
        for eid, s in new.items():
            old = self._specs.get(eid)
            if old is not None and old.category != s.category:
                self._routines.remove(eid)
                self._health.remove(eid)
                self._normaliser.forget(eid)
                added.add(eid)
            self._routines.add(eid, s.category, s.room)
            self._health.register(eid, s.category, s.room)
        self._specs = new
        return added, removed

    def rename_room(self, old: str, new: str) -> None:
        self._chains.rename_room(old, new)
        self._specs = {
            k: EntitySpec(v.entity_id, v.category, new if v.room == old else v.room)
            for k, v in self._specs.items()
        }
        for s in self._specs.values():
            self._routines.add(s.entity_id, s.category, s.room)
            self._health.register(s.entity_id, s.category, s.room)

    # -------------------------------------------------------------- state

    @property
    def holiday(self) -> bool:
        return self._holiday

    @holiday.setter
    def holiday(self, value: bool) -> None:
        value = bool(value)
        if self._holiday and not value:
            self._holiday_just_ended = True
        self._holiday = value

    @property
    def snooze_until(self) -> datetime | None:
        return self._snooze_until

    @snooze_until.setter
    def snooze_until(self, value: datetime | None) -> None:
        self._snooze_until = value

    def is_snoozed(self, now: datetime) -> bool:
        return self._snooze_until is not None and now < self._snooze_until

    def clear_panic(self, alert_id: str | None, now: datetime) -> list[DeliveryAction]:
        return self._router.clear_panic(alert_id, now)

    def reminders(self, reason: str) -> list[DeliveryAction]:
        return self._router.reminders(reason)

    def submit_test(self, now: datetime) -> list[DeliveryAction]:
        """Test alert: never touches other open alerts."""
        return self._router.submit_test(now)

    def reset(self, entity_id: str | None = None) -> None:
        if entity_id is None:
            specs = list(self._specs.values())
            # Re-initialising throws away every field, including the two the
            # user set deliberately. Resetting what was learned must not
            # silently take the site off holiday or cancel a snooze.
            holiday, snooze_until = self._holiday, self._snooze_until
            self.__init__(self._cfg, specs)  # type: ignore[misc]
            self._holiday = holiday
            self._snooze_until = snooze_until
            return
        s = self._specs.get(entity_id)
        if s is None:
            return
        self._routines.remove(entity_id)
        self._routines.add(entity_id, s.category, s.room)
        self._normaliser.forget(entity_id)
        for p in ("count:", "open:", "dwell:"):
            self._drift.remove_prefix(f"{p}{entity_id}")

    # -------------------------------------------------------------- events

    def handle_state(
        self,
        entity_id: str,
        old: str | None,
        new: str,
        ts: datetime,
        learn_only: bool = False,
    ) -> list[DeliveryAction]:
        spec = self._specs.get(entity_id)
        if spec is None:
            return []
        actions: list[DeliveryAction] = []
        events = self._normaliser.handle(
            entity_id, spec.category, spec.room, old, new, ts
        )
        for ev in events:
            if isinstance(ev, HealthEvent):
                self._health.record_health(ev)
                continue
            if ev.bypass:
                if not learn_only:
                    actions.extend(self._router.submit_panic(ev, ts))
                continue
            self._learn(ev)
        return actions

    def _learn(self, ev: ActivityEvent) -> None:
        if self._holiday:
            return
        if self._first_observation is None and ev.is_activity:
            self._first_observation = ev.timestamp
        if ev.is_activity:
            if self._today != ev.timestamp.date():
                self._today, self._today_count = ev.timestamp.date(), 0
            self._today_count += 1
        self._house.record(ev)
        self._where.record(ev)
        self._routines.record(ev)
        self._chains.record(ev)
        self._health.record_activity(ev)

    # ---------------------------------------------------------------- poll

    def poll(self, now: datetime) -> list[DeliveryAction]:
        for ev in self._normaliser.flush(now):
            self._learn(ev)
        # She may have moved while nothing was fed in. Flushed events come
        # first: they predate ``now`` and a moved clock would drop them. The
        # first poll back from holiday restarts every clock below anyway.
        if (
            self._last_poll is not None
            and now - self._last_poll >= POLL_GAP
            and not self._holiday_just_ended
        ):
            self._where.restart_clock(now, keep_anchored=True)
        self._last_poll = now

        if self._holiday:
            # No rollover while paused: there is nothing learned to finalise,
            # and running it would record zero daily counts into drift.
            self._last_poll_day = now.date()
        elif self._holiday_just_ended:
            # First poll back: the pause must not look like a stale multi-day
            # gap to rollover either, so skip it here too and pick back up
            # cleanly from today. Every clock that tracks "since when have I
            # been quiet" needs to restart, or the pause itself looks like an
            # anomaly to every downstream detector.
            self._house.restart_clock(now)
            self._where.restart_clock(now)
            self._chains.clear_runs()
            self._routines.restart_clock(now)
            self._health.restart_clock(now)
            self._last_poll_day = now.date()
            self._holiday_just_ended = False
        else:
            if self._last_poll_day is not None and now.date() != self._last_poll_day:
                day = self._last_poll_day
                while day < now.date():
                    self._finalise_day(day, now)
                    day += timedelta(days=1)
                self._chains.recompute()
                cutoff = now.date() - timedelta(days=self._cfg.window_days)
                self._house.prune(cutoff)
                self._where.prune(cutoff)
                self._routines.prune(cutoff)
                self._chains.prune(cutoff)
                self._drift.prune(cutoff)
            self._last_poll_day = now.date()

        learned = confidence(self._days_seen(), self._cfg.learning_days) >= 1.0
        alerts: list[Alert] = []
        alerts.extend(
            self._health.evaluate(
                now,
                # Before the learning period is up, "longest gap" only means
                # "longest so far", so the first time any entity idles longer
                # than it has before it looks silent. Withhold the measure
                # until it means something.
                self._routines.longest_gap if learned else _no_gap,
                self._house.last_activity,
            )
        )
        # On holiday nothing is suppressed for want of sensors: nothing is
        # raised at all, so the site must not read as degraded either.
        live = 1.0 if self._holiday else self._health.live_fraction(now)
        names = self.drift_names()
        where = self._where.evaluate(now, live, names=lambda eid: names.get(eid, eid))
        if learned and not self._holiday:
            if where.alert is not None:
                alerts.append(where.alert)
            alerts.extend(self._routines.evaluate(now))
            alerts.extend(self._chains.evaluate(now))
            alerts.extend(self._last_stat)
        self._degraded = where.degraded
        return self._router.submit(
            alerts, now, snoozed=self.is_snoozed(now), holiday=self._holiday
        )

    def _finalise_day(self, day: date, now: datetime) -> None:
        """Record one finished day's stats into drift and check for anomalies.

        Skips days with no activity anywhere (e.g. an offline gap, or a day a
        multi-day poll gap walks past with genuinely nothing recorded), so an
        empty day never gets written into drift as a false zero.
        """
        if self._house.rooms_visited(day):
            for eid, count in self._routines.daily_counts(day).items():
                self._drift.record(
                    f"count:{eid}", day, float(count), split_day_type=True
                )
            for eid, med in self._routines.daily_duration_medians(day).items():
                spec = self._specs.get(eid)
                key = "open" if spec and spec.category is Category.CONTACT else "dwell"
                self._drift.record(f"{key}:{eid}", day, med)
            for name, secs in self._chains.completions_for_day(day).items():
                self._drift.record(f"chain:{name}", day, secs, split_day_type=True)
            self._drift.record(
                "rooms",
                day,
                float(len(self._house.rooms_visited(day))),
                split_day_type=True,
            )
        # Always reassign: a day with nothing to say must clear yesterday's
        # alerts rather than leave them being resubmitted every poll.
        self._last_stat = self._drift.check(day, now, names=self.drift_names())

    def drift_names(self) -> dict[str, str]:
        """Readable names for drift explanations: room plus sensor type.

        Two sensors of one type in one room fall back to their entity id,
        tidied ("binary_sensor.back_door_door" reads as "Back door").
        """
        base = {
            eid: f"{s.room} {_NOUNS.get(s.category, 'sensor')}"
            for eid, s in self._specs.items()
        }
        taken = Counter(base.values())
        return {
            eid: name if taken[name] == 1 else _tidy_entity_id(eid)
            for eid, name in base.items()
        }

    # ------------------------------------------------------------ snapshot

    def _days_seen(self) -> int:
        """Days the house actually saw activity, not days on the calendar.

        An engine that was offline, or a site that was empty, has not learned
        anything on those days and must not be credited for them.
        """
        return self._house.days_observed

    def snapshot(self, now: datetime) -> dict[str, Any]:
        days = self._days_seen()
        conf = confidence(days, self._cfg.learning_days)
        sev = self._router.attention_severity
        if conf < 1.0:
            status = "learning"
        elif self._degraded:
            status = "degraded"
        else:
            status = sev.value if sev else "ok"
        open_alerts = self._router.open_alerts
        published = self._router.published()
        attention = [p for p in published if p["group"] == "attention"]
        information = [p for p in published if p["group"] == "information"]
        assessment_gap = (
            (now - self._house.last_activity).total_seconds()
            if self._house.last_activity
            else None
        )
        # Evaluating changes nothing, so the snapshot reads it fresh for ``now``.
        w = self._where.evaluate(now)
        return {
            "welfare": {
                "status": status,
                "reasons": [a["explanation"] for a in attention],
                "attention": attention,
                "information": information,
            },
            "house": {
                "last_activity": (
                    self._house.last_activity.isoformat()
                    if self._house.last_activity
                    else None
                ),
                "last_room": self._house.last_room,
                "gap_s": assessment_gap,
                "expected_s": (
                    self._house.expected_gap(self._house.last_activity)
                    if self._house.last_activity
                    else None
                ),
                "rooms_today": sorted(self._house.rooms_visited(now.date())),
                "daily_count": self._today_count if self._today == now.date() else 0,
            },
            "whereabouts": {
                "where": w.where.value if w.where else None,
                "where_since": w.since.isoformat() if w.since else None,
                "last_room": w.room,
                "limit_min": w.limit_min,
            },
            "anomalies": [
                a.to_dict() for a in open_alerts if a.cls is AlertClass.STATISTICAL
            ],
            "health": {
                "states": self._health.entity_states(now),
                "dropouts_today": self._health.sitewide_dropouts_today(now.date()),
                "alerts": [
                    a.to_dict() for a in open_alerts if a.cls is AlertClass.HEALTH
                ],
            },
            "learning": {
                "confidence": round(conf * 100, 1),
                "days_seen": days,
                "days_remaining": max(0, self._cfg.learning_days - days),
                "first_observation": (
                    self._first_observation.isoformat()
                    if self._first_observation
                    else None
                ),
                "models": {
                    "house": round(self._house.confidence(now), 2),
                    "routines": round(self._routines.confidence(now), 2),
                    "chains": round(self._chains.confidence(now), 2),
                },
            },
            "entities": {
                eid: {
                    "category": s.category.value,
                    "room": s.room,
                    "last_seen": (
                        le.isoformat()
                        if (le := self._routines.last_event(eid))
                        else None
                    ),
                    "expected_hours": self._routines.expected_windows(
                        eid, now.weekday()
                    ),
                    "health": self._health.entity_states(now).get(eid, "ok"),
                }
                for eid, s in self._specs.items()
            },
            "chains": [
                {
                    "name": c.name,
                    "rooms": c.rooms,
                    "hop_median_s": [h[0] for h in c.hop_stats],
                }
                for c in self._chains.chains
            ],
            "holiday": self._holiday,
            "snooze_until": (
                self._snooze_until.isoformat() if self._snooze_until else None
            ),
            "snoozed": self.is_snoozed(now),
        }

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "normaliser": self._normaliser.to_dict(),
            "house": self._house.to_dict(),
            "whereabouts": self._where.to_dict(),
            "routines": self._routines.to_dict(),
            "chains": self._chains.to_dict(),
            "drift": self._drift.to_dict(),
            "health": self._health.to_dict(),
            "router": self._router.to_dict(),
            "last_stat": [a.to_dict() for a in self._last_stat],
            "meta": {
                "holiday": self._holiday,
                "holiday_just_ended": self._holiday_just_ended,
                "snooze_until": (
                    self._snooze_until.isoformat() if self._snooze_until else None
                ),
                "last_poll_day": (
                    iso_day(self._last_poll_day) if self._last_poll_day else None
                ),
                "first_observation": (
                    self._first_observation.isoformat()
                    if self._first_observation
                    else None
                ),
                "today": iso_day(self._today) if self._today else None,
                "today_count": self._today_count,
                "last_poll": self._last_poll.isoformat() if self._last_poll else None,
            },
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], config: EngineConfig, entities: list[EntitySpec]
    ) -> "Engine":
        e = cls(config, entities)
        if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
            return e
        e._normaliser = Normaliser.from_dict(
            data.get("normaliser", {}), config.normaliser
        )
        e._house = HouseModel.from_dict(data.get("house", {}), config.house)
        e._where = Whereabouts.from_dict(
            data.get("whereabouts", {}), config.whereabouts
        )
        e._routines = EntityRoutineModel.from_dict(
            data.get("routines", {}), config.routine
        )
        e._chains = ChainModel.from_dict(data.get("chains", {}), config.chain)
        e._drift = DriftDetector.from_dict(data.get("drift", {}), config.drift)
        e._health = HealthTracker.from_dict(data.get("health", {}), config.health)
        e._router = AlertRouter.from_dict(data.get("router", {}), config.router)
        try:
            m = data.get("meta", {})
            e._holiday = bool(m.get("holiday", False))
            e._holiday_just_ended = bool(m.get("holiday_just_ended", False))
            e._snooze_until = (
                datetime.fromisoformat(m["snooze_until"])
                if m.get("snooze_until")
                else None
            )
            e._last_poll_day = (
                date.fromisoformat(m["last_poll_day"])
                if m.get("last_poll_day")
                else None
            )
            e._first_observation = (
                datetime.fromisoformat(m["first_observation"])
                if m.get("first_observation")
                else None
            )
            e._today = date.fromisoformat(m["today"]) if m.get("today") else None
            e._today_count = int(m.get("today_count", 0))
            e._last_poll = (
                datetime.fromisoformat(m["last_poll"]) if m.get("last_poll") else None
            )
            e._last_stat = [Alert.from_dict(a) for a in data.get("last_stat", [])]
        except (KeyError, TypeError, ValueError):
            pass
        # set_entities below only sees removals against what _specs already
        # holds, which cls(config, entities) already set to the new entity
        # list, so a no-longer-configured entity restored into the freshly
        # loaded models would never be dropped without this.
        orphans = set(e._routines.entity_ids) - {s.entity_id for s in entities}
        for eid in orphans:
            e._routines.remove(eid)
            e._health.remove(eid)
            e._normaliser.forget(eid)
            e._drift.remove_prefix(f"count:{eid}")
            e._drift.remove_prefix(f"open:{eid}")
            e._drift.remove_prefix(f"dwell:{eid}")
        e.set_entities(entities)
        return e


_NOUNS: dict[Category, str] = {
    Category.MOTION: "motion",
    Category.CONTACT: "door",
    Category.PLUG: "plug",
    Category.PANIC: "panic button",
    Category.LIGHT: "light",
    Category.OTHER: "sensor",
}


def _tidy_entity_id(entity_id: str) -> str:
    words: list[str] = []
    for w in entity_id.split(".", 1)[-1].split("_"):
        if w and (not words or words[-1] != w):
            words.append(w)
    return " ".join(words).capitalize()
