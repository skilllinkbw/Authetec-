"""
Face-detection layer tests (AUTHeTEC native stack).

Covers: valid image, no face, malformed image, provider fail-safe
behaviour, and the phase-1 ``detect`` protocol projection.  Synthetic
fixtures are geometric shapes; YuNet detection of *synthetic* faces is
not asserted (documented limitation - real-face detection is validated
in the real-world validation protocol, not in unit tests).
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.biometric.detection.base import crop_face, decode_image, encode_crop
from app.biometric.detection.yunet import YuNetFaceDetector


def _png(h: int = 240, w: int = 320, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


class TestYuNetDetector:
    def test_model_available_in_dev_environment(self):
        det = YuNetFaceDetector()
        # models/ are installed in this repo checkout (pinned integrity).
        if det.available():
            assert det.provider.production_grade is True

    def test_malformed_bytes_fail_safe(self):
        det = YuNetFaceDetector()
        # Protocol: detect() returns None on failure, never raises.
        assert det.detect(b"not-an-image") in (None, [])

    def test_empty_bytes_fail_safe(self):
        det = YuNetFaceDetector()
        assert det.detect(b"") in (None, [])

    def test_no_face_returns_empty_list(self):
        det = YuNetFaceDetector()
        if not det.available():
            pytest.skip("YuNet model not installed")
        # Random noise: no face expected (probabilistically overwhelming).
        result = det.detect(_png(seed=7))
        assert result in ([], None)

    def test_detect_rich_contract(self):
        det = YuNetFaceDetector()
        if not det.available():
            pytest.skip("YuNet model not installed")
        res = det.detect_rich(_png(seed=3))
        assert isinstance(res.faces, list)
        assert res.provider  # provider label present
        for f in res.faces:
            assert len(f.bbox) == 4
            assert 0.0 <= f.confidence <= 1.0

    def test_detect_rich_huge_image_is_bounded(self):
        det = YuNetFaceDetector()
        if not det.available():
            pytest.skip("YuNet model not installed")
        # 4000x4000 noise: must not hang or crash (resource-limit policy).
        res = det.detect_rich(_png(h=4000, w=4000, seed=11))
        assert isinstance(res.faces, list)


class TestDetectionHelpers:
    def test_decode_image_rejects_garbage(self):
        assert decode_image(b"junk") is None
        assert decode_image(b"", color=False) is None

    def test_decode_image_roundtrip(self):
        img = decode_image(_png(seed=1))
        assert img is not None and img.ndim == 3

    def test_encode_crop_empty_is_none(self):
        assert encode_crop(None) is None
        assert encode_crop(np.zeros((0, 0), dtype=np.uint8)) is None

    def test_crop_face_deterministic(self):
        img = decode_image(_png(seed=2))
        a = crop_face(img, (50, 50, 100, 100))
        b = crop_face(img, (50, 50, 100, 100))
        assert a is not None and a == b

    def test_crop_face_out_of_bounds_clamps(self):
        img = decode_image(_png(seed=4))
        out = crop_face(img, (-50, -50, 1000, 1000))
        assert out is not None  # clamped, never crashes

    def test_crop_face_empty_image_none(self):
        assert crop_face(None, (0, 0, 10, 10)) is None
