"""Ensemble Fraud Adapter — wraps repo2 (sunnynguyen-ai/fraud-detection-system)."""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, f1_score, precision_score,
    recall_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from .base import BaseBenchmarkAdapter, BenchmarkResult


class EnsembleFraudAdapter(BaseBenchmarkAdapter):
    """Adapter for repo2: sunnynguyen-ai/fraud-detection-system (MIT, cdd20d9)."""
    adapter_name = "ensemble_fraud"
    repo_full_name = "sunnynguyen-ai/fraud-detection-system"
    repo_commit = "cdd20d957ff616f50e95e029dd5c274714c5754d"
    repo_license = "MIT"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._model = None
        self._feature_names: List[str] = []
        self.random_state = config.get("random_state", 42) if config else 42

    def metadata(self) -> Dict[str, Any]:
        return {
            "adapter": self.adapter_name, "repo": self.repo_full_name,
            "commit": self.repo_commit, "license": self.repo_license,
            "purpose": "transaction fraud — ensemble RF + XGBoost + LR + SHAP",
            "original_metrics": {"precision": 0.942, "recall": 0.897, "f1": 0.919, "roc_auc": 0.968},
            "note": "Metrics from benchmark README; NOT Authetec-validated.",
        }

    def validate_environment(self) -> bool:
        for pkg in ("sklearn", "numpy", "pandas", "shap"):
            if importlib.util.find_spec(pkg) is None:
                print(f"  [FAIL] {pkg}")
                return False
        return True

    def _generate_synthetic_data(self, n: int = 10_000) -> Any:
        import pandas as pd
        rng = np.random.RandomState(self.random_state)
        n_features = 30
        X = rng.randn(n, n_features)
        n_fraud = int(n * 0.035)
        fraud_idx = rng.choice(n, n_fraud, replace=False)
        X[fraud_idx, :5] += 1.5
        feature_names = [f"V{i:02d}" for i in range(1, n_features + 1)]
        y = np.zeros(n, dtype=int)
        y[fraud_idx] = 1
        df = pd.DataFrame(X, columns=feature_names)
        df["Amount"] = rng.exponential(scale=150, size=n)
        df["Time"] = rng.uniform(0, 172800, size=n)
        df["isFraud"] = y
        return df

    def prepare_data(self, **kwargs: Any) -> Any:
        df = self._generate_synthetic_data(kwargs.get("n_samples", 10_000))
        feature_cols = [c for c in df.columns if c != "isFraud"]
        self._feature_names = feature_cols
        return train_test_split(df[feature_cols].values, df["isFraud"].values,
                                test_size=0.2, stratify=df["isFraud"].values, random_state=self.random_state)

    def train(self, **kwargs: Any) -> Dict[str, Any]:
        X_train, X_test, y_train, y_test = self.prepare_data(**kwargs)
        estimators = [
            ("rf", RandomForestClassifier(n_estimators=100, max_depth=12,
              class_weight="balanced", random_state=self.random_state, n_jobs=1)),
            ("lr", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=self.random_state)),
        ]
        try:
            from xgboost import XGBClassifier
            estimators.append(("xgb", XGBClassifier(n_estimators=100, max_depth=6,
              learning_rate=0.1, eval_metric="logloss", random_state=self.random_state, n_jobs=1, verbosity=0)))
        except ImportError:
            pass
        self._model = VotingClassifier(estimators=estimators, voting="soft", n_jobs=1)
        self._model.fit(X_train, y_train)
        self._trained = True
        self._X_test, self._y_test = X_test, y_test
        return {"model": "Ensemble", "n_train": len(X_train), "n_test": len(X_test),
                "estimators": [e[0] for e in estimators]}

    def predict(self, X: Any) -> Any:
        if self._model is None:
            raise RuntimeError("Call train() first.")
        return self._model.predict(X)

    def predict_proba(self, X: Any) -> Any:
        if self._model is None:
            raise RuntimeError("Call train() first.")
        return self._model.predict_proba(X)[:, 1]

    def explain(self, X: Any) -> Dict[str, Any]:
        if self._model is None:
            raise RuntimeError("Call train() first.")
        try:
            import shap
            rf = self._model.named_estimators_.get("rf")
            if rf is None:
                rf = list(self._model.named_estimators_.values())[0]
            explainer = shap.TreeExplainer(rf)
            shap_values = explainer.shap_values(X)
            return {"method": "shap_tree", "shap_values": shap_values.tolist(),
                    "feature_names": self._feature_names}
        except ImportError:
            rf = self._model.named_estimators_.get("rf")
            if rf:
                imp = rf.feature_importances_
            else:
                imp = np.zeros(len(self._feature_names))
            return {"method": "feature_importance", "importances": imp.tolist(),
                    "feature_names": self._feature_names}

    def evaluate(self, **kwargs: Any) -> BenchmarkResult:
        train_info = self.train(**kwargs)
        import time as _time
        t0 = _time.perf_counter()
        y_prob = self.predict_proba(self._X_test)
        latency = (_time.perf_counter() - t0) * 1000 / len(self._X_test)
        y_pred = (y_prob >= 0.5).astype(int)
        y_test = self._y_test
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
            model_name="Ensemble Fraud Detection",
            model_version=f"benchmark@{self.repo_commit[:8]}",
            dataset_name="Synthetic Transaction Data (ensemble schema replica)",
            dataset_version="synthetic-v1", dataset_url="N/A (synthetic)",
            features=self._feature_names[:50],
            train_split="80% stratified", validation_split="Built-in holdout",
            test_split="20% stratified", metrics=metrics, threshold=0.5,
            latency_ms=latency,
            leakage_notes="Synthetic data with explicit train/test split.",
            reproducibility_info={"random_state": self.random_state, "git_commit": self.repo_commit,
                                  "license": self.repo_license, "train_info": train_info},
            limitations=["Metrics on synthetic data", "Reported repo metrics not Authetec-validated",
                         "Does not reproduce real-time streaming architecture"],
        )
        from benchmarks.evaluation.reporter import save_results
        result.report_path = save_results(result)
        return result

    def save_model(self, path: str) -> str:
        import joblib
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        joblib.dump(self._model, path)
        return path

    def load_model(self, path: str) -> None:
        import joblib
        self._model = joblib.load(path)
        self._trained = True
