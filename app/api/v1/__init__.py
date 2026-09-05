"""API v1 routers."""
from . import (  # noqa: F401
    health, verification, payments, risk, alerts, audit, evidence,
    social, security,
)

__all__ = [
    "health", "verification", "payments", "risk", "alerts", "audit",
    "evidence", "social", "security",
]
