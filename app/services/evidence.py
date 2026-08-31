"""
Evidence Engine
===============

Stores immutable references to evidence artifacts.  Raw sensitive
files are referenced (object storage URI) rather than duplicated.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("authetec.evidence")


@dataclass
class EvidenceRecord:
    evidence_id: str
    tenant_id: str
    storage_uri: str
    content_type: str = ""
    purpose: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvidenceEngine:
    """Evidence reference store (in-memory + optional Supabase)."""

    def __init__(self) -> None:
        self._records: Dict[str, EvidenceRecord] = {}
        self._sb = None
        try:
            from app.infrastructure.supabase import get_supabase
            self._sb = get_supabase()
            if not self._sb.available:
                self._sb = None
        except Exception:
            self._sb = None

    def store(
        self,
        *,
        tenant_id: str,
        storage_uri: str,
        content_type: str = "",
        purpose: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvidenceRecord:
        if not storage_uri:
            raise ValueError("storage_uri is required")
        record = EvidenceRecord(
            evidence_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            storage_uri=storage_uri,
            content_type=content_type,
            purpose=purpose,
            metadata=metadata or {"retention_days": None, "immutable": True},
        )
        self._records[record.evidence_id] = record
        if self._sb:
            try:
                self._sb.insert("evidence", [{
                    "evidence_id": record.evidence_id,
                    "tenant_id": tenant_id,
                    "storage_uri": storage_uri,
                    "content_type": content_type,
                    "purpose": purpose,
                    "metadata": record.metadata,
                }])
            except Exception as e:
                logger.warning("Evidence persistence failed: %s", e)
        return record

    def get(self, evidence_id: str, tenant_id: str) -> Optional[EvidenceRecord]:
        rec = self._records.get(evidence_id)
        if rec and rec.tenant_id == tenant_id:
            return rec
        return None

    def list_for_tenant(self, tenant_id: str, limit: int = 50) -> List[EvidenceRecord]:
        out = [r for r in self._records.values() if r.tenant_id == tenant_id]
        return out[-limit:]


_engine: Optional[EvidenceEngine] = None


def get_evidence_engine() -> EvidenceEngine:
    global _engine
    if _engine is None:
        _engine = EvidenceEngine()
    return _engine