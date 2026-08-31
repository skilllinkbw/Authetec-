"""Unit tests for the payment fraud engine."""

from __future__ import annotations

from app.engines.payment import PaymentFraudEngine, Transaction, feature_extract


class TestFeatureExtraction:
    def test_feature_vector_shape(self):
        tx = Transaction(transaction_id="t1", amount=500.0, account_balance=1000.0)
        feats = feature_extract(tx, None)
        assert len(feats) == 16
        assert all(isinstance(f, float) for f in feats)

    def test_high_amount_flag(self):
        tx = Transaction(transaction_id="t1", amount=50_000.0)
        feats = feature_extract(tx, None)
        assert feats[3] == 1.0  # is_fraud_high_amount_signal


class TestScoring:
    def test_low_risk_transaction_clears(self):
        result = PaymentFraudEngine().score_transaction(
            Transaction(transaction_id="tx-1", amount=50.0, account_balance=5000.0,
                        channel="card"),
            tenant_id="t1",
        )
        assert result.engine == "payment"
        assert result.decision.value == "CLEAR"
        assert result.risk_score < 0.3
        assert result.extra["transaction_id"] == "tx-1"

    def test_high_risk_transaction_is_flagged(self):
        result = PaymentFraudEngine().score_transaction(
            Transaction(transaction_id="tx-2", amount=200_000.0, account_balance=300.0,
                        channel="crypto"),
            tenant_id="t1",
        )
        assert result.decision.value in ("REVIEW", "BLOCK")
        assert result.risk_score >= 0.3
        assert any("method" in r for r in result.reasons)

    def test_signals_have_provenance(self):
        result = PaymentFraudEngine().score_transaction(
            Transaction(transaction_id="tx-3", amount=100.0), tenant_id="t1"
        )
        assert all(s.source in ("payment", "device") for s in result.signals)
