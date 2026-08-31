"""FraudRiskPipeline Adapter — wraps repo3 (jeganathan-duraisamy/fraud-risk-detection)."""
from __future__ import annotations
import importlib.util, os
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score, f1_score, precision_score,
    recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from .base import BaseBenchmarkAdapter, BenchmarkResult

class FraudRiskPipelineAdapter(BaseBenchmarkAdapter):
    """Adapter for repo3: jeganathan-duraisamy/fraud-risk-detection (no license, 781280e)."""
    adapter_name = "fraud_risk_pipeline"
    repo_full_name = "jeganathan-duraisamy/fraud-risk-detection"
    repo_commit = "781280ed784f07ea781d48f4b6f04fc9bd4a0d69"
    repo_license = "NOT FOUND (no license file in repo)"

    def __init__(self, config=None):
        super().__init__(config)
        self._model = None
        self._feature_names: List[str] = []
        self.random_state = 42

    def metadata(self) -> Dict[str, Any]:
        return {"adapter": self.adapter_name, "repo": self.repo_full_name,
                "commit": self.repo_commit, "license": self.repo_license,
                "purpose": "transaction fraud — RF + leakage-controlled pipeline",
                "original_metrics": {"pr_auc": 0.999, "roc_auc": 0.9991, "precision": 1.0, "recall": 1.0},
                "note": "Original metrics from 6.3M-row AIML dataset; NOT Authetec-validated."}

    def validate_environment(self) -> bool:
        for pkg in ("sklearn", "numpy", "pandas"):
            if importlib.util.find_spec(pkg) is None:
                return False
        return True

    def _generate_synthetic(self, n=10_000):
        """Generate data matching repo3 AIML Dataset schema."""
        import pandas as pd
        rng = np.random.RandomState(self.random_state)
        types = rng.choice(["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"],
                            size=n, p=[0.30, 0.35, 0.05, 0.15, 0.15])
        amounts = rng.exponential(scale=1500, size=n)
        old_bal_orig = rng.exponential(scale=5000, size=n)
        new_bal_orig = np.maximum(old_bal_orig - amounts, 0)
        is_fraud = np.zeros(n, dtype=int)
        n_fraud = max(int(n * 0.0013), 10)
        fraud_mask = np.zeros(n, dtype=bool)
        idx = rng.choice(n, min(n_fraud, n // 2), replace=False)
        fraud_mask[idx] = True
        is_fraud[fraud_mask] = 1
        amounts[fraud_mask] *= 10
        new_bal_orig[fraud_mask] = 0
        return pd.DataFrame({
            "step": rng.randint(1, 1000, size=n), "type": types,
            "amount": amounts, "oldbalanceOrg": old_bal_orig,
            "newbalanceOrig": new_bal_orig,
            "oldbalanceDest": rng.exponential(scale=5000, size=n),
            "newbalanceDest": old_bal_orig + amounts,
            "isFraud": is_fraud, "isFlaggedFraud": np.zeros(n, dtype=int),
        })

    def _engineer_features(self, df):
        """Mirror repo3's 4 categories: amount, time, interaction, signal."""
        df["amount_to_oldbalanceOrg"] = np.where(df["oldbalanceOrg"] > 0,
            df["amount"] / df["oldbalanceOrg"], 0)
        df["origin_zero_after_txn"] = (df["newbalanceOrig"] == 0).astype(int)
        df["origin_drained_flag"] = ((df["oldbalanceOrg"] > 0) &
            (np.abs(df["oldbalanceOrg"] - df["amount"]) <= 1e-6) &
            (df["newbalanceOrig"] == 0)).astype(int)
        df["log_amount"] = np.log1p(df["amount"])
        df["hour_of_day"] = (df["step"] % 24).astype(int)
        df["day_index"] = (df["step"] // 24).astype(int)
        df["is_weekend_proxy"] = (df["day_index"] % 7 >= 5).astype(int)
        type_dummies = pd.get_dummies(df["type"], prefix="type")
        for col in type_dummies.columns:
            df[col] = type_dummies[col]
            df[f"{col}_x_amount"] = df[col] * df["amount"]
        high_thr = df["amount"].quantile(0.99)
        df["high_amount_flag"] = (df["amount"] >= high_thr).astype(int)
        df["origin_recon_mismatch_flag"] = (
            np.abs(df["oldbalanceOrg"] - df["amount"] - df["newbalanceOrig"]) > 1e-6
        ).astype(int)
        df["dest_recon_mismatch_flag"] = (
            np.abs(df["oldbalanceDest"] + df["amount"] - df["newbalanceDest"]) > 1e-6
        ).astype(int)
        df["strong_suspicion_flag"] = ((df["origin_drained_flag"] == 1) |
            (df["high_amount_flag"] == 1) |
            (df["origin_recon_mismatch_flag"] == 1)).astype(int)
        return df

    def prepare_data(self, **kwargs):
        df = self._generate_synthetic(kwargs.get("n_samples", 10_000))
        df = self._engineer_features(df)
        exclude = ["isFraud", "isFlaggedFraud", "nameOrig", "nameDest",
                    "oldbalanceOrg", "newbalanceOrig", "newbalanceDest",
                    "oldbalanceDest", "type", "amount"]
        feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype != "object"]
        self._feature_names = feature_cols
        X = df[feature_cols].values
        y = df["isFraud"].values
        return train_test_split(X, y, test_size=0.2, stratify=y, random_state=self.random_state)

    def train(self, **kwargs):
        X_train, X_test, y_train, y_test = self.prepare_data(**kwargs)
        self._model = RandomForestClassifier(n_estimators=200, max_depth=12,
            class_weight="balanced", random_state=self.random_state, n_jobs=1)
        self._model.fit(X_train, y_train)
        self._trained = True
        self._X_test, self._y_test = X_test, y_test
        return {"model": "RandomForest", "n_train": len(X_train),
                "n_test": len(X_test), "fraud_rate_test": float(np.mean(y_test))}

    def predict(self, X):
        if self._model is None:
            raise RuntimeError("Call train() first.")
        return self._model.predict(X)

    def predict_proba(self, X):
        if self._model is None:
            raise RuntimeError("Call train() first.")
        return self._model.predict_proba(X)[:, 1]

    def explain(self, X):
        if self._model is None:
            raise RuntimeError("Call train() first.")
        importances = self._model.feature_importances_
        return {"method": "feature_importance", "importances": importances.tolist(),
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
            model_name="Fraud Risk Pipeline (Random Forest)",
            model_version=f"benchmark@{self.repo_commit[:8]}",
            dataset_name="Synthetic AIML-Dataset replica",
            dataset_version="synthetic-v1", dataset_url="N/A (synthetic)",
            features=self._feature_names,
            train_split="80% stratified (leakage-controlled)",
            validation_split="N/A", test_split="20% stratified",
            metrics=metrics, threshold=0.5, latency_ms=latency,
            leakage_notes="Excluded isFlaggedFraud, nameOrig/nameDest, oldBalanceOrg. "
                          "class_weight='balanced' (no SMOTE).",
            reproducibility_info={"random_state": self.random_state, "git_commit": self.repo_commit,
                                  "license": self.repo_license, "train_info": train_info},
            limitations=["Metrics on synthetic data", "Original 6.3M-row metrics not reproduced"],
        )
        from benchmarks.evaluation.reporter import save_results
        result.report_path = save_results(result)
        return result

    def save_model(self, path: str):
        import joblib
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        joblib.dump(self._model, path); return path

    def load_model(self, path: str):
        import joblib
        self._model = joblib.load(path); self._trained = True