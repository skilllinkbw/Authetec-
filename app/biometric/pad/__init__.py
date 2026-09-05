"""AUTHeTEC PAD / liveness stack (multi-layer presentation-attack detection)."""

from app.biometric.pad.active import (
    ActiveChallengeManager,
    Challenge,
    ChallengeType,
    ChallengeVerification,
)
from app.biometric.pad.engine import (
    ACCEPT_SPOOF_SCORE,
    REJECT_SPOOF_SCORE,
    MultiLayerPadEngine,
    PadDecision,
    PadResult,
    get_pad_engine,
    passive_spoof_score,
    set_pad_engine,
)
from app.biometric.pad.injection import (
    InjectionSignals,
    analyze_source_integrity,
    injection_attack_indicators,
)
from app.biometric.pad.passive import PassiveSignals, compute_passive_signals
from app.biometric.pad.replay import (
    ReplaySignals,
    analyze_frame_sequence,
    replay_attack_indicators,
)

__all__ = [
    "ACCEPT_SPOOF_SCORE",
    "REJECT_SPOOF_SCORE",
    "ActiveChallengeManager",
    "Challenge",
    "ChallengeType",
    "ChallengeVerification",
    "InjectionSignals",
    "MultiLayerPadEngine",
    "PadDecision",
    "PadResult",
    "PassiveSignals",
    "ReplaySignals",
    "analyze_frame_sequence",
    "analyze_source_integrity",
    "compute_passive_signals",
    "get_pad_engine",
    "injection_attack_indicators",
    "passive_spoof_score",
    "replay_attack_indicators",
    "set_pad_engine",
]
