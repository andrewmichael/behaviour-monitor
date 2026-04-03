"""Shared alert result types for the behaviour monitor detection engines.

Pure Python stdlib only. Zero Home Assistant imports.
Used by both acute_detector.py and drift_detector.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AlertType(str, Enum):
    """Type of alert produced by a detection engine."""

    INACTIVITY = "inactivity"
    UNUSUAL_TIME = "unusual_time"
    DRIFT = "drift"
    CORRELATION_BREAK = "correlation_break"


class AlertSeverity(str, Enum):
    """Severity level of an alert."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class AlertResult:
    """Structured result produced by a detection engine.

    Carries enough context for the coordinator to decide whether to send
    a notification and to populate sensor attributes.

    Fields:
        entity_id:   The entity that triggered the alert.
        alert_type:  Which detection engine produced this alert.
        severity:    Severity tier (LOW / MEDIUM / HIGH).
        confidence:  0.0–1.0 confidence from the routine model at alert time.
        explanation: Human-readable description of the anomaly.
        timestamp:   ISO 8601 timestamp string at detection time.
        details:     Optional extra data (ratios, thresholds, etc.) for attrs.
    """

    entity_id: str
    alert_type: AlertType
    severity: AlertSeverity
    confidence: float
    explanation: str
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict with enum values as plain strings."""
        return {
            "entity_id": self.entity_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "timestamp": self.timestamp,
            "details": self.details,
        }
