"""
Secure embedding validation.

Biometric embeddings are the most sensitive derived artifact in the
system.  Before any comparison or persistence, every embedding must pass:

    * exact dtype validation        (float32/float64)
    * finite-value validation       (rejects NaN and +/-Inf)
    * dimensionality validation     (space must be the configured size)
    * norm validation               (unit-normalised within a tolerance)

These checks are deterministic and fail closed: an invalid embedding can
never participate in a similarity decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

ALLOWED_DTYPES = (np.float32, np.float64)
# Tolerance for "unit norm" embeddings (L2 == 1.0 within this epsilon).
NORM_TOLERANCE = 1e-2


@dataclass
class EmbeddingValidation:
    valid: bool
    reason: str = ""
    dim: int = 0
    norm: float = 0.0

    @property
    def is_valid(self) -> bool:
        return self.valid


class EmbeddingValidator:
    """Stateless, deterministic validator for face embeddings."""

    def __init__(
        self,
        expected_dim: Optional[int] = None,
        require_unit_norm: bool = True,
        norm_tolerance: float = NORM_TOLERANCE,
    ) -> None:
        self._expected_dim = expected_dim
        self._require_unit_norm = bool(require_unit_norm)
        self._norm_tolerance = float(norm_tolerance)

    def validate(self, embedding: object) -> EmbeddingValidation:
        if embedding is None:
            return EmbeddingValidation(False, "embedding is None")
        if not isinstance(embedding, np.ndarray):
            try:
                embedding = np.asarray(embedding, dtype=np.float64)
            except Exception as e:
                return EmbeddingValidation(False, f"not array-like: {e}")
        if embedding.ndim != 1:
            return EmbeddingValidation(False, f"expected 1-D vector, got {embedding.ndim}-D")
        if embedding.dtype.type not in ALLOWED_DTYPES and embedding.dtype != np.float64:
            # int arrays are coercible but never accepted as-is.
            return EmbeddingValidation(False, f"unexpected dtype {embedding.dtype}")
        if self._expected_dim is not None and embedding.shape[0] != self._expected_dim:
            return EmbeddingValidation(
                False, f"dimension mismatch: got {embedding.shape[0]}, "
                       f"expected {self._expected_dim}",
                dim=embedding.shape[0])
        if not np.isfinite(embedding).all():
            return EmbeddingValidation(
                False, "embedding contains NaN or Inf",
                dim=int(embedding.shape[0]))
        norm = float(np.linalg.norm(embedding))
        if self._require_unit_norm and abs(norm - 1.0) > self._norm_tolerance:
            return EmbeddingValidation(
                False, f"embedding not unit-normalised (norm={norm:.4f})",
                dim=int(embedding.shape[0]), norm=norm)
        return EmbeddingValidation(True, "ok", dim=int(embedding.shape[0]), norm=norm)

    def normalize(self, embedding: np.ndarray) -> Optional[np.ndarray]:
        """Return an L2-normalised float32 copy, or None if invalid.

        Normalisation is the purpose of this method, so the unit-norm
        requirement is deliberately NOT enforced on the input; only
        structural validity (dtype, shape, dimension, finite values) is.
        """
        relaxed = EmbeddingValidator(
            expected_dim=self._expected_dim, require_unit_norm=False)
        v = relaxed.validate(embedding)
        if not v.is_valid:
            return None
        arr = np.asarray(embedding, dtype=np.float32).ravel()
        n = float(np.linalg.norm(arr))
        if n < 1e-12:
            return None  # zero vector cannot be normalised
        return (arr / n).astype(np.float32)


DEFAULT_VALIDATOR = EmbeddingValidator()


def cosine_similarity_secure(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    """Deterministic cosine similarity with the same fail-closed policy."""
    va = DEFAULT_VALIDATOR.validate(a)
    vb = DEFAULT_VALIDATOR.validate(b)
    if not va.is_valid or not vb.is_valid:
        return None
    if va.dim != vb.dim:
        return None
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-9 or nb < 1e-9:
        return None
    return float(np.dot(a, b) / (na * nb))