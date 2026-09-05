"""AI security screening endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.common.deps import TenantContext, get_tenant_context
from app.schemas import AiScreenIn, AiScreenOut, AiScreenSignalOut
from app.services.ai_security import get_ai_security_monitor

logger = logging.getLogger("authetec.api.security")
router = APIRouter(tags=["security"])


@router.post(
    "/security/ai/screen",
    response_model=AiScreenOut,
    summary="Screen AI input/output for injection and secret leakage",
    description=(
        "Deterministic policy control around AI use. Screens prompts for "
        "prompt-injection indicators and both modes for credential-shaped "
        "content. The screened text is never echoed or persisted."
    ),
)
def screen_ai(
    payload: AiScreenIn,
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
) -> AiScreenOut:
    monitor = get_ai_security_monitor()
    if payload.mode == "output":
        result = monitor.screen_output(payload.text)
    else:
        result = monitor.screen_prompt(payload.text, context=payload.context)

    correlation_id = getattr(request.state, "correlation_id", "")
    monitor.record_telemetry(tenant_id=tenant.tenant_id, result=result,
                             correlation_id=correlation_id)

    return AiScreenOut(
        screening_id=result.screening_id,
        mode=result.mode,
        decision=result.decision.value,
        prompt_injection_score=round(result.prompt_injection_score, 4),
        secret_leak_score=round(result.secret_leak_score, 4),
        validation_valid=result.validation_valid,
        validation_notes=result.validation_notes,
        signals=[AiScreenSignalOut(**s.__dict__) for s in result.signals],
        reasons=result.reasons,
        model_version=result.model_version,
        timestamp=result.timestamp,
    )