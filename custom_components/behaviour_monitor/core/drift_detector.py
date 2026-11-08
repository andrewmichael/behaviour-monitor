"""Bidirectional CUSUM over named daily series."""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .alerts import Alert, AlertClass, Severity
from .slots import day_type, iso_day

CUSUM_PARAMS: dict[str, tuple[float, float]] = {
    "high": (0.25, 2.0),
    "medium": (0.5, 4.0),
    "low": (1.0, 6.0),
}
_DECAY = 0.95
# A drift whose days average this many standard deviations from usual, and is
# still on its side, counts as large.
_HIGH_Z = 3.0

# key prefix -> (what is measured, word for up, word for down, unit)
_METRICS: dict[str, tuple[str, str, str, str]] = {
    "count": ("activity", "higher", "lower", " a day"),
    "dwell": ("time spent", "higher", "lower", " s"),
    "open": ("time open", "longer", "shorter", " s"),
    "chain": ("time taken", "longer", "shorter", " s"),
    "rooms": ("rooms visited", "more", "fewer", " a day"),
}


@dataclass(frozen=True)
class DriftConfig:
    sensitivity: str = "medium"
    min_days: int = 3
    window_days: int = 28
    min_baseline_days: int = 5
    # Days in a row back near or past usual before a drift closes by itself.
    settle_days: int = 3


@dataclass
class DailySeries:
    values: dict[str, float] = field(default_factory=dict)
    split_day_type: bool = False

    def baseline(self, today: date) -> tuple[float, float, int]:
        """Decay-weighted mean, stdev and count of days before today, same day type if split."""
        rows: list[tuple[int, float]] = []
        want = day_type(today) if self.split_day_type else None
        for d, v in self.values.items():
            dd = date.fromisoformat(d)
            if dd >= today:
                continue
            if want is not None and day_type(dd) != want:
                continue
            rows.append(((today - dd).days, v))
        if self.split_day_type and len(rows) < 3:
            rows = [
                ((today - date.fromisoformat(d)).days, v)
                for d, v in self.values.items()
                if date.fromisoformat(d) < today
            ]
        if not rows:
            return 0.0, 0.0, 0
        weights = [_DECAY**age for age, _ in rows]
        mean = sum(w * v for w, (_, v) in zip(weights, rows)) / sum(weights)
        vals = [v for _, v in rows]
        stdev = statistics.stdev(vals) if len(vals) >= 2 else 0.0
        return mean, stdev, len(rows)


@dataclass
class CUSUMState:
    s_pos: float = 0.0
    s_neg: float = 0.0
    days_above: int = 0
    last_day: str | None = None
    settled_days: int = 0
    # Sum of z over the days counted in days_above, for the drift's mean size.
    z_sum: float = 0.0
    # True once this drift has been reported while still moving; a drift that
    # has already settled is only reported if it was open before.
    reported: bool = False

    def reset(self) -> None:
        self.s_pos = self.s_neg = 0.0
        self.days_above = 0
        self.settled_days = 0
        self.z_sum = 0.0
        self.reported = False


