# Benchmark Report ¡ª Ensemble Fraud Detection

**Generated:** 2026-08-30T20:15:59.446603
**Model ID:** ensemble_fraud_cdd20d95

## Dataset
- Name: Synthetic Transaction Data (ensemble schema replica)
- Version: synthetic-v1
- Source: N/A (synthetic)

## Data Splits
- Train: 80% stratified
- Validation: Built-in holdout
- Test: 20% stratified

## Features
V01, V02, V03, V04, V05, V06, V07, V08, V09, V10, V11, V12, V13, V14, V15, V16, V17, V18, V19, V20, V21, V22, V23, V24, V25, V26, V27, V28, V29, V30, Amount, Time

## Metrics

| Metric | Value |
|--------|-------|
| f1 | 0.750000 |
| false_negative_rate | 0.000000 |
| false_positive_rate | 0.025000 |
| pr_auc | 0.944444 |
| precision | 0.600000 |
| recall | 1.000000 |
| roc_auc | 0.996753 |

**Decision Threshold:** 0.5
**Latency:** 0.09 ms

## Leakage Analysis
Synthetic data with explicit train/test split.

## Reproducibility
{
  "random_state": 42,
  "git_commit": "cdd20d957ff616f50e95e029dd5c274714c5754d",
  "license": "MIT",
  "train_info": {
    "model": "Ensemble",
    "n_train": 640,
    "n_test": 160,
    "estimators": [
      "rf",
      "lr"
    ]
  }
}

## Limitations
- Metrics on synthetic data
- Reported repo metrics not Authetec-validated
- Does not reproduce real-time streaming architecture
