"""AI security screening schemas."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, field_validator

from .common import DecisionStr


class AiScreenIn(BaseModel):
    """Content to screen before/after an AI call.

    ``mode`` selects the policy: ``prompt`` screens adversarial and
    credential signals; ``output`` screens for secret leakage only.
    """

    text: str = Field(min_length=1, max_length=100_000)
    context: str = Field(default="", max_length=2_000)
    mode: str = Field(default="prompt", pattern="^(prompt|output)$")

    @field_validator("text")
    @classmethod
    def _strip_control_zeros(cls, v: str) -> str:
        # Reject embedded NUL bytes up front (defence-in-depth).
        if "\x00" in v:
            raise ValueError("NUL bytes are not allowed in screened content")
        return v


class AiScreenSignalOut(BaseModel):
    name: str
    detail: str = ""
    severity: float = 0.0


class AiScreenOut(BaseModel):
    """Structured screening record (no raw screened content is echoed)."""

    screening_id: str
    mode: str
    decision: DecisionStr
    prompt_injection_score: float
    secret_leak_score: float
    validation_valid: bool
    validation_notes: List[str] = Field(default_factory=list)
    signals: List[AiScreenSignalOut] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    model_version: str = ""
    timestamp: str = ""