"""
Biometric benchmark metrics.

All metrics are calculated from actual predictions — never hardcoded.
Every function is a pure calculation over arrays of scores and labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class ConfusionMatrix:
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.tn + self.fp + self.fn

    def accuracy(self) -> float:
        return (self.tp + self.tn) / max(1, self.total)

    def to_dict(self) -> dict:
        return {"tp": self.tp, "tn": self.tn, "fp": self.fp, "fn": self.fn}


def confusion_matrix(
    y_true: Sequence[int],
    y_pred: Sequence[int],
) -> ConfusionMatrix:
    """Binary confusion matrix from ground-truth and predicted labels.

    Labels: 1 = positive (genuine / live), 0 = negative (impostor / attack).
    """
    y_true = np.asarray(y_true, dtype=np.int32)
    y_pred = np.asarray(y_pred, dtype=np.int32)
    if y_true.shape != y_pred.shape:
        raise ValueError("y_true and y_pred must have the same length")
    return ConfusionMatrix(
        tp=int(np.sum((y_true == 1) & (y_pred == 1))),
        tn=int(np.sum((y_true == 0) & (y_pred == 0))),
        fp=int(np.sum((y_true == 0) & (y_pred == 1))),
        fn=int(np.sum((y_true == 1) & (y_pred == 0))),
    )


def far_frr(cm: ConfusionMatrix) -> Tuple[float, float]:
    """False Acceptance Rate and False Rejection Rate."""
    far = cm.fp / max(1, cm.fp + cm.tn)
    frr = cm.fn / max(1, cm.fn + cm.tp)
    return float(far), float(frr)


def precision_recall_f1(cm: ConfusionMatrix) -> Tuple[float, float, float]:
    """Precision, recall, F1 from a confusion matrix."""
    precision = cm.tp / max(1, cm.tp + cm.fp)
    recall = cm.tp / max(1, cm.tp + cm.fn)
    f1 = (
        2 * precision * recall / max(1e-12, precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return float(precision), float(recall), float(f1)


def rocAuc(y_true: Sequence[int], y_score: Sequence[float]) -> float:
    """Area under the ROC curve, computed from scores via the Mann-Whitney U
    statistic (equivalent to the trapezoidal rule on the empirical ROC).

    Returns 0.5 when there are no samples of one class (uninformative).
    """
    y_true = np.asarray(y_true, dtype=np.int32)
    y_score = np.asarray(y_score, dtype=np.float64)
    if y_true.shape != y_score.shape or y_true.size == 0:
        return 0.5
    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    if pos.size == 0 or neg.size == 0:
        return 0.5
    # Mann-Whitney U: for every (pos, neg) pair, count pos > neg.
    # Vectorized via broadcasting.
    diff = pos[:, None] - neg[None, :]
    auc = (np.sum(diff > 0) + 0.5 * np.sum(diff == 0)) / (pos.size * neg.size)
    return float(auc)


def eer(
    y_true: Sequence[int], y_score: Sequence[float], *, n_steps: int = 1000
) -> Tuple[float, float]:
    """Equal Error Rate: the point where FAR ≈ FRR.

    Returns (eer, threshold_at_eer). When the score distributions do not
    overlap cleanly, returns the threshold with the smallest |FAR - FRR|.
    """
    y_true = np.asarray(y_true, dtype=np.int32)
    y_score = np.asarray(y_score, dtype=np.float64)
    if y_true.size == 0 or y_true.shape != y_score.shape:
        return 0.0, 0.5
    if np.all(y_true == y_true[0]):
        return 0.0, 0.5

    thresholds = np.linspace(float(y_score.min()), float(y_score.max()), n_steps)
    far_list, frr_list = [], []
    for t in thresholds:
        y_pred = (y_score >= t).astype(np.int32)
        cm = confusion_matrix(y_true, y_pred)
        far, frr = far_frr(cm)
        far_list.append(far)
        frr_list.append(frr)
    far_arr = np.array(far_list)
    frr_arr = np.array(frr_list)
    idx = np.argmin(np.abs(far_arr - frr_arr))
    return float((far_arr[idx] + frr_arr[idx]) / 2), float(thresholds[idx])
