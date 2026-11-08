"""Open alert set, escalation, promotion and class-based delivery actions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .events import ActivityEvent


ATTENTION = "attention"
INFORMATION = "information"
HEALTH = "health"


@dataclass(frozen=True)
class RouterConfig:
    attention_min_severity: Severity = Severity.MEDIUM
    timing_promote_days: int = 7


@dataclass(frozen=True)
class DeliveryAction:
    action: str
    alert: Alert
    event: str | None = None
    reason: str | None = None
    alert_id: str | None = None
    group: str | None = None
    cleared_by: str | None = None
    test: bool = False


@dataclass
class _Open:
    alert: Alert
    opened_at: datetime
    group: str
    panic: bool = False
    test: bool = False
    held: bool = False

    @property
    def id(self) -> str:
        return f"{self.alert.key}@{self.opened_at.isoformat()}"


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

    @property
    def attention_severity(self) -> Severity | None:
        sevs = [o.alert.severity for o in self._open.values() if o.group == ATTENTION]
        return max(sevs) if sevs else None

    def published(self) -> list[dict[str, Any]]:
        return [
            {**o.alert.to_dict(), "id": o.id, "group": o.group}
            for o in self._open.values()
        ]

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
                o = _Open(alert, now, self._group(alert, False))
                self._open[alert.key] = o
                actions.extend(self._on_open(o, snoozed))
            else:
                rose = alert.severity > cur.alert.severity
                cur.alert = replace(alert, raised_at=cur.alert.raised_at)
                if rose:
                    actions.extend(self._on_rise(cur, snoozed))
        for key in list(self._open):
            o = self._open[key]
            if key in seen or (o.panic and not o.test):
                continue
            del self._open[key]
            actions.extend(self._on_clear(o, snoozed or holiday))
        if not snoozed:
            for o in self._open.values():
                if o.held:
                    o.held = False
                    actions.append(self._event(o, "reminder", reason="snooze_ended"))
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
        cur = self._open.get(alert.key)
        if cur is not None and cur.panic and not cur.test:
            return [self._event(cur, "reminder", reason="pressed_again")]
        o = _Open(alert, now, ATTENTION, panic=True)
        self._open[alert.key] = o
        return [self._event(o, "opened")]

    def submit_test(self, now: datetime) -> list[DeliveryAction]:
        """A test alert through the real delivery path.

        The alert has its own source, so it never collides with a real panic,
        and the next submit closes it with a cleared event.
        """
        alert = Alert(
            AlertClass.WELFARE,
            "test",
            "panic",
            Severity.CRITICAL,
            "Test: panic button pressed",
            now,
            {"room": "Test"},
        )
        actions: list[DeliveryAction] = []
        prior = self._open.get(alert.key)
        if prior is not None:
            actions.append(self._event(prior, "cleared"))
        o = _Open(alert, now, ATTENTION, panic=True, test=True)
        self._open[alert.key] = o
        actions.append(self._event(o, "opened"))
        return actions

    def clear_panic(self, alert_id: str | None, now: datetime) -> list[DeliveryAction]:
        actions: list[DeliveryAction] = []
        for key in list(self._open):
            o = self._open[key]
            if not o.panic or o.test or (alert_id is not None and o.id != alert_id):
                continue
            del self._open[key]
            actions.append(self._event(o, "cleared", cleared_by="user"))
        return actions

    def reminders(self, reason: str) -> list[DeliveryAction]:
        return [
            self._event(o, "reminder", reason=reason)
            for o in self._open.values()
            if o.group == ATTENTION and not o.test and not o.held
        ]

    # ------------------------------------------------------------ combining

    def _combine(self, alerts: list[Alert], now: datetime) -> list[Alert]:
        # Notes and stalls persist on their own (a note until the entity fires,
        # a stall for ChainConfig.stall_ttl_s), so counting the ones raised
        # right now is the agreement window. A note from an entity that has not
        # fired at all today says something about the sensor, not about the
        # person, so it never escalates welfare; and several missed windows on
        # one entity are one sign, which is why notes count by source.
        stalls = sorted(
            {
                a.key
                for a in alerts
                if a.cls is AlertClass.STATISTICAL and a.kind == "chain_stall"
            }
        )
        notes = sorted(
            {
                a.key
                for a in alerts
                if a.cls is AlertClass.STATISTICAL
                and a.kind == "routine_missed"
                and a.details.get("fired_today")
            }
        )
        signs = stalls + notes
        escalates = bool(stalls) or len(notes) >= 2
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
        if house is not None and escalates:
            out.remove(house)
            out.append(
                Alert(
                    house.cls,
                    house.source,
                    house.kind,
                    house.severity.bump(),
                    house.explanation + f" and {len(signs)} routine sign(s) missed",
                    house.raised_at,
                    {**house.details, "escalated_by": signs},
                )
            )
        elif house is None and len(signs) >= 2:
            out.append(
                Alert(
                    AlertClass.WELFARE,
                    "house",
                    "routine_agreement",
                    Severity.LOW,
                    f"{len(signs)} routine signs missed at the same time",
                    now,
                    {"notes": signs},
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

    def _group(self, alert: Alert, panic: bool) -> str:
        if alert.cls is AlertClass.HEALTH:
            return HEALTH
        if alert.cls is AlertClass.WELFARE and (
            panic or alert.severity.at_least(self._cfg.attention_min_severity)
        ):
            return ATTENTION
        return INFORMATION

    def _event(
        self,
        o: _Open,
        event: str,
        reason: str | None = None,
        cleared_by: str | None = None,
    ) -> DeliveryAction:
        return DeliveryAction(
            "event",
            o.alert,
            event=event,
            reason=reason,
            alert_id=o.id,
            group=o.group,
            cleared_by=cleared_by,
            test=o.test,
        )

    def _held(self, o: _Open, snoozed: bool) -> bool:
        if snoozed and o.group == ATTENTION and not o.panic:
            o.held = True
            return True
        return False

    def _on_open(self, o: _Open, snoozed: bool) -> list[DeliveryAction]:
        actions: list[DeliveryAction] = []
        if not self._held(o, snoozed):
            actions.append(self._event(o, "opened"))
        if o.alert.cls is AlertClass.HEALTH:
            actions.append(DeliveryAction("repair_create", o.alert))
        elif o.alert.cls is AlertClass.STATISTICAL and not snoozed:
            actions.append(DeliveryAction("log", o.alert))
        return actions

    def _on_rise(self, o: _Open, snoozed: bool) -> list[DeliveryAction]:
        if o.group == INFORMATION and o.alert.cls is AlertClass.WELFARE:
            o.group = self._group(o.alert, o.panic)
        actions: list[DeliveryAction] = []
        if not self._held(o, snoozed):
            # This push supersedes a pending snooze_ended reminder.
            o.held = False
            actions.append(self._event(o, "escalated"))
        if o.alert.cls is AlertClass.STATISTICAL and not snoozed:
            actions.append(DeliveryAction("log", o.alert))
        return actions

    def _on_clear(self, o: _Open, suppress: bool) -> list[DeliveryAction]:
        actions = [self._event(o, "cleared")]
        if o.alert.cls is AlertClass.HEALTH:
            actions.append(DeliveryAction("repair_delete", o.alert))
        elif o.alert.cls is AlertClass.STATISTICAL and not suppress:
            actions.append(DeliveryAction("log_clear", o.alert))
        return actions

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "open": {
                k: {
                    "alert": o.alert.to_dict(),
                    "opened_at": o.opened_at.isoformat(),
                    "group": o.group,
                    "panic": o.panic,
                    "test": o.test,
                    "held": o.held,
                }
                for k, o in self._open.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: RouterConfig) -> "AlertRouter":
        """Read the current shape and the v11 one (last_push, acknowledged)."""
        r = cls(config)
        try:
            for k, o in data.get("open", {}).items():
                panic = bool(o.get("panic", False))
                if panic and o.get("acknowledged", False):
                    continue
                alert = Alert.from_dict(o["alert"])
                r._open[k] = _Open(
                    alert,
                    datetime.fromisoformat(o["opened_at"]),
                    o.get("group") or r._group(alert, panic),
                    panic,
                    bool(o.get("test", False)),
                    bool(o.get("held", False)),
                )
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return r
