"""
Threshold analysis for face verification.

Evaluates a range of thresholds and reports FAR/FRR curves, EER, and the
selected operating point.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from benchmarks.biometric.metrics import (
    confusion_matrix,
    eer as compute_eer,
    far_frr,
    precision_recall_f1,
    rocAuc,
)


@dataclass
class ThresholdPoint:
    """Metrics at one threshold value."""
    threshold: float
    far: float
    frr: float
    precision: float
    recall: float
    f1: float
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0


@dataclass
class ThresholdAnalysis:
    """Complete threshold analysis results."""
    points: List[ThresholdPoint] = field(default_factory=list)
    eer: float = 0.0
    eer_threshold: float = 0.5
    rocauc: float = 0.5
    selected_threshold: float = 0.62
    selected_far: float = 0.0
    selected_frr: float = 0.0
    n_genuine: int = 0
    n_impostor: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "points": [
                {
                    "threshold": p.threshold,
                    "far": p.far,
                    "frr": p.frr,
                    "precision": p.precision,
                    "recall": p.recall,
                    "f1": p.f1,
                    "tp": p.tp, "tn": p.tn, "fp": p.fp, "fn": p.fn,
                }
                for p in self.points
            ],
            "eer": self.eer,
            "eer_threshold": self.eer_threshold,
            "rocauc": self.rocauc,
            "selected_threshold": self.selected_threshold,
            "selected_far": self.selected_far,
            "selected_frr": self.selected_frr,
            "n_genuine": self.n_genuine,
            "n_impostor": self.n_impostor,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


def analyze_thresholds(
    genuine_scores: Sequence[float],
    impostor_scores: Sequence[float],
    *,
    n_steps: int = 101,
    threshold_range: Tuple[float, float] = (-0.2, 1.0),
    selected_threshold: Optional[float] = None,
) -> ThresholdAnalysis:
    """Evaluate metrics across a range of thresholds.

    Args:
        genuine_scores: similarity scores for genuine (same-person) pairs.
        impostor_scores: similarity scores for impostor (different-person) pairs.
        n_steps: number of thresholds to evaluate.
        threshold_range: (min, max) threshold range.
        selected_threshold: if provided, mark this as the selected operating
            point (otherwise uses EER threshold).

    Returns:
        ThresholdAnalysis with the full curve and summary metrics.
    """
    genuine = np.asarray(genuine_scores, dtype=np.float64)
    impostor = np.asarray(impostor_scores, dtype=np.float64)

    analysis = ThresholdAnalysis(
        n_genuine=len(genuine),
        n_impostor=len(impostor),
    )

    # Combine all scores for ROC-AUC
    y_true = np.concatenate([
        np.ones(len(genuine), dtype=np.int32),
        np.zeros(len(impostor), dtype=np.int32),
    ])
    y_score = np.concatenate([genuine, impostor])
    analysis.rocauc = rocAuc(y_true, y_score)
    analysis.eer, analysis.eer_threshold = compute_eer(y_true, y_score)

    thresholds = np.linspace(threshold_range[0], threshold_range[1], n_steps)
    for t in thresholds:
        tp = int(np.sum(genuine >= t))
        fn = int(np.sum(genuine < t))
        fp = int(np.sum(impostor >= t))
        tn = int(np.sum(impostor < t))
        cm = confusion_matrix(y_true, np.concatenate([
            (genuine >= t).astype(np.int32),
            (impostor >= t).astype(np.int32),
        ]))
        far, frr = far_frr(cm)
        prec, rec, f1 = precision_recall_f1(cm)
        analysis.points.append(ThresholdPoint(
            threshold=round(float(t), 6),
            far=round(far, 6),
            frr=round(frr, 6),
            precision=round(prec, 6),
            recall=round(rec, 6),
            f1=round(f1, 6),
            tp=tp, tn=tn, fp=fp, fn=fn,
        ))

    # Selected operating point
    sel = selected_threshold if selected_threshold is not None else analysis.eer_threshold
    analysis.selected_threshold = round(float(sel), 6)
    # Find the closest threshold point
    closest = min(analysis.points, key=lambda p: abs(p.threshold - sel))
    analysis.selected_far = closest.far
    analysis.selected_frr = closest.frr

    analysis.metadata = {
        "n_steps": n_steps,
        "threshold_range": list(threshold_range),
    }
    return analysis
