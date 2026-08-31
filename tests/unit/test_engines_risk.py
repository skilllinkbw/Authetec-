"""Unit tests for the unified risk engine."""

from __future__ import annotations

from app.engines.risk import RiskEngine
from app.models.risk import Decision, EngineResult


def _result(engine: str, score: float, confidence: float = 1.0) -> EngineResult:
    return EngineResult(engine=engine, risk_score=score, confidence=confidence,
                        decision=Decision.REVIEW if score >= 0.3 else Decision.CLEAR)


class TestAggregation:
    def test_empty_inputs_clear(self):
        result = RiskEngine().aggregate([], tenant_id="t1")
        assert result.decision == Decision.CLEAR
        assert result.risk_score == 0.0
        assert result.correlation_id

    def test_high_risk_payment_blocks(self):
        result = RiskEngine().aggregate(
            [_result("payment", 0.95)], tenant_id="t1"
        )
        assert result.decision == Decision.BLOCK
        assert result.contributing_signals["payment"] > 0.9

    def test_low_risk_clears(self):
        result = RiskEngine().aggregate(
            [_result("payment", 0.05)], tenant_id="t1"
        )
        assert result.decision == Decision.CLEAR

    def test_multiple_sources_increase_confidence(self):
        low_conf = RiskEngine().aggregate([_result("payment", 0.5)], tenant_id="t1")
        high_conf = RiskEngine().aggregate(
            [_result("payment", 0.5), _result("document", 0.5),
             _result("signature", 0.5)], tenant_id="t1"
        )
        assert high_conf.confidence > low_conf.confidence

    def test_unknown_engine_is_ignored(self):
        result = RiskEngine().aggregate([_result("unknown_source", 0.99)], tenant_id="t1")
        assert result.risk_score == 0.0
        assert result.decision == Decision.CLEAR

    def test_correlation_ids_unique(self):
        a = RiskEngine().aggregate([_result("payment", 0.1)], tenant_id="t1")
        b = RiskEngine().aggregate([_result("payment", 0.1)], tenant_id="t1")
        assert a.correlation_id != b.correlation_id
