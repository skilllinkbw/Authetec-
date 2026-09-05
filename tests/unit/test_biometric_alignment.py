"""
Face-alignment tests: determinism, rotation/scale normalisation,
malformed-landmark and missing-face fail-safe behaviour.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.biometric.alignment.landmarks import (
    CANONICAL_5_POINT,
    LandmarkAligner,
    _umeyama,
)
from app.biometric.contracts import FaceLandmarks


def _face_png(h: int = 200, w: int = 200) -> bytes:
    img = np.full((h, w, 3), 120, np.uint8)
    cv2.circle(img, (w // 2, h // 2), 60, (200, 200, 200), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _landmarks(scale=1.0, dx=0.0, dy=0.0, angle_deg=0.0) -> FaceLandmarks:
    """Canonical-template landmarks transformed by scale/translation/rotation."""
    pts = CANONICAL_5_POINT.copy()
    if angle_deg:
        t = np.deg2rad(angle_deg)
        R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        center = pts.mean(axis=0)
        pts = (pts - center) @ R.T + center
    pts = pts * scale + np.array([dx, dy])
    return FaceLandmarks(points=pts, convention="5")


class TestUmeyamaTransform:
    def test_identity_when_points_match(self):
        M = _umeyama(CANONICAL_5_POINT, CANONICAL_5_POINT)
        np.testing.assert_allclose(M, np.eye(2, 3), atol=1e-9)

    def test_recovers_pure_scale(self):
        src = CANONICAL_5_POINT
        M = _umeyama(src, src * 2.0)
        np.testing.assert_allclose(M[:2, :2], 2.0 * np.eye(2), atol=1e-6)
        np.testing.assert_allclose(M[:, 2], 0.0, atol=1e-6)

    def test_recovers_translation(self):
        src = CANONICAL_5_POINT
        shifted = src + np.array([10.0, 20.0])
        M = _umeyama(src, shifted)
        np.testing.assert_allclose(M[:, 2], [10.0, 20.0], atol=1e-6)

    def test_recovers_rotation(self):
        t = np.deg2rad(17.0)
        R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        src = CANONICAL_5_POINT - CANONICAL_5_POINT.mean(axis=0)
        dst = src @ R.T
        M = _umeyama(src, dst)
        np.testing.assert_allclose(M[:2, :2] @ src.T, dst.T, atol=1e-6)


class TestLandmarkAligner:
    def test_warp_matrix_deterministic(self):
        al = LandmarkAligner()
        lm = _landmarks(scale=1.3, dx=15, dy=-7, angle_deg=9)
        M1 = al.warp_matrix(lm)
        M2 = al.warp_matrix(lm)
        assert M1 is not None
        np.testing.assert_array_equal(M1, M2)

    def test_warp_maps_landmarks_onto_template(self):
        al = LandmarkAligner()
        lm = _landmarks(scale=0.8, dx=40, dy=25, angle_deg=-12)
        M = al.warp_matrix(lm)
        src_h = np.hstack([lm.points, np.ones((5, 1))])
        mapped = (M @ src_h.T).T
        np.testing.assert_allclose(mapped, CANONICAL_5_POINT, atol=1e-4)

    def test_align_returns_bytes(self):
        al = LandmarkAligner()
        out = al.align_with_landmarks(_face_png(), _landmarks())
        assert out is not None and out[:8] == b"\x89PNG\r\n\x1a\n"

    def test_align_output_size(self):
        al = LandmarkAligner(output_size=112)
        out = al.align_with_landmarks(_face_png(), _landmarks())
        img = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
        assert img.shape[:2] == (112, 112)

    def test_malformed_landmarks_fail_safe(self):
        al = LandmarkAligner()
        # Wrong point count
        assert al.align_with_landmarks(
            _face_png(), FaceLandmarks(points=np.zeros((3, 2)))) is None
        # NaN coordinates
        bad = np.full((5, 2), np.nan)
        assert al.align_with_landmarks(
            _face_png(), FaceLandmarks(points=bad)) is None

    def test_missing_face_image_fail_safe(self):
        al = LandmarkAligner()
        assert al.align_with_landmarks(
            b"not-an-image", _landmarks()) is None

    def test_align_without_landmarks_returns_none(self):
        al = LandmarkAligner()
        # Protocol path without a working landmark detector -> None, not crash.
        assert al.align(b"definitely-not-an-image") is None

    def test_alignment_invariant_to_input_scale(self):
        """Same face at different image scales -> same ROTATION.

        The warp onto the fixed canonical template necessarily differs in
        scale (a 2x larger face needs a 0.5x correction), so the scale-
        dependent determinants cannot match.  The invariant that matters
        for pose normalisation is the rotation part, compared here after
        removing each matrix's uniform scale factor.
        """
        al = LandmarkAligner()
        M_small = al.warp_matrix(_landmarks(scale=1.0))
        M_large = al.warp_matrix(_landmarks(scale=2.0, dx=30, dy=10))
        assert M_small is not None and M_large is not None
        R_small = M_small[:2, :2] / np.linalg.norm(M_small[:2, :2])
        R_large = M_large[:2, :2] / np.linalg.norm(M_large[:2, :2])
        np.testing.assert_allclose(R_small, R_large, atol=1e-6)
        # And each warp must still map its own landmarks onto the template.
        for M, lm in ((M_small, _landmarks(scale=1.0)),
                      (M_large, _landmarks(scale=2.0, dx=30, dy=10))):
            src_h = np.hstack([lm.points, np.ones((5, 1))])
            mapped = (M @ src_h.T).T
            np.testing.assert_allclose(mapped, CANONICAL_5_POINT, atol=1e-4)
