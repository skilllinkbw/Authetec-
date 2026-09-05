"""
Authetec Risk Domain Models
===========================

Shared types used by all engines: risk scores, decisions, signals,
evidence references, and engine results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Decision(str, Enum):
    CLEAR = "CLEAR"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VectorSource(str, Enum):
    CHROMA = "chroma"
    QDRANT = "qdrant"
    MEMORY = "memory"


@dataclass
class Signal:
    """A single explainable signal produced by an engine."""

    name: str
    value: float
    weight: float = 1.0
    reason: str = ""
    source: str = ""


@dataclass
class EvidenceRef:
    """Immutable reference to stored evidence (never inline sensitive data)."""

    evidence_id: str
    storage_uri: str
    content_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineResult:
    """Standard engine output."""

    engine: str
    risk_score: float
    confidence: float
    decision: Decision
    signals: List[Signal] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    evidence: List[EvidenceRef] = field(default_factory=list)
    model_version: str = ""
    processing_time_ms: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine": self.engine,
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "decision": self.decision.value,
            "signals": [s.__dict__ for s in self.signals],
            "reasons": self.reasons,
            "evidence": [e.__dict__ for e in self.evidence],
            "model_version": self.model_version,
            "processing_time_ms": self.processing_time_ms,
            "extra": self.extra,
            "timestamp": self.timestamp,
        }


@dataclass
class UnifiedRiskResult:
    """Final unified risk output from the RiskEngine."""

    risk_score: float
    confidence: float
    decision: Decision
    contributing_signals: Dict[str, float]
    model_versions: Dict[str, str]
    evidence_ids: List[str]
    correlation_id: str
    timestamp: str = field(default_factory=utcnow_iso)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "decision": self.decision.value,
            "contributing_signals": self.contributing_signals,
            "model_versions": self.model_versions,
            "evidence_ids": self.evidence_ids,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "reasons": self.reasons,
        }