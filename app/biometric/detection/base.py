"""
Face detection base classes.

Implements the phase-1 ``FaceDetector`` protocol (``detect(bytes)``)
on top of a richer ``detect_rich(bytes)`` contract so that downstream
alignment has access to landmarks and bounding boxes.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from app.biometric.contracts import (
    BiometricProviderInfo,
    DetectedFace,
    DetectionResult,
    FaceLandmarks,
)


class FaceDetectorBase:
    """Base class for AUTHeTEC face detectors.

    Sub-classes implement :meth:`detect_rich`; :meth:`detect` is the
    protocol-compatible projection (returns cropped face image bytes).
    """

    provider: BiometricProviderInfo

    def detect_rich(self, image_bytes: bytes) -> DetectionResult:
        raise NotImplementedError

    # ── FaceDetector protocol (phase-1 boundary) ────────────────────
    def detect(self, image_bytes: bytes) -> Optional[List[bytes]]:
        """Return cropped face images, [] if no face, None on failure."""
        try:
            result = self.detect_rich(image_bytes)
        except Exception:
            return None
        if not result.success:
            return None
        crops = [f.crop_bytes for f in result.faces if f.crop_bytes]
        return crops or []

    def is_production_grade(self) -> bool:
        return self.provider.production_grade

    def provider_info(self) -> BiometricProviderInfo:
        return self.provider


def decode_image(image_bytes: bytes, color: bool = True):
    """Decode raw bytes to a BGR or grayscale image, or None."""
    if not image_bytes:
        return None  # cv2.imdecode raises on empty buffers (OpenCV 5)
    import cv2
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    flag = cv2.IMREAD_COLOR if color else cv2.IMREAD_GRAYSCALE
    try:
        return cv2.imdecode(arr, flag)
    except cv2.error:
        return None


def encode_crop(img) -> Optional[bytes]:
    """Encode a BGR/gray crop to PNG bytes; None on failure."""
    import cv2
    if img is None or img.size == 0:
        return None
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes() if ok else None


def crop_face(img, bbox, margin: float = 0.20,
              target_size: int = 160) -> Optional[bytes]:
    """Tightly crop a face with a proportional margin and resize.

    Deterministic: same input always produces the same crop.
    """
    if img is None or img.size == 0:
        return None
    import cv2
    h, w = img.shape[:2]
    x, y, bw, bh = (int(v) for v in bbox)
    mx = max(1, int(bw * margin))
    my = max(1, int(bh * margin))
    x0, y0 = max(0, x - mx), max(0, y - my)
    x1, y1 = min(w, x + bw + mx), min(h, y + bh + my)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    if target_size > 0 and (crop.shape[0] != target_size or crop.shape[1] != target_size):
        crop = cv2.resize(crop, (target_size, target_size),
                          interpolation=cv2.INTER_AREA)
    return encode_crop(crop)