class DriftDetector:
    def __init__(self, config: DriftConfig) -> None:
        self._cfg = config
        self._k, self._h = CUSUM_PARAMS.get(config.sensitivity, CUSUM_PARAMS["medium"])
        self._series: dict[str, DailySeries] = {}
        self._cusum: dict[str, CUSUMState] = {}

    def record(
        self, key: str, day: date, value: float, split_day_type: bool = False
    ) -> None:
        s = self._series.setdefault(key, DailySeries(split_day_type=split_day_type))
        s.split_day_type = split_day_type
        s.values[iso_day(day)] = float(value)

    def check(
        self,
        today: date,
        now: datetime,
        names: Mapping[str, str] | None = None,
    ) -> list[Alert]:
        """Update each series' CUSUM with today's value and report drifts.

        A drift closes by itself once the value has been back near usual, or
        past it, for settle_days in a row; a slow decline that keeps moving
        away from usual never settles, so it keeps alerting.
        """
        out: list[Alert] = []
        today_iso = iso_day(today)
        for key, series in self._series.items():
            if today_iso not in series.values:
                continue
            st = self._cusum.setdefault(key, CUSUMState())
            if st.last_day == today_iso:
                continue
            mean, stdev, n = series.baseline(today)
            if n < self._cfg.min_baseline_days:
                st.last_day = today_iso
                continue
            if stdev == 0.0:
                stdev = max(1.0, abs(mean) * 0.1)
            value = series.values[today_iso]
            z = (value - mean) / stdev
            st.s_pos = max(0.0, st.s_pos + z - self._k)
            st.s_neg = max(0.0, st.s_neg - z - self._k)
            if st.s_pos > self._h or st.s_neg > self._h:
                st.days_above += 1
                st.z_sum += z
            else:
                st.days_above = 0
                st.z_sum = 0.0
                st.reported = False
            st.last_day = today_iso
            direction = "increase" if st.s_pos >= st.s_neg else "decrease"
            current = "above" if z > self._k else "below" if z < -self._k else "near"
            agrees = current == ("above" if direction == "increase" else "below")
            st.settled_days = 0 if agrees or st.days_above == 0 else st.settled_days + 1
            if st.settled_days >= self._cfg.settle_days:
                st.reset()
                continue
            if st.days_above < self._cfg.min_days:
                continue
            settled = not agrees
            if settled and not st.reported:
                continue
            st.reported = True
            if settled:
                sev = Severity.LOW
            elif abs(st.z_sum / st.days_above) >= _HIGH_Z:
                sev = Severity.HIGH
            else:
                sev = Severity.MEDIUM
            out.append(
                Alert(
                    AlertClass.STATISTICAL,
                    key,
                    "drift",
                    sev,
                    _explain(
                        key, direction, current, st.days_above, mean, value, names
                    ),
                    now,
                    {
                        "direction": direction,
                        "days": st.days_above,
                        "baseline": round(mean, 2),
                        "today": value,
                        "current": current,
                        "settled": settled,
                    },
                )
            )
        return out

    def reset(self, key: str | None = None) -> None:
        for k, st in self._cusum.items():
            if key is None or k == key:
                st.reset()

    def remove_prefix(self, prefix: str) -> None:
        for k in [k for k in self._series if k.startswith(prefix)]:
            del self._series[k]
            self._cusum.pop(k, None)

    def prune(self, before: date) -> None:
        cutoff = iso_day(before)
        for s in self._series.values():
            s.values = {d: v for d, v in s.values.items() if d >= cutoff}

    def to_dict(self) -> dict[str, Any]:
        return {
            "series": {
                k: {"values": s.values, "split": s.split_day_type}
                for k, s in self._series.items()
            },
            "cusum": {
                k: {
                    "s_pos": c.s_pos,
                    "s_neg": c.s_neg,
                    "days_above": c.days_above,
                    "last_day": c.last_day,
                    "settled_days": c.settled_days,
                    "z_sum": c.z_sum,
                    "reported": c.reported,
                }
                for k, c in self._cusum.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: DriftConfig) -> "DriftDetector":
        d = cls(config)
        try:
            for k, s in data.get("series", {}).items():
                d._series[k] = DailySeries(
                    {str(dd): float(v) for dd, v in s["values"].items()},
                    bool(s.get("split", False)),
                )
            for k, c in data.get("cusum", {}).items():
                d._cusum[k] = CUSUMState(
                    float(c["s_pos"]),
                    float(c["s_neg"]),
                    int(c["days_above"]),
                    c.get("last_day"),
                    int(c.get("settled_days", 0)),
                    float(c.get("z_sum", 0.0)),
                    bool(c.get("reported", c.get("days_above", 0) > 0)),
                )
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return d


def _label(key: str, names: Mapping[str, str] | None) -> str:
    prefix, _, rest = key.partition(":")
    if prefix == "rooms":
        return "Rooms visited"
    if prefix == "chain":
        return f"Routine {rest}"
    return (names or {}).get(rest, rest)


def _explain(
    key: str,
    direction: str,
    current: str,
    days: int,
    usual: float,
    latest: float,
    names: Mapping[str, str] | None,
) -> str:
    prefix = key.partition(":")[0]
    metric, up, down, unit = _METRICS.get(prefix, ("value", "higher", "lower", ""))
    if prefix == "rooms":
        metric = ""
    word = up if direction == "increase" else down
    now_word = up if current == "above" else down
    if current == "near":
        now = "now back near usual"
    elif now_word == word:
        now = f"still {word}"
    else:
        now = f"now {now_word} than usual"
    what = f"{metric} {word}" if metric else word
    return (
        f"{_label(key, names)}: {what} than usual for {days} days; {now} "
        f"(usual {usual:.0f}{unit}, latest {latest:.0f}{unit})"
    )
