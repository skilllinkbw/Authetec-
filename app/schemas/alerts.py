"""Alert management schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertOut(BaseModel):
    alert_id: str
    tenant_id: str
    type: str
    severity: str
    risk_score: float
    source: str
    evidence_ids: List[str] = Field(default_factory=list)
    message: str = ""
    status: str = "OPEN"
    created_at: str = ""
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AlertActionOut(BaseModel):
    alert_id: str
    status: str
    updated: bool


class AlertListOut(BaseModel):
    alerts: List[AlertOut]
    count: int
