"""Verification endpoint schemas: documents, signatures, and faces."""

from __future__ import annotations

from typing import Dict, Any, List, Optional

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


class LivenessCheckIn(BaseModel):
    """One presentation-attack-detection check outcome supplied by the caller."""

    name: str = Field(min_length=1, max_length=64)
    passed: bool
    score: float = Field(default=1.0, ge=0.0, le=1.0)


class LivenessFrameIn(BaseModel):
    """One frame of a capture sequence (base64-encoded PNG/JPEG)."""

    image_b64: str = Field(min_length=8, max_length=2_000_000)
    timestamp_s: Optional[float] = None

    @field_validator("image_b64")
    @classmethod
    def _strip_data_url(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("data:"):
            _, _, v = v.partition(",")
        if not v:
            raise ValueError("frame payload is empty")
        return v


class LivenessVerifyIn(BaseModel):
    """Run native multi-layer PAD on a capture.

    The primary frame is mandatory; an optional ordered frame sequence
    enables replay detection and optional client-supplied capture
    metadata enables injection checks.  Payload sizes are strictly
    bounded: at most 24 frames of <= 2 MB each.
    """

    image_b64: str = Field(min_length=16, max_length=16_000_000)
    frames: List[LivenessFrameIn] = Field(default_factory=list, max_length=24)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timeout_s: Optional[float] = Field(default=None, gt=0.0, le=30.0)

    @field_validator("image_b64")
    @classmethod
    def _strip_data_url(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("data:"):
            _, _, v = v.partition(",")
        if not v:
            raise ValueError("image payload is empty")
        return v

    @field_validator("metadata")
    @classmethod
    def _bound_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if len(v) > 32:
            raise ValueError("metadata has too many keys (max 32)")
        return {str(k)[:64]: (str(val)[:256] if isinstance(val, str) else val)
                for k, val in v.items()}


class PadAttackOut(BaseModel):
    indicator: str
    confidence: float
    method: str


class LivenessResultOut(BaseModel):
    """PAD verdict.  Biometric content is never echoed back."""

    decision: str
    is_live: bool
    confidence: float
    timed_out: bool
    attacks: List[PadAttackOut] = Field(default_factory=list)
    signals: List[str] = Field(default_factory=list)
    notes: str = ""
    model_version: str = ""
    processing_time_ms: float = 0.0
    provider: str = ""
    quality_issues: List[str] = Field(default_factory=list)
    risk_signal: Optional[EngineResultOut] = None


class FaceVerifyIn(BaseModel):
    """Verify a candidate face against a reference face (base64 images).

    Similarity, liveness and identity consistency are evaluated as
    separate concerns.  Raw images/embeddings are never echoed back or
    persisted on the result.
    """

    reference_image_b64: str = Field(min_length=16, max_length=16_000_000)
    candidate_image_b64: str = Field(min_length=16, max_length=16_000_000)
    liveness_checks: List[LivenessCheckIn] = Field(default_factory=list)
    declared_identity_match: Optional[bool] = None

    @field_validator("reference_image_b64", "candidate_image_b64")
    @classmethod
    def _strip_data_url(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("data:"):
            _, _, v = v.partition(",")
        if not v:
            raise ValueError("image payload is empty")
        return v
