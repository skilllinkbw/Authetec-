"""Audit trail schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AuditEntryOut(BaseModel):
    """Serialised hash-chained audit entry."""

    event_id: str
    event_type: str
    actor_id: str = "system"
    tenant_id: str = "system"
    resource_type: str = ""
    resource_id: str = ""
    action: str = ""
    timestamp: str = ""
    correlation_id: str = ""
    request_id: Optional[str] = None
    result: str = "success"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = ""
    hash: str = ""


class AuditListOut(BaseModel):
    entries: List[AuditEntryOut]
    count: int


class AuditIntegrityOut(BaseModel):
    """Result of verifying the audit hash chain."""

    valid: bool
    entries_checked: int
    checked_at: str = ""
