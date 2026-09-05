"""
YuNet face detector (OpenCV DNN).

STATUS: PRODUCTION CANDIDATE — model must be explicitly installed
=================================================================

YuNet is a compact CNN face detector (OpenCV Zoo, Apache-2.0 code and
model).  It supports 5 facial landmarks, is small enough for edge/Android
deployment (ONNX), and runs on CPU.

Model download policy: AUTHeTEC never downloads the model silently at
startup.  The operator must install it explicitly and it is integrity
checked against a pinned SHA-256 (see ``app/biometric/security/integrity.py``
and ``docs/biometric_model_setup.md``).

If the model is not installed — or its pinned SHA-256 is not satisfied —
this detector reports ``available() == False`` and every detection call
fails safely (never a fake positive).
"""

from __future__ import annotations

import os
import time
from typing import Optional

import numpy as np

from app.biometric.contracts import (
    BiometricProviderInfo,
    DetectedFace,
    DetectionResult,
    FaceLandmarks,
)
from app.biometric.detection.base import FaceDetectorBase, crop_face, decode_image
from app.biometric.security.integrity import (
    expected_sha256,
    is_model_installed,
)

DEFAULT_MODEL_FILE = "face_detection_yunet_2023mar.onnx"

# Pinned SHA-256 of the OpenCV Zoo YuNet model (2023-03) is registered in
# the model manifest (app/biometric/models/manifest.py) — never hard-coded
# in two places.

PROVIDER = BiometricProviderInfo(
    name="opencv-zoo-yunet",
    version="2023mar",
    license="Apache-2.0",
    production_grade=True,
    usage_status="PRODUCTION_ALLOWED",
    notes="Compact CNN face detector with 5 landmarks; edge-friendly ONNX.",
)


def default_models_dir() -> str:
    """Resolve the configured models directory."""
    env = os.getenv("AUTHETEC_MODELS_DIR", "")
    if env:
        return env
    return os.path.join(os.getcwd(), "models", "face_detection")
class YuNetFaceDetector(FaceDetectorBase):
    """OpenCV DNN YuNet face detector.

    Usage::

        detector = YuNetFaceDetector()                  # search models dir
        if not detector.available():
            detector.install_instructions()            # print guidance
        result = detector.detect_rich(image_bytes)
    """

    provider = PROVIDER

    def __init__(
        self,
        model_path: Optional[str] = None,
        input_size: tuple = (320, 320),
        score_threshold: float = 0.6,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
        verify_integrity: bool = True,
    ) -> None:
        self._model_path = model_path or os.path.join(
            default_models_dir(), DEFAULT_MODEL_FILE)
        self._input_size = tuple(int(v) for v in input_size)
        self._score_threshold = float(score_threshold)
        self._nms_threshold = float(nms_threshold)
        self._top_k = int(top_k)
        self._verify_integrity = bool(verify_integrity)
        self._detector = None
        self._load_error = ""
        self._try_load()

    def _try_load(self) -> None:
        if not self.available():
            return
        try:
            import cv2
            detector = cv2.FaceDetectorYN.create(
                self._model_path, "", self._input_size,
                self._score_threshold, self._nms_threshold, self._top_k,
            )
            if detector is None:
                self._load_error = "cv2.FaceDetectorYN.create returned None"
                return
            self._detector = detector
        except Exception as e:  # pragma: no cover - environment dependent
            self._load_error = f"failed to initialise YuNet: {e}"

    def available(self) -> bool:
        if not is_model_installed(self._model_path):
            return False
        if self._verify_integrity:
            expected = expected_sha256("yunet_face_detection")
            if not expected:
                return False  # fail closed: hash not pinned
            if not self._fingerprint_matches(expected):
                return False
        return True

    def _fingerprint_matches(self, expected: str) -> bool:
        try:
            from app.biometric.security.integrity import sha256_file
            return sha256_file(self._model_path).lower() == expected.lower()
        except Exception:
            return False

    def install_instructions(self) -> str:
        return (
            "YuNet model is not installed or fails the integrity check.\n"
            f"Expected path : {self._model_path}\n"
            "Install command:\n"
            "  python -m scripts.install_biometric_models --detector yunet\n"
            "Manual URL    : https://huggingface.co/opencv/"
            "face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx\n"
            "Checksum      : see BIOMETRIC_LICENSE_MANIFEST.json / model manifest"
        )
# ── detection ───────────────────────────────────────────────────
    def detect_rich(self, image_bytes: bytes) -> DetectionResult:
        t0 = time.perf_counter()
        if self._detector is None:
            return DetectionResult(
                success=False,
                error=self._load_error or "YuNet model not available",
                provider=self.provider.name, latency_ms=0.0)
        img = decode_image(image_bytes, color=True)
        if img is None:
            return DetectionResult(
                success=False, error="image could not be decoded",
                provider=self.provider.name, latency_ms=0.0)
        h, w = img.shape[:2]
        if h < 20 or w < 20:
            return DetectionResult(
                success=False, error="image too small",
                provider=self.provider.name, latency_ms=0.0)
        try:
            self._detector.setInputSize((w, h))
            ok, faces = self._detector.detect(img)
        except Exception as e:
            return DetectionResult(
                success=False, error=f"YuNet inference failed: {e}",
                provider=self.provider.name,
                latency_ms=(time.perf_counter() - t0) * 1000)
        result = DetectionResult(
            provider=self.provider.name,
            latency_ms=(time.perf_counter() - t0) * 1000)
        if not ok or faces is None or len(faces) == 0:
            return result
        # Sort deterministically by confidence (desc), then area (desc).
        ordered = sorted(faces, key=lambda f: (-float(f[14]), -(f[2] * f[3])))
        for i, f in enumerate(ordered):
            x, y, bw, bh, *_ = (float(v) for v in f[:4])
            score = float(f[14])
            lm = np.array([
                [f[4], f[5]], [f[6], f[7]], [f[8], f[9]],
                [f[10], f[11]], [f[12], f[13]],
            ], dtype=np.float64)
            bbox = (int(x), int(y), int(bw), int(bh))
            result.faces.append(DetectedFace(
                bbox=bbox,
                confidence=score,
                landmarks=FaceLandmarks(points=lm, convention="5"),
                crop_bytes=crop_face(img, bbox),
                jerk=i,
            ))
        return result