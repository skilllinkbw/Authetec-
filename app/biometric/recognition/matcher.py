"""
1:1 face matcher with explicit, calibrated outcomes.

A face verification decision is never a bare similarity number.  It is
one of:

    MATCH        - similarity exceeds the calibrated acceptance threshold
    NO_MATCH     - similarity is below the calibrated rejection threshold
    INCONCLUSIVE - signal is too weak to decide either way

INCONCLUSIVE exists so that borderline cases are NEVER forced into MATCH
(a security policy, not an implementation detail).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import numpy as np

from app.biometric.recognition.embeddings import (
    EmbeddingValidator,
    cosine_similarity_secure,
)


class MatchOutcome(str, Enum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class MatchDecision:
    outcome: MatchOutcome
    similarity: Optional[float]
    threshold_match: float
    threshold_not_match: float
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)

    @property
    def is_match(self) -> bool:
        return self.outcome is MatchOutcome.MATCH


class FaceMatcher:
    """Calibrated 1:1 face matcher.

    Two thresholds:

      * ``threshold_match``      - score >= this  => MATCH
      * ``threshold_not_match``  - score <= this  => NO_MATCH

    Scores strictly between the two are INCONCLUSIVE.  The region between
    the thresholds is intentionally never accepted.
    """

    def __init__(
        self,
        threshold_match: float = 0.50,
        threshold_not_match: float = 0.35,
        validator: Optional[EmbeddingValidator] = None,
    ) -> None:
        self.threshold_match = float(threshold_match)
        self.threshold_not_match = float(threshold_not_match)
        self._validator = validator or EmbeddingValidator()

    def compare(self, a: np.ndarray, b: np.ndarray) -> MatchDecision:
        sim = cosine_similarity_secure(a, b)
        if sim is None:
            return MatchDecision(
                outcome=MatchOutcome.INCONCLUSIVE,
                similarity=None,
                threshold_match=self.threshold_match,
                threshold_not_match=self.threshold_not_match,
                confidence=0.05,
                reasons=["invalid embedding(s) - fail closed"],
            )
        reasons = [
            f"similarity={sim:.4f}",
            f"match_threshold={self.threshold_match:.2f}",
            f"not_match_threshold={self.threshold_not_match:.2f}",
        ]
        if sim >= self.threshold_match:
            outcome = MatchOutcome.MATCH
            confidence = self._confidence_match(sim)
        elif sim <= self.threshold_not_match:
            outcome = MatchOutcome.NO_MATCH
            confidence = self._confidence_no_match(sim)
        else:
            outcome = MatchOutcome.INCONCLUSIVE
            confidence = 0.30
            reasons.append(
                "score in indeterminate band - not forced into MATCH")

        return MatchDecision(
            outcome=outcome,
            similarity=round(sim, 6),
            threshold_match=self.threshold_match,
            threshold_not_match=self.threshold_not_match,
            confidence=round(confidence, 4),
            reasons=reasons,
        )

    @staticmethod
    def _confidence_match(sim: float) -> float:
        return max(0.50, min(0.999, 0.5 + (sim - 0.5) / 0.5))

    @staticmethod
    def _confidence_no_match(sim: float) -> float:
        return max(0.50, min(0.999, 0.5 + (0.35 - sim) / 0.5))