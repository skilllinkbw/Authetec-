"""Smoke tests for the SYNTHETIC/TEST-ONLY OCR benchmark framework."""

from __future__ import annotations

from benchmarks.evaluation.ocr_benchmark import (
    DATASET_LABEL,
    OcrBenchmarkReport,
    run_ocr_benchmark,
)


class TestOcrBenchmark:
    def test_report_is_labelled_synthetic(self):
        r = run_ocr_benchmark(n_samples=20)
        assert r.dataset == "SYNTHETIC/TEST-ONLY"
        d = r.to_dict()
        assert "NOT real-world accuracy" in d["disclaimer"]

    def test_benchmark_runs_without_failures(self):
        r = run_ocr_benchmark(n_samples=50, seed=1)
        assert isinstance(r, OcrBenchmarkReport)
        assert r.processing_failures == 0
        assert 0.0 <= r.character_accuracy <= 1.0
        assert 0.0 <= r.field_accuracy <= 1.0
        assert 0.0 <= r.mrz_validity_rate <= 1.0
        assert 0.0 <= r.false_acceptance_rate <= 1.0
        assert 0.0 <= r.false_rejection_rate <= 1.0

    def test_clean_mrzs_are_never_rejected(self):
        r = run_ocr_benchmark(n_samples=50, seed=2)
        assert r.false_rejection_rate == 0.0

    def test_deterministic_for_seed(self):
        a = run_ocr_benchmark(n_samples=30, seed=5)
        b = run_ocr_benchmark(n_samples=30, seed=5)
        assert a.to_dict() == b.to_dict()

    def test_tamper_far_is_bounded(self):
        # Mod-10 checksums catch ~90% of single-character substitutions;
        # residual FAR < 0.15 proves the tamper detection is live.
        r = run_ocr_benchmark(n_samples=100, seed=3)
        assert r.false_acceptance_rate < 0.15
