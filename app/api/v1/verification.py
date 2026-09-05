"""Document & signature verification endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, UploadFile

from app.common.deps import TenantContext, get_tenant_context
from app.common.errors import BadRequestError
from app.core.config import get_settings
from app.engines.document import DocumentEngine, DocumentInput
from app.engines.identity_document import IdentityDocumentEngine, IdentityDocumentInput
from app.engines.signature import SignatureEngine, SignatureSample, _b64_decode
from app.models.risk import Decision, Severity
from app.schemas import (
    EngineResultOut, SignatureEnrollIn, SignatureOut, SignatureVerifyIn,
    FaceVerifyIn, LivenessResultOut, LivenessVerifyIn,
)

logger = logging.getLogger("authetec.api.verification")
router = APIRouter(tags=["verification"])


def _result_out(result) -> EngineResultOut:
    return EngineResultOut.model_validate(result.to_dict())


# Mirrors engines.document.MAX_LENGTH; enforced at the API boundary BEFORE
# the body is fully buffered, defending against oversized uploads.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_UPLOAD_CHUNK = 1024 * 1024


async def _read_limited(file: UploadFile) -> bytes:
    """Stream an upload with a hard size cap.

    ``UploadFile.read()`` buffers the whole body; a malicious client can
    stream an arbitrarily large file unless we cap it while reading.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            # Abort before accumulating the oversized body in memory.
            raise BadRequestError("File exceeds 20 MB upload limit")
        chunks.append(chunk)
    return b"".join(chunks)


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
    content = await _read_limited(file)
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


@router.post(
    "/verification/faces",
    response_model=EngineResultOut,
    summary="Verify a candidate face against a reference face",
    description=(
        "Evaluates face similarity, liveness signals and identity "
        "consistency as separate concerns. Raw images and embeddings are "
        "never persisted or echoed back."
    ),
)
def verify_face(
    payload: FaceVerifyIn,
    tenant: TenantContext = Depends(get_tenant_context),
) -> EngineResultOut:
    from app.engines.face import (
        FaceMatchInput, get_face_engine, LivenessCheck, _b64_decode,
    )

    # Strict base64 validation up front: malformed payloads are a client
    # error (400), while valid-base64-but-undecodable images fail safe
    # inside the engine as a REVIEW decision.
    try:
        _b64_decode(payload.reference_image_b64)
        _b64_decode(payload.candidate_image_b64)
    except ValueError as e:
        raise BadRequestError(str(e)) from e

    # Provider-independent: the engine behind this endpoint is selected by
    # configuration (AUTHETEC_FACE_PROVIDER); default stays the phase-1
    # deterministic NON_PRODUCTION_FALLBACK.
    engine = get_face_engine()
    match = FaceMatchInput(
        reference_image_b64=payload.reference_image_b64,
        candidate_image_b64=payload.candidate_image_b64,
        liveness_checks=[
            LivenessCheck(name=c.name, passed=c.passed, score=c.score)
            for c in payload.liveness_checks
        ],
        declared_identity_match=payload.declared_identity_match,
    )
    result = engine.verify(match, tenant_id=tenant.tenant_id)

    if result.decision == Decision.BLOCK:
        try:
            from app.services.alerts import get_alert_engine
            get_alert_engine().create(
                tenant_id=tenant.tenant_id,
                alert_type="face_verification_failure",
                severity=Severity.HIGH,
                risk_score=result.risk_score,
                source="face",
                evidence_ids=[],
                message="; ".join(result.reasons[:2]),
                metadata={"similarity": result.extra.get("similarity")},
            )
        except Exception:
            pass  # alert creation must not break the response
    return _result_out(result)


@router.post(
    "/verification/liveness",
    response_model=LivenessResultOut,
    summary="Run native multi-layer presentation-attack detection (PAD)",
    description=(
        "Evaluates a capture with the AUTHeTEC native PAD engine: passive "
        "texture/spectral signals, frame-sequence replay detection and "
        "camera-source injection checks. Returns a tri-state decision "
        "(LIVE / NOT_LIVE / INCONCLUSIVE); INCONCLUSIVE and NOT_LIVE are "
        "never reported as live. Biometric content is never echoed back."
    ),
)
def verify_liveness(
    payload: LivenessVerifyIn,
    tenant: TenantContext = Depends(get_tenant_context),
) -> LivenessResultOut:
    from app.biometric.integration import pad_result_to_engine_result
    from app.biometric.pad import get_pad_engine

    def _frame_bytes(b64: str) -> bytes:
        try:
            return _b64_decode(b64)
        except ValueError as e:
            raise BadRequestError(str(e)) from e

    image = _frame_bytes(payload.image_b64)
    frames = [
        (_frame_bytes(f.image_b64), f.timestamp_s) for f in payload.frames
    ]
    frame_payloads = [f for f, _ in frames]
    frame_ts = [t for _, t in frames if t is not None]
    if frame_ts and len(frame_ts) != len(frame_payloads):
        raise BadRequestError(
            "frame timestamps must be provided for every frame or none")

    # Native PAD under a hard time budget; all failure modes fail safe
    # (timeout/exception/malformed -> NOT_LIVE, never LIVE).
    pad = get_pad_engine().check(
        image,
        timeout_s=payload.timeout_s,
        frames=frame_payloads,
        frame_timestamps_s=frame_ts or None,
        metadata=payload.metadata or None,
    )
    risk_signal = pad_result_to_engine_result(
        pad, tenant_id=tenant.tenant_id)
    return LivenessResultOut(
        decision=pad.decision.value,
        is_live=pad.is_live,
        confidence=pad.confidence,
        timed_out=pad.timed_out,
        attacks=[
            {"indicator": a.indicator, "confidence": a.confidence,
             "method": a.method}
            for a in pad.attacks
        ],
        signals=list(pad.signals)[:10],
        notes=pad.notes,
        model_version=pad.model_version,
        processing_time_ms=pad.processing_time_ms,
        provider=pad.provider,
        quality_issues=list(pad.quality_issues),
        risk_signal=_result_out(risk_signal),
    )


@router.post(
    "/verification/identity",
    response_model=EngineResultOut,
    summary="Verify an identity document (passport, national ID, driver's licence)",
    description=(
        "Unified identity document verification with document profiles, "
        "MRZ validation, and explainable risk decisions."
    ),
)
async def verify_identity_document(
    file: UploadFile = File(...),
    document_type: str = "",
    country_code: str = "",
    tenant: TenantContext = Depends(get_tenant_context),
) -> EngineResultOut:
    content = await _read_limited(file)
    declared = file.content_type or ""
    try:
        engine = IdentityDocumentEngine(tenant_id=tenant.tenant_id)
        result = engine.verify(
            IdentityDocumentInput(
                filename=file.filename or "upload",
                content=content,
                declared_content_type=declared,
                document_type=document_type,
                country_code=country_code,
            ),
            tenant_id=tenant.tenant_id,
        )
    except ValueError as e:
        raise BadRequestError(str(e)) from e

    if result.decision == Decision.BLOCK:
        try:
            from app.services.alerts import get_alert_engine
            get_alert_engine().create(
                tenant_id=tenant.tenant_id,
                alert_type="identity_document_fraud",
                severity=Severity.HIGH,
                risk_score=result.risk_score,
                source="identity_document",
                evidence_ids=[],
                message="; ".join(result.reasons[:2]),
                metadata={
                    "document_type": document_type,
                    "country_code": country_code,
                },
            )
        except Exception as e:
            logger.debug("identity document alert skipped: %s", e)
    return _result_out(result)
