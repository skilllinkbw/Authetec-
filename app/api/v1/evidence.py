"""Evidence registry endpoints (tenant-scoped, references only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.deps import TenantContext, get_tenant_context
from app.common.errors import NotFoundError
from app.schemas import EvidenceListOut, EvidenceOut
from app.services.evidence import get_evidence_engine

router = APIRouter(tags=["evidence"])


def _to_out(rec) -> EvidenceOut:
    return EvidenceOut(
        evidence_id=rec.evidence_id,
        tenant_id=rec.tenant_id,
        storage_uri=rec.storage_uri,
        content_type=rec.content_type,
        purpose=rec.purpose,
        created_at=rec.created_at,
        metadata=rec.metadata,
    )


@router.get("/evidence", response_model=EvidenceListOut,
            summary="List evidence references for the caller's tenant")
def list_evidence(
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
) -> EvidenceListOut:
    records = get_evidence_engine().list_for_tenant(tenant.tenant_id, limit=limit)
    out = [_to_out(r) for r in records]
    return EvidenceListOut(evidence=out, count=len(out))


@router.get("/evidence/{evidence_id}", response_model=EvidenceOut,
            summary="Fetch a single evidence reference (tenant-checked)")
def get_evidence(
    evidence_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> EvidenceOut:
    rec = get_evidence_engine().get(evidence_id, tenant.tenant_id)
    if rec is None:
        # Deliberately identical for missing AND cross-tenant ids (no IDOR oracle).
        raise NotFoundError(f"Evidence {evidence_id} not found")
    return _to_out(rec)
