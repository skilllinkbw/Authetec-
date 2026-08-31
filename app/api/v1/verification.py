"""Document & signature verification endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, UploadFile

from app.common.deps import TenantContext, get_tenant_context
from app.common.errors import BadRequestError
from app.core.config import get_settings
from app.engines.document import DocumentEngine, DocumentInput
from app.engines.signature import SignatureEngine, SignatureSample, _b64_decode
from app.models.risk import Decision, Severity
from app.schemas import EngineResultOut, SignatureEnrollIn, SignatureOut, SignatureVerifyIn

logger = logging.getLogger("authetec.api.verification")
router = APIRouter(tags=["verification"])


def _result_out(result) -> EngineResultOut:
    return EngineResultOut.model_validate(result.to_dict())


@router.post(
    "/verification/documents",
    response_model=EngineResultOut,
    summary="Verify an identity document (PDF/JPEG/PNG/TIFF)",
)
async def verify_document(
    file: UploadFile = File(...),
    expected_type: str = "",
    tenant: TenantContext = Depends(get_tenant_context),
) -> EngineResultOut:
    content = await file.read()
    declared = file.content_type or ""
    if declared and declared not in get_settings().allowed_image_types:
        # Content sniffing below is authoritative; a wrong declaration with
        # valid magic bytes still passes, but executable/archive types are
        # rejected by the engine regardless.
        logger.debug("Declared content type %s not in allow-list", declared)
    try:
        engine = DocumentEngine(tenant_id=tenant.tenant_id)
        result = engine.verify(
            DocumentInput(filename=file.filename or "upload", content=content,
                          declared_content_type=declared),
            expected_type=expected_type or None,
            tenant_id=tenant.tenant_id,
        )
    except ValueError as e:
        raise BadRequestError(str(e)) from e

    if result.decision == Decision.BLOCK:
        _create_document_alert(tenant.tenant_id, result)
    return _result_out(result)


def _create_document_alert(tenant_id: str, result) -> None:
    try:
        from app.services.alerts import get_alert_engine
        get_alert_engine().create(
            tenant_id=tenant_id,
            alert_type="document_fraud",
            severity=Severity.HIGH,
            risk_score=result.risk_score,
            source="document",
            evidence_ids=[ev.evidence_id for ev in result.evidence],
            message="; ".join(result.reasons[:2]),
            metadata={"classification": result.extra.get("classification", {})},
        )
    except Exception as e:  # alerting must never break verification
        logger.debug("document alert skipped: %s", e)


@router.post(
    "/verification/signatures/enroll",
    response_model=SignatureOut,
    summary="Enroll a reference signature",
)
def enroll_signature(
    payload: SignatureEnrollIn,
    tenant: TenantContext = Depends(get_tenant_context),
) -> SignatureOut:
    try:
        image = _b64_decode(payload.image_b64)
    except ValueError as e:
        raise BadRequestError(str(e)) from e
    result = SignatureEngine().enroll(
        SignatureSample(
            image_bytes=image, label=payload.label, owner_id=payload.owner_id,
            tenant_id=tenant.tenant_id, monitored=payload.monitored,
        ),
        tenant_id=tenant.tenant_id,
    )
    return SignatureOut(
        signature_id=result.extra.get("signature_id", ""),
        result=_result_out(result),
        metadata={"sha256": result.extra.get("sha256", "")},
    )


@router.post(
    "/verification/signatures/verify",
    response_model=SignatureOut,
    summary="Verify a signature against an enrolled reference",
)
def verify_signature(
    payload: SignatureVerifyIn,
    tenant: TenantContext = Depends(get_tenant_context),
) -> SignatureOut:
    try:
        image = _b64_decode(payload.image_b64)
    except ValueError as e:
        raise BadRequestError(str(e)) from e
    result = SignatureEngine().verify(
        SignatureSample(
            image_bytes=image, owner_id=payload.owner_id, tenant_id=tenant.tenant_id,
        ),
        reference_id=payload.reference_id,
        tenant_id=tenant.tenant_id,
    )
    return SignatureOut(
        signature_id=result.extra.get("signature_id", ""),
        result=_result_out(result),
    )
