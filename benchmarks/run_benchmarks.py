"""
Authetec Benchmark Runner
==========================

Run individual or all benchmark adapters and generate evaluation reports.

Usage:
    python -m benchmarks.run_benchmarks --all
    python -m benchmarks.run_benchmarks --adapter lightgbm_fraud
    python -m benchmarks.run_benchmarks --adapter lightgbm_fraud --adapter graph_fraud
"""

import argparse
import json
import sys
import time
from typing import Dict, List

sys.path.insert(0, "")

from benchmarks.adapters import ALL_ADAPTERS  # noqa: E402


def run_single(adapter_name: str, n_samples: int = 3000) -> Dict:
    """Train + evaluate a single adapter on a small synthetic dataset."""
    if adapter_name not in ALL_ADAPTERS:
        print(f"  [ERROR] Unknown adapter '{adapter_name}'. Known: {list(ALL_ADAPTERS)}")
        return {}

    cls = ALL_ADAPTERS[adapter_name]
    adapter = cls()
    print(f"\n=== Adapter: {adapter.adapter_name} ===")
    print(f"  Repo: {adapter.repo_full_name}")
    print(f"  Commit: {adapter.repo_commit[:12]}")
    print(f"  License: {adapter.repo_license}")

    print("  Validating environment...")
    if not adapter.validate_environment():
        print("  [FAIL] Environment validation failed.")
        return {"name": adapter_name, "status": "ENV_FAIL"}

    print(f"  Training on {n_samples} samples...")
    t0 = time.perf_counter()
    try:
        result = adapter.evaluate(n_samples=n_samples)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  [FAIL] Evaluation error: {e}")
        return {"name": adapter_name, "status": "EVAL_FAIL", "error": str(e)}
    elapsed = time.perf_counter() - t0
    print(f"  Done in {elapsed:.1f}s")
    print(f"  PR-AUC: {result.metrics.get('pr_auc', 'N/A')}")
    print(f"  ROC-AUC: {result.metrics.get('roc_auc', 'N/A')}")
    print(f"  Precision: {result.metrics.get('precision', 'N/A')}")
    print(f"  Recall: {result.metrics.get('recall', 'N/A')}")
    print(f"  F1: {result.metrics.get('f1', 'N/A')}")
    print(f"  Report: {result.report_path}")

    return {
        "name": adapter_name,
        "status": "OK",
        "metrics": result.metrics,
        "report": result.report_path,
        "elapsed_s": round(elapsed, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Authetec benchmark runner")
    parser.add_argument("--adapter", action="append", dest="adapters",
                        help="Run specific adapters (repeatable)")
    parser.add_argument("--all", action="store_true", help="Run all adapters")
    parser.add_argument("--n-samples", type=int, default=3000,
                        help="Number of synthetic samples per run")
    args = parser.parse_args()

    if args.all:
        targets = list(ALL_ADAPTERS.keys())
    elif args.adapters:
        targets = args.adapters
    else:
        print("Specify --adapter NAME or --all")
        parser.print_help()
        sys.exit(1)

    print(f"Running {len(targets)} benchmark(s) with {args.n_samples} samples each...")
    results = []
    for name in targets:
        results.append(run_single(name, n_samples=args.n_samples))

    print("\n\n=========== SUMMARY ===========")
    for r in results:
        if r.get("status") == "OK":
            m = r["metrics"]
            print(f"  {r['name']}: PR-AUC={m.get('pr_auc', 'N/A'):.4f} "
                  f"ROC={m.get('roc_auc', 'N/A'):.4f} "
                  f"P={m.get('precision', 'N/A'):.4f} R={m.get('recall', 'N/A'):.4f} "
                  f"F1={m.get('f1', 'N/A'):.4f} [{r['elapsed_s']}s]")
        else:
            print(f"  {r['name']}: {r.get('status')}")

    summary_path = "benchmarks/reports/summary.json"
    import os
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSummary written to {summary_path}")


if __name__ == "__main__":
    main()