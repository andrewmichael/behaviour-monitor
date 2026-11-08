from datetime import date, datetime, timedelta, timezone

from custom_components.behaviour_monitor.core.alerts import AlertClass, Severity
from custom_components.behaviour_monitor.core.drift_detector import (
    DriftConfig,
    DriftDetector,
)

D0 = date(2026, 9, 1)
NOW = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)


def _feed(
    det: DriftDetector, key: str, values: list[float], split: bool = False
) -> list[list]:
    out = []
    for i, v in enumerate(values):
        day = D0 + timedelta(days=i)
        det.record(key, day, v, split_day_type=split)
        out.append(det.check(day, datetime.combine(day, NOW.timetz())))
    return out


def test_stable_series_never_alerts():
    det = DriftDetector(DriftConfig())
    results = _feed(
        det, "count:x", [10, 11, 9, 10, 12, 10, 9, 11, 10, 10, 11, 9, 10, 10]
    )
    assert all(r == [] for r in results)


def test_step_change_alerts_after_min_days_with_direction_and_severity():
    det = DriftDetector(DriftConfig(min_days=3))
    values = [12.0] * 10 + [25.0] * 8
    results = _feed(det, "chain:Bedroom → Kitchen", values)
    first = next(i for i, r in enumerate(results) if r)
    assert first == 12  # 10 baseline days, alert on the third shifted day
    a = results[first][0]
    assert (
        a.cls is AlertClass.STATISTICAL
        and a.kind == "drift"
        and a.severity is Severity.HIGH  # roughly doubled: large by size
    )
    assert a.details["direction"] == "increase" and a.details["days"] == 3
    assert a.details["baseline"] < a.details["today"]
    # Severity follows size, not age: as the baseline absorbs the new level the
    # drift's mean size falls and it drops back to Medium.
    assert results[-1][0].severity is Severity.MEDIUM


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


def _alerting(results: list[list]) -> list[bool]:
    return [bool(r) for r in results]


def test_settled_drift_clears_within_settle_days_of_returning():
    det = DriftDetector(DriftConfig(min_days=3, settle_days=3))
    values = [12.0] * 10 + [25.0] * 10 + [12.0] * 8
    results = _feed(det, "count:x", values)
    assert any(_alerting(results[10:20]))
    back = 20
    # Within settle_days of returning to baseline the alert has closed and
    # stays closed.
    assert not any(_alerting(results[back + 3 :]))


def test_today_below_baseline_is_never_reported_as_ongoing_increase():
    det = DriftDetector(DriftConfig(min_days=3))
    values = [12.0] * 10 + [25.0] * 10 + [5.0] * 6
    for r in _feed(det, "count:x", values):
        for a in r:
            d = a.details
            if d["direction"] == "increase" and d["today"] < d["baseline"]:
                assert d["current"] == "below" and d["settled"] is True


def test_details_report_current_and_settled():
    det = DriftDetector(DriftConfig(min_days=3))
    results = _feed(det, "count:x", [12.0] * 10 + [25.0] * 4)
    d = results[-1][0].details
    assert {"direction", "days", "baseline", "today"} <= set(d)
    assert d["current"] == "above" and d["settled"] is False


def test_slow_sustained_decline_alerts_and_keeps_alerting():
    det = DriftDetector(DriftConfig(min_days=3))
    values = [100.0, 102.0, 98.0, 101.0, 99.0, 100.0, 103.0, 97.0, 100.0, 100.0]
    v = 100.0
    for _ in range(30):
        v *= 0.98
        values.append(v)
    results = _feed(det, "count:x", values)
    first = next(i for i, r in enumerate(results) if r)
    assert first < 25
    assert all(_alerting(results[first:]))
    assert all(r[0].details["direction"] == "decrease" for r in results[first:])


def test_severity_follows_size_not_age():
    det = DriftDetector(DriftConfig(min_days=3))
    # A modest shift (about one standard deviation) held for two weeks.
    base = [10.0, 12.0, 8.0, 11.0, 9.0, 10.0, 12.0, 8.0, 11.0, 9.0]
    results = _feed(det, "count:x", base + [13.0] * 14)
    sevs = [r[0].severity for r in results if r]
    assert sevs and Severity.HIGH not in sevs


def test_explanation_uses_display_names_and_current_wording():
    det = DriftDetector(DriftConfig(min_days=3))
    values = [60.0, 70.0, 65.0, 68.0, 66.0, 64.0, 70.0, 62.0, 67.0, 66.0]
    values += [120.0] * 4
    out = []
    for i, val in enumerate(values):
        day = D0 + timedelta(days=i)
        det.record("dwell:binary_sensor.bb", day, val)
        out.append(
            det.check(
                day,
                datetime.combine(day, NOW.timetz()),
                names={"binary_sensor.bb": "Back bedroom motion"},
            )
        )
    text = out[-1][0].explanation
    assert text.startswith("Back bedroom motion: time spent higher than usual for")
    assert "binary_sensor" not in text and "still higher" in text


def test_settled_days_round_trip():
    det = DriftDetector(DriftConfig(min_days=3))
    _feed(det, "count:x", [12.0] * 10 + [25.0] * 6 + [12.0])
    raw = det.to_dict()
    assert raw["cusum"]["count:x"]["settled_days"] == 1
    assert DriftDetector.from_dict(raw, DriftConfig()).to_dict() == raw
    old = {
        "series": raw["series"],
        "cusum": {
            "count:x": {"s_pos": 1.0, "s_neg": 0.0, "days_above": 2, "last_day": None}
        },
    }
    assert (
        DriftDetector.from_dict(old, DriftConfig()).to_dict()["cusum"]["count:x"][
            "settled_days"
        ]
        == 0
    )


def test_a_far_shift_still_moving_is_high():
    det = DriftDetector(DriftConfig(min_days=3))
    base = [10.0, 12.0, 8.0, 11.0, 9.0, 10.0, 12.0, 8.0, 11.0, 9.0]
    results = _feed(det, "count:x", base + [14.0, 18.0, 22.0, 26.0, 30.0, 34.0])
    assert results[-1][0].severity is Severity.HIGH


def test_a_drift_already_settled_does_not_open():
    det = DriftDetector(DriftConfig(min_days=3))
    # Two days high (not yet alerting), then straight back below usual: the
    # sum stays over h for a while but the drift is over before it reports.
    base = [10.0, 12.0, 8.0, 11.0, 9.0, 10.0, 12.0, 8.0, 11.0, 9.0]
    results = _feed(det, "count:x", base + [40.0, 40.0, 5.0, 5.0, 5.0, 10.0])
    assert all(a.details["settled"] is False for r in results for a in r)
