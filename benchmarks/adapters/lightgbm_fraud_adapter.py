"""LightGBM Fraud Detection Adapter - wraps repo1 (rpmjp)."""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict, List, Optional

import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from .base import BaseBenchmarkAdapter, BenchmarkResult


class LightGBMFraudAdapter(BaseBenchmarkAdapter):
    """
    Adapter for repo1: Fraud-Detection-with-LightGBM-99.9-ROC-AUC-Success.

    Wraps the LightGBM + SMOTE + SHAP pipeline. Uses synthetic transaction
    data matching the original dataset schema for self-contained
    reproducibility.
    """

    adapter_name = "lightgbm_fraud"
    repo_full_name = "rpmjp/Fraud-Detection-with-LightGBM-99.9-ROC-AUC-Success"
    repo_commit = "f257efc2973e7007aca146edd7f5621930343a0c"
    repo_license = "MIT"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._model: Optional[LGBMClassifier] = None
        self._feature_names: List[str] = []
        self.random_state = config.get("random_state", 42) if config else 42
        self._X_test = None

    def metadata(self) -> Dict[str, Any]:
        return {
            "adapter": self.adapter_name,
            "repo": self.repo_full_name,
            "commit": self.repo_commit,
            "license": self.repo_license,
            "purpose": "transaction fraud - LightGBM + SMOTE + SHAP",
            "original_metrics": {
                "precision": 0.9885, "recall": 0.9988,
                "f1": 0.9936, "roc_auc": 0.9994,
            },
            "note": "Original metrics from benchmark repo test set; NOT Authetec-validated.",
        }

    def validate_environment(self) -> bool:
        for pkg in ("lightgbm", "sklearn", "numpy", "pandas", "shap"):
            if importlib.util.find_spec(pkg) is None:
                print(f"  [FAIL] {pkg} not found")
                return False
            print(f"  [OK]   {pkg} found")
        return True

    def _generate_synthetic_data(self, n: int = 10_000) -> Any:
        import pandas as pd
        rng = np.random.RandomState(self.random_state)
        fraud_rate = 0.035
        types = rng.choice(
            ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"],
            size=n, p=[0.30, 0.35, 0.05, 0.15, 0.15],
        )
        amounts = rng.exponential(scale=1500, size=n)
        old_balances = rng.exponential(scale=5000, size=n)
        is_fraud = np.zeros(n, dtype=int)
        fraud_mask = rng.random(n) < fraud_rate
        is_fraud[fraud_mask] = 1
        amounts[fraud_mask] = np.maximum(
            amounts[fraud_mask],
            old_balances[fraud_mask] * 0.7 + rng.normal(0, 100, fraud_mask.sum()),
        )
        new_balances_orig = np.maximum(old_balances - amounts, 0)
        df = pd.DataFrame({
            "amount": amounts, "oldbalanceOrg": old_balances,
            "newbalanceOrig": new_balances_orig, "type": types,
        })
        df["delta_orig"] = df["oldbalanceOrg"] - df["newbalanceOrig"] - df["amount"]
        df["delta_dest"] = abs(df["amount"] - df["delta_orig"])
        df["is_weekend"] = rng.randint(0, 2, size=n)
        df["is_night"] = rng.randint(0, 2, size=n)
        df["sender_avg_amount"] = df["amount"].rolling(5, min_periods=1).mean().fillna(df["amount"].mean())
        df["sender_txn_count"] = rng.randint(1, 100, size=n)
        df["balance_jump_flag"] = (df["delta_orig"].abs() > df["amount"] * 0.9).astype(int)
        df["delta_orig_ratio"] = np.where(df["oldbalanceOrg"] > 0, df["delta_orig"] / df["oldbalanceOrg"], 0)
        df["is_c_to_c"] = df["type"].isin(["CASH_OUT", "TRANSFER"]).astype(int)
        type_dummies = pd.get_dummies(df["type"], prefix="type")
        df = pd.concat([df, type_dummies], axis=1)
        df["isFraud"] = is_fraud
        return df

    def prepare_data(self, **kwargs: Any) -> Any:
        df = self._generate_synthetic_data(kwargs.get("n_samples", 10_000))
        exclude = ["isFraud", "newbalanceOrig", "newbalanceDest", "nameOrig", "nameDest", "type"]
        feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype != "object"]
        self._feature_names = feature_cols
        X = df[feature_cols].values
        y = df["isFraud"].values
        return train_test_split(X, y, test_size=0.2, stratify=y, random_state=self.random_state)

    def train(self, **kwargs: Any) -> Dict[str, Any]:
        X_train, X_test, y_train, y_test = self.prepare_data(**kwargs)
        use_smote = self.config.get("use_smote", True)
        if use_smote:
            try:
                from imblearn.over_sampling import SMOTE
                sm = SMOTE(random_state=self.random_state)
                X_train, y_train = sm.fit_resample(X_train, y_train)
            except ImportError:
                use_smote = False
        self._model = LGBMClassifier(
            n_estimators=200, max_depth=8, learning_rate=0.1,
            class_weight="balanced", random_state=self.random_state,
            n_jobs=1, verbose=-1,
        )
        self._model.fit(X_train, y_train)
        self._trained = True
        self._X_test, self._y_test = X_test, y_test
        return {"model": "LightGBM", "smote_applied": use_smote,
                "n_train": len(X_train), "n_test": len(X_test),
                "fraud_rate_test": float(np.mean(y_test))}

    def predict(self, X: Any) -> Any:
        if self._model is None:
            raise RuntimeError("Model not trained. Call train() first.")
        return self._model.predict(X)

    def predict_proba(self, X: Any) -> Any:
        if self._model is None:
            raise RuntimeError("Model not trained. Call train() first.")
        return self._model.predict_proba(X)[:, 1]

    def explain(self, X: Any) -> Dict[str, Any]:
        if self._model is None:
            raise RuntimeError("Model not trained. Call train() first.")
        try:
            import shap
            explainer = shap.TreeExplainer(self._model)
            shap_values = explainer.shap_values(X)
            return {"method": "shap_tree", "shap_values": shap_values.tolist(),
                    "feature_names": self._feature_names}
        except Exception:
            importances = self._model.feature_importances_
            return {"method": "feature_importance", "importances": importances.tolist(),
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
            model_name="LightGBM Fraud Detection",
            model_version=f"benchmark@{self.repo_commit[:8]}",
            dataset_name="Synthetic Financial Transactions (Kaggle schema replica)",
            dataset_version="synthetic-v1",
            dataset_url="https://www.kaggle.com/datasets/aryan208/financial-transactions-dataset-for-fraud-detection",
            features=self._feature_names,
            train_split="80% stratified",
            validation_split="N/A",
            test_split="20% stratified holdout",
            metrics=metrics, threshold=0.5, latency_ms=latency,
            leakage_notes="Excluded newbalance* and isFlaggedFraud. SMOTE applied only after split.",
            reproducibility_info={"random_state": self.random_state,
                                  "git_commit": self.repo_commit,
                                  "license": self.repo_license,
                                  "train_info": train_info},
            limitations=[
                "Metrics on synthetic data, NOT original Kaggle dataset",
                "Reported repo metrics (0.9885 P / 0.9988 R) are benchmark-test-set values",
                "Latency approximated, not measured in production",
            ],
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
