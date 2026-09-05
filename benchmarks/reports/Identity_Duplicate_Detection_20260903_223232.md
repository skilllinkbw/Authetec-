# Benchmark Report ¡ª Identity Duplicate Detection

**Generated:** 2026-09-03T22:32:32.022691
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
| f1 | 0.860215 |
| false_negative_rate | 0.000000 |
| false_positive_rate | 0.043333 |
| pr_auc | 0.999405 |
| precision | 0.754717 |
| recall | 1.000000 |
| roc_auc | 0.999904 |

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
    "n_train": 2400,
    "n_test": 600
  }
}

## Limitations
- Original uses InsightFace + ChromaDB (not reproduced here)
- Contains sample biometric images in upstream repo (NOT committed)
- Metrics on synthetic data
