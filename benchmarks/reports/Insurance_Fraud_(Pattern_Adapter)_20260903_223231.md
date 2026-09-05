# Benchmark Report ¡ª Insurance Fraud (Pattern Adapter)

**Generated:** 2026-09-03T22:32:31.223071
**Model ID:** insurance_fraud_9b57aa27

## Dataset
- Name: Synthetic Insurance Claim Data (reusable pattern)
- Version: synthetic-v1
- Source: N/A (synthetic)

## Data Splits
- Train: 80% stratified
- Validation: N/A
- Test: 20% stratified

## Features
Claim_Amount, Policy_Term, Police_Report_Filed, Financial_Hardship, High_Risk_Indicator, Age, Vehicle_Damage, Total_Claim_Amount

## Metrics

| Metric | Value |
|--------|-------|
| f1 | 0.707547 |
| false_negative_rate | 0.025000 |
| false_positive_rate | 0.078333 |
| pr_auc | 0.870195 |
| precision | 0.614754 |
| recall | 0.833333 |
| roc_auc | 0.965969 |

**Decision Threshold:** 0.5
**Latency:** 0.05 ms

## Leakage Analysis
No label leakage. Original repo used SMOTE after split.

## Reproducibility
{
  "random_state": 42,
  "git_commit": "9b57aa27174c90ee0fd8cf460dac77ca623997ae",
  "license": "NOT FOUND (no license file in repo)",
  "train_info": {
    "model": "RandomForest",
    "n_train": 2400,
    "n_test": 600
  }
}

## Limitations
- NOT insurance-specific
- Metrics on synthetic data
- Does not reproduce XGBoost/SVM
