"""Insurance Fraud Adapter — wraps repo4 (akhilkarumanchi05)."""
from __future__ import annotations
import importlib.util, os
from typing import Any, Dict, List, Optional
import numpy as np
from sklearn.metrics import (
    average_precision_score, f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from .base import BaseBenchmarkAdapter, BenchmarkResult

class InsuranceFraudAdapter(BaseBenchmarkAdapter):
    """Adapter for repo4: capstone-insurance-fraud-detection (no license, 9b57aa2).
    Extracts reusable fraud-scoring patterns (NOT insurance-specific core logic)."""
    adapter_name = "insurance_fraud"
    repo_full_name = "akhilkarumanchi05/capstone-insurance-fraud-detection"
    repo_commit = "9b57aa27174c90ee0fd8cf460dac77ca623997ae"
    repo_license = "NOT FOUND (no license file in repo)"

    def __init__(self, config=None):
        super().__init__(config)
        self._model = None
        self._feature_names: List[str] = []
        self.random_state = 42

    def metadata(self) -> Dict[str, Any]:
        return {"adapter": self.adapter_name, "repo": self.repo_full_name,
                "commit": self.repo_commit, "license": self.repo_license,
                "purpose": "claim fraud — RF + XGBoost + SVM (pattern extraction only)",
                "original_metrics": {"precision": 0.99, "recall": 0.98, "f1": 0.98, "accuracy": 0.97},
                "note": "Original metrics from Zenodo insurance dataset; NOT Authetec-validated.",
                "production_suitability": "BENCHMARK_ONLY"}

    def validate_environment(self) -> bool:
        return all(importlib.util.find_spec(p) is not None
                   for p in ("sklearn", "numpy", "pandas"))

    def _generate_synthetic(self, n=5_000):
        import pandas as pd
        rng = np.random.RandomState(self.random_state)
        n_fraud = int(n * 0.15)
        y = np.zeros(n, dtype=int)
        fraud_idx = rng.choice(n, n_fraud, replace=False)
        y[fraud_idx] = 1
        data = {
            "Claim_Amount": rng.exponential(scale=2000, size=n),
            "Policy_Term": rng.randint(1, 12, size=n),
            "Police_Report_Filed": rng.randint(0, 2, size=n),
            "Financial_Hardship": rng.randint(0, 2, size=n),
            "High_Risk_Indicator": rng.randint(0, 2, size=n),
            "Age": rng.randint(18, 80, size=n),
            "Vehicle_Damage": rng.randint(0, 2, size=n),
            "Total_Claim_Amount": rng.exponential(scale=2000, size=n),
        }
        for idx in fraud_idx:
            data["Claim_Amount"][idx] *= 5
            data["Police_Report_Filed"][idx] = 1
            data["Financial_Hardship"][idx] = 1
        df = pd.DataFrame(data); df["isFraud"] = y; return df

    def prepare_data(self, **kwargs):
        df = self._generate_synthetic(kwargs.get("n_samples", 5_000))
        feature_cols = [c for c in df.columns if c != "isFraud"]
        self._feature_names = feature_cols
        return train_test_split(df[feature_cols].values, df["isFraud"].values,
                                test_size=0.2, stratify=df["isFraud"].values, random_state=self.random_state)

    def train(self, **kwargs):
        X_train, X_test, y_train, y_test = self.prepare_data(**kwargs)
        self._model = RandomForestClassifier(n_estimators=200, max_depth=12,
            class_weight="balanced", random_state=self.random_state, n_jobs=1)
        self._model.fit(X_train, y_train)
        self._trained = True; self._X_test, self._y_test = X_test, y_test
        return {"model": "RandomForest", "n_train": len(X_train), "n_test": len(X_test)}

    def predict(self, X):
        if self._model is None: raise RuntimeError("Call train() first.")
        return self._model.predict(X)

    def predict_proba(self, X):
        if self._model is None: raise RuntimeError("Call train() first.")
        return self._model.predict_proba(X)[:, 1]

    def explain(self, X):
        if self._model is None: raise RuntimeError("Call train() first.")
        return {"method": "feature_importance",
                "importances": self._model.feature_importances_.tolist(),
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
        }
        result = BenchmarkResult(
            model_id=f"{self.adapter_name}_{self.repo_commit[:8]}",
            model_name="Insurance Fraud (Pattern Adapter)",
            model_version=f"benchmark@{self.repo_commit[:8]}",
            dataset_name="Synthetic Insurance Claim Data (reusable pattern)",
            dataset_version="synthetic-v1", dataset_url="N/A (synthetic)",
            features=self._feature_names,
            train_split="80% stratified", validation_split="N/A",
            test_split="20% stratified", metrics=metrics, threshold=0.5,
            latency_ms=latency,
            leakage_notes="No label leakage. Original repo used SMOTE after split.",
            reproducibility_info={"random_state": self.random_state, "git_commit": self.repo_commit,
                                  "license": self.repo_license, "train_info": train_info},
            limitations=["NOT insurance-specific", "Metrics on synthetic data",
                         "Does not reproduce XGBoost/SVM"],
        )
        from benchmarks.evaluation.reporter import save_results
        result.report_path = save_results(result)
        return result

    def save_model(self, path: str):
        import joblib; os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        joblib.dump(self._model, path); return path

    def load_model(self, path: str):
        import joblib; self._model = joblib.load(path); self._trained = True
