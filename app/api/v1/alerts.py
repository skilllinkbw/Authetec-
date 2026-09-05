"""Alert / case-management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from app.common.deps import TenantContext, get_tenant_context
from app.common.errors import NotFoundError
from app.schemas import (
    AlertActionOut, AlertAssignIn, AlertListOut, AlertNoteIn, AlertOut,
)
from app.services.alerts import get_alert_engine

router = APIRouter(tags=["alerts"])


def _to_out(alert) -> AlertOut:
    return AlertOut(
        alert_id=alert.alert_id,
        tenant_id=alert.tenant_id,
        type=alert.type,
        severity=alert.severity.value,
        risk_score=alert.risk_score,
        source=alert.source,
        evidence_ids=alert.evidence_ids,
        message=alert.message,
        status=alert.status,
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        assigned_to=alert.assigned_to,
        notes=[{**n} for n in alert.notes],
        metadata=alert.metadata,
    )


@router.get("/alerts", response_model=AlertListOut, summary="List tenant alerts")
def list_alerts(
    status: str | None = Query(default=None, pattern="^(OPEN|ACKNOWLEDGED|RESOLVED)$"),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
) -> AlertListOut:
    alerts = get_alert_engine().list(tenant.tenant_id, limit=limit, status=status)
    out = [_to_out(a) for a in alerts]
    return AlertListOut(alerts=out, count=len(out))


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertActionOut,
             summary="Acknowledge an alert")
def acknowledge_alert(
    alert_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> AlertActionOut:
    alert = get_alert_engine().acknowledge(alert_id, tenant.tenant_id)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found")
    return AlertActionOut(alert_id=alert.alert_id, status=alert.status, updated=True)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertActionOut,
             summary="Resolve an alert")
def resolve_alert(
    alert_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> AlertActionOut:
    alert = get_alert_engine().resolve(alert_id, tenant.tenant_id)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found")
    return AlertActionOut(alert_id=alert.alert_id, status=alert.status,
                          updated=True, assigned_to=alert.assigned_to)


@router.post("/alerts/{alert_id}/assign", response_model=AlertActionOut,
             summary="Assign an open case to an analyst or queue")
def assign_alert(
    alert_id: str,
    payload: AlertAssignIn = Body(...),
    tenant: TenantContext = Depends(get_tenant_context),
) -> AlertActionOut:
    alert = get_alert_engine().assign(alert_id, tenant.tenant_id, payload.assignee)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found")
    _audit_case_action(tenant.tenant_id, alert_id, "assigned",
                       alert.status.lower(), {"assignee": payload.assignee})
    return AlertActionOut(alert_id=alert.alert_id, status=alert.status,
                          updated=True, assigned_to=alert.assigned_to)


@router.post("/alerts/{alert_id}/notes", response_model=AlertActionOut,
             summary="Append an analyst note to a case")
def add_alert_note(
    alert_id: str,
    payload: AlertNoteIn = Body(...),
    tenant: TenantContext = Depends(get_tenant_context),
) -> AlertActionOut:
    alert = get_alert_engine().add_note(alert_id, tenant.tenant_id,
                                        payload.text, payload.author)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found")
    _audit_case_action(tenant.tenant_id, alert_id, "note_added",
                       alert.status.lower(), {"author": payload.author})
    return AlertActionOut(alert_id=alert.alert_id, status=alert.status,
                          updated=True, assigned_to=alert.assigned_to)


def _audit_case_action(tenant_id: str, alert_id: str, action: str,
                       result: str, metadata: dict) -> None:
    """Audit case-management actions; never let audit failure break the API."""
    try:
        from app.services.audit import get_audit_logger
        get_audit_logger().log(
            event_type="case.updated",
            tenant_id=tenant_id,
            resource_type="case",
            resource_id=alert_id,
            action=action,
            result=result,
            metadata=metadata,
        )
    except Exception:
        pass
