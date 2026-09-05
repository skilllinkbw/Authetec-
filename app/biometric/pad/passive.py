"""
Passive PAD signals.

Each signal is a deterministic image statistic that published spoof-
detection research has shown to carry discriminative information between
a live bonafide capture and a re-presented photograph / display:

  * spectral energy ratios      - print/screen re-capture compresses
                                  high-frequency energy differently
  * moire pattern strength      - screen re-capture introduces periodic
                                  interference
  * Laplacian variance          - reprints and compressed frames blur
  * high-frequency noise floor  - re-encoded video frames lose detail
  * compression-artifact ratio  - heavy JPEG re-compression signature

The current implementations are DETERMINISTIC FALLBACKS.  They are
calibrated on a synthetic image-corruption model and MUST be re-validated
on a real presentation-attack dataset before any production claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np


@dataclass
class PassiveSignals:
    laplacian_variance: float = 0.0
    high_freq_ratio: float = 0.0       # fraction of spectral energy in HF band
    moire_score: float = 0.0           # 0..1 periodic artifact estimate
    compression_artifacts: float = 0.0 # 0..1 re-compression estimate
    edge_density: float = 0.0
    assessed: bool = False
    methods: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "laplacian_variance": round(self.laplacian_variance, 4),
            "high_freq_ratio": round(self.high_freq_ratio, 6),
            "moire_score": round(self.moire_score, 6),
            "compression_artifacts": round(self.compression_artifacts, 6),
            "edge_density": round(self.edge_density, 6),
            "assessed": self.assessed,
            "methods": self.methods,
        }


def _decode_gray(image_bytes: bytes):
    import cv2
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)


def compute_passive_signals(image_bytes: bytes) -> PassiveSignals:
    """Deterministic multi-signal passive analysis.

    Honesty note: thresholds are minima observed on synthetic degradation
    curves; production calibration requires a labelled presentation-attack
    dataset (documented blocker).
    """
    import cv2
    img = _decode_gray(image_bytes)
    s = PassiveSignals()
    if img is None or img.size == 0:
        return s
    h, w = img.shape[:2]
    if h < 32 or w < 32:
        s.assessed = False
        s.methods.append("too_small")
        return s

    s.laplacian_variance = float(cv2.Laplacian(img, cv2.CV_64F).var())
    s.edge_density = float(cv2.Canny(img, 80, 160).mean() / 255.0)

    # ── spectral energy bands (2D DFT) ────────────────────────────────
    f = np.fft.fft2(img.astype(np.float64))
    fshift = np.fft.fftshift(f)
    magnitude = np.abs(fshift)
    cy, cx = h // 2, w // 2
    radius = np.sqrt(
        (np.arange(h)[:, None] - cy) ** 2 + (np.arange(w)[None, :] - cx) ** 2)
    total = float(magnitude.sum())
    if total > 1e-9:
        high_band = radius > 0.25 * max(h, w)
        s.high_freq_ratio = float(magnitude[high_band].sum() / total)
        mid = (radius > 0.1 * max(h, w)) & (radius < 0.4 * max(h, w))
        if mid.any():
            mid_mag = magnitude[mid]
            peak_ratio = float(mid_mag.max()) / (float(mid_mag.mean()) + 1e-9)
            s.moire_score = min(1.0, max(0.0, (peak_ratio - 6.0) / 40.0))
        s.methods.append("spectral_bands")

    # ── JPEG re-compression artifact estimate ─────────────────────────
    # Re-captured print/screen media has usually been through at least
    # one extra lossy encode.  Estimating the blockiness (8x8 grid
    # discontinuity) relative to overall gradient energy gives a stable,
    # deterministic artifact signal.
    try:
        gx = cv2.Sobel(img, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(img, cv2.CV_64F, 0, 1, ksize=3)
        grad_energy = float(np.sqrt(gx ** 2 + gy ** 2).mean())
        blockiness = 0.0
        # Horizontal block boundaries at x = 8, 16, 24, ...
        col_diff = np.abs(np.diff(img.astype(np.float64), axis=1))
        boundary_cols = np.arange(7, col_diff.shape[1], 8)
        if boundary_cols.size and grad_energy > 1e-9:
            boundary_strength = float(col_diff[:, boundary_cols].mean())
            interior = np.delete(col_diff, boundary_cols, axis=1)
            interior_strength = float(interior.mean()) if interior.size else 0.0
            if interior_strength > 1e-9:
                blockiness = boundary_strength / interior_strength
        # blockiness ~1.0 for natural images; >>1 indicates JPEG grid
        s.compression_artifacts = min(
            1.0, max(0.0, (blockiness - 1.15) / 1.5))
        s.methods.append("jpeg_blockiness")
    except Exception:
        pass  # signal stays 0.0 — absence of evidence is not evidence

    s.assessed = True
    return s