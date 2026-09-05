"""Evidence registry schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvidenceOut(BaseModel):
    evidence_id: str
    tenant_id: str
    storage_uri: str
    content_type: str = ""
    purpose: str = ""
    created_at: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidenceListOut(BaseModel):
    evidence: List[EvidenceOut]
    count: int
