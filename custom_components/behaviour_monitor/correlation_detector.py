"""CorrelationDetector -- PMI-based co-occurrence discovery.

Pure Python stdlib only. Zero Home Assistant imports.
Discovers entity pairs that fire within a configurable time window,
scores them using Pointwise Mutual Information (PMI), and promotes
pairs that exceed both a minimum co-occurrence count and a PMI threshold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .alert_result import AlertResult, AlertSeverity, AlertType
from .const import (
    DEFAULT_CORRELATION_WINDOW,
    MIN_CO_OCCURRENCES,
    PMI_THRESHOLD,
    SUSTAINED_EVIDENCE_CYCLES,
)


# ---------------------------------------------------------------------------
# CorrelationPair
# ---------------------------------------------------------------------------


@dataclass
class CorrelationPair:
    """A pair of entities tracked for co-occurrence correlation.

    Fields:
        entities:        Sorted tuple of two entity IDs.
        co_occurrences:  Times both entities fired within the window.
        solo_counts:     Per-entity counts of firings without the partner.
        first_observed:  ISO timestamp of first co-occurrence (or None).
    """

    entities: tuple[str, str]
    co_occurrences: int = 0
    solo_counts: dict[str, int] = field(default_factory=dict)
    first_observed: str | None = None

    @property
    def total_events(self) -> int:
        """Total events across co-occurrences and solo firings."""
        return self.co_occurrences + sum(self.solo_counts.values())

    @property
    def co_occurrence_rate(self) -> float:
        """Fraction of total events that are co-occurrences."""
        total = self.total_events
        if total == 0:
            return 0.0
        return self.co_occurrences / total

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "co_occurrences": self.co_occurrences,
            "solo_counts": dict(self.solo_counts),
            "first_observed": self.first_observed,
        }

    @classmethod
    def from_dict(
        cls, entities: tuple[str, str], data: dict[str, Any]
    ) -> "CorrelationPair":
        """Restore from a serialized dict."""
        return cls(
            entities=entities,
            co_occurrences=int(data.get("co_occurrences", 0)),
            solo_counts=dict(data.get("solo_counts", {})),
            first_observed=data.get("first_observed"),
        )


# ---------------------------------------------------------------------------
# CorrelationDetector
# ---------------------------------------------------------------------------


class CorrelationDetector:
    """Discovers co-occurring entity pairs using PMI-based scoring.

    PMI (Pointwise Mutual Information) measures whether two entities
    co-occur more often than expected by chance:

        PMI = log2(P(a,b) / (P(a) * P(b)))

    where P(a,b) is the co-occurrence probability, and P(a), P(b)
    are marginal probabilities computed from global per-entity event
    counts across all pairs.

    Usage:
        detector = CorrelationDetector(co_occurrence_window_seconds=120)

        # On each entity state change:
        detector.record_event(entity_id, now, all_last_seen)

        # Periodically (e.g. daily):
        detector.recompute()

        # For sensor attributes:
        groups = detector.get_correlation_groups()
        partners = detector.get_correlated_entities("sensor.a")
    """

    def __init__(
        self,
        co_occurrence_window_seconds: int = DEFAULT_CORRELATION_WINDOW,
        min_observations: int = MIN_CO_OCCURRENCES,
        pmi_threshold: float = PMI_THRESHOLD,
    ) -> None:
        self._window_seconds = co_occurrence_window_seconds
        self._min_observations = min_observations
        self._pmi_threshold = pmi_threshold
        self._pairs: dict[tuple[str, str], CorrelationPair] = {}
        self._learned_pairs: set[tuple[str, str]] = set()
        # Global per-entity event counts for PMI marginal probabilities
        self._entity_event_counts: dict[str, int] = {}
        self._total_event_count: int = 0
        # Per-entity consecutive-miss counters for sustained-evidence gating
        self._break_cycles: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def record_event(
        self,
        entity_id: str,
        timestamp: datetime,
        all_last_seen: dict[str, datetime],
    ) -> None:
        """Record an entity state-change event and detect co-occurrences.

        For each other entity in *all_last_seen* whose last event falls
        within the co-occurrence window, the shared pair's co_occurrences
        counter is incremented. If no co-occurrence is found with any known
        partner, the entity's solo count is incremented on existing pairs.

        Also tracks global per-entity event counts for PMI computation.

        Args:
            entity_id:     The entity that just fired.
            timestamp:     The time of the event.
            all_last_seen: Map of entity_id -> last event datetime for all
                           currently tracked entities.
        """
        # Track global event count for this entity
        self._entity_event_counts[entity_id] = (
            self._entity_event_counts.get(entity_id, 0) + 1
        )
        self._total_event_count += 1

        had_co_occurrence = False

        for other_id, other_ts in all_last_seen.items():
            if other_id == entity_id:
                continue

            delta = abs((timestamp - other_ts).total_seconds())
            key = tuple(sorted((entity_id, other_id)))  # type: ignore[assignment]

            if delta <= self._window_seconds:
                pair = self._get_or_create_pair(key, timestamp)
                pair.co_occurrences += 1
                had_co_occurrence = True
            else:
                # Outside window -- increment solo if pair already exists
                if key in self._pairs:
                    self._pairs[key].solo_counts.setdefault(entity_id, 0)
                    self._pairs[key].solo_counts[entity_id] += 1

        # If the entity had no co-occurrence with any known partner,
        # increment solo counts on all existing pairs containing it.
        if not had_co_occurrence:
            for key, pair in self._pairs.items():
                if entity_id in key:
                    pair.solo_counts.setdefault(entity_id, 0)
                    pair.solo_counts[entity_id] += 1

    # ------------------------------------------------------------------
    # PMI recomputation
    # ------------------------------------------------------------------

    def recompute(self) -> None:
        """Recompute PMI for all pairs and update the learned set.

        A pair is promoted to the learned set if:
        1. co_occurrences >= min_observations
        2. PMI >= pmi_threshold

        PMI = log2(P(a,b) / (P(a) * P(b)))
        where:
          P(a,b) = co_occurrences / total_global_events
          P(a) = entity_a_global_events / total_global_events
          P(b) = entity_b_global_events / total_global_events

        Global event counts are tracked across all record_event() calls.
        """
        new_learned: set[tuple[str, str]] = set()

        total = self._total_event_count
        if total == 0:
            self._learned_pairs = new_learned
            return

        for key, pair in self._pairs.items():
            if pair.co_occurrences < self._min_observations:
                continue

            entity_a, entity_b = pair.entities
            count_a = self._entity_event_counts.get(entity_a, 0)
            count_b = self._entity_event_counts.get(entity_b, 0)

            if count_a == 0 or count_b == 0:
                continue

            p_co = pair.co_occurrences / total
            p_a = count_a / total
            p_b = count_b / total

            denominator = p_a * p_b
            if denominator <= 0:
                continue

            pmi = math.log2(p_co / denominator)

            if pmi >= self._pmi_threshold:
                new_learned.add(key)

        self._learned_pairs = new_learned

    # ------------------------------------------------------------------
    # Sensor attribute output
    # ------------------------------------------------------------------

    def get_correlation_groups(self) -> list[dict[str, Any]]:
        """Return learned correlation groups for sensor attributes.

        Returns:
            List of dicts with "entities", "co_occurrence_rate",
            and "total_observations" for each learned pair.
        """
        groups: list[dict[str, Any]] = []
        for key in sorted(self._learned_pairs):
            pair = self._pairs[key]
            groups.append(
                {
                    "entities": list(pair.entities),
                    "co_occurrence_rate": round(pair.co_occurrence_rate, 3),
                    "total_observations": pair.total_events,
                }
            )
        return groups

    def get_correlated_entities(self, entity_id: str) -> list[str]:
        """Return entity IDs that are learned partners of the given entity.

        Args:
            entity_id: The entity to look up partners for.

        Returns:
            List of partner entity IDs (may be empty).
        """
        partners: list[str] = []
        for key in sorted(self._learned_pairs):
            if entity_id in key:
                other = key[1] if key[0] == entity_id else key[0]
                partners.append(other)
        return partners

    # ------------------------------------------------------------------
    # Break detection
    # ------------------------------------------------------------------

    def check_breaks(
        self,
        entity_id: str,
        now: datetime,
        last_seen_map: dict[str, datetime],
    ) -> list[AlertResult]:
        """Check whether learned correlation partners are missing.

        Returns an AlertResult list (0 or 1 element) when the triggering
        entity's learned partners have not fired within the co-occurrence
        window for SUSTAINED_EVIDENCE_CYCLES consecutive checks.

        Multiple missing partners are grouped into a single alert (D-02).

        Args:
            entity_id:     The entity that just fired.
            now:           Current datetime.
            last_seen_map: Map of entity_id -> last event datetime for all
                           currently tracked entities.
        """
        partners = self.get_correlated_entities(entity_id)
        if not partners:
            return []

        missing_partners: list[str] = []
        for partner in partners:
            partner_ts = last_seen_map.get(partner)
            if partner_ts is None:
                missing_partners.append(partner)
            elif abs((now - partner_ts).total_seconds()) > self._window_seconds:
                missing_partners.append(partner)

        if not missing_partners:
            self._break_cycles[entity_id] = 0
            return []

        # Increment consecutive-miss counter
        current = self._break_cycles.get(entity_id, 0) + 1
        self._break_cycles[entity_id] = current

        if current < SUSTAINED_EVIDENCE_CYCLES:
            return []

        # Find best confidence from the highest co_occurrence_rate among missing
        best_rate = 0.0
        for partner in missing_partners:
            key = tuple(sorted((entity_id, partner)))
            pair = self._pairs.get(key)  # type: ignore[arg-type]
            if pair is not None:
                best_rate = max(best_rate, pair.co_occurrence_rate)

        sorted_missing = sorted(missing_partners)

        return [
            AlertResult(
                entity_id=entity_id,
                alert_type=AlertType.CORRELATION_BREAK,
                severity=AlertSeverity.LOW,
                confidence=best_rate,
                explanation=(
                    f"{entity_id}: correlation break — expected companion(s) "
                    f"{', '.join(sorted_missing)} not seen within "
                    f"{self._window_seconds}s window"
                ),
                timestamp=now.isoformat(),
                details={
                    "missing_partners": sorted_missing,
                    "consecutive_misses": current,
                    "window_seconds": self._window_seconds,
                },
            )
        ]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize detector state to a JSON-safe dict."""
        pairs_data: dict[str, Any] = {}
        for key, pair in self._pairs.items():
            pair_key = "|".join(key)
            pairs_data[pair_key] = pair.to_dict()

        return {
            "co_occurrence_window_seconds": self._window_seconds,
            "min_observations": self._min_observations,
            "pmi_threshold": self._pmi_threshold,
            "pairs": pairs_data,
            "learned_pairs": ["|".join(k) for k in sorted(self._learned_pairs)],
            "entity_event_counts": dict(self._entity_event_counts),
            "total_event_count": self._total_event_count,
            "break_cycles": dict(self._break_cycles),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CorrelationDetector":
        """Restore a CorrelationDetector from a serialized dict."""
        detector = cls(
            co_occurrence_window_seconds=int(
                data.get("co_occurrence_window_seconds", DEFAULT_CORRELATION_WINDOW)
            ),
            min_observations=int(
                data.get("min_observations", MIN_CO_OCCURRENCES)
            ),
            pmi_threshold=float(
                data.get("pmi_threshold", PMI_THRESHOLD)
            ),
        )

        for pair_key, pair_data in data.get("pairs", {}).items():
            entities = tuple(pair_key.split("|"))  # type: ignore[assignment]
            detector._pairs[entities] = CorrelationPair.from_dict(
                entities, pair_data
            )

        for learned_key in data.get("learned_pairs", []):
            entities = tuple(learned_key.split("|"))  # type: ignore[assignment]
            detector._learned_pairs.add(entities)

        detector._entity_event_counts = dict(
            data.get("entity_event_counts", {})
        )
        detector._total_event_count = int(
            data.get("total_event_count", 0)
        )
        detector._break_cycles = {
            k: int(v) for k, v in data.get("break_cycles", {}).items()
        }

        return detector

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_or_create_pair(
        self,
        key: tuple[str, str],
        timestamp: datetime,
    ) -> CorrelationPair:
        """Get or create a CorrelationPair, setting first_observed on creation."""
        if key not in self._pairs:
            self._pairs[key] = CorrelationPair(
                entities=key,
                first_observed=timestamp.isoformat(),
            )
        return self._pairs[key]
