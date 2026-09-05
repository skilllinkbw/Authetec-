"""
Threshold calibration for face verification.

Given genuine (same-person) and impostor (different-person) similarity
scores, compute:

    * FMR  (False Match Rate)   = impostor scores above threshold
    * FNMR (False Non-Match)    = genuine scores below threshold
    * EER  (Equal Error Rate)   = threshold where FMR == FNMR
    * threshold curves          = (threshold, FMR, FNMR) sweep

Calibration results are only as honest as the data they were computed on.
Every result carries a ``dataset_label`` and a ``NOT VALIDATED`` marker
unless ``validated=True`` was passed by an operator following the real-
world validation protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class CalibrationResult:
    threshold_match: float
    threshold_not_match: float
    eer: Optional[float]
    fmr_at_threshold: float
    fnmr_at_threshold: float
    n_genuine: int
    n_impostor: int
    dataset_label: str = "SYNTHETIC/TEST-ONLY"
    validated: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "threshold_match": round(self.threshold_match, 6),
            "threshold_not_match": round(self.threshold_not_match, 6),
            "eer": (round(self.eer, 6) if self.eer is not None else None),
            "fmr_at_threshold": round(self.fmr_at_threshold, 6),
            "fnmr_at_threshold": round(self.fnmr_at_threshold, 6),
            "n_genuine": self.n_genuine,
            "n_impostor": self.n_impostor,
            "dataset_label": self.dataset_label,
            "validated": self.validated,
            "notes": self.notes,
        }


def compute_eer(genuine: np.ndarray, impostor: np.ndarray) -> float:
    """Equal Error Rate from genuine/impostor score arrays."""
    gen = np.asarray(genuine, dtype=np.float64).ravel()
    imp = np.asarray(impostor, dtype=np.float64).ravel()
    if gen.size == 0 or imp.size == 0:
        raise ValueError("need at least one genuine and one impostor score")
    thresholds = np.unique(np.concatenate([gen, imp]))
    thresholds = np.sort(thresholds)
    best = 1.0
    for t in thresholds:
        fnmr = float((gen < t).mean())
        fmr = float((imp >= t).mean())
        best = min(best, abs(fmr - fnmr))
    return float(best)


def calibrate_thresholds(
    genuine_scores: List[float],
    impostor_scores: List[float],
    *,
    fallback_match: float = 0.50,
    fallback_not_match: float = 0.35,
    dataset_label: str = "SYNTHETIC/TEST-ONLY",
    validated: bool = False,
) -> CalibrationResult:
    """Choose match/not-match thresholds from score distributions.

    Strategy: place the match threshold at the point on the threshold sweep
    where FMR is minimised while keeping FNMR below 5%; the not-match
    threshold mirrors it at the symmetric position.  If there is not enough
    data, fall back to the conservative defaults and say so in the notes.
    """
    gen = np.asarray(genuine_scores, dtype=np.float64).ravel()
    imp = np.asarray(impostor_scores, dtype=np.float64).ravel()
    if gen.size < 5 or imp.size < 5:
        return CalibrationResult(
            threshold_match=fallback_match,
            threshold_not_match=fallback_not_match,
            eer=None,
            fmr_at_threshold=(
                float((imp >= fallback_match).mean())
                if imp.size else float("nan")),
            fnmr_at_threshold=(
                float((gen < fallback_match).mean())
                if gen.size else float("nan")),
            n_genuine=int(gen.size),
            n_impostor=int(imp.size),
            dataset_label=dataset_label,
            validated=validated,
            notes=["insufficient data - conservative defaults used"],
        )

    thresholds = np.sort(np.unique(np.concatenate([gen, imp])))
    best_t: Optional[float] = None
    best_fmr = 1.0
    for t in thresholds:
        fnmr = float((gen < t).mean())
        if fnmr > 0.05:
            continue  # do not accept FNMR > 5% on calibration data
        fmr = float((imp >= t).mean())
        if fmr < best_fmr:
            best_fmr = fmr
            best_t = float(t)

    if best_t is None:
        best_t = fallback_match

    eer = compute_eer(gen, imp)
    span = max(1e-6, best_t - fallback_not_match)
    not_match = max(0.0, float(best_t) - span * 0.5)

    notes = [
        f"calibrated on {gen.size} genuine / {imp.size} impostor scores",
        "FMR minimised with FNMR capped at 5% on calibration data",
        "thresholds MUST be re-checked on real-world data before production",
    ]
    return CalibrationResult(
        threshold_match=float(best_t),
        threshold_not_match=float(round(not_match, 6)),
        eer=float(eer),
        fmr_at_threshold=float((imp >= float(best_t)).mean()),
        fnmr_at_threshold=float((gen < float(best_t)).mean()),
        n_genuine=int(gen.size),
        n_impostor=int(imp.size),
        dataset_label=dataset_label,
        validated=validated,
        notes=notes,
    )