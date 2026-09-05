"""Biometric benchmark runner (CLI entry point).

Reproducible benchmark command::

    python -m benchmarks.biometric.runner [--manifest PATH] [--output DIR]
        [--threshold FLOAT] [--provider deterministic|native]
        [--seed INT] [--max-pairs INT]

Without ``--manifest`` a SYNTHETIC fixture dataset is generated (explicitly
labelled synthetic; never real-world evidence).

Every run records Git commit, environment, config, dataset provenance and
computes all metrics from actual predictions.  Outputs:

    benchmark_results.json      machine-readable results
    BIOMETRIC_BENCHMARK_REPORT.md  human-readable report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _build_embedder(provider: str):
    if provider == "native":
        try:
            from app.biometric.recognition.embedders import build_embedder
            emb = build_embedder()
            if emb is not None and getattr(emb, "available", lambda: True)():
                return emb
        except Exception:
            pass
        raise RuntimeError(
            "native provider requested but SFace model is missing/not "
            "available - install models per docs/biometric_model_setup.md")

    from app.biometric.recognition.deterministic_embedder import (
        DeterministicFaceEmbedder,
    )
    return DeterministicFaceEmbedder()


def _build_liveness(provider: str):
    if provider == "native":
        from app.biometric.pad import get_pad_engine
        return get_pad_engine()
    from app.engines.liveness import get_liveness_detector
    return get_liveness_detector()


def _security_self_test(embedder: Any, liveness: Any) -> Dict[str, Any]:
    """Fail-closed sanity checks: malformed input must not pass."""
    result: Dict[str, Any] = {"provider_fail_closed": True}
    try:
        r = liveness.check(b"this is not an image in any format")
        result["malformed_rejected"] = bool(r.is_live is False)
        if result["malformed_rejected"] is not True:
            result["provider_fail_closed"] = False
    except Exception:
        result["malformed_rejected"] = True  # raised => rejected
    try:
        emb = embedder.embed(b"garbage")
        result["embedder_never_accepts_garbage"] = bool(
            emb is None or not _finite(emb))
    except Exception:
        result["embedder_never_accepts_garbage"] = True
    return result


def _finite(emb: Any) -> bool:
    try:
        import numpy as np
        a = np.asarray(emb, dtype=np.float64)
        return bool(a.size and np.all(np.isfinite(a)))
    except Exception:
        return False


def run_benchmark(config: Any) -> Dict[str, Any]:
    """Execute the full benchmark pipeline; returns the results dict."""
    from benchmarks.biometric import (
        PadBenchmark,
        PerformanceBenchmark,
        VerificationBenchmark,
        analyze_thresholds,
    )
    from benchmarks.biometric.model_integrity import (
        integrity_passed,
        verify_model_pins,
    )
    from benchmarks.biometric.dataset import (
        generate_pad_samples,
        generate_verification_pairs,
        load_dataset,
    )
    from benchmarks.biometric.environment import capture_environment
    from benchmarks.biometric.regression_gates import RegressionGateSet
    from benchmarks.biometric.report import generate_report

    env = capture_environment()

    # ── dataset ───────────────────────────────────────────────────────
    if config.manifest_path:
        dataset = load_dataset(config.manifest_path)
        dataset_info = dataset.stats()
    else:
        from benchmarks.biometric.synthetic_fixtures import (
            create_synthetic_dataset,
        )
        manifest = create_synthetic_dataset(
            seed=config.dataset_seed,
            out_dir=Path("benchmarks/biometric/data/synthetic"),
        )
        dataset = load_dataset(manifest)
        dataset_info = dataset.stats()
        dataset_info["synthetic"] = True

    # ── provider + model integrity ────────────────────────────────────
    integrity = verify_model_pins()
    integrity_info = {
        "results": [r.to_dict() for r in integrity],
        "passed": integrity_passed(integrity),
    }
    if config.provider == "native" and not integrity_info["passed"]:
        raise RuntimeError(
            "native provider requested but model integrity checks failed - "
            "refusing to run (fail-safe)")

    embedder = _build_embedder(config.provider)
    liveness = _build_liveness(config.provider)

    # ── security self-test ────────────────────────────────────────────
    security = _security_self_test(embedder, liveness)

    # ── verification ──────────────────────────────────────────────────
    pairs = generate_verification_pairs(
        dataset, seed=config.dataset_seed, max_pairs=config.max_pairs,
        impostor_ratio=config.impostor_ratio)
    ver = VerificationBenchmark(
        embedder, threshold=config.threshold).run_pairs(pairs)

    # ── threshold analysis ────────────────────────────────────────────
    genuine = [p.similarity for p in ver.pairs if p.label == 1]
    impostor = [p.similarity for p in ver.pairs if p.label == 0]
    tha = analyze_thresholds(
        genuine, impostor, selected_threshold=config.threshold)

    # ── PAD ───────────────────────────────────────────────────────────
    pad_samples = generate_pad_samples(dataset, seed=config.dataset_seed)
    pad = PadBenchmark(liveness).run_samples(pad_samples)

    # ── performance (component-level) ─────────────────────────────────
    sample_img = b""
    if dataset.bonafide_samples():
        sample_img = dataset.bonafide_samples()[0].image_path.read_bytes()
    perf = PerformanceBenchmark(
        embedder, liveness_detector=liveness,
        n_warmup=config.n_warmup, n_iters=config.n_iters,
    ).run(sample_img) if sample_img else None

    # ── regression gates ──────────────────────────────────────────────
    metrics_flat = {
        "far": ver.far, "frr": ver.frr,
        "precision": ver.precision, "recall": ver.recall, "f1": ver.f1,
        "rocauc": ver.rocauc,
        "apcer": pad.apcer, "bpcer": pad.bpcer, "acer": pad.acer,
        "max_p95_latency_ms": _p95(perf, end_to_end=True),
    }
    gates = RegressionGateSet(config.gates).evaluate(metrics_flat)

    results: Dict[str, Any] = {
        "config": config.to_dict(),
        "environment": env,
        "dataset": dataset_info,
        "model_integrity": integrity_info,
        "security": security,
        "verification": ver.to_dict(),
        "threshold_analysis": tha.to_dict(),
        "pad": pad.to_dict(),
        "performance": perf.to_dict() if perf else {},
        "gates": gates,
        "metrics": metrics_flat,
    }
    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "benchmark_results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    generate_report(results, out_dir=out_dir)
    return results


def _p95(perf: Any, *, end_to_end: bool) -> Optional[float]:
    if perf is None:
        return None
    stage = getattr(perf, "end_to_end", None)
    if stage is None:
        return None
    return stage.p95_ms


def _cli(argv: Optional[List[str]] = None) -> int:
    from benchmarks.biometric.config import BenchmarkConfig

    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.biometric.runner",
        description="Reproducible AUTHeTEC biometric benchmark.")
    parser.add_argument("--manifest", default=None,
                        help="dataset manifest JSON (default: synthetic)")
    parser.add_argument("--output", default="benchmarks/biometric/reports",
                        help="output directory for results/report")
    parser.add_argument("--threshold", type=float, default=0.62,
                        help="verification similarity threshold")
    parser.add_argument("--provider", default="deterministic",
                        choices=("deterministic", "native"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-pairs", type=int, default=400)
    args = parser.parse_args(argv)

    cfg = BenchmarkConfig(
        manifest_path=args.manifest,
        output_dir=args.output,
        provider=args.provider,
        threshold=args.threshold,
        dataset_seed=args.seed,
        max_pairs=args.max_pairs,
    )
    results = run_benchmark(cfg)
    print(f"provider={cfg.provider} git={results['environment']['git_commit']}")
    v = results["verification"]
    print(f"  verification: rocauc={v['rocauc']} eer={v['eer']} "
          f"far={v['far']} frr={v['frr']}")
    p = results["pad"]
    print(f"  pad: apcer={p['apcer']} bpcer={p['bpcer']} acer={p['acer']}")
    print(f"  gates: passed={results['gates']['passed']} "
          f"skipped={len(results['gates']['skipped'])}")
    print(f"  outputs: {Path(cfg.output_dir).resolve()}")
    return 0 if results["gates"]["passed"] else 2


if __name__ == "__main__":
    sys.exit(_cli())