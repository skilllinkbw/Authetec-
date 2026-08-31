# Benchmark Report ¡ª Identity Duplicate Detection

**Generated:** 2026-08-30T20:16:00.261244
**Model ID:** identity_duplicate_095b0da8

## Dataset
- Name: Synthetic Identity Pairs (reusable pattern)
- Version: synthetic-v1
- Source: N/A (synthetic)

## Data Splits
- Train: 80% stratified
- Validation: N/A
- Test: 20% stratified

## Features
face_similarity, name_similarity, address_similarity, duplicate_flag, liveness_score, raw_fraud_score

## Metrics

| Metric | Value |
|--------|-------|
| f1 | 0.826087 |
| false_negative_rate | 0.000000 |
| false_positive_rate | 0.050000 |
| pr_auc | 0.994987 |
| precision | 0.703704 |
| recall | 1.000000 |
| roc_auc | 0.999253 |

**Decision Threshold:** 0.5
**Latency:** 0.00 ms

## Leakage Analysis
Score fusion with weighted signals. No temporal leakage.

## Reproducibility
{
  "random_state": 42,
  "git_commit": "095b0da82ec200a52c3875409761b447cf353e4d",
  "license": "NOT FOUND (no license file in repo)",
  "train_info": {
    "model": "ScoreFusion-LR",
    "n_train": 640,
    "n_test": 160
  }
}

## Limitations
- Original uses InsightFace + ChromaDB (not reproduced here)
- Contains sample biometric images in upstream repo (NOT committed)
- Metrics on synthetic data
