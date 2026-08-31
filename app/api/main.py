"""Authetec API application factory.

Layering (strict):
    Router (this package) -> Service -> Engine -> Infrastructure

No business logic lives here: routers validate input, delegate to
engines/services, and serialise the standard EngineResult contract.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.errors import register_exception_handlers
from app.common.middleware import CorrelationIdMiddleware, RateLimitMiddleware
from app.core.config import get_settings
from app.core.security import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging()
    # Production hard-fail on missing critical configuration.
    settings.require_secret("AUTHETEC_JWT_SECRET", settings.jwt_secret)
    settings.require_secret("AUTHETEC_API_KEY_SHA256", settings.api_key_sha256)
    if settings.is_production():
        settings.require_secret("SUPABASE_SERVICE_ROLE_KEY", settings.supabase_service_key)
    logger = logging.getLogger("authetec.api")
    logger.info("Authetec API starting (env=%s version=%s)",
                settings.environment, settings.app_version)
    yield
    logger.info("Authetec API shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AI-powered digital trust & fraud prevention platform: "
            "document, signature, payment-fraud and unified risk engines."
        ),
        lifespan=lifespan,
        docs_url=None if settings.is_production() else "/docs",
        redoc_url=None if settings.is_production() else "/redoc",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["X-API-Key", "X-Tenant-ID", "X-Request-ID", "Content-Type"],
        )

    # Middleware: last-added runs first. CorrelationId stays outermost so
    # even rate-limited 429 responses carry a request id.
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RateLimitMiddleware)
    register_exception_handlers(app)

    # Routers
    from app.api.v1 import alerts, audit, evidence, health, payments, risk, verification
    app.include_router(health.router)
    app.include_router(verification.router, prefix="/api/v1")
    app.include_router(payments.router, prefix="/api/v1")
    app.include_router(risk.router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(evidence.router, prefix="/api/v1")
    return app
