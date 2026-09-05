"""Unit tests for the AUTHeTEC native multi-layer PAD engine.

Covers (master-build section 20 - PAD):
    genuine pass, photo/replay/screen indicators, timeout, provider
    exception, malformed sequence, low quality, attack-like input and
    the safe-decision contract (never LIVE on failure).
All fixtures are SYNTHETIC (cv2-drawn) - no real biometric material.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.biometric.pad import (
    ActiveChallengeManager,
    ChallengeType,
    MultiLayerPadEngine,
    PadDecision,
    analyze_frame_sequence,
    analyze_source_integrity,
    compute_passive_signals,
    get_pad_engine,
    injection_attack_indicators,
    passive_spoof_score,
    replay_attack_indicators,
    set_pad_engine,
)


# ── synthetic image helpers ──────────────────────────────────────────

def _face_image(seed: int = 0, blur: bool = False, quality: int = 95,
                h: int = 240, w: int = 240) -> bytes:
    """Deterministic synthetic 'face-like' photo (circles + texture)."""
    import cv2

    rng = np.random.default_rng(seed)
    im = np.full((h, w, 3), 128, np.uint8)
    cv2.circle(im, (w // 2, h // 2), 60, (200, 200, 200), -1)
    cv2.circle(im, (w // 2 - 20, h // 2 - 15), 6, (40, 40, 40), -1)
    cv2.circle(im, (w // 2 + 20, h // 2 - 15), 6, (40, 40, 40), -1)
    for _ in range(400):
        cv2.circle(im, (int(rng.integers(0, w)), int(rng.integers(0, h))), 1,
                   (int(rng.integers(60, 200)),) * 3, -1)
    if blur:
        im = cv2.GaussianBlur(im, (31, 31), 9)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return buf.tobytes()


def _moving_frames(n: int = 6, seed: int = 10) -> list:
    """Frames whose perceptual hashes differ (distinct captures).

    Varies face position, size, lighting and noise so each frame produces
    a distinct aHash - simulating a genuine capture sequence where the
    user moves naturally between frames.
    """
    import cv2

    frames = []
    for i in range(n):
        rng = np.random.default_rng(seed + i * 7)
        h, w = 240, 240
        # Vary base brightness to simulate lighting changes.
        base = 110 + i * 8
        im = np.full((h, w, 3), base, np.uint8)
        # Vary face position and size to produce distinct aHashes.
        cx = w // 2 + int(rng.integers(-30, 30))
        cy = h // 2 + int(rng.integers(-30, 30))
        radius = 50 + i * 3
        cv2.circle(im, (cx, cy), radius, (200, 200, 200), -1)
        cv2.circle(im, (cx - 18, cy - 12), 6, (40, 40, 40), -1)
        cv2.circle(im, (cx + 18, cy - 12), 6, (40, 40, 40), -1)
        for _ in range(300):
            cv2.circle(im, (int(rng.integers(0, w)), int(rng.integers(0, h))),
                       1, (int(rng.integers(60, 200)),) * 3, -1)
        ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 92])
        assert ok
        frames.append(buf.tobytes())
    return frames


@pytest.fixture()
def engine():
    return MultiLayerPadEngine(secret=b"test-secret")


@pytest.fixture()
def global_engine_guard():
    original = get_pad_engine()
    yield
    set_pad_engine(original)


# ── passive layer ────────────────────────────────────────────────────

class TestPassiveLayer:
    def test_clean_image_scores_low(self):
        s = compute_passive_signals(_face_image())
        assert s.assessed is True
        assert passive_spoof_score(s) < 0.25

    def test_blurred_image_raises_spoof_score(self):
        clean = passive_spoof_score(compute_passive_signals(_face_image()))
        blurred = passive_spoof_score(
            compute_passive_signals(_face_image(blur=True, quality=40)))
        assert blurred > clean

    def test_undecodable_image_not_assessed(self):
        s = compute_passive_signals(b"not an image")
        assert s.assessed is False
        # Unknown -> middle of the band, never zero.
        assert passive_spoof_score(s) == 0.5


# ── replay layer ─────────────────────────────────────────────────────

class TestReplayLayer:
    def test_duplicated_frames_flagged(self):
        frames = [_face_image(seed=3)] * 5
        s = analyze_frame_sequence(frames, [0, 0.1, 0.2, 0.3, 0.4])
        assert s.duplicate_pairs == 10
        assert s.near_duplicate_ratio == 1.0
        names = {n for n, _ in replay_attack_indicators(s)}
        assert "replay.duplicate_frames" in names
        assert "replay.near_duplicate_sequence" in names

    def test_perfect_timestamp_regularity_flagged(self):
        s = analyze_frame_sequence(_moving_frames(6),
                                   [0, 0.1, 0.2, 0.3, 0.4, 0.5])
        assert s.perfect_regularity is True
        assert ("replay.perfect_frame_regularity", 0.60) in \
            replay_attack_indicators(s)

    def test_timestamp_inversion_flagged(self):
        s = analyze_frame_sequence(_moving_frames(5),
                                   [0.4, 0.3, 0.2, 0.1, 0.0])
        assert s.timestamp_inversions > 0
        assert any(n == "replay.timestamp_inversion"
                   for n, _ in replay_attack_indicators(s))

    def test_genuine_jittery_sequence_not_flagged(self):
        s = analyze_frame_sequence(
            _moving_frames(6), [0.0, 0.041, 0.082, 0.15, 0.219, 0.292])
        assert replay_attack_indicators(s) == []

    def test_short_sequence_not_assessed(self):
        s = analyze_frame_sequence([_face_image()] * 2, [0.0, 0.1])
        assert s.assessed is False
        assert replay_attack_indicators(s) == []


# ── injection layer ──────────────────────────────────────────────────

class TestInjectionLayer:
    def test_virtual_camera_label_detected(self):
        s = analyze_source_integrity({"device_label": "OBS Virtual Camera"})
        assert ("injection.virtual_camera_device", 0.9) in \
            injection_attack_indicators(s)

    def test_clean_metadata_clean(self):
        s = analyze_source_integrity({"device_label": "Front Camera",
                                      "platform": "Android"})
        assert injection_attack_indicators(s) == []

    def test_deterministic(self):
        meta = {"device_label": "ManyCam"}
        a = injection_attack_indicators(analyze_source_integrity(meta))
        b = injection_attack_indicators(analyze_source_integrity(meta))
        assert a == b


# ── active challenges ────────────────────────────────────────────────

class TestActiveChallenges:
    def test_challenges_are_randomized(self):
        m = ActiveChallengeManager(secret=b"k", n_challenges=3)
        seqs = {tuple(c.challenge_type for c in m.issue()) for _ in range(12)}
        # Randomised type+order+count: a fixed predictable challenge
        # sequence would collapse to a single observed variant.
        assert len(seqs) > 1

    def test_motion_verifies_challenge(self):
        m = ActiveChallengeManager(secret=b"k")
        ch = m.issue()
        # Provide motion that satisfies ANY challenge type.  Centroids and
        # widths are both in pixel coordinates (consistent units).
        centroids = [(500.0, 500.0), (440.0, 460.0), (380.0, 420.0), (300.0, 380.0)]
        widths = [100.0, 105.0, 112.0, 120.0]
        res = m.verify_response(ch, centroids, widths,
                                response_ts_s=ch[0].issued_at_s + 1.0)
        assert any(r.observed for r in res)

    def test_expired_challenge_fails_closed(self):
        m = ActiveChallengeManager(secret=b"k")
        ch = m.issue()
        res = m.verify_response(
            ch, [(0.5, 0.5)] * 4, [100.0] * 4,
            response_ts_s=ch[0].issued_at_s + ch[0].expires_in_s + 10)
        assert all(not r.observed for r in res)

    def test_prerecorded_frames_rejected(self):
        m = ActiveChallengeManager(secret=b"k")
        ch = m.issue()
        # All frame timestamps predate challenge issuance -> replay.
        res = m.verify_response(
            ch, [(0.5, 0.5), (0.4, 0.5), (0.3, 0.5)],
            [100.0] * 3, response_ts_s=ch[0].issued_at_s + 1.0,
            frame_ts_s=[ch[0].issued_at_s - 5.0] * 3)
        assert all(not r.observed for r in res)
        assert "replay" in res[0].reason

    def test_all_challenge_types_have_checks(self):
        for ct in ChallengeType:
            observed, reason, _ = ActiveChallengeManager._verify_one(
                ct, dx=0.5, dy=0.5, scale=0.5)
            assert isinstance(observed, bool)
            assert reason != "unknown challenge type"


# ── engine decision model (fail-safe contract) ───────────────────────

class TestPadDecisionModel:
    def test_genuine_capture_is_live(self, engine):
        r = engine.check(_face_image())
        assert r.decision is PadDecision.LIVE
        assert r.is_live is True
        assert isinstance(r.is_live, bool)  # real bool, not numpy

    def test_malformed_payload_not_live(self, engine):
        r = engine.check(b"notanimage")
        assert r.decision is PadDecision.NOT_LIVE
        assert r.is_live is False

    def test_empty_payload_not_live(self, engine):
        r = engine.check(b"")
        assert r.decision is PadDecision.NOT_LIVE

    def test_zero_timeout_fails_closed(self, engine):
        r = engine.check(_face_image(), timeout_s=0)
        assert r.decision is PadDecision.NOT_LIVE
        assert r.timed_out is True
        assert r.is_live is False

    def test_negative_timeout_fails_closed(self, engine):
        r = engine.check(_face_image(), timeout_s=-1.0)
        assert r.timed_out is True

    def test_replayed_sequence_not_live(self, engine):
        frames = [_face_image(seed=3)] * 5
        r = engine.check(_face_image(), frames=frames,
                         frame_timestamps_s=[0, 0.1, 0.2, 0.3, 0.4])
        assert r.decision is PadDecision.NOT_LIVE
        assert any(a.indicator.startswith("replay.") for a in r.attacks)

    def test_injected_source_not_live(self, engine):
        r = engine.check(_face_image(),
                         metadata={"device_label": "OBS Virtual Camera"})
        assert r.decision is PadDecision.NOT_LIVE
        assert any(a.indicator.startswith("injection.") for a in r.attacks)

    def test_low_quality_is_inconclusive_not_live(self, engine):
        r = engine.check(_face_image(seed=5, h=40, w=40))
        assert r.decision is PadDecision.INCONCLUSIVE
        assert r.is_live is False  # INCONCLUSIVE never counts as live
        assert r.quality_issues

    def test_provider_exception_fails_safe(self, engine, monkeypatch):
        def boom(self_inp, inp):
            raise RuntimeError("worker exploded")
        monkeypatch.setattr(MultiLayerPadEngine, "_do_check", boom)
        r = engine.check(_face_image())
        assert r.decision is PadDecision.NOT_LIVE
        assert r.is_live is False
        assert "exception" in r.notes.lower()

    def test_layer_timeout_returns_not_live(self, engine, monkeypatch):
        import time as _time

        def slow(self_inp, inp):
            _time.sleep(30)
        monkeypatch.setattr(MultiLayerPadEngine, "_do_check", slow)
        r = engine.check(_face_image(), timeout_s=0.5)
        assert r.decision is PadDecision.NOT_LIVE
        assert r.timed_out is True

    def test_degraded_quality_not_live_or_inconclusive(self, engine):
        r = engine.check(_face_image(blur=True, quality=40))
        assert r.decision in (PadDecision.INCONCLUSIVE, PadDecision.NOT_LIVE)
        assert r.is_live is False

    def test_result_has_no_raw_biometric_content(self, engine):
        r = engine.check(_face_image())
        # Signals/notes are bounded textual identifiers, no image data.
        assert all(isinstance(s, str) and len(s) < 200 for s in r.signals)
        assert len(r.notes) < 300

    def test_singleton_accessor(self, global_engine_guard):
        assert get_pad_engine() is get_pad_engine()
        custom = MultiLayerPadEngine()
        set_pad_engine(custom)
        assert get_pad_engine() is custom

    def test_deterministic_for_identical_input(self, engine):
        img = _face_image(seed=42)
        a = engine.check(img)
        b = engine.check(img)
        assert a.decision is b.decision
        assert a.confidence == b.confidence

    def test_timeout_config_is_respected(self, engine):
        r = engine.check(_face_image(), timeout_s=30.0)
        assert r.timed_out is False
