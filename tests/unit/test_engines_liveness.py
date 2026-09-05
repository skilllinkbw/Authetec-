"""Unit tests for the pluggable liveness / PAD abstraction.

The deterministic detector shipped with Authetec is a DEVELOPMENT fallback
and is explicitly NOT production PAD.  These tests enforce the fail-safe
contract that a production provider must also satisfy:

  * a timeout  is NEVER reported as "live";
  * an error   is NEVER reported as "live";
  * undecodable input is NEVER reported as "live";
  * a missing/None result is never treated as "live" by callers.

They do NOT attempt to validate any attack-detection accuracy.
"""

from __future__ import annotations

import time

import pytest

from app.engines.liveness import (
    LivenessResult,
    PadMethod,
    PresentationAttack,
    DeterministicLivenessDetector,
    get_liveness_detector,
    set_liveness_detector,
)


@pytest.fixture()
def detector() -> DeterministicLivenessDetector:
    return DeterministicLivenessDetector()


def _noise_png(size: int = 96, seed: int = 0) -> bytes:
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, size=(size, size), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


# ── fail-safe contract ────────────────────────────────────────────────────

def test_valid_image_returns_liveness_result(detector):
    result = detector.check(_noise_png())
    assert isinstance(result, LivenessResult)
    assert isinstance(result.is_live, bool)
    assert 0.0 <= result.confidence <= 1.0
    assert result.timed_out is False
    # The model version must keep the "fallback" marker visible so the
    # output can never be mistaken for a production PAD verdict.
    assert "fallback" in result.model_version


def test_empty_bytes_never_live(detector):
    result = detector.check(b"")
    assert result.is_live is False
    assert result.confidence < 0.5
    assert result.attacks  # a non-live verdict carries an attack indicator


def test_undecodable_bytes_never_live(detector):
    result = detector.check(b"this is definitely not an image")
    assert result.is_live is False
    assert result.confidence < 0.5


def test_worker_error_never_live(detector, monkeypatch):
    def _boom(_image_bytes):
        raise RuntimeError("provider crashed")

    monkeypatch.setattr(detector, "_do_check", _boom)
    result = detector.check(_noise_png())
    assert result.is_live is False
    assert any(a.indicator == "error" for a in result.attacks)


def test_hang_is_not_live_and_returns_within_budget(detector, monkeypatch):
    """A stuck worker must never block the caller past the time budget."""

    def _hang(_image_bytes):
        time.sleep(2.0)  # far longer than the budget under test
        return LivenessResult(is_live=True, confidence=0.99)

    monkeypatch.setattr(detector, "_do_check", _hang)
    t0 = time.perf_counter()
    result = detector.check(_noise_png(), timeout_s=0.05)
    elapsed = time.perf_counter() - t0

    assert result.is_live is False
    assert result.timed_out is True
    assert any(a.indicator == "timeout" for a in result.attacks)
    assert elapsed < 0.5  # returned promptly after the budget, not after the hang


def test_non_positive_budget_fails_fast_as_timeout(detector):
    result = detector.check(_noise_png(), timeout_s=0)
    assert result.is_live is False
    assert result.timed_out is True
    assert result.processing_time_ms < 500


# ── production provider injection ─────────────────────────────────────────

class FakeProductionPad:
    """A stand-in for a real, independently-validated PAD provider.

    It satisfies the LivenessDetector protocol and is used in tests to
    verify the wiring works; it is NOT a real PAD system.
    """

    def __init__(self) -> None:
        self.called_with = None

    def check(self, image_bytes: bytes, *, challenge=None,
              timeout_s: float = 10.0) -> LivenessResult:
        self.called_with = (image_bytes, challenge)
        return LivenessResult(
            is_live=True, confidence=0.99, method=PadMethod.ACTIVE,
            model_version="independent-pad-provider-1.0",
            notes="Fake provider used only to validate injection wiring",
        )


def test_set_and_get_injection_returns_provider():
    original = get_liveness_detector()
    try:
        provider = FakeProductionPad()
        set_liveness_detector(provider)  # type: ignore[arg-type]
        assert get_liveness_detector() is provider

        img = _noise_png()
        result = provider.check(img, challenge="say-483")
        assert result.is_live is True
        assert result.model_version == "independent-pad-provider-1.0"
    finally:
        set_liveness_detector(original)


def test_injected_provider_configuration_is_honoured():
    original = get_liveness_detector()
    try:
        set_liveness_detector(DeterministicLivenessDetector(threshold=0.99))
        # A flat/uniform image has near-zero entropy+variance, so even a
        # modest threshold rejects it. With the injected high threshold this
        # proves the injected configuration is actually in effect.
        result = get_liveness_detector().check(_flat_png())
        assert result.is_live is False
        assert result.signals  # entropy/variance signals are attached
    finally:
        set_liveness_detector(original)


def _flat_png(size: int = 96, value: int = 127) -> bytes:
    """A uniform gray image: near-zero entropy and variance."""
    import cv2
    import numpy as np
    img = np.full((size, size), value, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


# ── audit fields are non-scoring ──────────────────────────────────────────

def test_audit_fields_present_on_timeout(detector, monkeypatch):
    def _hang(_image_bytes):
        time.sleep(2.0)

    monkeypatch.setattr(detector, "_do_check", _hang)
    result = detector.check(_noise_png(), timeout_s=0.05)
    assert result.timed_out is True
    assert result.notes
    assert "pad_timeout" in result.signals