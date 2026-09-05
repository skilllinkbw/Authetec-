"""
Landmark-based face alignment.

Implements a deterministic similarity transform (scale + rotation +
translation, closed-form Umeyama / Kabsch variant) that maps detected
landmarks to the canonical 5-point template used by common embedding
models (right eye, left eye, nose tip, right mouth, left mouth).

Determinism: no RANSAC, no randomness, float64 closed-form algebra — the
same input always produces the same output.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from app.biometric.contracts import BiometricProviderInfo, FaceLandmarks

# Canonical 5-point template (ArcFace / InsightFace convention), sized for
# a 112x112 output crop.
CANONICAL_5_POINT = np.array(
    [
        [38.2946, 51.6963],  # right eye
        [73.5318, 51.5014],  # left eye
        [56.0252, 71.7366],  # nose tip
        [41.5493, 92.3655],  # right mouth corner
        [70.7299, 92.2041],  # left mouth corner
    ],
    dtype=np.float64,
)

DEFAULT_OUTPUT_SIZE = 112

# 68-point → 5-point mapping (dlib convention indices).
_68_TO_5 = np.array([36, 45, 30, 48, 54], dtype=int)

PROVIDER = BiometricProviderInfo(
    name="authetec-similarity-transform-aligner",
    version="1.0",
    license="MIT",
    production_grade=True,
    usage_status="PRODUCTION_ALLOWED",
    notes="Deterministic closed-form landmark alignment; no learned weights.",
)


def _umeyama(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Closed-form least-squares similarity transform.

    Returns a 2x3 affinity matrix M such that ``dst ≈ M @ [x, y, 1]``.
    Deterministic and analytically exact (no iterative solver).
    """
    src = np.asarray(src, dtype=np.float64).reshape(-1, 2)
    dst = np.asarray(dst, dtype=np.float64).reshape(-1, 2)
    n = src.shape[0]
    mu_s = src.mean(axis=0)
    mu_d = dst.mean(axis=0)
    src_c = src - mu_s
    dst_c = dst - mu_d
    var_s = float((src_c ** 2).sum()) / n
    cov = (dst_c.T @ src_c) / n
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(2)
    det = np.linalg.det(U) * np.linalg.det(Vt)
    if det < 0:
        S[1, 1] = -1
    R = U @ S @ Vt
    c = (np.trace(np.diag(D) @ S) / var_s) if var_s > 1e-12 else 1.0
    t = mu_d - c * R @ mu_s
    M = np.eye(3)
    M[:2, :2] = c * R
    M[:2, 2] = t
    return M[:2]


class LandmarkAligner:
    """Aligns a face crop to the canonical template using landmarks."""

    provider = PROVIDER

    def __init__(
        self,
        output_size: int = DEFAULT_OUTPUT_SIZE,
        template: Optional[np.ndarray] = None,
        eye_distance_clip: float = 1e-4,
    ) -> None:
        self._output_size = int(output_size)
        self._template = np.asarray(
            template if template is not None else CANONICAL_5_POINT,
            dtype=np.float64,
        )
        self._eye_distance_clip = float(eye_distance_clip)

    # ── FaceAligner protocol (phase-1 boundary) ──────────────────────
    def align(self, image_bytes: bytes) -> Optional[bytes]:
        """Align using landmarks detected on the fly (or whole-image).

        Requires valid landmarks; if they cannot be produced the call fails
        safely with None (the caller must treat None as a failure).
        """
        landmarks = self._detect_landmarks(image_bytes)
        if landmarks is None:
            return None
        return self.align_with_landmarks(image_bytes, landmarks)

    # ── richer API ────────────────────────────────────────────────────
    def align_with_landmarks(
        self, image_bytes: bytes, landmarks: FaceLandmarks
    ) -> Optional[bytes]:
        try:
            import cv2
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                return None
            src = landmarks.as_5_point()
            if src.shape[0] < self._template.shape[0]:
                return None
            M = _umeyama(src[: self._template.shape[0]], self._template)
            aligned = cv2.warpAffine(
                img, M, (self._output_size, self._output_size),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE,
            )
            ok, buf = cv2.imencode(".png", aligned)
            return buf.tobytes() if ok else None
        except Exception:
            return None

    def warp_matrix(
        self, landmarks: FaceLandmarks
    ) -> Optional[np.ndarray]:
        """Expose the 2x3 similarity matrix (deterministic)."""
        try:
            src = landmarks.as_5_point()
            if src.shape[0] < self._template.shape[0]:
                return None
            return _umeyama(src[: self._template.shape[0]], self._template)
        except Exception:
            return None

    @staticmethod
    def _detect_landmarks(image_bytes: bytes) -> Optional[FaceLandmarks]:
        """Best-effort landmark detection via OpenCV (YuNet if available,
        otherwise None).  Used only for the protocol convenience path."""
        try:
            from app.biometric.detection.yunet import YuNetFaceDetector
            det = YuNetFaceDetector()
            if not det.available():
                return None
            res = det.detect_rich(image_bytes)
            if not res.has_faces:
                return None
            return res.faces[0].landmarks
        except Exception:
            return None