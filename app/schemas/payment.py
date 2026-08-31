"""Payment fraud scoring request/response schemas."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .common import EngineResultOut


class TransactionIn(BaseModel):
    """Inbound transaction payload (maps to ``engines.payment.Transaction``)."""

    transaction_id: str = Field(min_length=1, max_length=64)
    amount: float = Field(ge=0.0)
    account_id: str = Field(default="", max_length=64)
    merchant: str = Field(default="", max_length=128)
    card_id: str = Field(default="", max_length=64)
    device_id: str = Field(default="", max_length=64)
    ip_address: str = Field(default="", max_length=45)
    channel: str = Field(default="card", max_length=32)
    timestamp: str = Field(default="", max_length=32)
    country: str = Field(default="", max_length=2)
    card_activation_days: int = Field(default=365, ge=0)
    history_amounts_24h: List[float] = Field(default_factory=list, max_length=100)
    history_amounts_7d: List[float] = Field(default_factory=list, max_length=500)
    account_balance: float = Field(default=0.0, ge=0.0)
    account_age_days: int = Field(default=365, ge=0)

    @field_validator("channel")
    @classmethod
    def _channel_known(cls, v: str) -> str:
        allowed = {"card", "bank_transfer", "mobile_money", "crypto", "wallet"}
        if v and v.lower() not in allowed:
            raise ValueError(f"channel must be one of {sorted(allowed)}")
        return v.lower() if v else v


class PaymentScoreOut(BaseModel):
    transaction_id: str
    result: EngineResultOut
