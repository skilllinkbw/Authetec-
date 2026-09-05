"""HTTP middleware: correlation ids, security headers, rate limiting."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import deque

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.security import new_correlation_id, structured_error

logger = logging.getLogger("authetec.access")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

# Paths exempt from rate limiting (liveness probes / load-balancer checks).
RATE_LIMIT_EXEMPT_PATHS = frozenset({"/", "/health", "/docs", "/redoc", "/openapi.json"})


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assign a correlation id per request and echo it back to the client."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Request-ID") or new_correlation_id()
        request.state.correlation_id = correlation_id
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        response.headers["X-Request-ID"] = correlation_id
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        logger.info(
            "%s %s -> %s %.1fms request_id=%s",
            request.method, request.url.path, response.status_code, elapsed_ms, correlation_id,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter (per process).

    Identity precedence: API key fingerprint > tenant id > client IP.
    This in-process limiter is correct for single-worker deployments;
    multi-worker/multi-node deployments should back this with Redis
    (config already carries ``REDIS_URL``) — tracked as future work.
    """

    WINDOW_SECONDS = 60.0
    _MAX_TRACKED_IDENTITIES = 10_000  # memory guard against key flooding

    def __init__(self, app, limit_per_minute: int | None = None) -> None:
        super().__init__(app)
        self.limit = int(limit_per_minute or get_settings().rate_limit_per_minute)
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _identity(self, request: Request) -> str:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return "key:" + hashlib.sha256(api_key.encode()).hexdigest()[:16]
        tenant = request.headers.get("X-Tenant-ID")
        if tenant:
            return "tenant:" + tenant.strip()[:64]
        host = request.client.host if request.client else "unknown"
        return "ip:" + host

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        now = time.monotonic()
        identity = self._identity(request)
        with self._lock:
            hits = self._hits.get(identity)
            if hits is None:
                if len(self._hits) >= self._MAX_TRACKED_IDENTITIES:
                    self._hits.clear()  # crude flood guard; Redis backend supersedes this
                hits = self._hits[identity] = deque()
            while hits and now - hits[0] > self.WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = max(1, int(self.WINDOW_SECONDS - (now - hits[0])) + 1)
                logger.warning("Rate limit exceeded for %s on %s", identity, request.url.path)
                return JSONResponse(
                    status_code=429,
                    content=structured_error(
                        "rate_limited",
                        f"Rate limit of {self.limit} requests/minute exceeded; "
                        f"retry in {retry_after}s",
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

        return await call_next(request)
