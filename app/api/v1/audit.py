"""Audit trail endpoints (read-only, tenant-scoped, integrity verification)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.common.deps import TenantContext, get_tenant_context
from app.schemas import AuditEntryOut, AuditIntegrityOut, AuditListOut
from app.services.audit import get_audit_logger

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=AuditListOut,
            summary="Recent audit entries for the caller's tenant")
def list_audit(
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
) -> AuditListOut:
    entries = get_audit_logger().recent(limit=limit, tenant_id=tenant.tenant_id)
    out = [AuditEntryOut.model_validate(e) for e in entries]
    return AuditListOut(entries=out, count=len(out))


@router.get("/audit/integrity", response_model=AuditIntegrityOut,
            summary="Verify the audit log hash chain")
def audit_integrity(
    tenant: TenantContext = Depends(get_tenant_context),
) -> AuditIntegrityOut:
    log = get_audit_logger()
    checked = len(log.recent(limit=10_000, tenant_id=tenant.tenant_id))
    return AuditIntegrityOut(
        valid=log.verify_chain(),
        entries_checked=checked,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
