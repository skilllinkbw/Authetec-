"""
Liveness / Presentation Attack Detection (PAD)
===============================================

Separates liveness detection from face similarity. A face match without
liveness verification is NOT identity verification.

This module provides a pluggable PAD abstraction with:
  - Passive liveness (texture/blink/motion analysis)
  - Active liveness (challenge-response)
  - A deterministic fallback for development/testing

Production deployments must inject a real PAD system (e.g. a dedicated
liveness model). The deterministic fallback is for development only.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Protocol

logger = logging.getLogger("authetec.liveness")

MODEL_VERSION = "liveness-deterministic-fallback-v1"


class PadMethod(str, Enum):
    PASSIVE = "passive"
    ACTIVE = "active"
    HYBRID = "hybrid"


@dataclass
class PresentationAttack:
    """A detected presentation attack indicator."""
    indicator: str
    confidence: float
    method: str
    evidence: str = ""


@dataclass
class LivenessResult:
    """Result of a liveness check."""
    is_live: bool
    confidence: float
    method: PadMethod = PadMethod.PASSIVE
    attacks: List[PresentationAttack] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)
    model_version: str = MODEL_VERSION
    processing_time_ms: float = 0.0
    notes: str = ""


class LivenessDetector(Protocol):
    """Protocol for pluggable liveness/PAD detectors."""

    def check(self, image_bytes: bytes, *, challenge: Optional[str] = None) -> LivenessResult:
        ...


class DeterministicLivenessDetector:
    """
    Deterministic liveness detector for development and testing.

    Uses image entropy and variance as simple signals. This is NOT a
    real PAD system — production must use a proper liveness model.
    """

    def __init__(self, threshold: float = 0.45) -> None:
        self._threshold = threshold

    def check(self, image_bytes: bytes, *, challenge: Optional[str] = None) -> LivenessResult:
        t0 = time.perf_counter()
        signals: List[str] = []
        attacks: List[PresentationAttack] = []

        try:
            import cv2
            import numpy as np
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return LivenessResult(
                    is_live=False, confidence=0.10,
                    attacks=[PresentationAttack("undecodable", 0.9, "structure")],
                    signals=["image could not be decoded"],
                    processing_time_ms=(time.perf_counter() - t0) * 1000,
                    notes="Could not decode image",
                )

            hist = cv2.calcHist([img], [0], None, [256], [0, 256]).flatten()
            hist = hist / hist.sum()
            entropy = -sum(p * np.log2(p) for p in hist if p > 0)
            variance = float(np.var(img))
            normalized_entropy = min(entropy / 7.0, 1.0)
            normalized_variance = min(variance / 5000.0, 1.0)

            score = 0.6 * normalized_entropy + 0.4 * normalized_variance
            is_live = score >= self._threshold

            signals.append(f"entropy={entropy:.2f}")
            signals.append(f"variance={variance:.2f}")

            if not is_live:
                if normalized_entropy < 0.3:
                    attacks.append(PresentationAttack(
                        "low_entropy", 0.7, "texture",
                        "Low image entropy suggests print/screen capture",
                    ))
                if normalized_variance < 0.2:
                    attacks.append(PresentationAttack(
                        "low_variance", 0.6, "texture",
                        "Low variance suggests flat/uniform image",
                    ))

            confidence = min(0.95, max(0.10, abs(score - self._threshold) + 0.5))

            return LivenessResult(
                is_live=is_live,
                confidence=round(confidence, 4),
                method=PadMethod.PASSIVE,
                attacks=attacks,
                signals=signals,
                model_version=MODEL_VERSION,
                processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
                notes="Deterministic fallback — NOT production liveness detection",
            )

        except Exception as e:
            logger.debug("Liveness check failed: %s", e)
            return LivenessResult(
                is_live=False,
                confidence=0.10,
                attacks=[PresentationAttack("error", 0.5, "system", str(e))],
                signals=[f"check error: {e}"],
                processing_time_ms=(time.perf_counter() - t0) * 1000,
                notes="Liveness check failed — treating as non-live",
            )


_detector: Optional[LivenessDetector] = None


def get_liveness_detector() -> LivenessDetector:
    """Get the global liveness detector (deterministic fallback)."""
    global _detector
    if _detector is None:
        _detector = DeterministicLivenessDetector()
    return _detector


def set_liveness_detector(detector: LivenessDetector) -> None:
    """Override the global liveness detector (for production injection)."""
    global _detector
    _detector = detector
