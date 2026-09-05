"""
Face verification benchmark.

Runs the configured embedder + matcher against genuine/impostor pairs and
computes verification metrics from actual predictions.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from benchmarks.biometric.metrics import (
    confusion_matrix,
    eer as compute_eer,
    far_frr,
    precision_recall_f1,
    rocAuc,
)


@dataclass
class PairResult:
    """Result for one verification pair."""
    label: int  # 1 = genuine, 0 = impostor
    similarity: float
    predicted: int  # 1 = match, 0 = no match
    latency_ms: float = 0.0


@dataclass
class VerificationResult:
    """Complete verification benchmark results."""
    pairs: List[PairResult] = field(default_factory=list)
    n_genuine: int = 0
    n_impostor: int = 0
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0
    far: float = 0.0
    frr: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    accuracy: float = 0.0
    rocauc: float = 0.5
    eer: float = 0.0
    eer_threshold: float = 0.5
    threshold: float = 0.62
    mean_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_genuine": self.n_genuine,
            "n_impostor": self.n_impostor,
            "tp": self.tp, "tn": self.tn, "fp": self.fp, "fn": self.fn,
            "far": self.far, "frr": self.frr,
            "precision": self.precision, "recall": self.recall, "f1": self.f1,
            "accuracy": self.accuracy,
            "rocauc": self.rocauc,
            "eer": self.eer, "eer_threshold": self.eer_threshold,
            "threshold": self.threshold,
            "mean_latency_ms": self.mean_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class VerificationBenchmark:
    """Benchmarks face verification using the configured embedder."""

    def __init__(
        self,
        embedder: Any,
        *,
        matcher: Optional[Any] = None,
        threshold: float = 0.62,
    ) -> None:
        self._embedder = embedder
        self._matcher = matcher
        self._threshold = threshold

    def run_pairs(
        self,
        pairs: Sequence[Tuple[bytes, bytes, int]],
        *,
        progress_fn: Optional[Callable[[int, int], None]] = None,
    ) -> VerificationResult:
        """Run verification on a list of (image_a, image_b, label) pairs.

        label=1 means genuine (same person), label=0 means impostor.
        """
        result = VerificationResult(threshold=self._threshold)
        latencies: List[float] = []

        for idx, (img_a, img_b, label) in enumerate(pairs):
            t0 = time.perf_counter()
            emb_a = self._embedder.embed(img_a)
            emb_b = self._embedder.embed(img_b)
            elapsed = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed)

            similarity = self._compute_similarity(emb_a, emb_b)
            predicted = 1 if similarity >= self._threshold else 0

            result.pairs.append(PairResult(
                label=int(label),
                similarity=round(float(similarity), 6),
                predicted=predicted,
                latency_ms=round(elapsed, 2),
            ))

            if progress_fn is not None:
                progress_fn(idx + 1, len(pairs))

        # Compute metrics
        y_true = [p.label for p in result.pairs]
        y_pred = [p.predicted for p in result.pairs]
        y_score = [p.similarity for p in result.pairs]

        cm = confusion_matrix(y_true, y_pred)
        result.tp = cm.tp
        result.tn = cm.tn
        result.fp = cm.fp
        result.fn = cm.fn
        result.n_genuine = int(sum(1 for p in result.pairs if p.label == 1))
        result.n_impostor = int(sum(1 for p in result.pairs if p.label == 0))

        far, frr = far_frr(cm)
        result.far = round(far, 6)
        result.frr = round(frr, 6)

        prec, rec, f1 = precision_recall_f1(cm)
        result.precision = round(prec, 6)
        result.recall = round(rec, 6)
        result.f1 = round(f1, 6)
        result.accuracy = round(cm.accuracy(), 6)

        result.rocauc = round(rocAuc(y_true, y_score), 6)
        eer_val, eer_thresh = compute_eer(y_true, y_score)
        result.eer = round(eer_val, 6)
        result.eer_threshold = round(eer_thresh, 6)

        if latencies:
            arr = np.array(latencies)
            result.mean_latency_ms = round(float(arr.mean()), 2)
            result.p95_latency_ms = round(float(np.percentile(arr, 95)), 2)

        result.metadata = {
            "threshold": self._threshold,
            "n_pairs": len(pairs),
            "embedder": getattr(self._embedder, '__class__', object).__name__,
        }
        return result

    def _compute_similarity(
        self,
        emb_a: Optional[np.ndarray],
        emb_b: Optional[np.ndarray],
    ) -> float:
        """Cosine similarity between two embeddings."""
        if emb_a is None or emb_b is None:
            return 0.0
        a = np.asarray(emb_a, dtype=np.float64).ravel()
        b = np.asarray(emb_b, dtype=np.float64).ravel()
        if a.shape != b.shape or a.size == 0:
            return 0.0
        na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
        if na < 1e-9 or nb < 1e-9:
            return 0.0
        return float(np.dot(a, b) / (na * nb))
