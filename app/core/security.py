"""Core security utilities: JWT, password hashing, API keys, safe logging."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

from .config import get_settings


SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|api[_-]?key|token|authorization|private[_-]?key|"
    r"biometric|biometrics|aadhaar|ssn|pan|credit[_-]?card|cvv|pin)",
    re.IGNORECASE,
)


# ── Logging without sensitive data ─────────────────────────────────────

class SensitiveDataFilter(logging.Filter):
    """Redact sensitive fields from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        for attr in ("args", "msg"):
            v = getattr(record, attr, None)
            s = str(v)
            redacted = SENSITIVE_KEY_RE.sub("***", s)
            if redacted != s:
                setattr(record, attr, redacted)
        return True


CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    global CONFIGURED
    if CONFIGURED:
        return
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    ))
    handler.addFilter(SensitiveDataFilter())
    root.addHandler(handler)
    root.setLevel(level)
    CONFIGURED = True


logger = logging.getLogger("authetec.security")


# ── Password / secrets ────────────────────────────────────────────────

def hash_secret(value: str) -> str:
    """Hash a secret with a per-secret salt (SHA-256, 100k iterations)."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", value.encode(), salt, 100_000)
    return f"pbkdf2_sha256$100000${salt.hex()}${dk.hex()}"


def verify_secret(value: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", value.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    claims: Optional[Dict[str, Any]] = None,
    expiry_minutes: Optional[int] = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=expiry_minutes or settings.jwt_expiry_minutes),
        "jti": secrets.token_hex(8),
    }
    if claims:
        payload.update(claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.jwt_secret:
        raise ValueError("JWT secret not configured")
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# ── API keys ──────────────────────────────────────────────────────────

def generate_api_key() -> str:
    """Generate a random API key prefixed with 'ak_'.

    Only the SHA-256 fingerprint is stored; the raw key is returned once.
    """
    raw = "ak_" + secrets.token_urlsafe(32)
    return raw


def api_key_fingerprint(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Correlation / request ids ─────────────────────────────────────────

def new_correlation_id() -> str:
    return secrets.token_hex(16)


# ── Safe structured error ─────────────────────────────────────────────

def structured_error(code: str, message: str, request_id: str | None = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if request_id:
        err["request_id"] = request_id
    return err