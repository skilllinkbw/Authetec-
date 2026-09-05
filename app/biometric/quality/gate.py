"""
Deterministic face quality gate.

Signals (all standard image statistics, deterministic):
    - resolution  (minimum spatial dimension of the crop)
    - blur        (Laplacian variance)
    - exposure    (mean brightness too dark / too bright)
    - contrast    (grayscale standard deviation)
    - saturation  (fraction of near-black / near-white pixels)

The gate is conservative: it blocks embedding when the image is clearly
unsuitable and otherwise reports a 0..1 quality score.  Threshold values
are derived from documented, repeatable definitions and MUST be re-
calibrated on real capture data before production use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from app.biometric.contracts import QualityVerdict

MIN_FACE_DIMENSION = 48
MIN_LAPLACIAN_VARIANCE = 18.0
MIN_CONTRAST_STD = 16.0
MIN_BRIGHTNESS = 32.0
MAX_BRIGHTNESS = 235.0
MAX_SATURATED_RATIO = 0.30


@dataclass
class FaceQualityMetrics:
    width: int = 0
    height: int = 0
    laplacian_variance: float = 0.0
    mean_brightness: float = 0.0
    contrast_std: float = 0.0
    saturated_ratio: float = 0.0
    assessed: bool = False

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "laplacian_variance": round(self.laplacian_variance, 4),
            "mean_brightness": round(self.mean_brightness, 4),
            "contrast_std": round(self.contrast_std, 4),
            "saturated_ratio": round(self.saturated_ratio, 6),
            "assessed": self.assessed,
        }


def assess_face_quality(image_bytes: bytes) -> FaceQualityMetrics:
    """Compute deterministic quality metrics for a face crop."""
    import cv2
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    m = FaceQualityMetrics()
    if gray is None or gray.size == 0:
        return m
    h, w = gray.shape[:2]
    m.width, m.height = w, h
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    m.laplacian_variance = float(lap.var())
    m.mean_brightness = float(gray.mean())
    m.contrast_std = float(gray.std())
    m.saturated_ratio = float(
        ((gray < 8) | (gray > 247)).sum() / gray.size)
    m.assessed = True
    return m


def evaluate_face_quality(metrics: FaceQualityMetrics) -> QualityVerdict:
    """Turn metrics into an accept/reject verdict with a 0..1 score."""
    issues: List[str] = []
    if metrics.width < MIN_FACE_DIMENSION or metrics.height < MIN_FACE_DIMENSION:
        issues.append("face_too_small")
    if metrics.laplacian_variance < MIN_LAPLACIAN_VARIANCE:
        issues.append("blurred")
    if metrics.contrast_std < MIN_CONTRAST_STD:
        issues.append("low_contrast")
    if metrics.mean_brightness < MIN_BRIGHTNESS:
        issues.append("too_dark")
    if metrics.mean_brightness > MAX_BRIGHTNESS:
        issues.append("too_bright")
    if metrics.saturated_ratio > MAX_SATURATED_RATIO:
        issues.append("saturation")

    score = max(0.0, 1.0 - 0.22 * len(issues))
    return QualityVerdict(
        accepted=len(issues) == 0,
        score=round(score, 4),
        issues=issues,
    )


class FaceQualityGate:
    """Gate that decides whether a face crop may enter the embedder."""

    def __init__(self, min_dimension: int = MIN_FACE_DIMENSION,
                 min_lap_var: float = MIN_LAPLACIAN_VARIANCE,
                 min_contrast: float = MIN_CONTRAST_STD) -> None:
        self._min_dim = int(min_dimension)
        self._min_lap = float(min_lap_var)
        self._min_contrast = float(min_contrast)

    def check(self, image_bytes: bytes) -> QualityVerdict:
        m = assess_face_quality(image_bytes)
        if not m.assessed:
            return QualityVerdict(
                accepted=False, score=0.0, issues=["undecodable"])
        return evaluate_face_quality(m)