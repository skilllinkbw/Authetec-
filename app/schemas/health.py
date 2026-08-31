"""Health and readiness schemas."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel


class ComponentHealth(BaseModel):
    name: str
    status: str
    detail: Dict[str, Any] = {}


class HealthOut(BaseModel):
    app: str
    version: str
    environment: str
    status: str
    components: List[ComponentHealth] = []
