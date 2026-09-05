"""
Provider-agnostic biometric contracts.

These dataclasses define the shapes exchanged between the detection,
alignment, embedding and PAD layers without coupling AUTHeTEC to any
specific model library.  Every component is described by a
:class:`BiometricProviderInfo` so callers can always tell whether they are
looking at a production-grade model or a labelled fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass(frozen=True)
class BiometricProviderInfo:
    """Descriptor of a biometric component (model / algorithm provider)."""

    name: str
    version: str
    license: str = "unknown"
    production_grade: bool = False
    usage_status: str = "RESEARCH_ONLY"  # see BIOMETRIC_LICENSE_MANIFEST.json
    notes: str = ""

    def describe(self) -> str:
        grade = "PRODUCTION" if self.production_grade else "NON_PRODUCTION"
        return f"{self.name}@{self.version} [{grade}] license={self.license}"


@dataclass
class FaceLandmarks:
    """Landmark points on a face image."""

    points: np.ndarray  # shape (N, 2), float
    convention: str = "5"  # "5" (eyes/nose/mouth) or "68"

    def __post_init__(self) -> None:
        arr = np.asarray(self.points, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[1] != 2 or arr.shape[0] == 0:
            raise ValueError("landmarks must be an (N, 2) array")
        self.points = arr

    def as_5_point(self) -> np.ndarray:
        """Map landmarks to the canonical 5-point template order:
        [right_eye, left_eye, nose_tip, right_mouth, left_mouth]."""
        if self.convention == "5":
            return self.points[:5].copy()
        if self.convention == "68":
            idx = [36, 45, 30, 48, 54]
            return self.points[idx].copy()
        raise ValueError(f"unknown landmark convention: {self.convention}")


@dataclass
class DetectedFace:
    """One detected face with optional landmarks and tight crop."""

    bbox: tuple  # (x, y, w, h) in original image coordinates
    confidence: float = 0.0
    landmarks: Optional[FaceLandmarks] = None
    crop_bytes: Optional[bytes] = None  # tightly cropped face image (PNG/JPEG)
    jerk: int = 0  # index within the detection result (stable ordering)


@dataclass
class DetectionResult:
    """Result of a face-detection call."""

    faces: List[DetectedFace] = field(default_factory=list)
    success: bool = True
    error: str = ""
    provider: str = ""
    latency_ms: float = 0.0

    @property
    def has_faces(self) -> bool:
        return bool(self.faces)


@dataclass
class QualityVerdict:
    """Deterministic quality assessment of a face image."""

    accepted: bool
    score: float  # 0..1; 1 = clean
    issues: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.accepted