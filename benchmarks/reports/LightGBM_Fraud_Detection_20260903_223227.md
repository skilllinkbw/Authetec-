# Benchmark Report ¡ª LightGBM Fraud Detection

**Generated:** 2026-09-03T22:32:27.117087
**Model ID:** lightgbm_fraud_f257efc2

## Dataset
- Name: Synthetic Financial Transactions (Kaggle schema replica)
- Version: synthetic-v1
- Source: https://www.kaggle.com/datasets/aryan208/financial-transactions-dataset-for-fraud-detection

## Data Splits
- Train: 80% stratified
- Validation: N/A
- Test: 20% stratified holdout

## Features
amount, oldbalanceOrg, delta_orig, delta_dest, is_weekend, is_night, sender_avg_amount, sender_txn_count, balance_jump_flag, delta_orig_ratio, is_c_to_c, type_CASH_IN, type_CASH_OUT, type_DEBIT, type_PAYMENT, type_TRANSFER

## Metrics

| Metric | Value |
|--------|-------|
| f1 | 0.227273 |
| false_negative_rate | 0.030000 |
| false_positive_rate | 0.026667 |
| pr_auc | 0.260718 |
| precision | 0.238095 |
| recall | 0.217391 |
| roc_auc | 0.895110 |

**Decision Threshold:** 0.5
**Latency:** 0.03 ms

## Leakage Analysis
Excluded newbalance* and isFlaggedFraud. SMOTE applied only after split.

## Reproducibility
{
  "random_state": 42,
  "git_commit": "f257efc2973e7007aca146edd7f5621930343a0c",
  "license": "MIT",
  "train_info": {
    "model": "LightGBM",
    "smote_applied": false,
    "n_train": 2400,
    "n_test": 600,
    "fraud_rate_test": 0.03833333333333333
  }
}

## Limitations
- Metrics on synthetic data, NOT original Kaggle dataset
- Reported repo metrics (0.9885 P / 0.9988 R) are benchmark-test-set values
- Latency approximated, not measured in production
