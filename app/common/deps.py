"""FastAPI dependencies: tenant context and API-key authentication.

API keys are issued out-of-band; only the SHA-256 fingerprint of the
expected key is configured (``AUTHETEC_API_KEY_SHA256``).  Raw keys are
never stored or logged.  When no fingerprint is configured (development),
authentication is skipped — production startup refuses to boot without it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Header

from app.common.errors import AuthenticationError, BadRequestError
from app.core.config import get_settings
from app.core.security import api_key_fingerprint

logger = logging.getLogger("authetec.deps")


@dataclass(frozen=True)
class TenantContext:
    """Identifies the caller's tenant for this request."""

    tenant_id: str
    authenticated: bool


async def get_tenant_context(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> TenantContext:
    settings = get_settings()

    authenticated = False
    if settings.api_key_sha256:
        if not x_api_key:
            raise AuthenticationError("Missing X-API-Key header")
        if api_key_fingerprint(x_api_key) != settings.api_key_sha256:
            logger.warning("Rejected request with invalid API key fingerprint")
            raise AuthenticationError("Invalid API key")
        authenticated = True
    elif x_api_key:
        # Key supplied but server has no fingerprint configured: verify
        # against per-tenant keys if available, otherwise reject.
        raise AuthenticationError("API keys are not configured on this deployment")

    tenant_id = (x_tenant_id or "default").strip()
    if not tenant_id or len(tenant_id) > 64 or any(c in tenant_id for c in "\r\n\t "):
        raise BadRequestError("Invalid X-Tenant-ID header")
    return TenantContext(tenant_id=tenant_id, authenticated=authenticated)
