"""Graph Fraud Adapter — wraps repo5 (tio121/financial-fraud-detector)."""
from __future__ import annotations
import importlib.util, os
from typing import Any, Dict, List, Optional
import numpy as np
from sklearn.metrics import (
    average_precision_score, f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from .base import BaseBenchmarkAdapter, BenchmarkResult

class GraphFraudAdapter(BaseBenchmarkAdapter):
    """Adapter for repo5: tio121/financial-fraud-detector (MIT, 823c0c4).
    GraphSAGE-based.  Uses sklearn surrogate for envs without PyTorch Geometric."""
    adapter_name = "graph_fraud"
    repo_full_name = "tio121/financial-fraud-detector"
    repo_commit = "823c0c448880728c9cbdc618b3a93c1a539ded73"
    repo_license = "MIT"

    def __init__(self, config=None):
        super().__init__(config)
        self._model = None
        self._feature_names: List[str] = []
        self.random_state = 42

    def metadata(self) -> Dict[str, Any]:
        return {"adapter": self.adapter_name, "repo": self.repo_full_name,
                "commit": self.repo_commit, "license": self.repo_license,
                "purpose": "graph fraud — GraphSAGE surrogate with aggregation patterns",
                "original_metrics": {"accuracy": 0.9665, "precision": 0.1179,
                                     "recall": 0.9424, "f1": 0.2096},
                "note": "Original GraphSAGE metrics from 21M-hf dataset; NOT Authetec-validated."}

    def validate_environment(self) -> bool:
        return all(importlib.util.find_spec(p) is not None
                   for p in ("sklearn", "numpy", "pandas"))

    def _generate_graph_data(self, n=10_000):
        """Generate synthetic transaction graph: node features + edge list."""
        rng = np.random.RandomState(self.random_state)
        n_fraud = max(int(n * 0.001), 10)
        if n_fraud >= n:
            n_fraud = n // 2
        y = np.zeros(n, dtype=int)
        fraud_idx = rng.choice(n, n_fraud, replace=False)
        y[fraud_idx] = 1
        X = rng.randn(n, 12)
        X[fraud_idx] += 2.0  # fraud signal
        edges = []
        for i in range(n):
            targets = rng.choice(n, rng.randint(1, 5), replace=False)
            for t in targets:
                edges.append((i, int(t)))
        for i in range(0, len(fraud_idx) - 1, 2):
            if i + 1 < len(fraud_idx):
                edges.append((int(fraud_idx[i]), int(fraud_idx[i + 1])))
        feat_names = [f"feat_{i:02d}" for i in range(12)]
        return X, y, feat_names, edges

    def _graph_aggregation_features(self, X, edges):
        """GraphSAGE-style mean pooling of neighbor features with skip connection."""
        n = X.shape[0]
        agg = np.zeros_like(X)
        counts = np.zeros(n)
        for src, dst in edges:
            if src < n and dst < n:
                agg[dst] += X[src]
                counts[dst] += 1
        counts = np.maximum(counts, 1)
        return np.hstack([X, agg / counts[:, np.newaxis]])

    def prepare_data(self, **kwargs):
        X, y, feat_names, edges = self._generate_graph_data(kwargs.get("n_samples", 10_000))
        X_agg = self._graph_aggregation_features(X, edges)
        self._feature_names = feat_names + [f"agg_{f}" for f in feat_names]
        return train_test_split(X_agg, y, test_size=0.2, stratify=y,
                                random_state=self.random_state)

    def train(self, **kwargs):
        X_train, X_test, y_train, y_test = self.prepare_data(**kwargs)
        self._model = LogisticRegression(class_weight="balanced", max_iter=1000,
                                         random_state=self.random_state)
        self._model.fit(X_train, y_train)
        self._trained = True; self._X_test, self._y_test = X_test, y_test
        return {"model": "GraphSAGE-Surrogate", "n_train": len(X_train), "n_test": len(X_test)}

    def predict(self, X):
        if self._model is None: raise RuntimeError("Call train() first.")
        return self._model.predict(X)

    def predict_proba(self, X):
        if self._model is None: raise RuntimeError("Call train() first.")
        return self._model.predict_proba(X)[:, 1]

    def explain(self, X):
        if self._model is None: raise RuntimeError("Call train() first.")
        return {"method": "coefficient_magnitude",
                "importances": np.abs(self._model.coef_[0]).tolist(),
                                "feature_names": self._feature_names}

    def evaluate(self, **kwargs):
        train_info = self.train(**kwargs)
        import time as _t; t0 = _t.perf_counter()
        y_prob = self.predict_proba(self._X_test)
        latency = (_t.perf_counter() - t0) * 1000 / len(self._X_test)
        y_pred = (y_prob >= 0.5).astype(int); y_test = self._y_test
        metrics = {
            "pr_auc": float(average_precision_score(y_test, y_prob)),
            "roc_auc": float(roc_auc_score(y_test, y_prob)),
            "precision": float(precision_score(y_test, y_pred, zero_division=0)),
            "recall": float(recall_score(y_test, y_pred, zero_division=0)),
            "f1": float(f1_score(y_test, y_pred, zero_division=0)),
            "false_positive_rate": float(np.mean((y_pred == 1) & (y_test == 0))),
            "false_negative_rate": float(np.mean((y_pred == 0) & (y_test == 1))),
            "accuracy": float(np.mean(y_pred == y_test)),
        }
        result = BenchmarkResult(
            model_id=f"{self.adapter_name}_{self.repo_commit[:8]}",
            model_name="Graph Fraud Detection (GraphSAGE Surrogate)",
            model_version=f"benchmark@{self.repo_commit[:8]}",
            dataset_name="Synthetic Transaction Graph (Cifer-AF schema replica)",
            dataset_version="synthetic-v1",
            dataset_url="https://huggingface.co/datasets/CiferAI/Cifer-Fraud-Detection-Dataset-AF",
            features=self._feature_names,
            train_split="80% stratified", validation_split="N/A",
            test_split="20% stratified", metrics=metrics, threshold=0.5,
            latency_ms=latency,
            leakage_notes="Graph aggregation uses only local neighborhood. "
                          "Original uses NeighborLoader for mini-batch sampling.",
            reproducibility_info={"random_state": self.random_state, "git_commit": self.repo_commit,
                                  "license": self.repo_license, "train_info": train_info},
            limitations=["GraphSAGE replaced with sklearn surrogate",
                         "Metrics on synthetic graph data",
                         "Original low precision (0.1179) due to 0.1% fraud rate"],
        )
        from benchmarks.evaluation.reporter import save_results
        result.report_path = save_results(result)
        return result

    def save_model(self, path: str):
        import joblib
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        joblib.dump({"model": self._model, "features": self._feature_names}, path)
        return path

    def load_model(self, path: str):
        import joblib
        data = joblib.load(path)
        self._model = data["model"]
        self._feature_names = data.get("features", [])
        self._trained = True
