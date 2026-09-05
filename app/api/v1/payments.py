"""Payment fraud scoring endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.common.deps import TenantContext, get_tenant_context
from app.engines.payment import PaymentFraudEngine, Transaction
from app.schemas import EngineResultOut, PaymentScoreOut, TransactionIn

router = APIRouter(tags=["payments"])


@router.post(
    "/payments/score",
    response_model=PaymentScoreOut,
    summary="Score a transaction for fraud risk",
)
def score_payment(
    payload: TransactionIn,
    tenant: TenantContext = Depends(get_tenant_context),
) -> PaymentScoreOut:
    # Device risk signals are resolved by the (future) device engine;
    # scoring is fully deterministic from the transaction payload today.
    result = PaymentFraudEngine().score_transaction(
        Transaction(**payload.model_dump()),
        tenant_id=tenant.tenant_id,
    )
    return PaymentScoreOut(
        transaction_id=payload.transaction_id,
        result=EngineResultOut.model_validate(result.to_dict()),
    )
