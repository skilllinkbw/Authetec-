"""Verification endpoint schemas: documents and signatures."""

from __future__ import annotations

from typing import Dict, Any

from pydantic import BaseModel, Field, field_validator

from .common import EngineResultOut


class SignatureEnrollIn(BaseModel):
    """Enroll a reference signature image (base64-encoded PNG/JPEG)."""

    owner_id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=128)
    image_b64: str = Field(min_length=16, max_length=16_000_000)
    monitored: bool = False

    @field_validator("image_b64")
    @classmethod
    def _strip_data_url(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("data:"):
            _, _, v = v.partition(",")
        if not v:
            raise ValueError("image_b64 payload is empty")
        return v


class SignatureVerifyIn(BaseModel):
    """Verify a signature image against a reference sample."""

    owner_id: str = Field(min_length=1, max_length=64)
    reference_id: str = Field(default="", max_length=64)
    image_b64: str = Field(min_length=16, max_length=16_000_000)

    @field_validator("image_b64")
    @classmethod
    def _strip_data_url(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("data:"):
            _, _, v = v.partition(",")
        if not v:
            raise ValueError("image_b64 payload is empty")
        return v


class SignatureOut(BaseModel):
    signature_id: str
    result: EngineResultOut
    metadata: Dict[str, Any] = Field(default_factory=dict)
