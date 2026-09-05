"""Unified risk aggregation endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from app.common.deps import TenantContext, get_tenant_context
from app.engines.risk import RiskEngine
from app.models.risk import Decision, EngineResult, EvidenceRef, Signal
from app.schemas import EngineResultOut, UnifiedRiskOut

router = APIRouter(tags=["risk"])


@router.post(
    "/risk/aggregate",
    response_model=UnifiedRiskOut,
    summary="Aggregate engine results into a unified risk decision",
)
def aggregate_risk(
    results: List[EngineResultOut],
    tenant: TenantContext = Depends(get_tenant_context),
) -> UnifiedRiskOut:
    engine_results = [
        EngineResult(
            engine=r.engine,
            risk_score=r.risk_score,
            confidence=r.confidence,
            decision=Decision(r.decision.value),
            signals=[Signal(**s.model_dump()) for s in r.signals],
            reasons=r.reasons,
            evidence=[
                EvidenceRef(
                    evidence_id=e.get("evidence_id", ""),
                    storage_uri=e.get("storage_uri", ""),
                    content_type=e.get("content_type", ""),
                )
                for e in r.evidence
            ],
            model_version=r.model_version,
            processing_time_ms=r.processing_time_ms,
            extra=r.extra,
            timestamp=r.timestamp,
        )
        for r in results
    ]
    unified = RiskEngine().aggregate(engine_results, tenant_id=tenant.tenant_id)
    return UnifiedRiskOut.model_validate(unified.to_dict())
