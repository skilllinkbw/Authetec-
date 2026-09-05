"""
Authetec Core Configuration
============================

Environment-driven settings.  No secrets are stored in source code;
every secret comes from the environment / secret manager.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    app_name: str = "Authetec Trust Intelligence"
    app_version: str = "0.1.0"
    environment: str = field(default_factory=lambda: os.getenv("AUTHETEC_ENV", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("AUTHETEC_DEBUG", "false").lower() == "true")

    # ── Security ────────────────────────────────────────────────
    jwt_secret: str = field(default_factory=lambda: os.getenv("AUTHETEC_JWT_SECRET", ""))
    jwt_algorithm: str = field(default_factory=lambda: os.getenv("AUTHETEC_JWT_ALGORITHM", "HS256"))
    jwt_expiry_minutes: int = field(default_factory=lambda: int(os.getenv("AUTHETEC_JWT_EXPIRY_MINUTES", "120")))

    # ── Supabase ────────────────────────────────────────────────
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_service_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    supabase_anon_key: str = field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", ""))

    # ── AI / Model endpoints ────────────────────────────────────
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    local_vision_model: str = field(default_factory=lambda: os.getenv("AUTHETEC_VISION_MODEL", "qwen2-vl:7b"))

    # ── Vector store ────────────────────────────────────────────
    vector_store_backend: str = field(default_factory=lambda: os.getenv("AUTHETEC_VECTOR_BACKEND", "memory"))
    qdrant_url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str = field(default_factory=lambda: os.getenv("QDRANT_API_KEY", ""))
    chroma_persist_dir: str = field(default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", ".chroma"))

    # ── Redis / Celery ──────────────────────────────────────────
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    # ── Rate limiting ───────────────────────────────────────────
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("AUTHETEC_RATE_LIMIT_PER_MIN", "120")))

    # ── API key auth (store ONLY the SHA-256 fingerprint) ───────
    api_key_sha256: str = field(default_factory=lambda: os.getenv("AUTHETEC_API_KEY_SHA256", ""))
    cors_origins: List[str] = field(default_factory=lambda: [
        o.strip() for o in os.getenv("AUTHETEC_CORS_ORIGINS", "").split(",") if o.strip()
    ])

    # ── Risk thresholds (configurable, not hard-coded) ──────────
    risk_clear_threshold: float = field(default_factory=lambda: float(os.getenv("AUTHETEC_RISK_CLEAR", "0.30")))
    risk_review_threshold: float = field(default_factory=lambda: float(os.getenv("AUTHETEC_RISK_REVIEW", "0.70")))

    # ── File upload limits ───────────────────────────────────────
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("AUTHETEC_MAX_UPLOAD_MB", "20")))
    allowed_image_types: tuple = ("image/jpeg", "image/png", "image/tiff", "application/pdf")

    # ── Data retention ──────────────────────────────────────────
    biometric_retention_days: int = field(default_factory=lambda: int(os.getenv("AUTHETEC_BIOMETRIC_RETENTION_DAYS", "90")))

    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    def require_secret(self, name: str, value: str) -> None:
        """Refuse to start in production if a required secret is missing."""
        if self.is_production() and not value:
            raise RuntimeError(f"Missing required secret: {name}")


@lru_cache
def get_settings() -> Settings:
    return Settings()