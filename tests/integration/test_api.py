"""Integration tests: full API surface via TestClient."""

from __future__ import annotations

import base64

import numpy as np
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _signature_png(seed: int = 3) -> bytes:
    import cv2
    rng = np.random.default_rng(seed)
    canvas = np.full((200, 200), 255, dtype=np.uint8)
    pts = rng.integers(25, 175, size=(10, 2)).astype(np.int32)
    for i in range(len(pts) - 1):
        cv2.line(canvas, tuple(pts[i]), tuple(pts[i + 1]), (0,), 3, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", canvas)
    assert ok
    return encoded.tobytes()


class TestStartup:
    def test_lifespan_boots_cleanly(self):
        # Context manager triggers the FastAPI lifespan (startup + shutdown).
        with TestClient(app) as c:
            r = c.get("/health")
            assert r.status_code == 200
            assert r.json()["status"] in ("ok", "degraded")


class TestAuditEndpoints:
    def test_audit_listing_after_activity(self):
        client.post("/api/v1/payments/score", json={
            "transaction_id": "audit-tx", "amount": 10.0},
            headers={"X-Tenant-ID": "audit-t"})
        r = client.get("/api/v1/audit", headers={"X-Tenant-ID": "audit-t"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 1
        entry = body["entries"][0]
        assert entry["event_type"] == "payment.score"
        assert entry["hash"] and entry["prev_hash"]

    def test_audit_tenant_isolation(self):
        # tenant with no activity sees nothing, not another tenant's data
        r = client.get("/api/v1/audit", headers={"X-Tenant-ID": "empty-t"})
        assert r.status_code == 200
        assert all(e["tenant_id"] == "empty-t" for e in r.json()["entries"])

    def test_integrity_endpoint(self):
        r = client.get("/api/v1/audit/integrity", headers={"X-Tenant-ID": "audit-t"})
        assert r.status_code == 200
        body = r.json()
        assert body["valid"] is True
        assert body["entries_checked"] >= 0


class TestEvidenceEndpoints:
    def test_list_and_get(self):
        from app.services.evidence import get_evidence_engine
        rec = get_evidence_engine().store(tenant_id="ev-t",
                                          storage_uri="objects/ev-t/x/1",
                                          content_type="image/png", purpose="test")
        listed = client.get("/api/v1/evidence", headers={"X-Tenant-ID": "ev-t"})
        assert listed.status_code == 200
        assert listed.json()["count"] >= 1
        got = client.get(f"/api/v1/evidence/{rec.evidence_id}",
                         headers={"X-Tenant-ID": "ev-t"})
        assert got.status_code == 200
        assert got.json()["storage_uri"] == "objects/ev-t/x/1"

    def test_cross_tenant_evidence_access_is_404(self):
        from app.services.evidence import get_evidence_engine
        rec = get_evidence_engine().store(tenant_id="ev-owner",
                                          storage_uri="objects/ev-owner/x/2")
        r = client.get(f"/api/v1/evidence/{rec.evidence_id}",
                       headers={"X-Tenant-ID": "ev-attacker"})
        assert r.status_code == 404

    def test_unknown_evidence_is_404(self):
        r = client.get("/api/v1/evidence/does-not-exist",
                       headers={"X-Tenant-ID": "ev-t"})
        assert r.status_code == 404


class TestRateLimiting:
    def test_rate_limit_enforced(self, monkeypatch):
        """Dedicated app instance with a 2 req/min limit; '/' is exempt."""
        from app.api.main import create_app
        from app.core.config import get_settings

        monkeypatch.setenv("AUTHETEC_RATE_LIMIT_PER_MIN", "2")
        get_settings.cache_clear()
        try:
            limited_app = create_app()
            c = TestClient(limited_app)
            # Exempt paths are never limited.
            assert c.get("/health").status_code == 200
            # POST /payments/score with an empty payload -> 422, still counted.
            assert c.post("/api/v1/payments/score", json={}).status_code == 422
            assert c.post("/api/v1/payments/score", json={}).status_code == 422
            limited = c.post("/api/v1/payments/score", json={})
            assert limited.status_code == 429
            body = limited.json()
            assert body["code"] == "rate_limited"
            assert "Retry-After" in limited.headers
        finally:
            get_settings.cache_clear()

    def test_default_limit_allows_normal_traffic(self):
        # The shared app (limit 120/min) must not throttle the test suite.
        for _ in range(5):
            assert client.post("/api/v1/payments/score", json={
                "transaction_id": "rl-1", "amount": 10.0,
            }).status_code == 200


class TestRootAndHealth:
    def test_root(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "app" in r.json()
        assert r.headers.get("x-request-id")

    def test_health_lists_components(self):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["app"]
        names = {c["name"] for c in body["components"]}
        assert {"vector_store", "database", "alerts", "model_registry"} <= names


class TestPayments:
    def test_score_low_risk(self):
        r = client.post(
            "/api/v1/payments/score",
            headers={"X-Tenant-ID": "acme"},
            json={"transaction_id": "tx-1", "amount": 50.0,
                  "account_balance": 5000.0, "channel": "card"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["transaction_id"] == "tx-1"
        assert body["result"]["decision"] == "CLEAR"

    def test_invalid_channel_is_422(self):
        r = client.post(
            "/api/v1/payments/score",
            json={"transaction_id": "tx-2", "amount": 10.0, "channel": "carrier_pigeon"},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "validation_error"

    def test_negative_amount_is_422(self):
        r = client.post(
            "/api/v1/payments/score",
            json={"transaction_id": "tx-3", "amount": -5.0},
        )
        assert r.status_code == 422


class TestDocumentVerification:
    def test_upload_png(self):
        r = client.post(
            "/api/v1/verification/documents",
            headers={"X-Tenant-ID": "acme"},
            files={"file": ("id.png", PNG_1PX, "image/png")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["engine"] == "document"
        assert body["extra"]["sha256"]

    def test_upload_executable_is_400(self):
        r = client.post(
            "/api/v1/verification/documents",
            files={"file": ("evil.exe", b"MZ" + b"\x00" * 300, "application/octet-stream")},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "bad_request"

    def test_empty_upload_is_400(self):
        r = client.post(
            "/api/v1/verification/documents",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert r.status_code == 400

    def test_oversized_upload_rejected_at_api_boundary(self):
        # 20 MB + 1 byte: rejected by the streaming size cap in the API
        # layer before the full body is buffered, regardless of content.
        big = b"x" * (20 * 1024 * 1024 + 1)
        r = client.post(
            "/api/v1/verification/documents",
            files={"file": ("huge.png", big, "image/png")},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "bad_request"


class TestSignatures:
    def test_enroll_and_verify_roundtrip(self):
        image = _signature_png(seed=5)
        enroll = client.post(
            "/api/v1/verification/signatures/enroll",
            headers={"X-Tenant-ID": "acme"},
            json={"owner_id": "alice", "label": "passport",
                  "image_b64": base64.b64encode(image).decode(), "monitored": True},
        )
        assert enroll.status_code == 200
        sig_id = enroll.json()["signature_id"]
        assert sig_id

        verify = client.post(
            "/api/v1/verification/signatures/verify",
            headers={"X-Tenant-ID": "acme"},
            json={"owner_id": "alice", "reference_id": sig_id,
                  "image_b64": base64.b64encode(image).decode()},
        )
        assert verify.status_code == 200
        assert verify.json()["result"]["decision"] == "CLEAR"

    def test_enroll_invalid_base64_is_400(self):
        r = client.post(
            "/api/v1/verification/signatures/enroll",
            json={"owner_id": "bob", "image_b64": "!!!not-base64!!!"},
        )
        assert r.status_code == 400


class TestRisk:
    def test_aggregate(self):
        r = client.post(
            "/api/v1/risk/aggregate",
            headers={"X-Tenant-ID": "acme"},
            json=[{"engine": "payment", "risk_score": 0.95, "confidence": 1.0,
                   "decision": "BLOCK"}],
        )
        assert r.status_code == 200
        assert r.json()["decision"] == "BLOCK"

    def test_aggregate_rejects_bad_score(self):
        r = client.post(
            "/api/v1/risk/aggregate",
            json=[{"engine": "payment", "risk_score": 5.0, "confidence": 1.0,
                   "decision": "BLOCK"}],
        )
        assert r.status_code == 422


class TestAlerts:
    def test_list_acknowledge_resolve_flow(self):
        from app.models.risk import Severity
        from app.services.alerts import get_alert_engine
        alert = get_alert_engine().create(tenant_id="api-t", alert_type="payment_fraud",
                                          severity=Severity.HIGH, risk_score=0.8,
                                          source="payment")

        listed = client.get("/api/v1/alerts", headers={"X-Tenant-ID": "api-t"})
        assert listed.status_code == 200
        assert listed.json()["count"] >= 1

        ack = client.post(f"/api/v1/alerts/{alert.alert_id}/acknowledge",
                          headers={"X-Tenant-ID": "api-t"})
        assert ack.status_code == 200
        assert ack.json()["status"] == "ACKNOWLEDGED"

        res = client.post(f"/api/v1/alerts/{alert.alert_id}/resolve",
                          headers={"X-Tenant-ID": "api-t"})
        assert res.status_code == 200

    def test_unknown_alert_is_404(self):
        r = client.post("/api/v1/alerts/nope/acknowledge", headers={"X-Tenant-ID": "api-t"})
        assert r.status_code == 404
        assert r.json()["code"] == "not_found"

    def test_tenant_isolation_over_http(self):
        from app.models.risk import Severity
        from app.services.alerts import get_alert_engine
        alert = get_alert_engine().create(tenant_id="tenant-x",
                                          alert_type="watchlist_event",
                                          severity=Severity.MEDIUM, risk_score=0.5,
                                          source="identity")
        r = client.post(f"/api/v1/alerts/{alert.alert_id}/acknowledge",
                        headers={"X-Tenant-ID": "tenant-y"})
        assert r.status_code == 404
