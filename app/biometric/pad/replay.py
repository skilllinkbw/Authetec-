"""
Replay / media-reuse detection for frame sequences.

Analyzes the temporal integrity of a capture session:

    * duplicated frames        - identical perceptual digests repeated
    * near-duplicate ratio     - re-encoded replay shows unnatural repetition
    * timestamp anomalies      - non-monotonic, perfectly regular, or gapped
    * frame-rate anomalies     - rates outside plausible camera behaviour

All analysis is deterministic: the same frame sequence always yields the
same verdict.  Like every PAD layer here the calibration is SYNTHETIC;
production claims require a labelled replay-attack dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


# Frames captured by real cameras never arrive perfectly regularly.
PERFECT_REGULARITY_TOLERANCE_S = 0.0005
MIN_PLAUSIBLE_FPS = 2.0
MAX_PLAUSIBLE_FPS = 90.0
MIN_FRAMES_FOR_TEMPORAL = 3


@dataclass
class ReplaySignals:
    n_frames: int = 0
    duplicate_pairs: int = 0
    near_duplicate_ratio: float = 0.0
    timestamp_inversions: int = 0
    perfect_regularity: bool = False
    fps_estimate: float = 0.0
    implausible_fps: bool = False
    assessed: bool = False
    methods: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n_frames": self.n_frames,
            "duplicate_pairs": self.duplicate_pairs,
            "near_duplicate_ratio": round(self.near_duplicate_ratio, 6),
            "timestamp_inversions": self.timestamp_inversions,
            "perfect_regularity": self.perfect_regularity,
            "fps_estimate": round(self.fps_estimate, 4),
            "implausible_fps": self.implausible_fps,
            "assessed": self.assessed,
            "methods": self.methods,
        }


def _perceptual_digest(frame_bytes: bytes) -> Optional[bytes]:
    """Deterministic 8x8 mean-threshold hash (aHash) of a frame."""
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if gray is None or gray.size == 0:
            return None
        small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
        mean = float(small.mean())
        bits = (small.astype(np.float64) > mean).flatten()
        return np.packbits(bits).tobytes()
    except Exception:
        return None


def _hamming(a: bytes, b: bytes) -> int:
    return sum(bin(x ^ y).count("1") for x, y in zip(a, b))


def analyze_frame_sequence(
    frame_bytes_list: Sequence[bytes],
    timestamps_s: Optional[Sequence[float]] = None,
    *,
    near_duplicate_hamming: int = 4,
) -> ReplaySignals:
    """Analyze a frame sequence for replay / duplication indicators.

    ``frame_bytes_list`` - encoded frames in capture order.
    ``timestamps_s``     - per-frame capture timestamps (seconds); optional.
    """
    s = ReplaySignals(n_frames=len(frame_bytes_list))
    if len(frame_bytes_list) < MIN_FRAMES_FOR_TEMPORAL:
        return s  # not assessable; caller must not treat this as "live"

    digests = [_perceptual_digest(f) for f in frame_bytes_list]
    if not all(d is not None for d in digests):
        s.methods.append("undecodable_frames")
        return s

    # ── exact duplicates ──────────────────────────────────────────────
    pairs = 0
    for i in range(len(digests)):
        for j in range(i + 1, len(digests)):
            if digests[i] == digests[j]:
                pairs += 1
    s.duplicate_pairs = pairs
    s.methods.append("exact_duplicates")

    # ── near-duplicate ratio (adjacent-frame Hamming distance) ────────
    dists = [_hamming(digests[i], digests[i + 1])
             for i in range(len(digests) - 1)]
    near = sum(1 for d in dists if d <= near_duplicate_hamming)
    s.near_duplicate_ratio = near / max(1, len(dists))
    s.methods.append("near_duplicates")

    # ── timestamp analysis ────────────────────────────────────────────
    if timestamps_s is not None and len(timestamps_s) == len(frame_bytes_list):
        ts = [float(t) for t in timestamps_s]
        s.timestamp_inversions = sum(
            1 for i in range(len(ts) - 1) if ts[i + 1] < ts[i])
        deltas = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
        positive = [d for d in deltas if d > 0]
        if positive:
            mean_d = sum(positive) / len(positive)
            s.fps_estimate = 1.0 / mean_d if mean_d > 0 else 0.0
            s.implausible_fps = not (
                MIN_PLAUSIBLE_FPS <= s.fps_estimate <= MAX_PLAUSIBLE_FPS)
            if len(positive) >= 2 and mean_d > 0:
                spread = max(positive) - min(positive)
                if spread < PERFECT_REGULARITY_TOLERANCE_S:
                    # Real camera pipelines jitter; perfectly constant
                    # deltas across >=3 frames indicate synthetic media.
                    s.perfect_regularity = True
        s.methods.append("timestamp_analysis")

    s.assessed = True
    return s


def replay_attack_indicators(s: ReplaySignals) -> List[Tuple[str, float]]:
    """Return (indicator, confidence) pairs; empty list = no evidence.

    Confidence values are heuristic placeholders pending calibration on
    a labelled replay dataset (documented blocker) — they are risk
    signals for the decision engine, not scientific probabilities.
    """
    out: List[Tuple[str, float]] = []
    if not s.assessed:
        return out
    if s.duplicate_pairs > 0:
        out.append(("replay.duplicate_frames",
                    min(0.95, 0.6 + 0.1 * s.duplicate_pairs)))
    if s.near_duplicate_ratio > 0.8:
        out.append(("replay.near_duplicate_sequence",
                    min(0.90, 0.5 + 0.4 * s.near_duplicate_ratio)))
    if s.timestamp_inversions > 0:
        out.append(("replay.timestamp_inversion", 0.85))
    if s.perfect_regularity:
        out.append(("replay.perfect_frame_regularity", 0.60))
    if s.implausible_fps:
        out.append(("replay.implausible_frame_rate", 0.55))
    return out
