"""
AUTHeTEC Native Biometric Engine
================================

Provider-independent biometric stack that implements the AUTHeTEC phase-1
interfaces (``FaceDetector``, ``FaceAligner``, ``FaceEmbedder``,
``LivenessDetector``) with self-hosted, open-source based components.

Architecture:

    biometric/
        detection/    face detection (YuNet candidate + Haar fallback)
        alignment/    deterministic landmark-based similarity alignment
        recognition/  embeddings, matcher, threshold calibration
        pad/          multi-layer presentation-attack detection
        quality/      face quality gate
        security/     numerical hardening + model integrity
        evaluation/   repeatable machine-readable benchmarks
        models/       model registry / integrity manifest

Every component exposes an explicit ``is_production_grade`` flag and a
``provider`` label so no synthetic or fallback signal can be mistaken for
a production biometric verdict.

Only technology that is legally permitted for commercial deployment is
used in production paths; anything licence-ambiguous is restricted to the
benchmark harness (see ``BIOMETRIC_LICENSE_MANIFEST.json``).
"""

from __future__ import annotations

__version__ = "2.0.0"

from app.biometric.integration import (  # noqa: E402,F401
    FACE_PROVIDER_ENV,
    PAD_PROVIDER_ENV,
    bootstrap_face_provider,
    bootstrap_pad_provider,
    pad_result_to_engine_result,
)
from app.biometric.pad.engine import (  # noqa: E402,F401
    MultiLayerPadEngine,
    PadDecision,
    PadResult,
    get_pad_engine,
    set_pad_engine,
)
