"""Shared slot arithmetic and small statistics helpers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from statistics import median

SLOTS: int = 168
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def slot_index(ts: datetime) -> int:
    """Return weekday * 24 + hour for a local-time datetime."""
    return ts.weekday() * 24 + ts.hour


def slot_label(idx: int) -> str:
    return f"{_DAYS[idx // 24]} {idx % 24:02d}:00"


def median_mad(values: Iterable[float]) -> tuple[float, float]:
    """Median and median absolute deviation. (0.0, 0.0) for empty input."""
    vals = [float(v) for v in values]
    if not vals:
        return 0.0, 0.0
    med = float(median(vals))
    mad = float(median(abs(v - med) for v in vals))
    return med, mad


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def day_type(d: date) -> str:
    return "weekend" if is_weekend(d) else "weekday"


def confidence(days_seen: int, learning_days: int) -> float:
    if learning_days <= 0:
        return 1.0
    return max(0.0, min(1.0, days_seen / learning_days))


def iso_day(d: date) -> str:
    return d.isoformat()
