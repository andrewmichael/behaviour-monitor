"""Wires normaliser, models, health, drift and router. Drives on a supplied clock."""

from __future__ import annotations

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
from .house_model import HouseAssessment, HouseConfig, HouseModel
from .normaliser import Normaliser, NormaliserConfig
from .slots import confidence, iso_day

# 2: chain pairs, steps and chains are keyed by three-hour time bucket,
# so a store written by schema 1 carries no usable chain learning.
SCHEMA_VERSION = 2


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
    learning_days: int = 14
    window_days: int = 28

    @classmethod
    def from_options(cls, o: dict[str, Any]) -> "EngineConfig":
        ld = int(o.get("learning_days", 14))
        wd = int(o.get("window_days", 28))
        low = float(o.get("house_low_ratio", 3.0))
        return cls(
            normaliser=NormaliserConfig(
                motion_debounce_s=float(o.get("motion_debounce_s", 90)),
                plug_margin_w=float(o.get("plug_margin_w", 5)),
            ),
            house=HouseConfig(
                learning_days=ld,
                window_days=wd,
                low_ratio=low,
                medium_ratio=low * 2,
                high_ratio=low * 4,
            ),
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
                push_min_severity=Severity(str(o.get("push_min_severity", "medium"))),
                push_repeat_s=float(o.get("push_repeat_s", 1800)),
                timing_promote_days=int(o.get("timing_promote_days", 7)),
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

    def acknowledge(self, now: datetime) -> None:
        self._router.acknowledge(now)

    def reset(self, entity_id: str | None = None) -> None:
        if entity_id is None:
            specs = list(self._specs.values())
            self.__init__(self._cfg, specs)  # type: ignore[misc]
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
        self._routines.record(ev)
        self._chains.record(ev)
        self._health.record_activity(ev)

    # ---------------------------------------------------------------- poll

    def poll(self, now: datetime) -> list[DeliveryAction]:
        for ev in self._normaliser.flush(now):
            self._learn(ev)

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
                self._routines.prune(cutoff)
                self._chains.prune(cutoff)
                self._drift.prune(cutoff)
            self._last_poll_day = now.date()

        alerts: list[Alert] = []
        alerts.extend(
            self._health.evaluate(
                now, self._routines.longest_gap, self._house.last_activity
            )
        )
        learned = confidence(self._days_seen(), self._cfg.learning_days) >= 1.0
        if self._holiday:
            assessment = HouseAssessment(
                None, None, None, None, False, self._house.last_room
            )
        else:
            live = self._health.live_fraction(now)
            assessment = self._house.evaluate(now, live_fraction=live)
        if learned and not self._holiday:
            if assessment.severity is not None:
                hours = (assessment.gap_s or 0) / 3600
                alerts.append(
                    Alert(
                        AlertClass.WELFARE,
                        "house",
                        "inactivity",
                        assessment.severity,
                        f"No activity anywhere for {hours:.1f} h; last seen in "
                        f"{assessment.last_room} (usual gap "
                        f"{((assessment.expected_s or 0) / 60):.0f} min)",
                        now,
                        {
                            "gap_s": assessment.gap_s,
                            "expected_s": assessment.expected_s,
                            "ratio": assessment.ratio,
                            "last_room": assessment.last_room,
                        },
                    )
                )
            alerts.extend(self._routines.evaluate(now))
            alerts.extend(self._chains.evaluate(now))
            alerts.extend(self._last_stat)
        self._degraded = assessment.degraded
        return self._router.submit(
            alerts, now, snoozed=self.is_snoozed(now), holiday=self._holiday
        )

    def _finalise_day(self, day: date, now: datetime) -> None:
        """Record one finished day's stats into drift and check for anomalies.

        Skips days with no activity anywhere (e.g. an offline gap, or a day a
        multi-day poll gap walks past with genuinely nothing recorded), so an
        empty day never gets written into drift as a false zero.
        """
        if not self._house.rooms_visited(day):
            return
        for eid, count in self._routines.daily_counts(day).items():
            self._drift.record(f"count:{eid}", day, float(count), split_day_type=True)
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
        self._last_stat = self._drift.check(day, now)

    # ------------------------------------------------------------ snapshot

    def _days_seen(self) -> int:
        if self._first_observation is None:
            return 0
        last = self._last_poll_day or self._first_observation.date()
        return max(0, (last - self._first_observation.date()).days)

    def snapshot(self, now: datetime) -> dict[str, Any]:
        days = self._days_seen()
        conf = confidence(days, self._cfg.learning_days)
        sev = self._router.welfare_severity
        if conf < 1.0:
            status = "learning"
        elif self._degraded:
            status = "degraded"
        else:
            status = sev.value if sev else "ok"
        open_alerts = self._router.open_alerts
        assessment_gap = (
            (now - self._house.last_activity).total_seconds()
            if self._house.last_activity
            else None
        )
        return {
            "welfare": {
                "status": status,
                "reasons": [
                    a.explanation for a in open_alerts if a.cls is AlertClass.WELFARE
                ],
                "open_alerts": [a.to_dict() for a in open_alerts],
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
        }

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "normaliser": self._normaliser.to_dict(),
            "house": self._house.to_dict(),
            "routines": self._routines.to_dict(),
            "chains": self._chains.to_dict(),
            "drift": self._drift.to_dict(),
            "health": self._health.to_dict(),
            "router": self._router.to_dict(),
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
