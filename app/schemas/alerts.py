"""Alert / case-management schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertNoteOut(BaseModel):
    author: str
    text: str
    created_at: str


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
    assigned_to: Optional[str] = None
    notes: List[AlertNoteOut] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AlertActionOut(BaseModel):
    alert_id: str
    status: str
    updated: bool
    assigned_to: Optional[str] = None


class AlertListOut(BaseModel):
    alerts: List[AlertOut]
    count: int


class AlertAssignIn(BaseModel):
    """Assign an open case to an analyst/queue."""

    assignee: str = Field(min_length=1, max_length=64)


class AlertNoteIn(BaseModel):
    """Add an evidence note to a case."""

    text: str = Field(min_length=1, max_length=2000)
    author: str = Field(default="analyst", min_length=1, max_length=64)
