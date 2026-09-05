"""Health / readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas import ComponentHealth, HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut, summary="Component health")
def health() -> HealthOut:
    settings = get_settings()
    components: list[ComponentHealth] = []

    components.append(ComponentHealth(
        name="vector_store",
        status="ok",
        detail={"backend": settings.vector_store_backend},
    ))

    from app.infrastructure.supabase import get_supabase
    sb = get_supabase().health()
    components.append(ComponentHealth(
        name="database",
        status="ok" if sb.get("reachable") else "degraded",
        detail=sb,
    ))

    from app.services.alerts import get_alert_engine
    components.append(ComponentHealth(
        name="alerts",
        status="ok",
        detail=get_alert_engine().health(),
    ))

    from app.services.model_registry import get_model_registry
    components.append(ComponentHealth(
        name="model_registry",
        status="ok",
        detail=get_model_registry().health(),
    ))

    from app.services.ai_security import get_ai_security_monitor
    components.append(ComponentHealth(
        name="ai_security",
        status="ok",
        detail=get_ai_security_monitor().health(),
    ))

    degraded = any(c.status != "ok" for c in components)
    return HealthOut(
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        status="degraded" if degraded else "ok",
        components=components,
    )


@router.get("/", include_in_schema=False)
def root() -> dict:
    settings = get_settings()
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs" if not settings.is_production() else None,
    }
