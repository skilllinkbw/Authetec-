# Benchmark Report ¡ª Fraud Risk Pipeline (Random Forest)

**Generated:** 2026-09-03T22:32:30.262641
**Model ID:** fraud_risk_pipeline_781280ed

## Dataset
- Name: Synthetic AIML-Dataset replica
- Version: synthetic-v1
- Source: N/A (synthetic)

## Data Splits
- Train: 80% stratified (leakage-controlled)
- Validation: N/A
- Test: 20% stratified

## Features
step, amount_to_oldbalanceOrg, origin_zero_after_txn, origin_drained_flag, log_amount, hour_of_day, day_index, is_weekend_proxy, type_CASH_IN, type_CASH_IN_x_amount, type_CASH_OUT, type_CASH_OUT_x_amount, type_DEBIT, type_DEBIT_x_amount, type_PAYMENT, type_PAYMENT_x_amount, type_TRANSFER, type_TRANSFER_x_amount, high_amount_flag, origin_recon_mismatch_flag, dest_recon_mismatch_flag, strong_suspicion_flag

## Metrics

| Metric | Value |
|--------|-------|
| f1 | 0.500000 |
| false_negative_rate | 0.001667 |
| false_positive_rate | 0.001667 |
| pr_auc | 0.312500 |
| precision | 0.500000 |
| recall | 0.500000 |
| roc_auc | 0.987458 |

**Decision Threshold:** 0.5
**Latency:** 0.06 ms

## Leakage Analysis
Excluded isFlaggedFraud, nameOrig/nameDest, oldBalanceOrg. class_weight='balanced' (no SMOTE).

## Reproducibility
{
  "random_state": 42,
  "git_commit": "781280ed784f07ea781d48f4b6f04fc9bd4a0d69",
  "license": "NOT FOUND (no license file in repo)",
  "train_info": {
    "model": "RandomForest",
    "n_train": 2400,
    "n_test": 600,
    "fraud_rate_test": 0.0033333333333333335
  }
}

## Limitations
- Metrics on synthetic data
- Original 6.3M-row metrics not reproduced
