"""
AUTHeTEC multi-layer PAD engine (safe decision model).

Combines the PAD layers behind the phase-1 ``LivenessDetector`` protocol:

    passive/    texture / spectral / moire / compression signals
    replay/     frame-sequence duplication + timestamp integrity
    injection/  camera-source integrity
    active/     randomized challenge-response (session driven)

DECISION MODEL — the engine NEVER returns "live" because a layer failed:

    timeout                  -> NOT_LIVE   (timed_out=True)
    exception / crash        -> NOT_LIVE
    malformed input          -> NOT_LIVE
    undecodable image        -> NOT_LIVE
    insufficient quality     -> INCONCLUSIVE (never forced either way)
    suspected attack         -> NOT_LIVE
    signals inconclusive     -> INCONCLUSIVE
    clean signals            -> LIVE

``is_live`` is ALWAYS a real Python ``bool``.  The tri-state decision is
carried in ``PadResult.decision`` so callers can distinguish "definitely
an attack" from "cannot decide" without weakening the fail-safe default.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from app.biometric.pad.active import ActiveChallengeManager
from app.biometric.pad.injection import (
    analyze_source_integrity,
    injection_attack_indicators,
)
from app.biometric.pad.passive import PassiveSignals, compute_passive_signals
from app.biometric.pad.replay import (
    ReplaySignals,
    analyze_frame_sequence,
    replay_attack_indicators,
)
from app.biometric.quality.gate import FaceQualityGate
from app.engines.liveness import LivenessResult, PadMethod, PresentationAttack

logger = logging.getLogger("authetec.pad")

MODEL_VERSION = "authetec-pad-multilayer-v2"
PROVIDER_LABEL = "authetec-native-pad"


class PadDecision(str, Enum):
    LIVE = "LIVE"
    NOT_LIVE = "NOT_LIVE"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class PadResult(LivenessResult):
    """LivenessResult + explicit tri-state decision and layer evidence."""

    decision: PadDecision = PadDecision.NOT_LIVE
    layers: Dict[str, Any] = field(default_factory=dict)
    provider: str = PROVIDER_LABEL
    quality_issues: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Contract: is_live is always a real Python bool, never numpy.
        self.is_live = bool(self.is_live)


# ── passive-signal scoring (deterministic, SYNTHETICALLY calibrated) ──
SPOOF_WEIGHT_MOIRE = 0.35
SPOOF_WEIGHT_COMPRESSION = 0.25
SPOOF_WEIGHT_BLUR = 0.25
SPOOF_WEIGHT_HF_ANOMALY = 0.15
BLUR_LAPLACIAN_FLOOR = 15.0
ACCEPT_SPOOF_SCORE = 0.25   # <= this  -> LIVE (clean capture)
REJECT_SPOOF_SCORE = 0.55   # >= this  -> NOT_LIVE (attack-like)
ATTACK_CONFIDENCE_FLOOR = 0.50


def passive_spoof_score(s: PassiveSignals) -> float:
    """Map passive signals to a 0..1 spoof likelihood.

    Deterministic mapping calibrated on the synthetic degradation model
    (see benchmarks/biometric).  NOT validated against a labelled real
    presentation-attack dataset — that is a documented blocker.
    """
    if not s.assessed:
        return 0.5  # unknown -> middle of the INCONCLUSIVE band
    score = 0.0
    score += SPOOF_WEIGHT_MOIRE * min(1.0, s.moire_score)
    score += SPOOF_WEIGHT_COMPRESSION * min(1.0, s.compression_artifacts)
    if s.laplacian_variance < BLUR_LAPLACIAN_FLOOR:
        depth = (BLUR_LAPLACIAN_FLOOR - s.laplacian_variance) / BLUR_LAPLACIAN_FLOOR
        score += SPOOF_WEIGHT_BLUR * min(1.0, max(0.0, depth))
    # Screen re-captures suppress natural high-frequency energy.
    if s.high_freq_ratio < 0.05:
        score += SPOOF_WEIGHT_HF_ANOMALY * (0.05 - s.high_freq_ratio) / 0.05
    return min(1.0, score)


@dataclass
class _LayerInputs:
    image_bytes: bytes
    frames: Sequence[bytes]
    frame_timestamps_s: Optional[Sequence[float]]
    metadata: Optional[Dict[str, Any]]
    challenge: Optional[str]


class MultiLayerPadEngine:
    """Native AUTHeTEC PAD engine behind the LivenessDetector protocol."""

    DEFAULT_TIMEOUT_S = 10.0

    def __init__(
        self,
        secret: Optional[bytes] = None,
        quality_gate: Optional[FaceQualityGate] = None,
        accept_spoof_score: float = ACCEPT_SPOOF_SCORE,
        reject_spoof_score: float = REJECT_SPOOF_SCORE,
    ) -> None:
        self._challenges = ActiveChallengeManager(secret=secret)
        self._quality = quality_gate or FaceQualityGate()
        self._accept = float(accept_spoof_score)
        self._reject = float(reject_spoof_score)

    # ── LivenessDetector protocol ─────────────────────────────────────
    def check(
        self,
        image_bytes: bytes,
        *,
        challenge: Optional[str] = None,
        timeout_s: Optional[float] = None,
        frames: Optional[Sequence[bytes]] = None,
        frame_timestamps_s: Optional[Sequence[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PadResult:
        """Run PAD under a hard time budget (fail-safe on timeout)."""
        t0 = time.perf_counter()
        limit = self.DEFAULT_TIMEOUT_S if timeout_s is None else float(timeout_s)
        if limit <= 0 or not isinstance(image_bytes, (bytes, bytearray)):
            return self._fail(t0, PadDecision.NOT_LIVE,
                              "invalid time budget or payload",
                              timed_out=limit <= 0)

        inputs = _LayerInputs(
            image_bytes=bytes(image_bytes),
            frames=list(frames or []),
            frame_timestamps_s=(
                list(frame_timestamps_s) if frame_timestamps_s else None),
            metadata=metadata,
            challenge=challenge,
        )

        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="authetec-pad")
        try:
            future = pool.submit(self._do_check, inputs)
            done, _ = wait_all([future], limit)
            if not done:
                # Worker released without waiting on exit: a stuck worker
                # can never block the caller past the budget (phase-1 rule).
                pool.shutdown(wait=False)
                return self._timeout_result(t0, limit)
            result = future.result()
            pool.shutdown(wait=False)
            return result
        except Exception as e:  # includes worker exceptions
            logger.debug("PAD worker raised: %s", e)
            pool.shutdown(wait=False)
            return self._fail(
                t0, PadDecision.NOT_LIVE,
                f"pad worker exception: {type(e).__name__}")

    # ── layer orchestration ───────────────────────────────────────────
    def _do_check(self, inp: _LayerInputs) -> PadResult:
        t0 = time.perf_counter()
        if not inp.image_bytes:
            return self._fail(t0, PadDecision.NOT_LIVE, "empty payload")

        attacks: List[PresentationAttack] = []
        signals: List[str] = []
        layers: Dict[str, Any] = {}

        # ── quality gate (decodability + capture suitability) ─────────
        verdict = self._quality.check(inp.image_bytes)
        layers["quality"] = {"accepted": verdict.accepted,
                             "score": verdict.score,
                             "issues": verdict.issues}
        if "undecodable" in verdict.issues:
            return self._fail(t0, PadDecision.NOT_LIVE, "undecodable image")
        if verdict.issues:
            return self._inconclusive(
                t0, f"insufficient quality: {', '.join(verdict.issues)}",
                layers, verdict.issues)

        # ── passive layer ─────────────────────────────────────────────
        passive = compute_passive_signals(inp.image_bytes)
        layers["passive"] = passive.to_dict()
        if not passive.assessed:
            return self._inconclusive(
                t0, "passive layer could not assess the image", layers, [])
        spoof = passive_spoof_score(passive)
        signals.append(f"passive_spoof_score={spoof:.4f}")

        # ── replay layer (frame sequence, optional) ───────────────────
        if len(inp.frames) >= 3:
            replay = analyze_frame_sequence(inp.frames, inp.frame_timestamps_s)
            layers["replay"] = replay.to_dict()
            for name, conf in replay_attack_indicators(replay):
                attacks.append(PresentationAttack(name, conf, "replay"))

        # ── injection layer (source metadata, optional) ───────────────
        if inp.metadata is not None:
            inj = analyze_source_integrity(inp.metadata)
            layers["injection"] = inj.to_dict()
            for name, conf in injection_attack_indicators(inj):
                attacks.append(PresentationAttack(name, conf, "injection"))

        # ── decision ──────────────────────────────────────────────────
        strong = [a for a in attacks if a.confidence >= ATTACK_CONFIDENCE_FLOOR]
        if strong:
            names = sorted({a.indicator for a in strong})
            return self._not_live(
                t0, f"presentation-attack indicators: {', '.join(names)}",
                layers, attacks, signals, spoof_score=0.9)
        if spoof >= self._reject:
            return self._not_live(
                t0, f"passive spoof score {spoof:.4f} >= reject threshold "
                    f"{self._reject:.2f}",
                layers, attacks, signals, spoof_score=spoof)
        if spoof > self._accept:
            return self._inconclusive(
                t0, f"passive spoof score {spoof:.4f} in indeterminate band "
                    f"({self._accept:.2f}, {self._reject:.2f})",
                layers, [], attacks=attacks, spoof=spoof)

        signals.append("all assessed PAD layers clean")
        return PadResult(
            is_live=True,
            confidence=round(max(0.5, 0.95 - spoof), 4),
            method=PadMethod.HYBRID,
            attacks=attacks,
            signals=signals,
            model_version=MODEL_VERSION,
            processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            notes="AUTHeTEC native PAD - synthetic calibration; real-world "
                  "validation pending",
            timed_out=False,
            decision=PadDecision.LIVE,
            layers=layers,
        )

    # ── result helpers ────────────────────────────────────────────────
    def _timeout_result(self, t0: float, limit: float) -> PadResult:
        return PadResult(
            is_live=False, confidence=0.05, method=PadMethod.HYBRID,
            attacks=[PresentationAttack("pad_timeout", 0.5, "system")],
            signals=[f"pad exceeded {limit:.2f}s budget"],
            model_version=MODEL_VERSION,
            processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            notes="PAD timed out - treated as NOT_LIVE (fail-safe)",
            timed_out=True,
            decision=PadDecision.NOT_LIVE,
        )

    def _fail(self, t0: float, decision: PadDecision, reason: str,
              timed_out: bool = False) -> PadResult:
        return PadResult(
            is_live=False, confidence=0.10, method=PadMethod.HYBRID,
            attacks=[PresentationAttack("pad_failure", 0.5, "system", reason)],
            signals=[reason],
            model_version=MODEL_VERSION,
            processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            notes=f"PAD failed safe: {reason}",
            timed_out=timed_out,
            decision=decision,
        )

    def _not_live(self, t0: float, reason: str, layers: Dict[str, Any],
                  attacks: List[PresentationAttack],
                  signals: List[str], spoof_score: float) -> PadResult:
        return PadResult(
            is_live=False,
            confidence=round(min(0.95, 0.5 + spoof_score / 2), 4),
            method=PadMethod.HYBRID, attacks=attacks,
            signals=signals + [reason],
            model_version=MODEL_VERSION,
            processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            notes=f"NOT_LIVE: {reason}",
            timed_out=False, decision=PadDecision.NOT_LIVE, layers=layers,
        )

    def _inconclusive(self, t0: float, reason: str, layers: Dict[str, Any],
                      quality_issues: List[str],
                      attacks: Optional[List[PresentationAttack]] = None,
                      spoof: float = 0.0) -> PadResult:
        return PadResult(
            is_live=False,  # INCONCLUSIVE is never "live"
            confidence=round(max(0.05, 0.35 - spoof), 4),
            method=PadMethod.HYBRID,
            attacks=attacks or [],
            signals=[reason],
            model_version=MODEL_VERSION,
            processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            notes=f"INCONCLUSIVE: {reason}",
            timed_out=False, decision=PadDecision.INCONCLUSIVE,
            layers=layers, quality_issues=list(quality_issues),
        )


def wait_all(futures, timeout_s: float):
    """concurrent.futures.wait wrapper (kept tiny for testability)."""
    from concurrent.futures import wait
    return wait(futures, timeout=timeout_s)


_engine: Optional[MultiLayerPadEngine] = None


def get_pad_engine() -> MultiLayerPadEngine:
    """Process-wide native PAD engine singleton."""
    global _engine
    if _engine is None:
        _engine = MultiLayerPadEngine()
    return _engine


def set_pad_engine(engine: MultiLayerPadEngine) -> None:
    global _engine
    _engine = engine
