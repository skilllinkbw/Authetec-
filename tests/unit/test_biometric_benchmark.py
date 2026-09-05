"""Unit tests for the biometric benchmark infrastructure.

Covers: metrics correctness, dataset ingestion/validation, model
integrity, regression gates, report generation, environment capture,
and an end-to-end synthetic benchmark run.
"""

from __future__ import annotations

import json
import shutil

import numpy as np
import pytest

from benchmarks.biometric.metrics import (
    ConfusionMatrix,
    confusion_matrix,
    eer as compute_eer,
    far_frr,
    precision_recall_f1,
    rocAuc,
)


# ── metrics ────────────────────────────────────────────────────────────

class TestMetrics:
    def test_confusion_matrix_and_rates(self):
        cm = confusion_matrix([1, 1, 0, 0, 0], [1, 0, 0, 1, 1])
        assert cm.tp == 1 and cm.fn == 1 and cm.tn == 1 and cm.fp == 2
        far, frr = far_frr(cm)
        assert far == pytest.approx(2 / 3)
        assert frr == pytest.approx(0.5)
        p, r, f1 = precision_recall_f1(cm)
        assert p == pytest.approx(1 / 3)
        assert r == pytest.approx(0.5)

    def test_roc_auc_separable(self):
        y = [1, 1, 1, 0, 0, 0]
        s = [0.9, 0.8, 0.7, 0.2, 0.1, 0.0]
        assert rocAuc(y, s) == pytest.approx(1.0)

    def test_roc_auc_random(self):
        rng = np.random.default_rng(7)
        y = rng.integers(0, 2, 200).tolist()
        s = rng.random(200).tolist()
        assert 0.3 <= rocAuc(y, s) <= 0.7

    def test_eer_separable(self):
        y = [1] * 50 + [0] * 50
        s = np.linspace(0.6, 1.0, 50).tolist() + \
            np.linspace(0.0, 0.4, 50).tolist()
        eer, thr = compute_eer(y, s)
        assert 0.0 <= eer <= 0.05
        assert 0.4 < thr < 0.6

    def test_confusion_matrix_accuracy(self):
        cm = ConfusionMatrix(tp=9, tn=90, fp=5, fn=1)
        assert cm.total == 105
        assert cm.accuracy() == pytest.approx(99 / 105)


def _make_tiny_dataset(tmp_path, *, corrupt: bool = False,
                       leaky: bool = False, duplicate: bool = False):
    from PIL import Image
    d = tmp_path  # images live in the manifest parent directory
    samples = []
    img = Image.new("RGB", (16, 16), (128, 128, 128))
    for sid in range(2):
        for cap in range(2):
            p = d / f"s{sid}_c{cap}.png"
            img.save(p)
            samples.append({
                "subject_id": f"s{sid}", "path": p.name,
                "split": "train" if (leaky and sid == 0 and cap == 0)
                else "eval",
                "label": 1, "attack_type": "",
            })
    if corrupt:
        bad = d / "corrupt.png"
        bad.write_bytes(b"not a real image")
        samples.append({"subject_id": "s9", "path": bad.name,
                        "split": "eval", "label": 1, "attack_type": ""})
    if duplicate:
        shutil.copy(d / "s0_c1.png", d / "s0_c1_copy.png")
        samples.append({"subject_id": "s0", "path": "s0_c1_copy.png",
                        "split": "eval", "label": 1, "attack_type": ""})
    atk = d / "atk_print.jpg"
    img.save(atk, quality=50)
    samples.append({"subject_id": "s1", "path": atk.name, "split": "eval",
                    "label": 0, "attack_type": "print"})
    manifest = {
        "name": "tiny", "version": "1.0.0", "source": "test",
        "license": "test-license", "samples": samples,
    }
    mp = tmp_path / "manifest.json"
    mp.write_text(json.dumps(manifest), encoding="utf-8")
    return mp
# ── model integrity ───────────────────────────────────────────────────

class TestModelIntegrity:
    def _make_models(self, tmp_path, *, mutate: bool = False):
        import hashlib
        models = tmp_path / "models"
        (models / "face_recognition").mkdir(parents=True)
        (models / "face_detection").mkdir(parents=True)
        rec = models / "face_recognition" / "sface.onnx"
        det = models / "face_detection" / "yunet.onnx"
        rec.write_bytes(b"model-bytes-rec")
        det.write_bytes(b"model-bytes-det")
        if mutate:
            rec.write_bytes(b"tampered-model-bytes")
        pins = {
            "sface_recognition": hashlib.sha256(b"model-bytes-rec").hexdigest(),
            "yunet_face_detection": hashlib.sha256(b"model-bytes-det").hexdigest(),
        }
        pins_path = tmp_path / "model_pins.json"
        pins_path.write_text(json.dumps(pins), encoding="utf-8")
        return models, pins_path

    def test_verify_ok(self, tmp_path):
        from benchmarks.biometric.model_integrity import (
            integrity_passed, verify_model_pins,
        )
        models, pins = self._make_models(tmp_path)
        results = verify_model_pins(models_dir=models, pins_path=pins)
        assert len(results) == 2
        assert all(r.status == "OK" for r in results)
        assert integrity_passed(results)

    def test_verify_tamper_detected(self, tmp_path):
        from benchmarks.biometric.model_integrity import (
            integrity_passed, verify_model_pins,
        )
        models, pins = self._make_models(tmp_path, mutate=True)
        results = verify_model_pins(models_dir=models, pins_path=pins)
        assert any(r.status == "HASH_MISMATCH" for r in results)
        assert not integrity_passed(results)

    def test_verify_missing_not_found(self, tmp_path):
        from benchmarks.biometric.model_integrity import verify_model_pins
        models, pins = self._make_models(tmp_path)
        (models / "face_recognition" / "sface.onnx").unlink()
        results = verify_model_pins(models_dir=models, pins_path=pins)
        assert any(r.status == "NOT_FOUND" for r in results)

    def test_embeddings_finite(self):
        from benchmarks.biometric.model_integrity import assert_embeddings_finite
        assert assert_embeddings_finite(np.array([0.5, -0.2], dtype=np.float32))
        assert not assert_embeddings_finite(np.array([0.5, np.nan]))
        assert not assert_embeddings_finite(np.array([np.inf, 0.0]))


