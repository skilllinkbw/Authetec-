"""Unit tests for the face verification engine.

Covers: genuine vs impostor separation, threshold behaviour, liveness /
identity separation, fail-safe behaviour on invalid input, determinism,
and the no-biometric-data-in-output policy.
"""

from __future__ import annotations

import base64

import numpy as np
import pytest

from app.engines.face import (
    DEFAULT_MATCH_THRESHOLD,
    DeterministicFaceEmbedder,
    FaceMatchInput,
    FaceVerificationEngine,
    LivenessCheck,
    cosine_similarity,
)
from app.models.risk import Decision


# ── synthetic face image helpers (deterministic, cv2-drawn) ─────────────

def _encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _face_image(seed: int, size: int = 96, variant: int = 0) -> bytes:
    """A deterministic synthetic 'face' pattern.

    Geometry (position/size of facial structure) is derived from the seed,
    so different seeds produce genuinely different 'identities'.  variant
    applies only photometric/micro-geometric perturbations that leave the
    structure recognisably the same (like two photos of the same person).
    """
    import cv2
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, size=(size, size), dtype=np.uint8)
    img = cv2.GaussianBlur(img, (5, 5), 0)
    # Seed-dependent facial structure: different seeds = different identities.
    cx, cy = (int(v) for v in rng.integers(size // 3, 2 * size // 3, 2))
    r = int(rng.integers(size // 6, size // 3))
    cv2.circle(img, (cx, cy), r, 255, 3)
    cv2.circle(img, (cx - r // 2, cy - r // 3), max(2, r // 6), 255, -1)
    cv2.circle(img, (cx + r // 2, cy - r // 3), max(2, r // 6), 255, -1)
    cv2.line(img, (cx - r // 2, cy + r // 3), (cx + r // 2, cy + r // 3), 255, 2)
    if variant:
        # Photometric shift + 1px translation: same identity, new capture.
        img = cv2.convertScaleAbs(img, alpha=1.0 + 0.05 * variant,
                                  beta=3.0 * variant)
        img = np.roll(img, shift=variant, axis=1)
    ok, encoded = cv2.imencode(".png", img)
    assert ok
    return encoded.tobytes()


@pytest.fixture()
def engine() -> FaceVerificationEngine:
    return FaceVerificationEngine()


def _match(**kwargs) -> FaceMatchInput:
    # Tests may pass raw image bytes; the API contract uses base64 strings.
    for key in ("reference_image_b64", "candidate_image_b64"):
        if isinstance(kwargs.get(key), bytes):
            kwargs[key] = _encode_b64(kwargs[key])
    return FaceMatchInput(**kwargs)


# ── similarity separation ────────────────────────────────────────────────

def test_identical_image_is_strong_match(engine):
    img = _face_image(seed=1)
    result = engine.verify(_match(reference_image_b64=img,
                                  candidate_image_b64=img))
    assert result.extra["similarity"] >= DEFAULT_MATCH_THRESHOLD
    assert result.decision == Decision.CLEAR


def test_genuine_variant_scores_higher_than_impostor(engine):
    ref = _face_image(seed=7)
    genuine = _face_image(seed=7, variant=2)
    impostor = _face_image(seed=99)

    r_genuine = engine.verify(_match(reference_image_b64=ref,
                                     candidate_image_b64=genuine))
    r_impostor = engine.verify(_match(reference_image_b64=ref,
                                      candidate_image_b64=impostor))
    assert r_genuine.extra["similarity"] > r_impostor.extra["similarity"]
    assert r_genuine.risk_score < r_impostor.risk_score


def test_impostor_never_clears(engine):
    ref = _face_image(seed=3)
    impostor = _face_image(seed=555)
    result = engine.verify(_match(reference_image_b64=ref,
                                  candidate_image_b64=impostor))
    assert result.decision in (Decision.REVIEW, Decision.BLOCK)


# ── liveness / identity separation ──────────────────────────────────────

def test_failed_liveness_raises_risk_and_blocks_clear(engine):
    img = _face_image(seed=11)
    base = engine.verify(_match(reference_image_b64=img,
                                candidate_image_b64=img))
    with_liveness_fail = engine.verify(_match(
        reference_image_b64=img, candidate_image_b64=img,
        liveness_checks=[LivenessCheck(name="blink", passed=False, score=0.1)],
    ))
    assert with_liveness_fail.risk_score > base.risk_score
    assert with_liveness_fail.decision != Decision.CLEAR
    assert any(s.name == "liveness_risk" for s in with_liveness_fail.signals)


def test_passing_liveness_improves_confidence(engine):
    img = _face_image(seed=13)
    without_checks = engine.verify(_match(reference_image_b64=img,
                                          candidate_image_b64=img))
    with_checks = engine.verify(_match(
        reference_image_b64=img, candidate_image_b64=img,
        liveness_checks=[
            LivenessCheck(name="blink", passed=True),
            LivenessCheck(name="head_turn", passed=True),
        ],
    ))
    assert with_checks.confidence > without_checks.confidence


def test_declared_identity_mismatch_adds_risk(engine):
    img = _face_image(seed=21)
    consistent = engine.verify(_match(reference_image_b64=img,
                                      candidate_image_b64=img,
                                      declared_identity_match=True))
    mismatch = engine.verify(_match(reference_image_b64=img,
                                    candidate_image_b64=img,
                                    declared_identity_match=False))
    assert mismatch.risk_score > consistent.risk_score
    assert mismatch.decision != Decision.CLEAR


# ── failure injection / fail-safe ────────────────────────────────────────

def test_missing_embeddings_fail_safe(engine):
    result = engine.verify(_match())
    assert result.decision == Decision.REVIEW
    assert result.confidence <= 0.15
    assert result.extra.get("fail_safe") is True


def test_garbage_image_fails_safe(engine):
    ref_b64 = _encode_b64(b"not-an-image-at-all-xyz")
    cand_b64 = _encode_b64(_face_image(seed=5))
    result = engine.verify(_match(reference_image_b64=ref_b64,
                                  candidate_image_b64=cand_b64))
    assert result.decision == Decision.REVIEW
    assert result.confidence <= 0.15


def test_dimension_mismatch_fails_safe():
    ref = np.ones(64, dtype=np.float32)
    cand = np.ones(32, dtype=np.float32)
    result = FaceVerificationEngine().verify(
        _match(reference_embedding=ref, candidate_embedding=cand))
    assert result.decision == Decision.REVIEW
    assert cosine_similarity(ref, cand) is None


def test_embedder_never_crashes_on_random_bytes(engine):
    for blob in (b"", b"\x00" * 32, b"MZ" + b"\x00" * 100, b"\xff\xd8\xffnotreally"):
        result = engine.verify(_match(
            reference_image_b64=_encode_b64(blob),
            candidate_image_b64=_encode_b64(_face_image(seed=2)),
        ))
        assert result.decision == Decision.REVIEW
        assert 0.0 <= result.risk_score <= 1.0


# ── determinism & policy invariants ─────────────────────────────────────

def test_verification_is_deterministic(engine):
    img_a, img_b = _face_image(seed=31), _face_image(seed=31, variant=1)
    r1 = engine.verify(_match(reference_image_b64=img_a,
                              candidate_image_b64=img_b))
    r2 = engine.verify(_match(reference_image_b64=img_a,
                              candidate_image_b64=img_b))
    assert r1.risk_score == r2.risk_score
    assert r1.decision == r2.decision
    assert r1.extra["similarity"] == r2.extra["similarity"]


def test_embedding_is_deterministic_and_normalised():
    emb = DeterministicFaceEmbedder()
    e1 = emb.embed(_face_image(seed=42))
    e2 = emb.embed(_face_image(seed=42))
    assert e1 is not None and e1.shape == (emb.DIM,)
    assert np.allclose(e1, e2)
    assert abs(float(np.linalg.norm(e1)) - 1.0) < 1e-5


def test_no_raw_biometric_data_in_output(engine):
    img = _face_image(seed=77)
    img_b64 = _encode_b64(img)
    result = engine.verify(_match(reference_image_b64=img_b64,
                                  candidate_image_b64=img_b64))
    serialized = repr(result.to_dict())
    # Raw image bytes or their base64 must never leak into the result.
    assert img_b64[:40] not in serialized
    assert _encode_b64(img[:20]) not in serialized
