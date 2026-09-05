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
    # Audit trail fields (do not influence the decision directly).
    timed_out: bool = False
    audit_id: str = ""


class LivenessDetector(Protocol):
    """Protocol for pluggable liveness/PAD detectors.

    Production deployments inject a real, independently-validated PAD
    system that conforms to this interface.  The return type is part of
    the contract: callers must NEVER treat a missing/None liveness
    result as "live".
    """

    def check(self, image_bytes: bytes, *, challenge: Optional[str] = None,
              timeout_s: float = 10.0) -> LivenessResult:
        ...


class DeterministicLivenessDetector:
    """
    Deterministic liveness detector for development and testing.

    Uses image entropy and variance as simple signals. This is NOT a
    real PAD system — production must use a proper liveness model.
    """

    DEFAULT_TIMEOUT_S = 10.0

    def __init__(self, threshold: float = 0.45,
                 timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._threshold = threshold
        self._timeout_s = float(timeout_s)

    def check(self, image_bytes: bytes, *, challenge: Optional[str] = None,
              timeout_s: Optional[float] = None) -> LivenessResult:
        """Run PAD within a hard time budget.

        A hang or timeout is treated as "not live" (never the reverse).

        The worker is released without waiting on exit, so a genuinely
        stuck worker can never block the caller past the time budget.
        """
        t0 = time.perf_counter()
        limit = self._timeout_s if timeout_s is None else float(timeout_s)
        if limit <= 0:
            logger.warning("liveness non-positive time budget %.2fs", limit)
            return self._timeout_result(t0)

        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="authetec-pad",
        )
        try:
            fut = pool.submit(self._do_check, image_bytes)
            try:
                return fut.result(timeout=limit)
            except TimeoutError:
                logger.warning("liveness PAD check timed out after %.2fs", limit)
                return self._timeout_result(t0)
        except Exception as e:
            logger.debug("Liveness check error: %s", e)
            return LivenessResult(
                is_live=False, confidence=0.10,
                attacks=[PresentationAttack("error", 0.5, "system", str(e))],
                signals=[f"check error: {e}"],
                processing_time_ms=(time.perf_counter() - t0) * 1000,
                notes="Liveness check failed — treating as non-live",
            )
        finally:
            # Never block the caller on a stuck worker.
            pool.shutdown(wait=False)

    @staticmethod
    def _timeout_result(t_start: float) -> LivenessResult:
        return LivenessResult(
            is_live=False, confidence=0.10,
            attacks=[PresentationAttack("timeout", 0.8, "system",
                                        "PAD check exceeded time budget")],
            signals=["pad_timeout"],
            processing_time_ms=(time.perf_counter() - t_start) * 1000,
            timed_out=True,
            notes="Deterministic fallback — NOT production liveness detection (timeout)",
        )

    def _do_check(self, image_bytes: bytes) -> LivenessResult:
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
            # bool(...) — score components are numpy scalars; the result
            # field contract requires a real Python bool.
            is_live = bool(score >= self._threshold)

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