# ── regression gates ──────────────────────────────────────────────────

class TestRegressionGates:
    def test_unconfigured_gates_skipped(self):
        from benchmarks.biometric.regression_gates import RegressionGateSet
        out = RegressionGateSet({}).evaluate(
            {"far": 0.01, "f1": 0.9, "apcer": 0.1})
        assert out["passed"] is True
        assert all(g["status"] == "SKIPPED" for g in out["gates"])
        assert all("CONFIGURATION REQUIRED" in g["note"] for g in out["gates"])

    def test_configured_gates_pass_fail(self):
        from benchmarks.biometric.regression_gates import RegressionGateSet
        gates = RegressionGateSet({
            "max_far": 0.02, "min_f1": 0.8, "min_rocauc": 0.9,
        })
        out = gates.evaluate(
            {"far": 0.01, "f1": 0.85, "rocauc": 0.95})
        assert out["passed"] is True
        by_name = {g["name"]: g for g in out["gates"]}
        assert by_name["max_far"]["status"] == "PASS"

        out2 = gates.evaluate(
            {"far": 0.05, "f1": 0.85, "rocauc": 0.95})
        assert out2["passed"] is False
        by_name2 = {g["name"]: g for g in out2["gates"]}
        assert by_name2["max_far"]["status"] == "FAIL"


# ── environment + report + runner ─────────────────────────────────────

class TestRunner:
    def test_environment_capture(self):
        from benchmarks.biometric.environment import capture_environment
        env = capture_environment()
        assert env["git_commit"]
        assert env["timestamp_utc"]
        assert "python_version" in env

    def test_report_generation(self, tmp_path):
        from benchmarks.biometric.report import generate_report
        results = {
            "environment": {"git_commit": "abc", "timestamp_utc": "now",
                            "git_branch": "x", "git_dirty": False},
            "dataset": {"name": "synthetic-fixture", "version": "1.0.0",
                        "n_subjects": 2, "n_bonafide": 4, "n_attack": 2,
                        "attack_types": {"print": 2}, "integrity_issues": [],
                        "source": "s", "license": "l"},
            "verification": {"rocauc": 0.9, "eer": 0.1, "threshold": 0.62,
                             "f1": 0.8, "tp": 1, "tn": 1, "fp": 1, "fn": 1,
                             "far": 0.5, "frr": 0.5, "precision": 0.5,
                             "recall": 0.5, "accuracy": 0.5,
                             "eer_threshold": 0.5},
            "threshold_analysis": {"points": [], "selected_threshold": 0.62,
                                   "selected_far": 0.1, "selected_frr": 0.1,
                                   "rocauc": 0.9, "eer": 0.1,
                                   "eer_threshold": 0.5},
            "pad": {"n_bonafide": 4, "n_attack": 2, "apcer": 0.5,
                    "bpcer": 0.5, "acer": 0.5, "attack_accept_rate": 0.5,
                    "bonafide_accept_rate": 0.5, "attack_specific": {}},
            "performance": {"end_to_end": {"stage": "end_to_end", "n": 5,
                            "mean_ms": 1, "p50_ms": 1, "p95_ms": 1,
                            "p99_ms": 1}},
            "security": {"malformed_rejected": True,
                         "provider_fail_closed": True},
            "gates": {"passed": True},
            "model_integrity": {"results": []},
            "config": {"provider": "deterministic", "threshold": 0.62,
                       "dataset_seed": 42},
        }
        out = generate_report(results, out_dir=tmp_path)
        text = out.read_text(encoding="utf-8")
        assert "BIOMETRIC VALIDATION REPORT" in text
        assert "## 1. Executive Summary" in text
        assert "## 16. Production Readiness" in text
        assert "SYNTHETIC DATA ONLY" in text

    def test_runner_end_to_end_synthetic(self, tmp_path):
        from benchmarks.biometric.config import BenchmarkConfig
        from benchmarks.biometric.runner import run_benchmark
        manifest = _make_tiny_dataset(tmp_path)
        cfg = BenchmarkConfig(
            manifest_path=str(manifest),
            output_dir=str(tmp_path / "out"),
            provider="deterministic",
            threshold=0.5,
            max_pairs=20,
            n_warmup=1,
            n_iters=3,
        )
        results = run_benchmark(cfg)
        v = results["verification"]
        assert results["dataset"]["n_bonafide"] == 4
        assert 0.0 <= v["rocauc"] <= 1.0  # computed, finite
        assert results["pad"]["n_attack"] == 1
        assert (tmp_path / "out" / "benchmark_results.json").exists()
        assert (tmp_path / "out" / "BIOMETRIC_BENCHMARK_REPORT.md").exists()
