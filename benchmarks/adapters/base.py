"""
Authetec Benchmark Adapter — Base Contract
==========================================

Every benchmark adapter exposes a consistent interface so the evaluation
framework and the production Authetec engines can treat them uniformly.

Adapters are thin wrappers around external benchmark code.  They **never**
import arbitrary benchmark internals into the Authetec production path;
they load, reproduce, and re-score within an isolated boundary.
"""

from __future__ import annotations

import abc
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Evaluation result container ──────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """Structured result returned by ``Adapter.evaluate()``."""

    model_id: str
    model_name: str
    model_version: str
    dataset_name: str
    dataset_version: str
    dataset_url: str
    features: List[str]
    train_split: str
    validation_split: str
    test_split: str
    metrics: Dict[str, float]
    threshold: float
    latency_ms: float
    leakage_notes: str
    reproducibility_info: Dict[str, Any]
    limitations: List[str]
    report_path: Optional[str] = None


# ── Adapter contract ────────────────────────────────────────────────────

class BaseBenchmarkAdapter(abc.ABC):
    """
    Common interface for all benchmark adapters.

    Concrete adapters wrap an external benchmark repository's model
    code, reproduce its results on compatible datasets, and expose
    a uniform ``train / predict / evaluate`` surface.
    """

    #: Human-readable name shown in reports
    adapter_name: str = "base"

    #: Repository the adapter wraps
    repo_full_name: str = ""
    repo_commit: str = ""
    repo_license: str = ""

    #: Default dataset the adapter uses for reproduction
    default_dataset: str = ""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self._model: Any = None
        self._metadata: Dict[str, Any] = {}
        self._trained: bool = False

    # ── Lifecycle ──────────────────────────────────────────────────

    @abc.abstractmethod
    def metadata(self) -> Dict[str, Any]:
        """Return static metadata about the wrapped benchmark."""

    @abc.abstractmethod
    def validate_environment(self) -> bool:
        """Verify that required libraries and data are present."""

    @abc.abstractmethod
    def prepare_data(self, **kwargs: Any) -> Any:
        """Load and preprocess the dataset into model-ready form."""

    @abc.abstractmethod
    def train(self, **kwargs: Any) -> Dict[str, Any]:
        """Train the model.  Returns a summary dict."""

    @abc.abstractmethod
    def predict(self, X: Any) -> Any:
        """Return class predictions (0 / 1)."""

    @abc.abstractmethod
    def predict_proba(self, X: Any) -> Any:
        """Return probability estimates for the positive class."""

    @abc.abstractmethod
    def explain(self, X: Any) -> Dict[str, Any]:
        """Return SHAP / feature-importance explanations for samples in X."""

    @abc.abstractmethod
    def evaluate(self, **kwargs: Any) -> BenchmarkResult:
        """Run full evaluation and return a :class:`BenchmarkResult`."""

    @abc.abstractmethod
    def save_model(self, path: str) -> str:
        """Persist the trained model to *path*.  Returns the path."""

    @abc.abstractmethod
    def load_model(self, path: str) -> None:
        """Load a previously saved model from *path*."""

    def health(self) -> Dict[str, Any]:
        """Lightweight health check — subclasses may override."""
        return {
            "adapter": self.adapter_name,
            "repo": self.repo_full_name,
            "commit": self.repo_commit,
            "license": self.repo_license,
            "trained": self._trained,
        }


# ── Helper: build a unique run id ───────────────────────────────────────

def _run_id() -> str:
    return f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
