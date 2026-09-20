"""Bidirectional CUSUM over named daily series."""

from __future__ import annotations

import statistics
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


@dataclass(frozen=True)
class DriftConfig:
    sensitivity: str = "medium"
    min_days: int = 3
    window_days: int = 28
    min_baseline_days: int = 5


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
            rows = [((today - date.fromisoformat(d)).days, v) for d, v in self.values.items() if date.fromisoformat(d) < today]
        if not rows:
            return 0.0, 0.0, 0
        weights = [_DECAY ** age for age, _ in rows]
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

    def reset(self) -> None:
        self.s_pos = self.s_neg = 0.0
        self.days_above = 0


class DriftDetector:
    def __init__(self, config: DriftConfig) -> None:
        self._cfg = config
        self._k, self._h = CUSUM_PARAMS.get(config.sensitivity, CUSUM_PARAMS["medium"])
        self._series: dict[str, DailySeries] = {}
        self._cusum: dict[str, CUSUMState] = {}

    def record(self, key: str, day: date, value: float, split_day_type: bool = False) -> None:
        s = self._series.setdefault(key, DailySeries(split_day_type=split_day_type))
        s.split_day_type = split_day_type
        s.values[iso_day(day)] = float(value)

    def check(self, today: date, now: datetime) -> list[Alert]:
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
            z = (series.values[today_iso] - mean) / stdev
            st.s_pos = max(0.0, st.s_pos + z - self._k)
            st.s_neg = max(0.0, st.s_neg - z - self._k)
            st.days_above = st.days_above + 1 if (st.s_pos > self._h or st.s_neg > self._h) else 0
            st.last_day = today_iso
            if st.days_above < self._cfg.min_days:
                continue
            direction = "increase" if st.s_pos >= st.s_neg else "decrease"
            sev = Severity.HIGH if st.days_above >= 7 else Severity.MEDIUM
            out.append(
                Alert(
                    AlertClass.STATISTICAL,
                    key,
                    "drift",
                    sev,
                    f"{key}: sustained {direction} for {st.days_above} days (baseline {mean:.1f}, today {series.values[today_iso]:.1f})",
                    now,
                    {"direction": direction, "days": st.days_above, "baseline": round(mean, 2), "today": series.values[today_iso]},
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
            "series": {k: {"values": s.values, "split": s.split_day_type} for k, s in self._series.items()},
            "cusum": {k: {"s_pos": c.s_pos, "s_neg": c.s_neg, "days_above": c.days_above, "last_day": c.last_day} for k, c in self._cusum.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: DriftConfig) -> "DriftDetector":
        d = cls(config)
        try:
            for k, s in data.get("series", {}).items():
                d._series[k] = DailySeries({str(dd): float(v) for dd, v in s["values"].items()}, bool(s.get("split", False)))
            for k, c in data.get("cusum", {}).items():
                d._cusum[k] = CUSUMState(float(c["s_pos"]), float(c["s_neg"]), int(c["days_above"]), c.get("last_day"))
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls(config)
        return d
