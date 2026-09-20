"""Open alert set, escalation, promotion and class-based delivery actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent

_NOTE_KINDS = {"routine_missed", "chain_stall"}


@dataclass(frozen=True)
class RouterConfig:
    push_min_severity: Severity = Severity.MEDIUM
    push_repeat_s: float = 1800.0
    timing_promote_days: int = 7


@dataclass(frozen=True)
class DeliveryAction:
    action: str
    alert: Alert


@dataclass
class _Open:
    alert: Alert
    opened_at: datetime
    last_push: datetime | None = None
    acknowledged: bool = False
    panic: bool = False


class AlertRouter:
    def __init__(self, config: RouterConfig) -> None:
        self._cfg = config
        self._open: dict[str, _Open] = {}

    # ------------------------------------------------------------ properties

    @property
    def open_alerts(self) -> list[Alert]:
        return [o.alert for o in self._open.values()]

    @property
    def welfare_severity(self) -> Severity | None:
        sevs = [
            o.alert.severity
            for o in self._open.values()
            if o.alert.cls is AlertClass.WELFARE
        ]
        return max(sevs) if sevs else None

    # --------------------------------------------------------------- submit

    def submit(
        self,
        alerts: list[Alert],
        now: datetime,
        snoozed: bool = False,
        holiday: bool = False,
    ) -> list[DeliveryAction]:
        incoming = self._combine(
            [a for a in alerts if not (holiday and a.cls is not AlertClass.HEALTH)], now
        )
        actions: list[DeliveryAction] = []
        seen: set[str] = set()
        for alert in incoming:
            seen.add(alert.key)
            cur = self._open.get(alert.key)
            if cur is None:
                self._open[alert.key] = _Open(alert, now)
                actions.extend(self._on_open(alert, now, snoozed))
            else:
                rose = alert.severity > cur.alert.severity
                cur.alert = alert
                if rose and alert.cls is AlertClass.WELFARE:
                    cur.acknowledged = False
                    actions.extend(self._push(cur, now, snoozed))
                elif rose and alert.cls is AlertClass.STATISTICAL and not snoozed:
                    actions.append(DeliveryAction("log", alert))
        for key in list(self._open):
            o = self._open[key]
            if key in seen or (o.panic and not o.acknowledged):
                continue
            del self._open[key]
            actions.extend(self._on_clear(o, snoozed or holiday))
        for o in self._open.values():
            if (
                o.alert.cls is AlertClass.WELFARE
                and not o.acknowledged
                and o.alert.severity.at_least(self._cfg.push_min_severity)
            ):
                if (
                    o.last_push is not None
                    and (now - o.last_push).total_seconds() >= self._cfg.push_repeat_s
                ):
                    actions.extend(self._push(o, now, snoozed))
        return actions

    def submit_panic(self, event: ActivityEvent, now: datetime) -> list[DeliveryAction]:
        alert = Alert(
            AlertClass.WELFARE,
            event.entity_id,
            "panic",
            Severity.CRITICAL,
            f"{event.room}: panic button pressed",
            now,
            {"room": event.room},
        )
        o = _Open(alert, now, panic=True)
        self._open[alert.key] = o
        return self._push(o, now, snoozed=False)

    def acknowledge(self, now: datetime) -> None:
        for o in self._open.values():
            if o.alert.cls is AlertClass.WELFARE:
                o.acknowledged = True

    # ------------------------------------------------------------ combining

    def _combine(self, alerts: list[Alert], now: datetime) -> list[Alert]:
        # Notes and stalls persist on their own (a note until the entity fires,
        # a stall for ChainConfig.stall_ttl_s), so counting the ones raised
        # right now is the agreement window.
        notes = sorted(
            a.key
            for a in alerts
            if a.cls is AlertClass.STATISTICAL and a.kind in _NOTE_KINDS
        )
        out = list(alerts)
        house = next(
            (
                a
                for a in out
                if a.cls is AlertClass.WELFARE
                and a.source == "house"
                and a.kind == "inactivity"
            ),
            None,
        )
        if house is not None and notes:
            out.remove(house)
            out.append(
                Alert(
                    house.cls,
                    house.source,
                    house.kind,
                    house.severity.bump(),
                    house.explanation + f" and {len(notes)} routine sign(s) missed",
                    house.raised_at,
                    {**house.details, "escalated_by": notes},
                )
            )
        elif house is None and len(notes) >= 2:
            out.append(
                Alert(
                    AlertClass.WELFARE,
                    "house",
                    "routine_agreement",
                    Severity.LOW,
                    f"{len(notes)} routine signs missed at the same time",
                    now,
                    {"notes": notes},
                )
            )
        for a in alerts:
            if (
                a.cls is AlertClass.STATISTICAL
                and a.kind == "drift"
                and a.source.startswith("chain:")
                and a.details.get("direction") == "increase"
                and int(a.details.get("days", 0)) >= self._cfg.timing_promote_days
            ):
                out.append(
                    Alert(
                        AlertClass.WELFARE,
                        a.source,
                        "timing_drift",
                        Severity.LOW,
                        f"Routine {a.source[6:]} has been taking longer for {a.details['days']} days",
                        a.raised_at,
                        dict(a.details),
                    )
                )
        return out

    # ------------------------------------------------------------- delivery

    def _on_open(
        self, alert: Alert, now: datetime, snoozed: bool
    ) -> list[DeliveryAction]:
        if alert.cls is AlertClass.WELFARE:
            return self._push(self._open[alert.key], now, snoozed)
        if alert.cls is AlertClass.HEALTH:
            return [DeliveryAction("repair_create", alert)]
        return [] if snoozed else [DeliveryAction("log", alert)]

    def _on_clear(self, o: _Open, suppress: bool) -> list[DeliveryAction]:
        alert = o.alert
        if alert.cls is AlertClass.WELFARE:
            return (
                []
                if suppress or o.last_push is None
                else [DeliveryAction("push_clear", alert)]
            )
        if alert.cls is AlertClass.HEALTH:
            return [DeliveryAction("repair_delete", alert)]
        return [] if suppress else [DeliveryAction("log_clear", alert)]

    def _push(self, o: _Open, now: datetime, snoozed: bool) -> list[DeliveryAction]:
        if not o.alert.severity.at_least(self._cfg.push_min_severity):
            return []
        o.last_push = now
        return [] if snoozed and not o.panic else [DeliveryAction("push", o.alert)]

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "open": {
                k: {
                    "alert": o.alert.to_dict(),
                    "opened_at": o.opened_at.isoformat(),
                    "last_push": o.last_push.isoformat() if o.last_push else None,
                    "acknowledged": o.acknowledged,
                    "panic": o.panic,
                }
                for k, o in self._open.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: RouterConfig) -> "AlertRouter":
        r = cls(config)
        try:
            for k, o in data.get("open", {}).items():
                r._open[k] = _Open(
                    Alert.from_dict(o["alert"]),
                    datetime.fromisoformat(o["opened_at"]),
                    (
                        datetime.fromisoformat(o["last_push"])
                        if o.get("last_push")
                        else None
                    ),
                    bool(o.get("acknowledged", False)),
                    bool(o.get("panic", False)),
                )
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return r
