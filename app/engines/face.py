"""
Face Verification Engine
========================

Face matching with explicit separation of the three concerns that must
never be conflated:

    1. Face SIMILARITY      — is it the same face?
    2. LIVENESS             — is a live person present? (anti-spoofing)
    3. IDENTITY CONSISTENCY — does the face agree with the declared
                               identity / identity document?

A similarity score alone is never accepted as proof of identity: a failed
or absent liveness result degrades the decision, and identity consistency
contributes its own explainable signal.

Embedders are pluggable.  The bundled :class:`DeterministicFaceEmbedder`
is a lightweight, fully deterministic content projector intended for
development, testing and the benchmark harness.  It is **NOT** a
production biometric model; production deployments must inject a real
embedding model (e.g. an InsightFace-style embedder) via the
``FaceEmbedder`` protocol.  Benchmark numbers produced with the
deterministic embedder are SYNTHETIC and are labelled as such — they are
never presented as real-world identity-verification accuracy.

No raw biometric data (images or embeddings) is stored on the result;
only derived, non-invertible metrics are reported.
"""

from __future__ import annotations

import base64
import binascii
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

import numpy as np

from app.core.config import get_settings
from app.models.risk import Decision, EngineResult, Signal

logger = logging.getLogger("authetec.face")

MODEL_VERSION = "face-cosine-deterministic-embedder-v1"

# Cosine-similarity threshold above which two embeddings are considered a
# match.  Configurable via AUTHETEC_FACE_MATCH_THRESHOLD.  The default was
# chosen on SYNTHETIC data only; it MUST be re-calibrated on real data
# before production use.
DEFAULT_MATCH_THRESHOLD = 0.62

# Contribution weights of the three concerns to the final risk score.
W_SIMILARITY = 0.60
W_LIVENESS = 0.25
W_IDENTITY = 0.15


class FaceEmbedder(Protocol):
    """Protocol for pluggable face embedding models."""

    def embed(self, image_bytes: bytes) -> Optional[np.ndarray]:
        """Return a unit-normalised embedding vector, or None on failure."""
        ...


def _b64_decode(payload: str) -> bytes:
    """Strict base64 decoding (rejects empty / malformed payloads)."""
    payload = payload.strip()
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")
    if not payload:
        raise ValueError("image payload is empty")
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"invalid base64 image payload: {e}") from e


def _to_gray(image_bytes: bytes) -> Optional[np.ndarray]:
    """Decode image bytes to a grayscale array; None if undecodable."""
    try:
        import cv2
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None


class DeterministicFaceEmbedder:
    """Deterministic content-based face embedding (development / harness).

    Pipeline: decode -> grayscale -> resize 32x32 -> brightness-normalise
    -> flatten -> fixed random projection to 64-d -> L2 normalise.

    The projection matrix is fixed (seed 42) so the same image always
    produces the same embedding and similar images produce similar
    embeddings — reproducible across runs and machines.
    """

    DIM = 64
    CANVAS = 32

    def __init__(self) -> None:
        # Fixed projection matrix — part of the "model", never re-randomised.
        rng = np.random.default_rng(42)
        self._projection = rng.standard_normal(
            (self.CANVAS * self.CANVAS, self.DIM)
        ).astype(np.float32)
        self._projection /= np.linalg.norm(self._projection, axis=0, keepdims=True)

    def embed(self, image_bytes: bytes) -> Optional[np.ndarray]:
        gray = _to_gray(image_bytes)
        if gray is None or gray.size < 64:
            return None
        try:
            import cv2
            resized = cv2.resize(gray, (self.CANVAS, self.CANVAS)).astype(np.float32)
        except Exception:
            return None
        flat = resized.reshape(-1).astype(np.float32)
        # Brightness/contrast normalisation: zero mean, unit variance.
        std = float(flat.std())
        if std < 1e-6:
            flat = flat - float(flat.mean())
        else:
            flat = (flat - float(flat.mean())) / std
        emb = flat @ self._projection
        norm = float(np.linalg.norm(emb))
        if norm < 1e-9:
            return None
        return (emb / norm).astype(np.float32)


@dataclass
class LivenessCheck:
    """One presentation-attack-detection check outcome."""

    name: str
    passed: bool
    score: float = 1.0  # 0..1 confidence the check succeeded

    def __post_init__(self) -> None:
        self.score = max(0.0, min(1.0, float(self.score)))


