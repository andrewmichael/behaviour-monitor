"""Tests for the CorrelationDetector — PMI-based co-occurrence discovery.

Pure Python stdlib only. Zero Home Assistant imports.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.behaviour_monitor.alert_result import AlertSeverity, AlertType
from custom_components.behaviour_monitor.const import SUSTAINED_EVIDENCE_CYCLES
from custom_components.behaviour_monitor.correlation_detector import (
    CorrelationDetector,
    CorrelationPair,
)


# ---------------------------------------------------------------------------
# CorrelationPair unit tests
# ---------------------------------------------------------------------------


class TestCorrelationPair:
    """Tests for the CorrelationPair dataclass."""

    def test_total_events(self) -> None:
        pair = CorrelationPair(
            entities=("sensor.a", "sensor.b"),
            co_occurrences=10,
            solo_counts={"sensor.a": 5, "sensor.b": 3},
        )
        # total = co_occurrences + sum(solo_counts)
        assert pair.total_events == 10 + 5 + 3

    def test_co_occurrence_rate(self) -> None:
        pair = CorrelationPair(
            entities=("sensor.a", "sensor.b"),
            co_occurrences=6,
            solo_counts={"sensor.a": 2, "sensor.b": 2},
        )
        # rate = 6 / (6 + 2 + 2) = 0.6
        assert pair.co_occurrence_rate == pytest.approx(0.6)

    def test_co_occurrence_rate_zero_events(self) -> None:
        pair = CorrelationPair(
            entities=("sensor.a", "sensor.b"),
            co_occurrences=0,
            solo_counts={},
        )
        assert pair.co_occurrence_rate == 0.0

    def test_to_dict_round_trip(self) -> None:
        pair = CorrelationPair(
            entities=("sensor.a", "sensor.b"),
            co_occurrences=15,
            solo_counts={"sensor.a": 3, "sensor.b": 7},
            first_observed="2026-01-01T00:00:00",
        )
        data = pair.to_dict()
        restored = CorrelationPair.from_dict(("sensor.a", "sensor.b"), data)
        assert restored.entities == pair.entities
        assert restored.co_occurrences == pair.co_occurrences
        assert restored.solo_counts == pair.solo_counts
        assert restored.first_observed == pair.first_observed

    def test_from_dict_empty(self) -> None:
        pair = CorrelationPair.from_dict(("sensor.a", "sensor.b"), {})
        assert pair.co_occurrences == 0
        assert pair.solo_counts == {}
        assert pair.first_observed is None


# ---------------------------------------------------------------------------
# CorrelationDetector — record_event
# ---------------------------------------------------------------------------


class TestRecordEvent:
    """Tests for CorrelationDetector.record_event()."""

    def test_co_occurrence_within_window(self) -> None:
        """Two entities seen within the window increment co_occurrences."""
        det = CorrelationDetector(co_occurrence_window_seconds=120)
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        t1 = t0 + timedelta(seconds=60)

        all_last_seen = {"sensor.a": t1, "sensor.b": t0}
        det.record_event("sensor.a", t1, all_last_seen)

        key = ("sensor.a", "sensor.b")
        assert key in det._pairs
        assert det._pairs[key].co_occurrences == 1

    def test_co_occurrence_outside_window(self) -> None:
        """Two entities seen outside the window do NOT co-occur."""
        det = CorrelationDetector(co_occurrence_window_seconds=120)
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        t1 = t0 + timedelta(seconds=300)  # 5 minutes > 2 min window

        all_last_seen = {"sensor.a": t1, "sensor.b": t0}
        det.record_event("sensor.a", t1, all_last_seen)

        # Pair may exist but should have 0 co-occurrences and solo count
        key = ("sensor.a", "sensor.b")
        if key in det._pairs:
            assert det._pairs[key].co_occurrences == 0

    def test_no_other_entities_no_pairs(self) -> None:
        """Single entity with no others creates no pairs."""
        det = CorrelationDetector()
        t = datetime(2026, 1, 1, 12, 0, 0)
        det.record_event("sensor.a", t, {"sensor.a": t})
        assert len(det._pairs) == 0

    def test_sorted_key_consistency(self) -> None:
        """Recording (A,B) and (B,A) updates the same pair."""
        det = CorrelationDetector(co_occurrence_window_seconds=120)
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        t1 = t0 + timedelta(seconds=30)
        t2 = t1 + timedelta(seconds=30)

        det.record_event("sensor.b", t1, {"sensor.a": t0, "sensor.b": t1})
        det.record_event("sensor.a", t2, {"sensor.a": t2, "sensor.b": t1})

        # Only one pair should exist
        assert len(det._pairs) == 1
        key = ("sensor.a", "sensor.b")
        assert key in det._pairs
        assert det._pairs[key].co_occurrences == 2

    def test_first_observed_set_on_creation(self) -> None:
        """First observation timestamp is set when pair is first created."""
        det = CorrelationDetector(co_occurrence_window_seconds=120)
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        t1 = t0 + timedelta(seconds=30)

        det.record_event("sensor.a", t1, {"sensor.a": t1, "sensor.b": t0})

        key = ("sensor.a", "sensor.b")
        assert det._pairs[key].first_observed is not None


# ---------------------------------------------------------------------------
# CorrelationDetector — recompute (PMI)
# ---------------------------------------------------------------------------


class TestRecompute:
    """Tests for CorrelationDetector.recompute() PMI logic."""

    @staticmethod
    def _build_detector_with_pair(
        co_occurrences: int,
        solo_a: int,
        solo_b: int,
        extra_global_events: int = 200,
    ) -> CorrelationDetector:
        """Helper: create a detector with a pre-populated pair and global counts.

        Global entity event counts include additional background events
        (from other entities) to give PMI meaningful base rates. Without
        background events, marginal probabilities P(a) and P(b) would be
        too high for PMI to exceed 1.0.
        """
        det = CorrelationDetector(
            co_occurrence_window_seconds=120,
            min_observations=10,
            pmi_threshold=1.0,
        )
        pair = CorrelationPair(
            entities=("sensor.a", "sensor.b"),
            co_occurrences=co_occurrences,
            solo_counts={"sensor.a": solo_a, "sensor.b": solo_b},
            first_observed="2026-01-01T00:00:00",
        )
        det._pairs[("sensor.a", "sensor.b")] = pair
        # Set global event counts: each entity's total = co-occurrences + solos
        det._entity_event_counts["sensor.a"] = co_occurrences + solo_a
        det._entity_event_counts["sensor.b"] = co_occurrences + solo_b
        # Total includes background events from other entities in the system
        det._total_event_count = (
            co_occurrences + solo_a + solo_b + extra_global_events
        )
        return det

    def test_high_pmi_pair_becomes_learned(self) -> None:
        """Pair with high co-occurrence and PMI > 1.0 is promoted to learned."""
        # 47 co-occurrences, 10 solo A, 5 solo B = high PMI
        det = self._build_detector_with_pair(47, 10, 5)
        det.recompute()
        assert ("sensor.a", "sensor.b") in det._learned_pairs

    def test_below_min_observations_not_learned(self) -> None:
        """Pair with co_occurrences < MIN_CO_OCCURRENCES (10) is NOT promoted."""
        det = self._build_detector_with_pair(3, 2, 2)
        det.recompute()
        assert ("sensor.a", "sensor.b") not in det._learned_pairs

    def test_low_pmi_not_learned(self) -> None:
        """Pair with sufficient count but low PMI is NOT learned."""
        # Many co-occurrences but also tons of solo events, no background
        # events => marginals are high => PMI < 1.0
        det = self._build_detector_with_pair(15, 500, 500, extra_global_events=0)
        det.recompute()
        assert ("sensor.a", "sensor.b") not in det._learned_pairs

    def test_recompute_removes_previously_learned(self) -> None:
        """Pair that was learned but no longer meets criteria is removed."""
        det = self._build_detector_with_pair(47, 10, 5)
        det.recompute()
        assert ("sensor.a", "sensor.b") in det._learned_pairs

        # Now add massive solo counts to dilute marginals and drop PMI
        det._pairs[("sensor.a", "sensor.b")].solo_counts["sensor.a"] = 5000
        det._pairs[("sensor.a", "sensor.b")].solo_counts["sensor.b"] = 5000
        det._entity_event_counts["sensor.a"] = 47 + 5000
        det._entity_event_counts["sensor.b"] = 47 + 5000
        det._total_event_count = 47 + 5000 + 5000 + 200
        det.recompute()
        assert ("sensor.a", "sensor.b") not in det._learned_pairs


# ---------------------------------------------------------------------------
# CorrelationDetector — sensor attribute output
# ---------------------------------------------------------------------------


class TestSensorOutput:
    """Tests for get_correlation_groups() and get_correlated_entities()."""

    @staticmethod
    def _build_learned_detector() -> CorrelationDetector:
        """Create a detector with one learned pair."""
        det = CorrelationDetector(
            co_occurrence_window_seconds=120,
            min_observations=10,
            pmi_threshold=1.0,
        )
        pair = CorrelationPair(
            entities=("sensor.a", "sensor.b"),
            co_occurrences=47,
            solo_counts={"sensor.a": 10, "sensor.b": 5},
            first_observed="2026-01-01T00:00:00",
        )
        det._pairs[("sensor.a", "sensor.b")] = pair
        # Set global counts with background events for PMI > 1.0
        det._entity_event_counts["sensor.a"] = 57
        det._entity_event_counts["sensor.b"] = 52
        det._total_event_count = 62 + 200  # background events from other entities
        det.recompute()
        return det

    def test_get_correlation_groups_with_learned(self) -> None:
        det = self._build_learned_detector()
        groups = det.get_correlation_groups()
        assert len(groups) == 1
        group = groups[0]
        assert set(group["entities"]) == {"sensor.a", "sensor.b"}
        assert "co_occurrence_rate" in group
        assert "total_observations" in group
        assert isinstance(group["total_observations"], int)

    def test_get_correlation_groups_empty(self) -> None:
        det = CorrelationDetector()
        groups = det.get_correlation_groups()
        assert groups == []

    def test_get_correlated_entities_found(self) -> None:
        det = self._build_learned_detector()
        partners = det.get_correlated_entities("sensor.a")
        assert "sensor.b" in partners

    def test_get_correlated_entities_reverse(self) -> None:
        det = self._build_learned_detector()
        partners = det.get_correlated_entities("sensor.b")
        assert "sensor.a" in partners

    def test_get_correlated_entities_none(self) -> None:
        det = self._build_learned_detector()
        partners = det.get_correlated_entities("sensor.unknown")
        assert partners == []


# ---------------------------------------------------------------------------
# CorrelationDetector — persistence
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CorrelationDetector — break detection
# ---------------------------------------------------------------------------


class TestCheckBreaks:
    """Tests for CorrelationDetector.check_breaks() method."""

    @staticmethod
    def _build_learned_detector(
        *,
        extra_pair: bool = False,
    ) -> CorrelationDetector:
        """Create a detector with one (or two) learned pairs involving sensor.a.

        Pair 1: ("sensor.a", "sensor.b") — always present.
        Pair 2: ("sensor.a", "sensor.c") — only when extra_pair=True.
        """
        det = CorrelationDetector(
            co_occurrence_window_seconds=120,
            min_observations=10,
            pmi_threshold=1.0,
        )
        pair_ab = CorrelationPair(
            entities=("sensor.a", "sensor.b"),
            co_occurrences=47,
            solo_counts={"sensor.a": 10, "sensor.b": 5},
            first_observed="2026-01-01T00:00:00",
        )
        det._pairs[("sensor.a", "sensor.b")] = pair_ab
        det._entity_event_counts["sensor.a"] = 57
        det._entity_event_counts["sensor.b"] = 52
        det._total_event_count = 262

        if extra_pair:
            pair_ac = CorrelationPair(
                entities=("sensor.a", "sensor.c"),
                co_occurrences=40,
                solo_counts={"sensor.a": 8, "sensor.c": 4},
                first_observed="2026-01-02T00:00:00",
            )
            det._pairs[("sensor.a", "sensor.c")] = pair_ac
            det._entity_event_counts["sensor.a"] = 57 + 48
            det._entity_event_counts["sensor.c"] = 44
            det._total_event_count = 262 + 52 + 200

        det.recompute()
        return det

    def test_no_learned_partners_returns_empty(self) -> None:
        """Entity with no learned partners gets no break alerts."""
        det = self._build_learned_detector()
        now = datetime(2026, 3, 1, 12, 0, 0)
        last_seen: dict[str, datetime] = {}
        result = det.check_breaks("sensor.unknown", now, last_seen)
        assert result == []

    def test_all_partners_within_window_returns_empty(self) -> None:
        """No break when all learned partners fired within window."""
        det = self._build_learned_detector()
        now = datetime(2026, 3, 1, 12, 0, 0)
        last_seen = {"sensor.b": now - timedelta(seconds=60)}
        result = det.check_breaks("sensor.a", now, last_seen)
        assert result == []

    def test_first_miss_returns_empty(self) -> None:
        """First consecutive miss does not fire an alert (counter=1 < 3)."""
        det = self._build_learned_detector()
        now = datetime(2026, 3, 1, 12, 0, 0)
        # sensor.b not seen within window
        last_seen = {"sensor.b": now - timedelta(seconds=300)}
        result = det.check_breaks("sensor.a", now, last_seen)
        assert result == []
        assert det._break_cycles.get("sensor.a", 0) == 1

    def test_second_miss_returns_empty(self) -> None:
        """Second consecutive miss still below threshold (counter=2 < 3)."""
        det = self._build_learned_detector()
        now = datetime(2026, 3, 1, 12, 0, 0)
        last_seen = {"sensor.b": now - timedelta(seconds=300)}
        det.check_breaks("sensor.a", now, last_seen)
        det.check_breaks("sensor.a", now, last_seen)
        assert det._break_cycles["sensor.a"] == 2

    def test_third_miss_returns_alert(self) -> None:
        """Third consecutive miss fires an AlertResult."""
        det = self._build_learned_detector()
        now = datetime(2026, 3, 1, 12, 0, 0)
        last_seen = {"sensor.b": now - timedelta(seconds=300)}
        # First two misses — no alert
        det.check_breaks("sensor.a", now, last_seen)
        det.check_breaks("sensor.a", now, last_seen)
        # Third miss — alert fires
        result = det.check_breaks("sensor.a", now, last_seen)
        assert len(result) == 1
        alert = result[0]
        assert alert.entity_id == "sensor.a"
        assert alert.alert_type == AlertType.CORRELATION_BREAK
        assert alert.severity == AlertSeverity.LOW
        assert "sensor.b" in alert.explanation
        assert alert.details["consecutive_misses"] == SUSTAINED_EVIDENCE_CYCLES

    def test_counter_resets_on_satisfied(self) -> None:
        """Counter resets to 0 when correlation is satisfied after misses."""
        det = self._build_learned_detector()
        now = datetime(2026, 3, 1, 12, 0, 0)
        last_seen_miss = {"sensor.b": now - timedelta(seconds=300)}
        last_seen_ok = {"sensor.b": now - timedelta(seconds=60)}
        # Two misses
        det.check_breaks("sensor.a", now, last_seen_miss)
        det.check_breaks("sensor.a", now, last_seen_miss)
        assert det._break_cycles["sensor.a"] == 2
        # Satisfied — counter resets
        det.check_breaks("sensor.a", now, last_seen_ok)
        assert det._break_cycles["sensor.a"] == 0

    def test_multi_partner_group_dedup(self) -> None:
        """Multiple missing partners produce ONE alert (group dedup)."""
        det = self._build_learned_detector(extra_pair=True)
        now = datetime(2026, 3, 1, 12, 0, 0)
        # Both sensor.b and sensor.c are missing (outside window)
        last_seen = {
            "sensor.b": now - timedelta(seconds=300),
            "sensor.c": now - timedelta(seconds=300),
        }
        for _ in range(SUSTAINED_EVIDENCE_CYCLES):
            result = det.check_breaks("sensor.a", now, last_seen)
        # Exactly one alert for entity sensor.a
        assert len(result) == 1
        alert = result[0]
        assert alert.entity_id == "sensor.a"
        # Explanation should mention both missing partners
        assert "sensor.b" in alert.explanation
        assert "sensor.c" in alert.explanation
        # Details should list both
        assert sorted(alert.details["missing_partners"]) == [
            "sensor.b",
            "sensor.c",
        ]

    def test_alert_result_fields(self) -> None:
        """Verify AlertResult fields match specification."""
        det = self._build_learned_detector()
        now = datetime(2026, 3, 1, 12, 0, 0)
        last_seen = {"sensor.b": now - timedelta(seconds=300)}
        for _ in range(SUSTAINED_EVIDENCE_CYCLES):
            result = det.check_breaks("sensor.a", now, last_seen)
        assert len(result) == 1
        alert = result[0]
        assert alert.alert_type == AlertType.CORRELATION_BREAK
        assert alert.severity == AlertSeverity.LOW
        assert alert.timestamp == now.isoformat()
        assert "window_seconds" in alert.details
        assert alert.details["window_seconds"] == 120
        assert isinstance(alert.confidence, float)

    def test_partner_not_in_last_seen_counts_as_miss(self) -> None:
        """Partner absent from last_seen map entirely counts as a miss."""
        det = self._build_learned_detector()
        now = datetime(2026, 3, 1, 12, 0, 0)
        last_seen: dict[str, datetime] = {}  # sensor.b not present at all
        for _ in range(SUSTAINED_EVIDENCE_CYCLES):
            result = det.check_breaks("sensor.a", now, last_seen)
        assert len(result) == 1
        assert "sensor.b" in result[0].details["missing_partners"]


class TestPersistence:
    """Tests for to_dict() / from_dict() round-tripping."""

    def test_to_dict_structure(self) -> None:
        det = CorrelationDetector(co_occurrence_window_seconds=180)
        data = det.to_dict()
        assert "co_occurrence_window_seconds" in data
        assert "pairs" in data
        assert data["co_occurrence_window_seconds"] == 180

    def test_round_trip(self) -> None:
        det = CorrelationDetector(co_occurrence_window_seconds=120)
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        t1 = t0 + timedelta(seconds=30)

        # Record enough events to create a pair
        for i in range(15):
            ti = t1 + timedelta(seconds=i)
            det.record_event("sensor.a", ti, {"sensor.a": ti, "sensor.b": t0 + timedelta(seconds=i)})

        det.recompute()

        data = det.to_dict()
        restored = CorrelationDetector.from_dict(data)

        # Verify pair data preserved
        key = ("sensor.a", "sensor.b")
        assert key in restored._pairs
        assert restored._pairs[key].co_occurrences == det._pairs[key].co_occurrences
        assert restored._pairs[key].solo_counts == det._pairs[key].solo_counts
        assert restored._pairs[key].first_observed == det._pairs[key].first_observed

        # Verify learned pairs preserved
        assert restored._learned_pairs == det._learned_pairs

    def test_break_cycles_round_trip(self) -> None:
        """_break_cycles dict survives to_dict/from_dict round trip."""
        det = CorrelationDetector(co_occurrence_window_seconds=120)
        det._break_cycles = {"sensor.a": 2, "sensor.b": 1}
        data = det.to_dict()
        assert "break_cycles" in data
        restored = CorrelationDetector.from_dict(data)
        assert restored._break_cycles == {"sensor.a": 2, "sensor.b": 1}

    def test_from_dict_empty(self) -> None:
        det = CorrelationDetector.from_dict({})
        assert len(det._pairs) == 0
        assert len(det._learned_pairs) == 0


# ---------------------------------------------------------------------------
# Edge case — zero HA imports
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CorrelationDetector — decay and entity removal
# ---------------------------------------------------------------------------


class TestDecayAndRemoval:
    """Tests for decay_stale_pairs() and remove_entity() methods."""

    @staticmethod
    def _build_detector_with_pairs() -> CorrelationDetector:
        """Build a detector with multiple pairs in various states.

        Pair ("sensor.a", "sensor.b"):
            - 47 co-occurrences, learned (high PMI)
        Pair ("sensor.a", "sensor.c"):
            - 3 co-occurrences, NOT learned, below min_observations
        Pair ("sensor.b", "sensor.c"):
            - 15 co-occurrences, NOT learned (low PMI due to high solos)
        """
        det = CorrelationDetector(
            co_occurrence_window_seconds=120,
            min_observations=10,
            pmi_threshold=1.0,
        )
        # Pair 1: high PMI, will be learned
        pair_ab = CorrelationPair(
            entities=("sensor.a", "sensor.b"),
            co_occurrences=47,
            solo_counts={"sensor.a": 10, "sensor.b": 5},
            first_observed="2026-01-01T00:00:00",
        )
        det._pairs[("sensor.a", "sensor.b")] = pair_ab

        # Pair 2: too few co-occurrences, noise pair
        pair_ac = CorrelationPair(
            entities=("sensor.a", "sensor.c"),
            co_occurrences=3,
            solo_counts={"sensor.a": 2, "sensor.c": 1},
            first_observed="2026-01-02T00:00:00",
        )
        det._pairs[("sensor.a", "sensor.c")] = pair_ac

        # Pair 3: enough co-occurrences but low PMI (lots of solos)
        pair_bc = CorrelationPair(
            entities=("sensor.b", "sensor.c"),
            co_occurrences=15,
            solo_counts={"sensor.b": 500, "sensor.c": 500},
            first_observed="2026-01-03T00:00:00",
        )
        det._pairs[("sensor.b", "sensor.c")] = pair_bc

        # Global event counts
        det._entity_event_counts = {
            "sensor.a": 62,
            "sensor.b": 567,
            "sensor.c": 519,
        }
        det._total_event_count = 62 + 567 + 519 + 200  # background events
        det._break_cycles = {"sensor.a": 2, "sensor.c": 1}

        det.recompute()
        return det

    def test_decay_removes_noise_pair(self) -> None:
        """decay_stale_pairs removes pair with co_occurrences < min_observations
        that is NOT in _learned_pairs."""
        det = self._build_detector_with_pairs()
        # Pair ("sensor.a", "sensor.c") has 3 co-occurrences < 10, not learned
        assert ("sensor.a", "sensor.c") not in det._learned_pairs
        det.decay_stale_pairs()
        assert ("sensor.a", "sensor.c") not in det._pairs

    def test_decay_keeps_learned_pair(self) -> None:
        """decay_stale_pairs keeps pair that IS in _learned_pairs."""
        det = self._build_detector_with_pairs()
        assert ("sensor.a", "sensor.b") in det._learned_pairs
        det.decay_stale_pairs()
        assert ("sensor.a", "sensor.b") in det._pairs

    def test_decay_keeps_pair_with_enough_observations(self) -> None:
        """decay_stale_pairs keeps pair with co_occurrences >= min_observations
        even if not learned (may become learned later)."""
        det = self._build_detector_with_pairs()
        # Pair ("sensor.b", "sensor.c") has 15 co-occurrences >= 10, but low PMI
        assert ("sensor.b", "sensor.c") not in det._learned_pairs
        det.decay_stale_pairs()
        assert ("sensor.b", "sensor.c") in det._pairs

    def test_recompute_calls_decay(self) -> None:
        """recompute() calls decay_stale_pairs() automatically at the end."""
        det = self._build_detector_with_pairs()
        # Add a new noise pair that should be pruned
        noise_pair = CorrelationPair(
            entities=("sensor.x", "sensor.y"),
            co_occurrences=2,
            solo_counts={},
            first_observed="2026-02-01T00:00:00",
        )
        det._pairs[("sensor.x", "sensor.y")] = noise_pair
        assert ("sensor.x", "sensor.y") in det._pairs
        # recompute should prune it
        det.recompute()
        assert ("sensor.x", "sensor.y") not in det._pairs

    def test_remove_entity_purges_pairs(self) -> None:
        """remove_entity purges all pairs containing that entity from _pairs."""
        det = self._build_detector_with_pairs()
        det.remove_entity("sensor.a")
        for key in det._pairs:
            assert "sensor.a" not in key

    def test_remove_entity_purges_learned_pairs(self) -> None:
        """remove_entity purges matching entries from _learned_pairs."""
        det = self._build_detector_with_pairs()
        assert ("sensor.a", "sensor.b") in det._learned_pairs
        det.remove_entity("sensor.a")
        for key in det._learned_pairs:
            assert "sensor.a" not in key

    def test_remove_entity_purges_event_counts(self) -> None:
        """remove_entity purges entity from _entity_event_counts and
        decrements _total_event_count by that entity's count."""
        det = self._build_detector_with_pairs()
        count_a = det._entity_event_counts["sensor.a"]
        old_total = det._total_event_count
        det.remove_entity("sensor.a")
        assert "sensor.a" not in det._entity_event_counts
        assert det._total_event_count == old_total - count_a

    def test_remove_entity_purges_break_cycles(self) -> None:
        """remove_entity purges entity from _break_cycles."""
        det = self._build_detector_with_pairs()
        assert "sensor.a" in det._break_cycles
        det.remove_entity("sensor.a")
        assert "sensor.a" not in det._break_cycles

    def test_remove_entity_unknown_is_noop(self) -> None:
        """remove_entity with unknown entity_id is a no-op (no error)."""
        det = self._build_detector_with_pairs()
        pairs_before = dict(det._pairs)
        learned_before = set(det._learned_pairs)
        total_before = det._total_event_count
        det.remove_entity("sensor.nonexistent")
        assert det._pairs == pairs_before
        assert det._learned_pairs == learned_before
        assert det._total_event_count == total_before


class TestNoHAImports:
    """Ensure the module has no Home Assistant dependencies."""

    def test_no_homeassistant_import(self) -> None:
        import inspect

        import custom_components.behaviour_monitor.correlation_detector as mod

        source = inspect.getsource(mod)
        assert "homeassistant" not in source
