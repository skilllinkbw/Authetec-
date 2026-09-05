"""
Performance benchmark for the biometric pipeline.

Measures latency and throughput of the detection, alignment, embedding,
and PAD stages.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np


@dataclass
class StageResult:
    """Latency results for one pipeline stage."""
    stage: str
    n: int = 0
    mean_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0


@dataclass
class PerformanceResult:
    """Complete performance benchmark results."""
    detection: Optional[StageResult] = None
    alignment: Optional[StageResult] = None
    embedding: Optional[StageResult] = None
    pad: Optional[StageResult] = None
    end_to_end: Optional[StageResult] = None
    throughput_per_sec: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detection": self._stage_dict(self.detection),
            "alignment": self._stage_dict(self.alignment),
            "embedding": self._stage_dict(self.embedding),
            "pad": self._stage_dict(self.pad),
            "end_to_end": self._stage_dict(self.end_to_end),
            "throughput_per_sec": self.throughput_per_sec,
            "metadata": self.metadata,
        }

    @staticmethod
    def _stage_dict(s: Optional[StageResult]) -> Optional[Dict[str, Any]]:
        if s is None:
            return None
        return {
            "stage": s.stage, "n": s.n,
            "mean_ms": s.mean_ms, "p50_ms": s.p50_ms,
            "p95_ms": s.p95_ms, "p99_ms": s.p99_ms,
            "min_ms": s.min_ms, "max_ms": s.max_ms,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


def _measure_latency(fn: Callable[[], Any], n_warmup: int = 3, n_iters: int = 20) -> StageResult:
    """Measure latency of a callable with warm-up."""
    # Warm-up
    for _ in range(n_warmup):
        fn()
    times: List[float] = []
    for _ in range(n_iters):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    arr = np.array(times)
    return StageResult(
        stage="",
        n=n_iters,
        mean_ms=round(float(arr.mean()), 2),
        p50_ms=round(float(np.percentile(arr, 50)), 2),
        p95_ms=round(float(np.percentile(arr, 95)), 2),
        p99_ms=round(float(np.percentile(arr, 99)), 2),
        min_ms=round(float(arr.min()), 2),
        max_ms=round(float(arr.max()), 2),
    )


class PerformanceBenchmark:
    """Benchmarks the performance of the biometric pipeline stages."""

    def __init__(
        self,
        embedder: Any,
        *,
        detector: Optional[Any] = None,
        aligner: Optional[Any] = None,
        liveness_detector: Optional[Any] = None,
        n_warmup: int = 3,
        n_iters: int = 20,
    ) -> None:
        self._embedder = embedder
        self._detector = detector
        self._aligner = aligner
        self._liveness = liveness_detector
        self._n_warmup = n_warmup
        self._n_iters = n_iters

    def run(self, sample_image_bytes: bytes) -> PerformanceResult:
        """Run performance benchmarks on a sample image."""
        result = PerformanceResult()

        # Detection
        if self._detector is not None:
            def detect():
                return self._detector.detect(sample_image_bytes)
            r = _measure_latency(detect, self._n_warmup, self._n_iters)
            r.stage = "detection"
            result.detection = r

        # Alignment
        if self._aligner is not None:
            def align():
                return self._aligner.align(sample_image_bytes)
            r = _measure_latency(align, self._n_warmup, self._n_iters)
            r.stage = "alignment"
            result.alignment = r

        # Embedding
        if self._embedder is not None:
            def embed():
                return self._embedder.embed(sample_image_bytes)
            r = _measure_latency(embed, self._n_warmup, self._n_iters)
            r.stage = "embedding"
            result.embedding = r

        # PAD
        if self._liveness is not None:
            def pad():
                return self._liveness.check(sample_image_bytes)
            r = _measure_latency(pad, self._n_warmup, self._n_iters)
            r.stage = "pad"
            result.pad = r

        # End-to-end (full pipeline)
        def e2e():
            data = sample_image_bytes
            if self._detector is not None:
                det = self._detector.detect(data)
                if det and det.faces and det.faces[0].crop_bytes:
                    data = det.faces[0].crop_bytes
            if self._aligner is not None:
                aligned = self._aligner.align(data)
                if aligned is not None:
                    data = aligned
            if self._embedder is not None:
                self._embedder.embed(data)
            if self._liveness is not None:
                self._liveness.check(sample_image_bytes)
        r = _measure_latency(e2e, self._n_warmup, self._n_iters)
        r.stage = "end_to_end"
        result.end_to_end = r

        # Throughput
        if result.end_to_end and result.end_to_end.mean_ms > 0:
            result.throughput_per_sec = round(1000.0 / result.end_to_end.mean_ms, 2)

        result.metadata = {
            "n_warmup": self._n_warmup,
            "n_iters": self._n_iters,
            "provider": getattr(self._embedder, 'provider', None)
            and getattr(self._embedder.provider, 'name', '')
            or getattr(self._embedder, '__class__', object).__name__,
        }
        return result
