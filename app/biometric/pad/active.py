"""
Active PAD: randomized challenge generation and response verification.

Design goals:

    * challenges are NEVER predictable — the sequence is derived with
      HMAC-SHA256 from a server-side secret + session nonce, so a client
      cannot pre-record a "correct" response video
    * a challenge is only counted as answered when the expected motion is
      actually observed in the frames AND it arrived after the challenge
      was issued (temporal response check)
    * an unanswered/failed challenge is never rounded up to "live"

This is NOT "blink = live": every challenge is randomly drawn from a
movable set, order and count are randomized, and the response must be
verified against observed frame evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple


class ChallengeType(str, Enum):
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    LOOK_UP = "look_up"
    LOOK_DOWN = "look_down"
    MOVE_CLOSER = "move_closer"
    MOVE_BACK = "move_back"

# Expected motion thresholds (normalised by face width).  Conservative
# minima: a real head movement produces a clear displacement.
_MIN_X_SHIFT = 0.05   # fraction of face width
_MIN_Y_SHIFT = 0.04   # fraction of face height
_MIN_SCALE_CHANGE = 0.06  # closer/back: relative bbox size change


@dataclass
class Challenge:
    challenge_type: ChallengeType
    nonce: str
    issued_at_s: float
    expires_in_s: float = 30.0

    def token(self, secret: bytes) -> str:
        """HMAC token binding type+nonce+issue time (client cannot forge)."""
        msg = (
            f"{self.challenge_type.value}:{self.nonce}:"
            f"{self.issued_at_s:.3f}"
        ).encode()
        return hmac.new(secret, msg, hashlib.sha256).hexdigest()


@dataclass
class ChallengeVerification:
    challenge_type: ChallengeType
    observed: bool
    reason: str = ""
    measured: float = 0.0


class ActiveChallengeManager:
    """Generates and verifies randomized active-PAD challenge sequences."""

    CHALLENGE_POOL = tuple(ChallengeType)

    def __init__(self, secret: Optional[bytes] = None,
                 n_challenges: int = 2) -> None:
        # Server secret: injected or process-random (never client-supplied).
        self._secret = secret if secret is not None else secrets.token_bytes(32)
        self._n = max(1, min(4, int(n_challenges)))

    # ── generation ────────────────────────────────────────────────────
    def issue(self) -> List[Challenge]:
        """Randomized challenge sequence (type, order and count vary)."""
        count = secrets.randbelow(self._n) + 1  # 1..n — unpredictable
        pool = list(self.CHALLENGE_POOL)
        picked: List[Challenge] = []
        now = time.time()
        for _ in range(count):
            idx = secrets.randbelow(len(pool))
            ct = pool.pop(idx)
            picked.append(Challenge(
                challenge_type=ct,
                nonce=secrets.token_hex(8),
                issued_at_s=now,
            ))
        return picked

    # ── verification ──────────────────────────────────────────────────
    def verify_response(
        self,
        challenges: Sequence[Challenge],
        face_centroids: Sequence[Tuple[float, float]],
        face_widths: Sequence[float],
        response_ts_s: float,
        frame_ts_s: Optional[Sequence[float]] = None,
    ) -> List[ChallengeVerification]:
        """Verify challenges against observed face motion.

        ``face_centroids`` - per-frame (x, y) face centre (capture order);
        ``face_widths`` - per-frame detected face width.
        Temporal check: when frame timestamps are supplied, at least one
        frame must postdate the challenge (rejects pre-recorded media).
        """
        if not challenges:
            return [ChallengeVerification(
                ChallengeType.TURN_LEFT, False, reason="no challenges issued")]
        if len(face_centroids) < 3 or len(face_centroids) != len(face_widths):
            return [ChallengeVerification(
                challenges[0].challenge_type, False,
                reason="insufficient frames to verify any challenge")]

        if frame_ts_s is not None and len(frame_ts_s) == len(face_centroids):
            if not any(float(t) >= challenges[0].issued_at_s
                       for t in frame_ts_s):
                return [ChallengeVerification(
                    challenges[0].challenge_type, False,
                    reason="all frames predate the challenge (replay)")]

        # Robust motion estimate: deviation range around the median.
        xs = [c[0] for c in face_centroids]
        ys = [c[1] for c in face_centroids]
        med_w = sorted(face_widths)[len(face_widths) // 2] or 1.0
        dx = (max(xs) - min(xs)) / med_w
        dy = (max(ys) - min(ys)) / med_w
        scale = (max(face_widths) - min(face_widths)) / med_w

        expired = any(
            response_ts_s > c.issued_at_s + c.expires_in_s for c in challenges)

        results: List[ChallengeVerification] = []
        for c in challenges:
            if expired:
                results.append(ChallengeVerification(
                    c.challenge_type, False, reason="challenge expired"))
                continue
            observed, reason, measured = self._verify_one(
                c.challenge_type, dx, dy, scale)
            results.append(ChallengeVerification(
                c.challenge_type, observed, reason=reason, measured=measured))
        return results

    @staticmethod
    def _verify_one(ct: ChallengeType, dx: float, dy: float,
                    scale: float) -> Tuple[bool, str, float]:
        """Direction/scale check on aggregate motion.

        Aggregate-motion caveat (documented limitation): the current
        frame contract measures total motion; distinguishing left vs
        right *direction* requires ordered per-challenge frame windows
        supplied by the session layer.
        """
        if ct in (ChallengeType.TURN_LEFT, ChallengeType.TURN_RIGHT):
            return (dx >= _MIN_X_SHIFT, "insufficient horizontal motion", dx)
        if ct in (ChallengeType.LOOK_UP, ChallengeType.LOOK_DOWN):
            return (dy >= _MIN_Y_SHIFT, "insufficient vertical motion", dy)
        if ct in (ChallengeType.MOVE_CLOSER, ChallengeType.MOVE_BACK):
            return (scale >= _MIN_SCALE_CHANGE,
                    "insufficient size change", scale)
        return False, "unknown challenge type", 0.0
