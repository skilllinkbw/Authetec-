"""
Haar-cascade face detector (OpenCV built-in data).

STATUS: NON_PRODUCTION_FALLBACK
================================

This detector ships with every OpenCV install and is deterministic, but it
is a 2001-era Viola-Jones detector.  It is intentionally weak: poor on
pose, occlusion, small faces and lighting variation.  It exists so that
the AUTHeTEC pipeline can always run (development / test / graceful
degradation) and is NEVER labelled production-grade.

Production deployments must provide the YuNet detector model (see
``yunet.py``) or inject an independently-validated detector.
"""

from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

import numpy as np

from app.biometric.contracts import (
    BiometricProviderInfo,
    DetectedFace,
    DetectionResult,
)
from app.biometric.detection.base import FaceDetectorBase, crop_face, decode_image

PROVIDER = BiometricProviderInfo(
    name="opencv-haar-viola-jones",
    version="4.x",
    license="Apache-2.0",
    production_grade=False,
    usage_status="NON_PRODUCTION_FALLBACK",
    notes="Deterministic fallback detector; not suitable as a production "
          "biometric detector.",
)


class HaarFaceDetector(FaceDetectorBase):
    """Viola-Jones detector using OpenCV's bundled Haar cascades."""

    provider = PROVIDER

    def __init__(
        self,
        cascade: str = "haarcascade_frontalface_default.xml",
        min_size: int = 40,
        scale_factor: float = 1.1,
        min_neighbors: int = 5,
    ) -> None:
        import cv2
        cascade_path = cascade if os.path.isabs(cascade) else os.path.join(
            cv2.data.haarcascades, cascade)
        if not os.path.exists(cascade_path):
            raise FileNotFoundError(
                f"Haar cascade not found: {cascade_path}")
        self._cascade = cv2.CascadeClassifier(cascade_path)
        if self._cascade.empty():
            raise RuntimeError(f"Failed to load cascade: {cascade_path}")
        self._min_size = max(20, int(min_size))
        self._scale_factor = float(scale_factor)
        self._min_neighbors = int(min_neighbors)

    def detect_rich(self, image_bytes: bytes) -> DetectionResult:
        import cv2
        t0 = time.perf_counter()
        img = decode_image(image_bytes, color=False)
        if img is None:
            return DetectionResult(
                success=False, error="image could not be decoded",
                provider=self.provider.name, latency_ms=0.0)
        h, w = img.shape[:2]
        if h < 20 or w < 20:
            return DetectionResult(
                success=False, error="image too small for detection",
                provider=self.provider.name, latency_ms=0.0)
        faces = self._cascade.detectMultiScale(
            img, scaleFactor=self._scale_factor,
            minNeighbors=self._min_neighbors,
            minSize=(self._min_size, self._min_size),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        color = decode_image(image_bytes, color=True)
        result = DetectionResult(
            provider=self.provider.name,
            latency_ms=(time.perf_counter() - t0) * 1000)
        if faces is None or len(faces) == 0:
            return result
        boxes: List[Tuple[int, int, int, int]] = sorted(
            ((int(x), int(y), int(bw), int(bh)) for (x, y, bw, bh) in faces),
            key=lambda b: b[2] * b[3], reverse=True)
        for i, bbox in enumerate(boxes):
            result.faces.append(DetectedFace(
                bbox=bbox,
                confidence=1.0,  # Haar cascades expose no calibrated score
                crop_bytes=crop_face(color, bbox),
                jerk=i,
            ))
        return result