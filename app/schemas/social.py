"""Social trust scoring schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from .common import EngineResultOut


class SocialProfileIn(BaseModel):
    """Profile features for social trust scoring (see engine docs)."""

    profile_id: str = Field(default="", max_length=64)
    username: str = Field(default="", max_length=64)
    account_age_days: float = Field(default=365.0, ge=0.0, le=100_000.0)
    email_verified: bool = False
    phone_verified: bool = False
    email_domain: str = Field(default="", max_length=255)
    profile_image_present: bool = True
    bio_present: bool = True
    post_count: int = Field(default=0, ge=0, le=10_000_000)
    following_count: int = Field(default=0, ge=0, le=10_000_000)
    follower_count: int = Field(default=0, ge=0, le=10_000_000)
    post_frequency_per_day: float = Field(default=0.0, ge=0.0, le=100_000.0)
    links: List[str] = Field(default_factory=list, max_length=20)
    declared_country: str = Field(default="", max_length=64)
    phone_calling_code: str = Field(default="", max_length=8)
    name_matches_document: Optional[bool] = None
    suspension_history_count: int = Field(default=0, ge=0, le=1000)
    network_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ip_reputation: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("links")
    @classmethod
    def _limit_links(cls, v: List[str]) -> List[str]:
        if len(v) > 20:
            raise ValueError("at most 20 links are accepted")
        return v


class SocialScoreOut(BaseModel):
    profile_id: str
    result: "EngineResultOut"