"""Social trust scoring endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.common.deps import TenantContext, get_tenant_context
from app.engines.social import SocialProfileInput, SocialTrustEngine
from app.schemas import EngineResultOut, SocialProfileIn, SocialScoreOut

logger = logging.getLogger("authetec.api.social")
router = APIRouter(tags=["social"])


@router.post(
    "/social/score",
    response_model=SocialScoreOut,
    summary="Score a social/consumer profile for trust risk",
    description=(
        "Deterministic, explainable rule-based social trust scoring. "
        "Protected attributes are never used. External graph/IP signals may "
        "be supplied and are labelled as external in the result."
    ),
)
def score_social(
    payload: SocialProfileIn,
    tenant: TenantContext = Depends(get_tenant_context),
) -> SocialScoreOut:
    profile = SocialProfileInput(**payload.model_dump())
    result = SocialTrustEngine().score(profile, tenant_id=tenant.tenant_id)
    return SocialScoreOut(
        profile_id=payload.profile_id,
        result=EngineResultOut.model_validate(result.to_dict()),
    )