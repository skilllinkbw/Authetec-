"""Unit tests for services: audit, alerts, evidence, model registry."""

from __future__ import annotations

import pytest

from app.models.risk import Severity
from app.services.alerts import get_alert_engine
from app.services.audit import get_audit_logger
from app.services.evidence import get_evidence_engine
from app.services.model_registry import ModelStatus, get_model_registry


class TestAudit:
    def test_entry_is_hash_chained(self):
        log = get_audit_logger()
        log.log(event_type="payment.score", tenant_id="t1",
                resource_type="transaction", resource_id="tx-9")
        entry = log.log(event_type="fraud.decision", tenant_id="t1")
        assert entry["hash"]
        assert entry["prev_hash"] != "0" * 64
        assert log.verify_chain()

    def test_unknown_event_type_rejected(self):
        with pytest.raises(ValueError):
            get_audit_logger().log(event_type="not.an.event")


class TestAlerts:
    def test_create_acknowledge_resolve(self):
        engine = get_alert_engine()
        alert = engine.create(tenant_id="t1", alert_type="payment_fraud",
                              severity=Severity.HIGH, risk_score=0.9, source="payment")
        assert alert.status == "OPEN"
        assert engine.acknowledge(alert.alert_id, "t1").status == "ACKNOWLEDGED"
        assert engine.resolve(alert.alert_id, "t1").status == "RESOLVED"

    def test_tenant_isolation(self):
        alert = get_alert_engine().create(tenant_id="iso-a", alert_type="device_anomaly",
                                          severity=Severity.LOW, risk_score=0.4,
                                          source="device")
        assert get_alert_engine().acknowledge(alert.alert_id, "iso-b") is None

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError):
            get_alert_engine().create(tenant_id="t1", alert_type="nope",
                                      severity=Severity.LOW, risk_score=0.1,
                                      source="x")

    def test_persistence_disabled_without_supabase(self):
        # Dev/test environment has no Supabase configured: alerts must
        # still work, reporting that persistence is unavailable.
        engine = get_alert_engine()
        assert engine.persistence_enabled is False
        assert engine.health()["persistence_enabled"] is False
        alert = engine.create(tenant_id="t1", alert_type="identity_anomaly",
                              severity=Severity.MEDIUM, risk_score=0.5,
                              source="identity")
        assert alert.status == "OPEN"  # in-memory fallback intact


class TestEvidence:
    def test_store_and_get(self):
        engine = get_evidence_engine()
        rec = engine.store(tenant_id="t1", storage_uri="objects/t1/documents/abc",
                           content_type="image/png", purpose="test")
        assert engine.get(rec.evidence_id, "t1") is not None
        assert engine.get(rec.evidence_id, "other") is None


class TestModelRegistry:
    def test_promotion_requires_approval(self):
        registry = get_model_registry()
        model = registry.register(name="fraud-clf", version="0.1", model_type="classifier",
                                  framework="lightgbm", training_dataset="synthetic-v1",
                                  features=["amount", "velocity"], metrics={"auc": 0.91},
                                  threshold=0.65)
        with pytest.raises(ValueError):
            registry.transition(model.model_id, ModelStatus.PRODUCTION)
        registry.transition(model.model_id, ModelStatus.APPROVED, approver="risk-lead")
        promoted = registry.transition(model.model_id, ModelStatus.PRODUCTION,
                                       approver="risk-lead")
        assert promoted.status == ModelStatus.PRODUCTION
        assert promoted.approved_at is not None
