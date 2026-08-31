"""
Payment Fraud Engine
====================

Scores individual transactions using a gradient-boosted model with
transparent, explainable features.  Decision thresholds are configurable
and calibrated from validation data - never hard-coded magic numbers.

Pipeline: Transaction -> feature extraction -> validation -> risk model
        -> explanation -> risk score -> threshold policy -> decision
        -> audit event -> optional alert
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.models.risk import Decision, EngineResult, Signal

logger = logging.getLogger("authetec.payment")

# Feature definition catalogue (documented for model cards).
FEATURES = [
    "amount", "log_amount", "amount_per_balance",
    "is_fraud_high_amount_signal", "velocity_1h", "velocity_24h",
    "avg_amount_7d", "max_amount_7d", "is_night", "is_weekend",
    "device_seen_before", "geo_distance_km", "new_merchant",
    "card_fresh", "bin_risk", "channel_risk",
]


@dataclass
class Transaction:
    """Raw transaction input (validated)."""
    transaction_id: str
    amount: float
    account_id: str = ""
    merchant: str = ""
    card_id: str = ""
    device_id: str = ""
    ip_address: str = ""
    channel: str = "card"
    timestamp: str = ""
    country: str = ""
    card_activation_days: int = 365
    history_amounts_24h: List[float] = field(default_factory=list)
    history_amounts_7d: List[float] = field(default_factory=list)
    account_balance: float = 0.0
    account_age_days: int = 365


def feature_extract(tx: Transaction, settings) -> List[float]:
    """Deterministic feature extraction - no hidden state.

    Velocity features come from supplied history windows (temporal-safe).
    """
    import math
    amount = max(tx.amount, 0.0)
    hist_24 = [max(0, a) for a in tx.history_amounts_24h]
    hist_7 = [max(0, a) for a in tx.history_amounts_7d]

    avg_7 = sum(hist_7) / len(hist_7) if hist_7 else amount
    max_7 = max(hist_7) if hist_7 else amount

    f_high_amt = 1.0 if amount >= 10_000 else 0.0
    f_frac_bal = 0.0
    if tx.account_balance > 0:
        f_frac_bal = min(amount / tx.account_balance, 5.0)

    f_velocity_1h = 0.0
    if hist_24:
        f_velocity_1h = min(sum(hist_24[-2:]) / 10_000.0, 5.0)
    f_velocity_24h = min(sum(hist_24) / 50_000.0, 5.0)

    f_night = 1.0 if tx.timestamp and 22 <= _extract_hour(tx.timestamp) < 5 else 0.0
    f_weekend = 1.0 if tx.timestamp and _extract_weekend(tx.timestamp) else 0.0
    f_device_seen = 0.0   # resolved via DeviceRiskEngine
    f_geo = 0.0           # resolved via DeviceRiskEngine
    f_new_merchant = 0.0
    f_card_fresh = 1.0 if tx.card_activation_days < 14 else 0.0
    f_bin_risk = 0.0
    f_channel_risk = 1.0 if tx.channel == "crypto" else 0.0

    return [
        round(amount, 2), round(math.log1p(amount), 4), round(f_frac_bal, 4),
        f_high_amt, round(f_velocity_1h, 4), round(f_velocity_24h, 4),
        round(avg_7, 2), round(max_7, 2),
        f_night, f_weekend, f_device_seen, f_geo, f_new_merchant,
        f_card_fresh, f_bin_risk, f_channel_risk,
    ]


def _extract_hour(ts: str) -> int:
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts).hour
    except Exception:
        return 12


def _extract_weekend(ts: str) -> bool:
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts).weekday() >= 5
    except Exception:
        return False


class PaymentFraudEngine:
    """Gradient-boosted payment fraud scorer with explainable decisions."""

    MODEL_VERSION = "payment-lightgbm-v0.1-benchmark"

    def __init__(self, model=None) -> None:
        self._model = model
        self._settings = get_settings()
        self._thresholds = {
            "clear": self._settings.risk_clear_threshold,
            "review": self._settings.risk_review_threshold,
        }

    # rules used only when no validated model is deployed ----------
    def _rule_risk(self, tx: Transaction, feats: List[float]) -> float:
        """Transparent rule fallback; NOT a validated production model."""
        score = 0.0
        if feats[3] == 1.0:
            score += 0.25
        if feats[4] > 1.0:
            score += 0.15
        if feats[5] > 2.0:
            score += 0.15
        if feats[13] == 1.0:
            score += 0.10
        if tx.channel == "crypto":
            score += 0.20
        return min(score, 0.95)

    def _model_risk(self, feats: List[float]) -> float:
        if self._model is None:
            return -1.0
        try:
            if hasattr(self._model, "predict_proba"):
                return float(self._model.predict_proba([feats])[0][1])
            return float(self._model.predict([feats])[0])
        except Exception as e:
            logger.error("Model inference failed: %s", e)
            return -1.0

    def score_transaction(
        self,
        tx: Transaction,
        *,
        tenant_id: str = "default",
        device_signals: Optional[Dict[str, float]] = None,
    ) -> EngineResult:
        t0 = time.perf_counter()
        feats = feature_extract(tx, self._settings)
        model_score = self._model_risk(feats)
        rule_score = self._rule_risk(tx, feats)
        device_score = (device_signals or {}).get("device_risk", 0.0)

        if model_score >= 0.0:
            risk = 0.7 * model_score + 0.2 * rule_score + 0.1 * device_score
            model_version = self.MODEL_VERSION
            method = "model+rule"
        else:
            risk = 0.85 * rule_score + 0.15 * device_score
            model_version = "rules-only"
            method = "rule"

        risk = min(max(risk, 0.0), 1.0)
        decision, reason = self._decide(risk)

        signals = [
            Signal("is_fraud_high_amount_signal", feats[3], 0.25,
                   "Amount >= 10,000 threshold", "payment"),
            Signal("velocity_1h", feats[4], 0.20, "1-hour velocity signal", "payment"),
            Signal("velocity_24h", feats[5], 0.20, "24-hour velocity signal", "payment"),
            Signal("card_fresh", feats[13], 0.10, "Card activated < 14 days", "payment"),
            Signal("channel_risk", feats[15], 0.10, "Cryptocurrency channel", "payment"),
            Signal("device_risk", device_score, 0.10, "Device risk signal", "device"),
        ]
        elapsed_ms = (time.perf_counter() - t0) * 1000

        result = EngineResult(
            engine="payment",
            risk_score=round(risk, 4),
            confidence=round(0.5 + abs(risk - 0.5), 4),
            decision=decision,
            signals=signals,
            reasons=[reason, f"scoring_method={method}"],
            model_version=model_version,
            processing_time_ms=round(elapsed_ms, 2),
            extra={"transaction_id": tx.transaction_id, "feature_version": "v0.1"},
        )
        self._audit(tenant_id, tx, result)
        return result

    def _decide(self, risk: float):
        if risk < self._thresholds["clear"]:
            return Decision.CLEAR, "Risk below CLEAR threshold"
        if risk < self._thresholds["review"]:
            return Decision.REVIEW, "Risk within REVIEW band, requires human review"
        return Decision.BLOCK, "Risk above BLOCK threshold"

    def _audit(self, tenant_id: str, tx: Transaction, result: EngineResult) -> None:
        try:
            from app.services.audit import get_audit_logger
            get_audit_logger().log(
                event_type="payment.score",
                tenant_id=tenant_id,
                resource_type="transaction",
                resource_id=tx.transaction_id,
                action="scored",
                result=result.decision.value.lower(),
                metadata={"risk_score": result.risk_score, "decision": result.decision.value},
            )
        except Exception as e:
            logger.debug("audit skipped: %s", e)

    def explain(self, tx: Transaction) -> Dict[str, Any]:
        res = self.score_transaction(tx)
        return {
            "feature_vector": feature_extract(tx, self._settings),
            "feature_names": FEATURES,
            "signals": [s.__dict__ for s in res.signals],
            "method": res.extra.get("feature_version"),
        }