"""Alert value types shared by every model and the router."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import total_ordering
from typing import Any


class AlertClass(str, Enum):
    WELFARE = "welfare"
    HEALTH = "health"
    STATISTICAL = "statistical"


@total_ordering
class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def _rank(self) -> int:
        return SEVERITY_ORDER.index(self)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self._rank() < other._rank()

    def bump(self) -> "Severity":
        """One level higher, capped at CRITICAL."""
        return SEVERITY_ORDER[min(self._rank() + 1, len(SEVERITY_ORDER) - 1)]

    def at_least(self, floor: "Severity") -> bool:
        return self._rank() >= floor._rank()


SEVERITY_ORDER: list[Severity] = [
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
]


@dataclass
class Alert:
    cls: AlertClass
    source: str
    kind: str
    severity: Severity
    explanation: str
    raised_at: datetime
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.cls.value}:{self.source}:{self.kind}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "class": self.cls.value,
            "source": self.source,
            "kind": self.kind,
            "severity": self.severity.value,
            "explanation": self.explanation,
            "raised_at": self.raised_at.isoformat(),
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Alert":
        return cls(
            cls=AlertClass(data["class"]),
            source=str(data["source"]),
            kind=str(data["kind"]),
            severity=Severity(data["severity"]),
            explanation=str(data.get("explanation", "")),
            raised_at=datetime.fromisoformat(data["raised_at"]),
            details=dict(data.get("details", {})),
        )
