# AUTHeTEC Biometric Benchmark & Dataset Guide

This document describes how to run the native AUTHeTEC biometric benchmark,
prepare a real dataset, interpret results, and configure regression gates.

It is intended for any engineer who needs to reproduce or extend biometric
validation **without** reading the master build prompt.

---

## 1. What the benchmark measures

| Module | Measures |
|---|---|
| `VerificationBenchmark` | genuine vs impostor verification: TP/TN/FP/FN, FAR, FRR, precision, recall, F1, accuracy, ROC-AUC, EER |
| `ThresholdAnalysis` | FAR/FRR curves, EER, selected operating point across thresholds |
| `PadBenchmark` | APCER / BPCER / ACER + per-attack-type acceptance rates |
| `PerformanceBenchmark` | detection/alignment/embedding/PAD/end-to-end latency (p50/p95/p99) + throughput |

All metrics are computed **from actual predictions** — nothing is hard-coded.

## 2. Running the benchmark

Synthetic-fixture run (no dataset required; pipeline self-test only):

```bash
python -m benchmarks.biometric.runner --provider deterministic --output benchmark_out
```

Real-dataset run:

```bash
python -m benchmarks.biometric.runner \
    --manifest /path/to/manifest.json \
    --provider deterministic \
    --threshold 0.62 \
    --seed 42 \
    --output benchmark_out
```

Native provider (YuNet + SFace + AUTHeTEC PAD) — requires the ONNX models
installed **and** integrity-verified:

```bash
python -m benchmarks.biometric.runner --provider native --output benchmark_out
```

If native is requested but model integrity checks fail, the runner **aborts**
(fail-safe) instead of running with a half-configured stack.

Outputs (in `--output`):
- `benchmark_results.json` — machine-readable results incl. environment, config, dataset provenance, all metrics, gate outcomes.
- `BIOMETRIC_BENCHMARK_REPORT.md` — human-readable report.

Every run records: timestamp, Git commit, model versions, dataset version,
threshold, seed, hardware, and software versions.

## 3. Dataset format

Datasets are referenced by a JSON **manifest**. No biometric image data is
committed to Git. Identities are pseudonymous (`s0001`). The manifest must
declare provenance (source, version, license, permitted usage) and one
`samples` array per file:

```json
{
  "name": "my-dataset",
  "version": "1.0.0",
  "source": "https://... or internal provenance",
  "license": "e.g. research-only, custom-commercial",
  "permitted_usage": "research",
  "notes": "free text",
  "samples": [
    {"subject_id": "s0001", "path": "eval/s0001_01.jpg",
     "split": "eval", "label": 1, "attack_type": ""},
    {"subject_id": "s0001", "path": "eval/s0001_02.jpg",
     "split": "eval", "label": 1, "attack_type": ""},
    {"subject_id": "s0001", "path": "eval/s0001_attack_print.jpg",
     "split": "eval", "label": 0, "attack_type": "print"}
  ]
}
```

- `label`: `1` = bona-fide (live), `0` = presentation attack.
- `attack_type`: only for attacks; examples `print`, `screen`, `replay`.
- Paths are relative to the manifest file; supported formats: jpg/png/tiff/bmp/webp.
- Splits must be identity-disjoint: `load_dataset` flags **IDENTITY LEAKAGE**
  if a subject appears in more than one split.
- Corrupt images, duplicate files (by SHA-256), checksum mismatches, and
  missing attack types are all detected and reported in `integrity_issues`.

## 4. Privacy & hygiene

- Biometric images are never written into reports, logs, or result JSON.
- Only pseudonymous subject IDs and checksums are recorded.
- `.gitignore` refuses raw image files and `benchmarks/biometric/data/`,
  `datasets/`, `datasets_biometric/` by default.
- Add real datasets through the manifest path; do not copy samples into the repo.

## 5. Interpreting results — synthetic vs real

- A run whose dataset name is `synthetic-fixture` is **SYNTHETIC ONLY**: it
  exercises the pipeline but is **not** real-world evidence. The report header
  states this and Section 16 is auto-set to **NOT READY**.
- Real-world validation requires lawful labelled data. The exact remaining
  requirement is: genuine + impostor pairs and labelled presentation-attack
  samples (ideally print/screen/replay) with an identity-disjoint split and
  documented licence permitting your deployment.

## 6. Regression gates

Gates are defined in `benchmarks/biometric/regression_gates.py`. Each gate is
either:

- `ENGINEERING_REGRESSION_GATE` — catches broken pipelines / gross regressions
  (e.g. `max_p95_latency_ms`, `min_rocauc`).
- `PRODUCTION_ACCEPTANCE_REQUIREMENT` — a threshold that needs legitimate
  scientific justification from dataset/analysis before it can be enforced.

Unconfigured gates are reported as **SKIPPED / CONFIGURATION REQUIRED** —
never silently assumed. Configure limits per run via the `gates` dict in
`benchmarks/biometric/config.py` (`BenchmarkConfig.gates`).

See `RegressionGateSet` for the gate names (`max_far`, `min_f1`, `max_apcer`,
`max_bpcer`, `max_acer`, …).

## 7. Model integrity

`benchmarks/biometric/model_integrity.py` verifies every model file in
`models/model_pins.json` against its recorded SHA-256. Status per model:
`OK` / `NOT_FOUND` / `HASH_MISMATCH`. Native providers are allowed to activate
only when all pins verify; otherwise the runner and `bootstrap_face_provider`
fail safe to the deterministic fallback.

`assert_embeddings_finite` rejects NaN/Inf embeddings — a model producing one
is treated as failed, never as a match.