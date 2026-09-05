"""
Presentation-attack detection benchmark.

Runs the configured PAD / liveness engine against bona-fide and attack
samples and computes PAD metrics from actual predictions.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np


@dataclass
class PadSampleResult:
    """Result for one PAD sample."""
    label: int  # 1 = bona-fide (live), 0 = attack
    predicted_live: bool
    confidence: float
    latency_ms: float = 0.0
    attack_type: str = ""  # e.g. "print", "screen", "replay"; "" for bona-fide


@dataclass
class PadResult:
    """Complete PAD benchmark results."""
    samples: List[PadSampleResult] = field(default_factory=list)
    n_bonafide: int = 0
    n_attack: int = 0
    tp: int = 0  # correctly accepted bona-fide
    tn: int = 0  # correctly rejected attack
    fp: int = 0  # attack accepted (bad)
    fn: int = 0  # bona-fide rejected
    apcer: float = 0.0  # attack presentation classification error rate
    bpcer: float = 0.0  # bona-fide presentation classification error rate
    acer: float = 0.0  # average classification error rate
    bonafide_accept_rate: float = 0.0
    attack_accept_rate: float = 0.0
    mean_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    attack_specific: Dict[str, Dict[str, float]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_bonafide": self.n_bonafide,
            "n_attack": self.n_attack,
            "tp": self.tp, "tn": self.tn, "fp": self.fp, "fn": self.fn,
            "apcer": self.apcer,
            "bpcer": self.bpcer,
            "acer": self.acer,
            "bonafide_accept_rate": self.bonafide_accept_rate,
            "attack_accept_rate": self.attack_accept_rate,
            "mean_latency_ms": self.mean_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "attack_specific": self.attack_specific,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class PadBenchmark:
    """Benchmarks PAD / liveness detection."""

    def __init__(self, liveness_detector: Any) -> None:
        self._detector = liveness_detector

    def run_samples(
        self,
        samples: Sequence[Tuple[bytes, int, str]],
        *,
        progress_fn: Optional[Callable[[int, int], None]] = None,
    ) -> PadResult:
        """Run PAD on a list of (image_bytes, label, attack_type) samples.

        label=1 means bona-fide (live), label=0 means attack.
        attack_type is a string label like "print", "screen", "replay" (or "" for bona-fide).
        """
        result = PadResult()
        latencies: List[float] = []

        for idx, (img_bytes, label, attack_type) in enumerate(samples):
            t0 = time.perf_counter()
            try:
                check = self._detector.check(img_bytes)
                predicted_live = bool(check.is_live)
                confidence = float(getattr(check, 'confidence', 0.5))
            except Exception:
                predicted_live = False
                confidence = 0.0
            elapsed = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed)

            result.samples.append(PadSampleResult(
                label=int(label),
                predicted_live=predicted_live,
                confidence=round(confidence, 4),
                latency_ms=round(elapsed, 2),
                attack_type=attack_type,
            ))

            if progress_fn is not None:
                progress_fn(idx + 1, len(samples))

        # Compute metrics
        bonafide = [s for s in result.samples if s.label == 1]
        attacks = [s for s in result.samples if s.label == 0]
        result.n_bonafide = len(bonafide)
        result.n_attack = len(attacks)

        result.tp = sum(1 for s in bonafide if s.predicted_live)
        result.fn = sum(1 for s in bonafide if not s.predicted_live)
        result.fp = sum(1 for s in attacks if s.predicted_live)
        result.tn = sum(1 for s in attacks if not s.predicted_live)

        # APCER: attack presentations classified as bona-fide (fp / n_attacks)
        result.apcer = result.fp / max(1, result.n_attack)
        # BPCER: bona-fide presentations classified as attacks (fn / n_bonafide)
        result.bpcer = result.fn / max(1, result.n_bonafide)
        # ACER: average of APCER and BPCER
        result.acer = (result.apcer + result.bpcer) / 2.0

        result.bonafide_accept_rate = result.tp / max(1, result.n_bonafide)
        result.attack_accept_rate = result.fp / max(1, result.n_attack)

        # Attack-specific breakdown
        attack_types: Dict[str, List[PadSampleResult]] = {}
        for s in attacks:
            attack_types.setdefault(s.attack_type or "unknown", []).append(s)
        for atype, samples_of_type in attack_types.items():
            accepted = sum(1 for s in samples_of_type if s.predicted_live)
            result.attack_specific[atype] = {
                "n": len(samples_of_type),
                "accepted": accepted,
                "rejected": len(samples_of_type) - accepted,
                "accept_rate": round(accepted / max(1, len(samples_of_type)), 6),
            }

        if latencies:
            arr = np.array(latencies)
            result.mean_latency_ms = round(float(arr.mean()), 2)
            result.p95_latency_ms = round(float(np.percentile(arr, 95)), 2)

        result.metadata = {
            "n_samples": len(samples),
            "detector": getattr(self._detector, '__class__', object).__name__,
        }
        return result
