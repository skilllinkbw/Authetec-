"""AUTHeTEC face recognition: embeddings, matcher, calibration."""

from app.biometric.recognition.embeddings import (
    EmbeddingValidator,
    cosine_similarity_secure,
)
from app.biometric.recognition.matcher import (
    FaceMatcher,
    MatchDecision,
    MatchOutcome,
)
from app.biometric.recognition.calibration import (
    CalibrationResult,
    calibrate_thresholds,
    compute_eer,
)
from app.biometric.recognition.sface import (
    SFaceFaceEmbedder,
    default_sface_path,
)
from app.biometric.recognition.deterministic_embedder import (
    DeterministicFaceEmbedder,
)
from app.biometric.recognition.embedders import build_embedder

__all__ = [
    "EmbeddingValidator",
    "cosine_similarity_secure",
    "FaceMatcher",
    "MatchDecision",
    "MatchOutcome",
    "CalibrationResult",
    "calibrate_thresholds",
    "compute_eer",
    "SFaceFaceEmbedder",
    "default_sface_path",
    "DeterministicFaceEmbedder",
    "build_embedder",
]