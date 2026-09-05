"""Unit tests for the signature engine (enrollment + verification)."""

from __future__ import annotations

import numpy as np

from app.engines.signature import SignatureEngine, SignatureSample


def _signature_image(seed: int = 1, size: int = 240) -> bytes:
    """Draw a deterministic synthetic signature (ink strokes on white)."""
    import cv2
    rng = np.random.default_rng(seed)
    canvas = np.full((size, size), 255, dtype=np.uint8)
    pts = rng.integers(30, size - 30, size=(12, 2)).astype(np.int32)
    for i in range(len(pts) - 1):
        cv2.line(canvas, tuple(pts[i]), tuple(pts[i + 1]), (0,), 3, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", canvas)
    assert ok
    return encoded.tobytes()


def _diagonal_image(size: int = 240) -> bytes:
    """A deliberately different mark: a single diagonal stroke."""
    import cv2
    canvas = np.full((size, size), 255, dtype=np.uint8)
    cv2.line(canvas, (20, size - 20), (size - 20, 20), (0,), 3, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", canvas)
    assert ok
    return encoded.tobytes()


def _blank_image() -> bytes:
    import cv2
    ok, encoded = cv2.imencode(".png", np.full((120, 120), 255, dtype=np.uint8))
    assert ok
    return encoded.tobytes()


class TestEnrollment:
    def test_enroll_returns_reference_id(self):
        result = SignatureEngine().enroll(
            SignatureSample(image_bytes=_signature_image(), owner_id="alice",
                            tenant_id="t1", monitored=True),
            tenant_id="t1",
        )
        assert result.engine == "signature"
        assert result.decision.value == "CLEAR"
        assert result.extra["signature_id"]
        assert result.extra["stored_evidence_id"]

    def test_blank_image_is_rejected_for_review(self):
        result = SignatureEngine().enroll(
            SignatureSample(image_bytes=_blank_image(), owner_id="bob", tenant_id="t1"),
            tenant_id="t1",
        )
        assert result.decision.value == "REVIEW"
        assert result.extra.get("signature_id", "") == ""


class TestVerification:
    def test_matching_signature_clears(self):
        engine = SignatureEngine()
        image = _signature_image(seed=7)
        enrolled = engine.enroll(
            SignatureSample(image_bytes=image, owner_id="carol", tenant_id="t1"),
            tenant_id="t1",
        )
        result = engine.verify(
            SignatureSample(image_bytes=image, owner_id="carol", tenant_id="t1"),
            reference_id=enrolled.extra["signature_id"],
            tenant_id="t1",
        )
        assert result.decision.value == "CLEAR"
        assert result.signals[0].value >= 0.99  # similarity to itself

    def test_different_signature_is_flagged(self):
        engine = SignatureEngine()
        engine.enroll(
            SignatureSample(image_bytes=_signature_image(seed=11), owner_id="dave",
                            tenant_id="t1", monitored=True),
            tenant_id="t1",
        )
        result = engine.verify(
            SignatureSample(image_bytes=_diagonal_image(), owner_id="dave",
                            tenant_id="t1"),
            tenant_id="t1",
        )
        assert result.decision.value in ("REVIEW", "BLOCK")

    def test_unknown_owner_is_review(self):
        result = SignatureEngine().verify(
            SignatureSample(image_bytes=_signature_image(), owner_id="nobody",
                            tenant_id="t1"),
            tenant_id="t1",
        )
        assert result.decision.value == "REVIEW"

    def test_missing_reference_id_is_review(self):
        engine = SignatureEngine()
        engine.enroll(
            SignatureSample(image_bytes=_signature_image(), owner_id="erin", tenant_id="t1"),
            tenant_id="t1",
        )
        result = engine.verify(
            SignatureSample(image_bytes=_signature_image(), owner_id="erin",
                            tenant_id="t1"),
            reference_id="does-not-exist",
            tenant_id="t1",
        )
        assert result.decision.value == "REVIEW"
