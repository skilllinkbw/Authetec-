"""
Deterministic face embedder (NON_PRODUCTION_FALLBACK).

The phase-1 whole-image content projector, retained for development,
tests and the synthetic benchmark harness.  It performs no detection and
no alignment and is never labelled production-grade.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from app.biometric.contracts import BiometricProviderInfo
from app.biometric.recognition.embeddings import EmbeddingValidator

DIM = 64
CANVAS = 32

PROVIDER = BiometricProviderInfo(
    name="authetec-deterministic-content-projector",
    version="v1",
    license="MIT",
    production_grade=False,
    usage_status="NON_PRODUCTION_FALLBACK",
    notes="Deterministic whole-image projection for tests/benchmarks.",
)


class DeterministicFaceEmbedder:
    """Deterministic 64-d content projector (tests / benchmarks only)."""

    DIM = DIM
    CANVAS = CANVAS
    provider = PROVIDER

    @property
    def model_version(self) -> str:
        return "deterministic-content-projector-v1"

    def available(self) -> bool:
        """Always available (pure NumPy); NOT production-grade."""
        return True

    def install_instructions(self) -> str:
        return "No install needed - NON_PRODUCTION_FALLBACK backend."

    def __init__(self) -> None:
        rng = np.random.default_rng(42)
        self._projection = rng.standard_normal(
            (CANVAS * CANVAS, DIM)).astype(np.float32)
        self._projection /= np.linalg.norm(
            self._projection, axis=0, keepdims=True)
        self.validator = EmbeddingValidator(
            expected_dim=DIM, require_unit_norm=False)

    def embed(self, image_bytes: bytes) -> Optional[np.ndarray]:
        import cv2
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if gray is None or gray.size < 64:
            return None
        try:
            resized = cv2.resize(
                gray, (CANVAS, CANVAS)).astype(np.float32)
        except Exception:
            return None
        flat = resized.reshape(-1).astype(np.float32)
        std = float(flat.std())
        if std < 1e-6:
            flat = flat - float(flat.mean())
        else:
            flat = (flat - float(flat.mean())) / std
        emb = flat @ self._projection
        norm = float(np.linalg.norm(emb))
        if norm < 1e-9:
            return None
        emb = (emb / norm).astype(np.float32)
        return emb if self.validator.validate(emb).is_valid else None