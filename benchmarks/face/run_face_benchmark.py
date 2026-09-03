"""Face verification benchmark harness (SYNTHETIC data).

IMPORTANT — ACCURACY POLICY
---------------------------
All metrics produced by this harness are measured on **synthetic**
embeddings generated here. They demonstrate the behaviour of the matching
pipeline (threshold sweep, FAR/FRR trade-off, separation quality) and are
NOT evidence of real-world identity-verification accuracy. They must
never be quoted as production performance. Real validation requires
labelled face datasets (e.g. LFW for research context) with a production
embedding model plugged into the ``FaceEmbedder`` protocol.

Usage:
    python -m benchmarks.face.run_face_benchmark
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
MODEL_VERSION = "face-cosine-deterministic-embedder-v1"


def _generate_pairs(n_identities: int, pairs_per_identity: int,
                    seed: int = 7):
    """Generate genuine and impostor embedding pairs.

    Identities are Gaussian clusters in 64-d space; genuine pairs come
    from the same cluster (intra-cluster noise), impostor pairs from
    different clusters.  The cluster separation is intentionally moderate
    so the threshold sweep covers an interesting FAR/FRR trade-off.
    """
    rng = np.random.default_rng(seed)
    dim = 64
    centers = rng.standard_normal((n_identities, dim))
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)

    genuine = []
    for i in range(n_identities):
        for _ in range(pairs_per_identity):
            a = centers[i] + rng.standard_normal(dim) * 0.05
            b = centers[i] + rng.standard_normal(dim) * 0.05
            genuine.append((a, b))

    impostor = []
    for i in range(n_identities):
        j = (i + 1 + int(rng.integers(0, n_identities - 1))) % n_identities
        for _ in range(pairs_per_identity):
            a = centers[i] + rng.standard_normal(dim) * 0.05
            b = centers[j] + rng.standard_normal(dim) * 0.05
            impostor.append((a, b))
    return genuine, impostor


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _roc_auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based ROC-AUC (Mann-Whitney U; handles ties)."""
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1)
    sorted_scores = scores[order]
    i = 0
    while i < len(scores):
        j = i
        while j + 1 < len(scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    n_pos = int(labels.sum())
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[labels == 1].sum() -
                  n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def evaluate(n_identities: int = 120, pairs_per_identity: int = 20,
             seed: int = 7) -> dict:
    genuine, impostor = _generate_pairs(n_identities, pairs_per_identity, seed)
    gen_scores = np.array([_cosine(a, b) for a, b in genuine])
    imp_scores = np.array([_cosine(a, b) for a, b in impostor])
    all_scores = np.concatenate([gen_scores, imp_scores])
    all_labels = np.concatenate([np.ones(len(gen_scores)),
                                 np.zeros(len(imp_scores))])

    # Threshold sweep for FAR / FRR / EER.
    sweep = []
    for t in np.arange(0.30, 0.95, 0.01):
        far = float((imp_scores >= t).mean())   # impostors accepted
        frr = float((gen_scores < t).mean())    # genuine rejected
        sweep.append({"threshold": round(float(t), 2),
                      "far": round(far, 6), "frr": round(frr, 6)})
    # EER: threshold where FAR and FRR curves cross.
    eer, eer_threshold = float("nan"), None
    prev = None
    for s in sweep:
        if prev is not None and (s["far"] - s["frr"]) * (prev["far"] - prev["frr"]) <= 0:
            eer_threshold = s["threshold"]
            eer = round((s["far"] + s["frr"]) / 2, 6)
            break
        prev = s

    # Operating point: default production threshold.
    t0 = 0.62
    tp = int((gen_scores >= t0).sum())
    fn = int((gen_scores < t0).sum())
    fp = int((imp_scores >= t0).sum())
    tn = int((imp_scores < t0).sum())
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    f1 = (2 * precision * recall / (precision + recall)
          if (tp + fp) and (tp + fn) and (precision + recall) else float("nan"))

    # Latency: similarity comparison cost.
    a, b = genuine[0]
    n_lat = 2000
    t_start = time.perf_counter()
    for _ in range(n_lat):
        _cosine(a, b)
    latency_ms = (time.perf_counter() - t_start) / n_lat * 1000

    return {
        "model": "Authetec face verification (cosine, deterministic embedder)",
        "model_version": MODEL_VERSION,
        "benchmark_class": "SYNTHETIC - not a research or production benchmark",
        "dataset": {
            "name": "authetec-synthetic-gaussian-identities",
            "version": "1.0",
            "seed": seed,
            "n_identities": n_identities,
            "genuine_pairs": len(gen_scores),
            "impostor_pairs": len(imp_scores),
            "embedding_dim": 64,
        },
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "python": platform.python_version(),
        },
        "metrics": {
            "roc_auc": round(_roc_auc(all_scores, all_labels), 6),
            "eer": eer,
            "eer_threshold": eer_threshold,
            "operating_threshold": t0,
            "far_at_threshold": round(fp / (fp + tn), 6) if fp + tn else None,
            "frr_at_threshold": round(fn / (fn + tp), 6) if fn + tp else None,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "similarity_latency_ms": round(latency_ms, 4),
        },
        "threshold_sweep": sweep,
        "limitations": [
            "SYNTHETIC data: Gaussian identity clusters, not real faces.",
            "Deterministic projection embedder, not a production biometric model.",
            "No liveness/PAD performance is measured here.",
            "Metrics MUST NOT be quoted as real-world identity-verification accuracy.",
            "Real validation requires labelled datasets (e.g. LFW for research) "
            "with a production embedder via the FaceEmbedder protocol.",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Face verification benchmark (SYNTHETIC)")
    parser.add_argument("--identities", type=int, default=120)
    parser.add_argument("--pairs", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    print("Running SYNTHETIC face verification benchmark...")
    result = evaluate(n_identities=args.identities,
                      pairs_per_identity=args.pairs, seed=args.seed)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS_DIR / f"Face_Verification_Synthetic_{stamp}.json"
    md_path = REPORTS_DIR / f"Face_Verification_Synthetic_{stamp}.md"
    json_path.write_text(json.dumps(result, indent=2))

    m = result["metrics"]
    md = [
        "# Benchmark Report - Face Verification (SYNTHETIC)",
        "",
        f"**Generated:** {result['generated_at']}",
        f"**Model:** {result['model']} ({result['model_version']})",
        f"**Benchmark class:** {result['benchmark_class']}",
        "",
        "## Dataset",
        f"- Name: {result['dataset']['name']} v{result['dataset']['version']}",
        f"- Identities: {result['dataset']['n_identities']}",
        f"- Genuine pairs: {result['dataset']['genuine_pairs']}",
        f"- Impostor pairs: {result['dataset']['impostor_pairs']}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| ROC-AUC | {m['roc_auc']} |",
        f"| EER | {m['eer']} @ threshold {m['eer_threshold']} |",
        f"| FAR @ {m['operating_threshold']} | {m['far_at_threshold']} |",
        f"| FRR @ {m['operating_threshold']} | {m['frr_at_threshold']} |",
        f"| Precision | {m['precision']} |",
        f"| Recall | {m['recall']} |",
        f"| F1 | {m['f1']} |",
        f"| Similarity latency | {m['similarity_latency_ms']} ms |",
        "",
        "## Limitations",
        *[f"- {lim}" for lim in result["limitations"]],
        "",
    ]
    md_path.write_text("\n".join(md))

    print(f"  ROC-AUC: {m['roc_auc']}  EER: {m['eer']} @ {m['eer_threshold']}")
    print(f"  FAR/FRR @ {m['operating_threshold']}: "
          f"{m['far_at_threshold']}/{m['frr_at_threshold']}")
    print(f"  Precision: {m['precision']}  Recall: {m['recall']}  F1: {m['f1']}")
    print(f"  JSON report: {json_path}")
    print(f"  MD report:   {md_path}")
    print("\n  NOTE: SYNTHETIC results only - not real-world accuracy evidence.")


if __name__ == "__main__":
    main()
