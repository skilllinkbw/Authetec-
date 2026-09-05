"""Integration tests for the face verification API endpoint.

Covers the happy path, liveness handling, malformed payloads (failure
injection) and request validation.
"""

from __future__ import annotations

import base64

import numpy as np
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _face_png(seed: int, size: int = 96) -> bytes:
    import cv2
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, size=(size, size), dtype=np.uint8)
    img = cv2.GaussianBlur(img, (5, 5), 0)
    cx, cy = (int(v) for v in rng.integers(size // 3, 2 * size // 3, 2))
    r = int(rng.integers(size // 6, size // 3))
    cv2.circle(img, (cx, cy), r, 255, 3)
    cv2.circle(img, (cx - r // 2, cy - r // 3), max(2, r // 6), 255, -1)
    cv2.circle(img, (cx + r // 2, cy - r // 3), max(2, r // 6), 255, -1)
    ok, encoded = cv2.imencode(".png", img)
    assert ok
    return encoded.tobytes()


def _b64(seed: int) -> str:
    return base64.b64encode(_face_png(seed)).decode()


def _payload(ref: int, cand: int, **extra) -> dict:
    return {
        "reference_image_b64": _b64(ref),
        "candidate_image_b64": _b64(cand),
        **extra,
    }


class TestFaceVerificationEndpoint:
    def test_same_face_clears(self):
        r = client.post("/api/v1/verification/faces",
                        json=_payload(101, 101),
                        headers={"X-Tenant-ID": "face-t"})
        assert r.status_code == 200
        body = r.json()
        assert body["engine"] == "face_verification"
        assert body["decision"] == "CLEAR"
        assert body["extra"]["similarity"] >= 0.62

    def test_different_face_not_cleared(self):
        r = client.post("/api/v1/verification/faces",
                        json=_payload(101, 202),
                        headers={"X-Tenant-ID": "face-t"})
        assert r.status_code == 200
        assert r.json()["decision"] in ("REVIEW", "BLOCK")

    def test_liveness_check_passed_in_result(self):
        r = client.post("/api/v1/verification/faces", json=_payload(
            303, 303,
            liveness_checks=[{"name": "blink", "passed": True, "score": 0.9}],
        ), headers={"X-Tenant-ID": "face-t"})
        assert r.status_code == 200
        body = r.json()
        names = [s["name"] for s in body["signals"]]
        assert "liveness_risk" in names
        assert body["extra"]["liveness_failed"] == []

    def test_failed_liveness_never_clears(self):
        r = client.post("/api/v1/verification/faces", json=_payload(
            404, 404,
            liveness_checks=[{"name": "head_turn", "passed": False, "score": 0.2}],
        ), headers={"X-Tenant-ID": "face-t"})
        assert r.status_code == 200
        assert r.json()["decision"] != "CLEAR"

    def test_no_biometric_data_echoed(self):
        r = client.post("/api/v1/verification/faces",
                        json=_payload(505, 505),
                        headers={"X-Tenant-ID": "face-t"})
        body_text = r.text
        assert _b64(505)[:40] not in body_text

    # ── failure injection ────────────────────────────────────────────

    def test_malformed_base64_is_rejected_with_400(self):
        r = client.post("/api/v1/verification/faces", json={
            "reference_image_b64": "!!!!not-base64!!!!",
            "candidate_image_b64": _b64(606),
        }, headers={"X-Tenant-ID": "face-t"})
        assert r.status_code == 400

    def test_missing_fields_are_rejected_with_422(self):
        r = client.post("/api/v1/verification/faces", json={},
                        headers={"X-Tenant-ID": "face-t"})
        assert r.status_code == 422

    def test_valid_base64_but_not_an_image_fails_safe(self):
        not_image = base64.b64encode(b"definitely-not-an-image").decode()
        r = client.post("/api/v1/verification/faces", json={
            "reference_image_b64": not_image,
            "candidate_image_b64": _b64(707),
        }, headers={"X-Tenant-ID": "face-t"})
        assert r.status_code == 200
        body = r.json()
        assert body["decision"] == "REVIEW"
        assert body["confidence"] <= 0.15
