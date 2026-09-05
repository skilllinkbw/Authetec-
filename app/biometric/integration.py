"""
Biometric <-> fraud/risk integration.

AUTHeTEC rule: a face match or a "LIVE" PAD verdict is NEVER an approval.
Biometric outputs become *signals* that the existing unified risk engine
aggregates with every other source (document, OCR quality, payment,
device, ...).  This adapter converts native biometric results into the
standard ``EngineResult`` contract without exposing any biometric
content (no images, no embeddings, no raw scores beyond the audited
signal values).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.biometric.pad.engine import MultiLayerPadEngine, PadDecision, PadResult
from app.models.risk import Decision, EngineResult, Signal

logger = logging.getLogger("authetec.biometric.integration")

# The risk engine already reserves a "media" source weight (0.10) for
# presentation/media-integrity signals; PAD is the first producer for it.
PAD_SOURCE = "media"

MODEL_VERSION = "authetec-biometric-adapter-v2"


def pad_result_to_engine_result(
    pad: PadResult,
    *,
    tenant_id: str = "default",
    correlation_id: Optional[str] = None,
) -> EngineResult:
    """Map a native PAD verdict to a fraud-engine signal.

    Mapping (fail-safe by design):
        LIVE          -> low risk contribution, confidence = PAD confidence
        INCONCLUSIVE  -> mid risk (0.50) with LOW confidence -> pushes the
                         unified decision toward REVIEW, never CLEAR
        NOT_LIVE      -> high risk (0.90) with the PAD confidence
        timeout/failure -> mid-high risk (0.60) with LOW confidence

    Signals carry only aggregate numeric values and indicator names --
    never images, embeddings, or per-layer raw image statistics.
    """
    signals: List[Signal] = [
        Signal(name="pad_is_live", value=1.0 if pad.is_live else 0.0, weight=1.0,
               source="pad"),
        Signal(name="pad_decision", value=_decision_code(pad.decision), weight=1.0,
               source="pad"),
        Signal(name="pad_timed_out", value=1.0 if pad.timed_out else 0.0, weight=0.5,
               source="pad"),
    ]
    # Attack indicator names are safe identifiers (no biometric content).
    for a in pad.attacks:
        signals.append(Signal(name=f"pad_attack:{a.indicator}",
                              value=float(a.confidence), weight=1.0,
                              source=f"pad.{a.method}"))

    if pad.decision is PadDecision.LIVE:
        risk, confidence = 0.05, max(0.5, pad.confidence)
        decision = Decision.CLEAR
        reasons = ["PAD: genuine presentation (native engine)"]
    elif pad.decision is PadDecision.INCONCLUSIVE:
        risk, confidence = 0.50, 0.15
        decision = Decision.REVIEW
        reasons = ["PAD: inconclusive - human review required"]
    elif pad.timed_out:
        risk, confidence = 0.60, 0.20
        decision = Decision.REVIEW
        reasons = ["PAD: timed out - fail-safe review required"]
    else:
        risk = 0.90
        confidence = max(0.5, pad.confidence)
        decision = Decision.BLOCK
        reasons = ["PAD: presentation attack indicators detected"]
        reasons.extend(sorted({a.indicator for a in pad.attacks}) or
                       ["pad_not_live"])

    reasons.extend(pad.signals[:5])  # bounded; textual, no biometric content

    return EngineResult(
        engine=PAD_SOURCE,
        risk_score=risk,
        confidence=confidence,
        decision=decision,
        signals=signals,
        reasons=reasons,
        evidence=[],  # never inline biometric evidence
        model_version=pad.model_version or MODEL_VERSION,
        processing_time_ms=pad.processing_time_ms,
        extra={
            "provider": pad.provider,
            "pad_decision": pad.decision.value,
            "timed_out": pad.timed_out,
            "quality_issues": list(pad.quality_issues),
            "correlation_id": correlation_id,
            # NOTE: layers dict intentionally omitted - may contain raw
            # image statistics that are unnecessary for the risk decision.
        },
    )


def _decision_code(d: PadDecision) -> float:
    return {"LIVE": 0.0, "INCONCLUSIVE": 0.5, "NOT_LIVE": 1.0}[d.value]


# ── provider bootstrap ────────────────────────────────────────────────
# Provider-independent wiring: the PAD provider behind the phase-1
# LivenessDetector protocol is selected by configuration, never
# hard-coded.  Default stays the phase-1 deterministic fallback
# (NON_PRODUCTION_FALLBACK); "native" selects the AUTHeTEC PAD engine.

PAD_PROVIDER_ENV = "AUTHETEC_PAD_PROVIDER"
KNOWN_PAD_PROVIDERS = ("deterministic", "native")


def bootstrap_pad_provider() -> str:
    """Wire the configured PAD provider into the global liveness slot.

    Returns the active provider label.  Unknown values fail safe to the
    deterministic fallback (and are logged), never to a silent default
    change.
    """
    import os

    from app.biometric.pad.engine import get_pad_engine
    from app.engines.liveness import set_liveness_detector

    provider = os.getenv(PAD_PROVIDER_ENV, "deterministic").strip().lower()
    if provider == "native":
        set_liveness_detector(get_pad_engine())
        logger.info("PAD provider: AUTHeTEC native multi-layer engine")
        return "native"
    if provider != "deterministic":
        logger.warning(
            "Unknown %s=%r - falling back to deterministic PAD", PAD_PROVIDER_ENV, provider)
    return "deterministic"


FACE_PROVIDER_ENV = "AUTHETEC_FACE_PROVIDER"
KNOWN_FACE_PROVIDERS = ("deterministic", "native")


def bootstrap_face_provider() -> str:
    """Wire the configured face-verification provider into the engine.

    "native" selects the AUTHeTEC stack (YuNet detection -> landmark
    alignment -> quality gate -> SFace embeddings) *only when the models
    are installed*; if any model is missing the provider fails safe to the
    deterministic NON_PRODUCTION_FALLBACK with a clear warning, never to a
    half-configured pipeline.

    Returns the active provider label.
    """
    import os

    from app.engines.face import FaceVerificationEngine, set_face_engine
    from app.biometric.alignment.landmarks import LandmarkAligner
    from app.biometric.detection.yunet import YuNetFaceDetector
    from app.biometric.recognition.embedders import build_embedder

    provider = os.getenv(FACE_PROVIDER_ENV, "deterministic").strip().lower()
    if provider != "native":
        if provider != "deterministic":
            logger.warning(
                "Unknown %s=%r - using deterministic face provider",
                FACE_PROVIDER_ENV, provider)
        return "deterministic"

    detector = YuNetFaceDetector()
    if not detector.available():
        logger.warning(
            "native face provider requested but YuNet model is missing - "
            "install models per docs/biometric_model_setup.md; using "
            "deterministic fallback (NON_PRODUCTION_FALLBACK)")
        return "deterministic"
    embedder = build_embedder()
    if embedder is None or not getattr(embedder, "available", lambda: True)():
        logger.warning(
            "native face provider requested but no embedding backend is "
            "available - install models per docs/biometric_model_setup.md; "
            "using deterministic fallback (NON_PRODUCTION_FALLBACK)")
        return "deterministic"

    engine = FaceVerificationEngine(
        embedder=embedder,
        detector=detector,
        aligner=LandmarkAligner(),
    )
    set_face_engine(engine)
    logger.info("Face provider: AUTHeTEC native (YuNet + SFace, "
                "model_version=%s)", embedder.model_version)
    return "native"


