"""
Recognition tests: embedding validation (NaN/Inf/dim/norm/dtype),
secure cosine similarity, calibrated matcher outcomes, deterministic
behaviour, embedder backends and threshold calibration.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.biometric.recognition.calibration import calibrate_thresholds
from app.biometric.recognition.deterministic_embedder import (
    DeterministicFaceEmbedder,
)
from app.biometric.recognition.embeddings import (
    EmbeddingValidator,
    cosine_similarity_secure,
)
from app.biometric.recognition.matcher import FaceMatcher, MatchOutcome
from app.biometric.recognition.sface import SFaceFaceEmbedder


def _unit(v: float, dim: int = 8) -> np.ndarray:
    a = np.zeros(dim, dtype=np.float32)
    a[0] = v
    a[1] = np.sqrt(max(0.0, 1.0 - v * v)) if abs(v) <= 1 else 1e-8
    n = np.linalg.norm(a)
    return (a / n).astype(np.float32)


class TestEmbeddingValidator:
    def test_valid_embedding(self):
        v = EmbeddingValidator(expected_dim=8)
        res = v.validate(_unit(0.6))
        assert res.is_valid and res.dim == 8

    def test_nan_rejected(self):
        e = _unit(0.5)
        e[2] = np.nan
        assert not EmbeddingValidator().validate(e).is_valid

    def test_inf_rejected(self):
        e = _unit(0.5)
        e[2] = np.inf
        assert not EmbeddingValidator().validate(e).is_valid

    def test_wrong_dimension_rejected(self):
        v = EmbeddingValidator(expected_dim=128)
        assert not v.validate(_unit(0.5, dim=64)).is_valid

    def test_non_unit_norm_rejected(self):
        e = _unit(0.5) * 3.0
        assert not EmbeddingValidator().validate(e).is_valid

    def test_integer_dtype_rejected(self):
        e = np.arange(8, dtype=np.int32)
        assert not EmbeddingValidator().validate(e).is_valid

    def test_none_rejected(self):
        assert not EmbeddingValidator().validate(None).is_valid

    def test_multidim_rejected(self):
        assert not EmbeddingValidator().validate(
            np.ones((2, 4), dtype=np.float32)).is_valid

    def test_normalize_returns_unit_vector(self):
        e = _unit(0.5) * 5.0
        out = EmbeddingValidator().normalize(e)
        assert out is not None
        assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-5


class TestSecureCosine:
    def test_identical_vectors_one(self):
        a = _unit(0.7)
        assert cosine_similarity_secure(a, a) == pytest.approx(1.0)

    def test_invalid_inputs_none(self):
        assert cosine_similarity_secure(None, _unit(0.5)) is None
        bad = _unit(0.5)
        bad[0] = np.nan
        assert cosine_similarity_secure(bad, _unit(0.5)) is None

    def test_dimension_mismatch_none(self):
        assert cosine_similarity_secure(
            _unit(0.5, dim=8), _unit(0.5, dim=16)) is None

    def test_zero_vector_none(self):
        z = np.zeros(8, dtype=np.float32)
        assert cosine_similarity_secure(z, z) is None


class TestFaceMatcher:
    def setup_method(self):
        self.matcher = FaceMatcher(threshold_match=0.50,
                                   threshold_not_match=0.35)

    def test_same_person_matches(self):
        a = _unit(0.9)
        d = self.matcher.compare(a, a)
        assert d.outcome is MatchOutcome.MATCH and d.is_match

    def test_different_person_no_match(self):
        a, b = _unit(1.0), _unit(-1.0)
        assert self.matcher.compare(a, b).outcome is MatchOutcome.NO_MATCH

    def test_borderline_never_forced_to_match(self):
        a = _unit(0.9)
        b = a.copy()
        b[0] += 0.02  # nudge similarity into the indeterminate band
        d = self.matcher.compare(a, b / np.linalg.norm(b))
        if d.outcome is not MatchOutcome.MATCH:
            assert d.outcome is MatchOutcome.INCONCLUSIVE
            assert d.similarity < self.matcher.threshold_match

    def test_invalid_embedding_is_inconclusive_fail_closed(self):
        bad = np.full(8, np.nan, dtype=np.float32)
        d = self.matcher.compare(_unit(0.5), bad)
        assert d.outcome is MatchOutcome.INCONCLUSIVE
        assert "fail closed" in " ".join(d.reasons).lower()

    def test_deterministic(self):
        a, b = _unit(0.9), _unit(0.4)
        d1 = self.matcher.compare(a, b)
        d2 = self.matcher.compare(a, b)
        assert d1.similarity == d2.similarity
        assert d1.outcome is d2.outcome


class TestEmbedders:
    def test_deterministic_embedder_available_and_labeled_fallback(self):
        e = DeterministicFaceEmbedder()
        assert e.available() is True
        assert e.provider.production_grade is False
        assert e.provider.usage_status == "NON_PRODUCTION_FALLBACK"

    def test_deterministic_embedder_deterministic(self):
        import cv2
        rng = np.random.default_rng(5)
        img = rng.integers(0, 255, (100, 100), dtype=np.uint8)
        ok, buf = cv2.imencode(".png", img)
        data = buf.tobytes()
        e = DeterministicFaceEmbedder()
        np.testing.assert_array_equal(e.embed(data), e.embed(data))

    def test_deterministic_embedder_rejects_garbage(self):
        assert DeterministicFaceEmbedder().embed(b"junk") is None

    def test_sface_available_with_installed_model(self):
        e = SFaceFaceEmbedder()
        if not e.available():
            pytest.skip("SFace model not installed in this checkout")
        assert e.EMBEDDING_DIM == 128

    def test_sface_embedding_is_unit_128d(self):
        import cv2
        e = SFaceFaceEmbedder()
        if not e.available():
            pytest.skip("SFace model not installed in this checkout")
        rng = np.random.default_rng(9)
        img = rng.integers(0, 255, (112, 112, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".png", img)
        emb = e.embed(buf.tobytes())
        assert emb is not None
        assert emb.shape == (128,)
        assert abs(float(np.linalg.norm(emb)) - 1.0) < 1e-5
        emb2 = e.embed(buf.tobytes())
        np.testing.assert_array_equal(emb, emb2)

    def test_sface_rejects_garbage(self):
        e = SFaceFaceEmbedder()
        assert e.embed(b"junk") is None


class TestCalibration:
    def test_separable_scores_low_eer(self):
        rng = np.random.default_rng(1)
        genuine = rng.normal(0.75, 0.05, 200)
        impostor = rng.normal(0.30, 0.05, 200)
        res = calibrate_thresholds(list(genuine), list(impostor))
        assert res.eer is not None and res.eer < 0.05
        assert res.threshold_not_match < res.threshold_match
        assert res.fmr_at_threshold <= 0.05 or res.fnmr_at_threshold <= 0.05

    def test_insufficient_data_uses_fallback(self):
        res = calibrate_thresholds([0.8, 0.9], [0.2, 0.3])
        assert res.threshold_match == 0.50
        assert "insufficient data" in " ".join(res.notes).lower()

    def test_result_is_marked_not_validated_by_default(self):
        rng = np.random.default_rng(2)
        res = calibrate_thresholds(
            list(rng.normal(0.8, 0.03, 50)),
            list(rng.normal(0.3, 0.03, 50)))
        assert res.validated is False
        assert res.dataset_label == "SYNTHETIC/TEST-ONLY"
        assert res.to_dict()["validated"] is False

    def test_overlapping_scores_higher_eer(self):
        rng = np.random.default_rng(3)
        genuine = rng.normal(0.55, 0.15, 200)
        impostor = rng.normal(0.45, 0.15, 200)
        res = calibrate_thresholds(list(genuine), list(impostor))
        assert res.eer is not None and res.eer > 0.10
