"""
Model Registry
==============

Model lifecycle management.  A benchmark model CANNOT become
a production model without explicit approval and validation records.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("authetec.model_registry")


class ModelStatus(str, Enum):
    EXPERIMENTAL = "EXPERIMENTAL"
    BENCHMARK = "BENCHMARK"
    VALIDATION = "VALIDATION"
    APPROVED = "APPROVED"
    PRODUCTION = "PRODUCTION"
    RETIRED = "RETIRED"


@dataclass
class RegisteredModel:
    model_id: str
    name: str
    version: str
    model_type: str
    framework: str
    training_dataset: str
    features: List[str]
    metrics: Dict[str, float]
    threshold: float
    status: ModelStatus
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class ModelRegistry:
    def __init__(self) -> None:
        self._models: Dict[str, RegisteredModel] = {}

    def register(
        self,
        *,
        name: str,
        version: str,
        model_type: str,
        framework: str,
        training_dataset: str,
        features: List[str],
        metrics: Dict[str, float],
        threshold: float,
        notes: str = "",
    ) -> RegisteredModel:
        model = RegisteredModel(
            model_id=uuid.uuid4().hex,
            name=name, version=version, model_type=model_type,
            framework=framework, training_dataset=training_dataset,
            features=features, metrics=metrics, threshold=threshold,
            status=ModelStatus.BENCHMARK, notes=notes,
        )
        self._models[model.model_id] = model
        logger.info("Registered model %s v%s (status=%s)", name, version, model.status.value)
        return model

    def get(self, model_id: str) -> Optional[RegisteredModel]:
        return self._models.get(model_id)

    def list(self, status: Optional[ModelStatus] = None) -> List[RegisteredModel]:
        out = list(self._models.values())
        if status:
            out = [m for m in out if m.status == status]
        return out

    def transition(self, model_id: str, new_status: ModelStatus, approver: str = "") -> RegisteredModel:
        model = self._models.get(model_id)
        if model is None:
            raise KeyError(f"Unknown model {model_id}")
        if new_status == ModelStatus.APPROVED and model.status not in (
            ModelStatus.BENCHMARK, ModelStatus.VALIDATION
        ):
            raise ValueError("Only BENCHMARK/VALIDATION models can be approved")
        if new_status == ModelStatus.PRODUCTION:
            if model.status != ModelStatus.APPROVED:
                raise ValueError("Only APPROVED models can move to PRODUCTION")
            model.approved_at = datetime.now(timezone.utc).isoformat()
        model.status = new_status
        logger.info("Model %s transitioned to %s by %s", model_id, new_status.value, approver or "system")
        return model

    def health(self) -> Dict[str, Any]:
        by_status = {}
        for m in self._models.values():
            by_status[m.status.value] = by_status.get(m.status.value, 0) + 1
        return {"count": len(self._models), "by_status": by_status}


_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry