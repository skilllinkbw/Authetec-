# Benchmark Report ¡ª Graph Fraud Detection (GraphSAGE Surrogate)

**Generated:** 2026-09-03T22:32:31.719504
**Model ID:** graph_fraud_823c0c44

## Dataset
- Name: Synthetic Transaction Graph (Cifer-AF schema replica)
- Version: synthetic-v1
- Source: https://huggingface.co/datasets/CiferAI/Cifer-Fraud-Detection-Dataset-AF

## Data Splits
- Train: 80% stratified
- Validation: N/A
- Test: 20% stratified

## Features
feat_00, feat_01, feat_02, feat_03, feat_04, feat_05, feat_06, feat_07, feat_08, feat_09, feat_10, feat_11, agg_feat_00, agg_feat_01, agg_feat_02, agg_feat_03, agg_feat_04, agg_feat_05, agg_feat_06, agg_feat_07, agg_feat_08, agg_feat_09, agg_feat_10, agg_feat_11

## Metrics

| Metric | Value |
|--------|-------|
| accuracy | 1.000000 |
| f1 | 1.000000 |
| false_negative_rate | 0.000000 |
| false_positive_rate | 0.000000 |
| pr_auc | 1.000000 |
| precision | 1.000000 |
| recall | 1.000000 |
| roc_auc | 1.000000 |

**Decision Threshold:** 0.5
**Latency:** 0.00 ms

## Leakage Analysis
Graph aggregation uses only local neighborhood. Original uses NeighborLoader for mini-batch sampling.

## Reproducibility
{
  "random_state": 42,
  "git_commit": "823c0c448880728c9cbdc618b3a93c1a539ded73",
  "license": "MIT",
  "train_info": {
    "model": "GraphSAGE-Surrogate",
    "n_train": 2400,
    "n_test": 600
  }
}

## Limitations
- GraphSAGE replaced with sklearn surrogate
- Metrics on synthetic graph data
- Original low precision (0.1179) due to 0.1% fraud rate
