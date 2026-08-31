"""Shared schema primitives derived from the risk domain models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class DecisionStr(str, Enum):
    CLEAR = "CLEAR"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class SignalOut(BaseModel):
    name: str
    value: float
    weight: float = 1.0
    reason: str = ""
    source: str = ""


class EngineResultOut(BaseModel):
    """Serialised form of ``app.models.risk.EngineResult``."""

    engine: str
    risk_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    decision: DecisionStr
    signals: List[SignalOut] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    model_version: str = ""
    processing_time_ms: float = 0.0
    extra: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class UnifiedRiskOut(BaseModel):
    """Serialised form of ``app.models.risk.UnifiedRiskResult``."""

    risk_score: float
    confidence: float
    decision: DecisionStr
    contributing_signals: Dict[str, float] = Field(default_factory=dict)
    model_versions: Dict[str, str] = Field(default_factory=dict)
    evidence_ids: List[str] = Field(default_factory=list)
    correlation_id: str
    timestamp: str = ""
    reasons: List[str] = Field(default_factory=list)
