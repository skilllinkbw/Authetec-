"""
Unified Risk Engine
===================

The core intelligence layer.  Combines signals from all specialized
engines into a single calibrated risk decision.

It NEVER blindly averages scores.  Aggregation is explicit: signals are
normalized, weighted per source with provenance, aggregated, and then
the final risk score is mapped to CLEAR / REVIEW / BLOCK using
configurable thresholds.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.security import new_correlation_id
from app.models.risk import Decision, EngineResult, UnifiedRiskResult

logger = logging.getLogger("authetec.risk")

# Signal-to-source configuration.  Weights are editable policy, not
# tuned magical numbers; calibration happens against ground-truth data.
DEFAULT_SOURCE_WEIGHTS: Dict[str, float] = {
    "document": 0.20,
    "face": 0.15,
    "signature": 0.10,
    "media": 0.10,
    "identity": 0.15,
    "social": 0.05,
    "payment": 0.15,
    "device": 0.10,
}


class RiskEngine:
    """Collects EngineResults from multiple engines and aggregates risk."""

    def __init__(self, source_weights: Optional[Dict[str, float]] = None) -> None:
        self._settings = get_settings()
        self._weights = {**DEFAULT_SOURCE_WEIGHTS, **(source_weights or {})}
        for name, w in list(self._weights.items()):
            if w == 0:
                self._weights.pop(name)
        total = sum(self._weights.values())
        if total > 0:
            self._weights = {k: v / total for k, v in self._weights.items()}
        self._thresholds = {
            "clear": self._settings.risk_clear_threshold,
            "review": self._settings.risk_review_threshold,
        }

    def _normalize(self, engine: str, score: float, confidence: float) -> float:
        """Map an engine confidence-weighted risk contribution into [0, 1]."""
        score = max(0.0, min(score, 1.0))
        confidence = max(0.0, min(confidence, 1.0))
        return score * confidence + 0.5 * (1 - confidence)

    def aggregate(
        self,
        engine_results: List[EngineResult],
        *,
        tenant_id: str = "default",
        correlation_id: Optional[str] = None,
    ) -> UnifiedRiskResult:
        t0 = time.perf_counter()
        corr_id = correlation_id or new_correlation_id()
        if not engine_results:
            return UnifiedRiskResult(
                risk_score=0.0, confidence=0.5, decision=Decision.CLEAR,
                contributing_signals={}, model_versions={}, evidence_ids=[],
                correlation_id=corr_id, reasons=["No signals available"],
            )

        weighted_sum = 0.0
        weight_total = 0.0
        contributions: Dict[str, float] = {}
        model_versions: Dict[str, str] = {}
        evidence_ids: List[str] = []
        reasons: List[str] = []

        for res in engine_results:
            weight = self._weights.get(res.engine, 0.0)
            if weight <= 0:
                continue
            norm = self._normalize(res.engine, res.risk_score, res.confidence)
            weighted_sum += norm * weight
            weight_total += weight
            contributions[res.engine] = round(norm, 4)
            if res.model_version:
                model_versions[res.engine] = res.model_version
            for ev in res.evidence:
                if ev.evidence_id not in evidence_ids:
                    evidence_ids.append(ev.evidence_id)
            for r in res.reasons:
                reasons.append(f"[{res.engine}] {r}")

        if weight_total <= 0:
            final_risk = 0.0
            confidence = 0.5
        else:
            final_risk = weighted_sum / weight_total
            confidence = 0.6 + 0.4 * min(1.0, weight_total / 2.0)

        decision = self._decide(final_risk)
        reasons.append(f"aggregated {len(engine_results)} source(s) with confidence {confidence:.2f}")

        result = UnifiedRiskResult(
            risk_score=round(final_risk, 4),
            confidence=round(confidence, 4),
            decision=decision,
            contributing_signals=contributions,
            model_versions=model_versions,
            evidence_ids=evidence_ids,
            correlation_id=corr_id,
            reasons=reasons,
        )
        self._audit(tenant_id, result, engine_results)
        logger.info("Risk decision for %s: %s score=%.2f conf=%.2f in %.1fms",
                    corr_id, decision.value, final_risk, confidence,
                    (time.perf_counter() - t0) * 1000)
        return result

    def _decide(self, risk: float) -> Decision:
        if risk < self._thresholds["clear"]:
            return Decision.CLEAR
        if risk < self._thresholds["review"]:
            return Decision.REVIEW
        return Decision.BLOCK

    def _audit(self, tenant_id: str, result: UnifiedRiskResult,
               sources: List[EngineResult]) -> None:
        try:
            from app.services.audit import get_audit_logger
            get_audit_logger().log(
                event_type="fraud.decision",
                tenant_id=tenant_id,
                resource_type="case",
                resource_id=result.correlation_id,
                action="unified_risk",
                result=result.decision.value.lower(),
                correlation_id=result.correlation_id,
                metadata={
                    "risk_score": result.risk_score,
                    "decision": result.decision.value,
                    "sources": list(result.contributing_signals.keys()),
                },
            )
        except Exception as e:
            logger.debug("audit skipped: %s", e)