@dataclass
class FaceMatchInput:
    """Inputs for one face verification.  Embeddings may be supplied
    directly (e.g. from a real model) or derived from base64 images via
    the configured embedder."""

    reference_embedding: Optional[np.ndarray] = None
    candidate_embedding: Optional[np.ndarray] = None
    reference_image_b64: str = ""
    candidate_image_b64: str = ""
    liveness_checks: List[LivenessCheck] = field(default_factory=list)
    #: True/False from an external identity cross-check; None = unknown.
    declared_identity_match: Optional[bool] = None


def cosine_similarity(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> Optional[float]:
    """Cosine similarity in [-1, 1]; None if either vector is invalid."""
    if a is None or b is None:
        return None
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    if a.size == 0 or b.size == 0 or a.shape != b.shape:
        return None
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-9 or nb < 1e-9:
        return None
    return float(np.dot(a, b) / (na * nb))


class FaceVerificationEngine:
    """Verifies a candidate face against a reference face.

    Decision policy (fail-safe):
      * Missing/invalid embeddings -> REVIEW, confidence <= 0.15
      * Dimension mismatch         -> REVIEW, confidence <= 0.15
      * Any failed liveness check  -> at least REVIEW (policy floor)
      * No liveness information    -> decision confidence penalised
      * Declared identity mismatch -> strong risk contribution
    """

    def __init__(self, embedder: Optional[FaceEmbedder] = None) -> None:
        self._settings = get_settings()
        self._embedder = embedder or DeterministicFaceEmbedder()
        self._threshold = self._read_threshold()

    def _read_threshold(self) -> float:
        import os
        try:
            return float(os.getenv("AUTHETEC_FACE_MATCH_THRESHOLD",
                                   str(DEFAULT_MATCH_THRESHOLD)))
        except ValueError:
            return DEFAULT_MATCH_THRESHOLD

    # ── risk components ──────────────────────────────────────────────

    @staticmethod
    def _similarity_risk(sim: float, threshold: float) -> float:
        """0 when sim >= threshold, rising linearly to 1 at sim <= -0.2."""
        if sim >= threshold:
            return 0.0
        span = threshold + 0.2
        return max(0.0, min(1.0, (threshold - sim) / max(span, 1e-6)))

    @staticmethod
    def _liveness_risk(checks: List[LivenessCheck]):
        if not checks:
            return 0.25, ["no_liveness_signals_provided"]
        failed = [c.name for c in checks if not c.passed]
        risk = len(failed) / len(checks)
        return risk, [f"liveness_failed:{n}" for n in failed]

    def verify(self, match: FaceMatchInput, *, tenant_id: str = "default") -> EngineResult:
        t0 = time.perf_counter()
        ref, cand = match.reference_embedding, match.candidate_embedding

        # Resolve embeddings from images when not supplied directly.
        if ref is None and match.reference_image_b64:
            ref = self._safe_embed(match.reference_image_b64, "reference")
        if cand is None and match.candidate_image_b64:
            cand = self._safe_embed(match.candidate_image_b64, "candidate")

        signals: List[Signal] = []

        sim = cosine_similarity(ref, cand)
        if sim is None:
            return self._fail_safe(
                "Face embeddings unavailable or invalid; verification could "
                "not be performed (fail-safe REVIEW).", t0, tenant_id,
            )

        sim_risk = self._similarity_risk(sim, self._threshold)
        is_match = sim >= self._threshold
        reasons = [
            f"face_similarity={sim:.4f} vs threshold={self._threshold:.2f} "
            f"-> {'match' if is_match else 'no_match'}"
        ]
        signals.append(Signal(
            name="face_similarity", value=round(sim, 4), weight=W_SIMILARITY,
            reason="cosine similarity of face embeddings", source="face",
        ))

        liv_risk, failed_names = self._liveness_risk(match.liveness_checks)
        if failed_names and failed_names[0] == "no_liveness_signals_provided":
            reasons.append("no liveness signals provided; "
                           "presentation-attack status unknown")
        elif failed_names:
            reasons.append("liveness checks failed: " + ", ".join(failed_names))
        else:
            reasons.append(f"all {len(match.liveness_checks)} liveness checks passed")
        signals.append(Signal(
            name="liveness_risk", value=round(liv_risk, 4), weight=W_LIVENESS,
            reason=f"{len(match.liveness_checks)} check(s) evaluated", source="face",
        ))

        if match.declared_identity_match is True:
            id_risk = 0.0
            reasons.append("declared identity consistent with reference identity")
        elif match.declared_identity_match is False:
            id_risk = 1.0
            reasons.append("declared identity does NOT match reference identity")
        else:
            id_risk = 0.20
            reasons.append("identity cross-check not performed; neutral risk applied")
        signals.append(Signal(
            name="identity_consistency_risk", value=round(id_risk, 4),
            weight=W_IDENTITY, reason="declared identity vs reference identity",
            source="face",
        ))

        risk = W_SIMILARITY * sim_risk + W_LIVENESS * liv_risk + W_IDENTITY * id_risk

        # Policy floors: certain evidence can never be traded away by a
        # good similarity score.
        decision = self._decide(risk)
        liv_known_failure = bool(failed_names) and \
            failed_names[0] != "no_liveness_signals_provided"
        floor_reason: Optional[str] = None
        if liv_known_failure and decision == Decision.CLEAR:
            decision = Decision.REVIEW
            floor_reason = "failed liveness forces at least REVIEW"
        elif match.declared_identity_match is False and decision == Decision.CLEAR:
            decision = Decision.REVIEW
            floor_reason = "declared identity mismatch forces at least REVIEW"
        if floor_reason:
            reasons.append(f"policy floor: {floor_reason}")

        confidence = self._confidence(sim, is_match, match.liveness_checks,
                                      match.declared_identity_match)

        elapsed = (time.perf_counter() - t0) * 1000
        result = EngineResult(
            engine="face_verification",
            risk_score=round(min(1.0, max(0.0, risk)), 4),
            confidence=round(confidence, 4),
            decision=decision,
            signals=signals,
            reasons=reasons,
            evidence=[],  # raw biometric data is never attached to results
            model_version=MODEL_VERSION,
            processing_time_ms=round(elapsed, 2),
            extra={
                "similarity": round(sim, 4),
                "match_threshold": self._threshold,
                "liveness_failed": failed_names,
                "identity_match_declared": match.declared_identity_match,
                # NOTE: no image bytes or raw embeddings are included here.
            },
        )
        logger.info("face verify tenant=%s decision=%s sim=%.3f risk=%.3f in %.1fms",
                    tenant_id, decision.value, sim, result.risk_score, elapsed)
        return result

    def _safe_embed(self, b64: str, which: str) -> Optional[np.ndarray]:
        try:
            emb = self._embedder.embed(_b64_decode(b64))
        except ValueError as e:
            logger.debug("face embed failed (%s): %s", which, e)
            return None
        except Exception as e:  # embedder failure must never crash the API
            logger.debug("face embedder error (%s): %s", which, e)
            return None
        return emb

    def _fail_safe(self, reason: str, t0: float, tenant_id: str) -> EngineResult:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.warning("face verification fail-safe tenant=%s: %s", tenant_id, reason)
        return EngineResult(
            engine="face_verification",
            risk_score=0.5,
            confidence=0.10,
            decision=Decision.REVIEW,
            signals=[],
            reasons=[reason, "fail-safe: human review required"],
            evidence=[],
            model_version=MODEL_VERSION,
            processing_time_ms=round(elapsed, 2),
            extra={"fail_safe": True},
        )

    def _decide(self, risk: float) -> Decision:
        if risk < self._settings.risk_clear_threshold:
            return Decision.CLEAR
        if risk < self._settings.risk_review_threshold:
            return Decision.REVIEW
        return Decision.BLOCK

    @staticmethod
    def _confidence(sim: float, is_match: bool, checks: List[LivenessCheck],
                    identity: Optional[bool]) -> float:
        """Confidence in the decision, penalised by missing evidence."""
        conf = 0.75 if is_match else 0.80
        # Distance from the threshold sharpens confidence.
        conf = min(0.97, conf + min(0.15, abs(sim - DEFAULT_MATCH_THRESHOLD)))
        if not checks:
            conf -= 0.30  # unknown presentation-attack status
        else:
            conf += 0.05
        if identity is None:
            conf -= 0.10  # identity cross-check missing
        return max(0.10, min(0.99, conf))
