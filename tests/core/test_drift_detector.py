from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import AlertClass, Severity
from custom_components.behaviour_monitor.core.drift_detector import DriftConfig, DriftDetector

D0 = date(2026, 9, 1)
NOW = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)


def _feed(det: DriftDetector, key: str, values: list[float], split: bool = False) -> list[list]:
    out = []
    for i, v in enumerate(values):
        day = D0 + timedelta(days=i)
        det.record(key, day, v, split_day_type=split)
        out.append(det.check(day, datetime.combine(day, NOW.timetz())))
    return out


def test_stable_series_never_alerts():
    det = DriftDetector(DriftConfig())
    results = _feed(det, "count:x", [10, 11, 9, 10, 12, 10, 9, 11, 10, 10, 11, 9, 10, 10])
    assert all(r == [] for r in results)


def test_step_change_alerts_after_min_days_with_direction_and_severity():
    det = DriftDetector(DriftConfig(min_days=3))
    values = [12.0] * 10 + [25.0] * 8
    results = _feed(det, "chain:Bedroom → Kitchen", values)
    first = next(i for i, r in enumerate(results) if r)
    assert first == 12  # 10 baseline days, alert on the third shifted day
    a = results[first][0]
    assert a.cls is AlertClass.STATISTICAL and a.kind == "drift" and a.severity is Severity.MEDIUM
    assert a.details["direction"] == "increase" and a.details["days"] == 3
    assert a.details["baseline"] < a.details["today"]
    assert results[-1][0].severity is Severity.HIGH  # 7+ days


def test_gradual_lengthening_is_caught():
    det = DriftDetector(DriftConfig(min_days=3))
    values = [12.0] * 10 + [12.0 + 2 * i for i in range(1, 15)]
    results = _feed(det, "chain:x", values)
    first = next(i for i, r in enumerate(results) if r)
    assert 13 <= first <= 20


def test_check_is_idempotent_per_day_and_needs_baseline():
    det = DriftDetector(DriftConfig(min_baseline_days=5))
    det.record("count:x", D0, 5.0)
    assert det.check(D0, NOW) == []
    for i in range(1, 6):
        det.record("count:x", D0 + timedelta(days=i), 5.0)
    day = D0 + timedelta(days=5)
    det.check(day, NOW)
    det.record("count:x", day, 50.0)
    assert det.check(day, NOW) == []  # already processed today


def test_reset_prune_remove_and_round_trip():
    det = DriftDetector(DriftConfig())
    _feed(det, "count:x", [12.0] * 10 + [30.0] * 3)
    det2 = DriftDetector.from_dict(det.to_dict(), DriftConfig())
    assert det2.to_dict() == det.to_dict()
    det2.reset("count:x")
    assert det2.to_dict()["cusum"]["count:x"]["days_above"] == 0
    det2.remove_prefix("count:")
    assert "count:x" not in det2.to_dict()["series"]
    det.prune(D0 + timedelta(days=12))
    assert len(det.to_dict()["series"]["count:x"]["values"]) == 1
    assert DriftDetector.from_dict({"x": 1}, DriftConfig()).to_dict()["series"] == {}
