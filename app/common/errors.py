"""Application error hierarchy + FastAPI exception handlers.

Every client-facing error uses the shared ``structured_error`` shape:
``{"code": ..., "message": ..., "request_id": ...}``.  Internal details are
logged server-side and never leaked into responses.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.security import new_correlation_id, structured_error

logger = logging.getLogger("authetec.errors")


class AppError(Exception):
    """Base class for expected, well-described application errors."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "", *, details: Dict[str, Any] | None = None) -> None:
        self.message = message or self.code.replace("_", " ")
        self.details = details or {}
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthorized"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    code = "unsupported_media_type"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


def _error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=structured_error(code, message, request_id),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach consistent JSON error handling to the application."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "correlation_id", None)
        logger.warning("AppError %s: %s path=%s", exc.code, exc.message, request.url.path)
        return _error_response(exc.status_code, exc.code, exc.message, request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "correlation_id", None)
        summary = "; ".join(
            f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', 'invalid')}"
            for e in exc.errors()[:5]
        )
        return _error_response(422, "validation_error", summary, request_id)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = getattr(request.state, "correlation_id", None)
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error_response(exc.status_code, code, str(exc.detail), request_id)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "correlation_id", None) or new_correlation_id()
        logger.exception("Unhandled error on %s request_id=%s", request.url.path, request_id)
        return _error_response(500, "internal_error", "Internal server error", request_id)
