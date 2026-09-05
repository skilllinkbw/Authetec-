"""
AUTHeTEC native biometric benchmark infrastructure.

Provides reproducible benchmarking for:
  - Face verification (genuine/impostor pairs)
  - Presentation-attack detection (bona-fide vs attack)
  - Threshold analysis (FAR/FRR curves, EER)
  - Performance (latency, throughput, memory)

All metrics are calculated from actual model predictions — never hardcoded.
Results are written as machine-readable JSON and human-readable Markdown.

Dataset policy:
  - No biometric data is committed to Git
  - Datasets are referenced by manifest (path, version, license, checksum)
  - Only synthetic fixtures live inside the repository
  - Real datasets must be obtained lawfully by the operator
"""

from benchmarks.biometric.metrics import (
    confusion_matrix,
    far_frr,
    precision_recall_f1,
    rocAuc,
    eer as compute_eer,
)
from benchmarks.biometric.verification_benchmark import (
    VerificationBenchmark,
    VerificationResult,
)
from benchmarks.biometric.pad_benchmark import (
    PadBenchmark,
    PadResult,
)
from benchmarks.biometric.threshold_analysis import (
    ThresholdAnalysis,
    analyze_thresholds,
)
from benchmarks.biometric.performance import (
    PerformanceBenchmark,
    PerformanceResult,
)
from benchmarks.biometric.dataset import (
    BiometricDataset,
    DatasetSample,
    generate_pad_samples,
    generate_verification_pairs,
    load_dataset,
)
from benchmarks.biometric.config import BenchmarkConfig, default_config
from benchmarks.biometric.regression_gates import RegressionGateSet
from benchmarks.biometric.model_integrity import (
    ModelIntegrityResult,
    assert_embeddings_finite,
    integrity_passed,
    verify_model_pins,
)

__all__ = [
    "confusion_matrix",
    "far_frr",
    "precision_recall_f1",
    "rocAuc",
    "compute_eer",
    "VerificationBenchmark",
    "VerificationResult",
    "PadBenchmark",
    "PadResult",
    "ThresholdAnalysis",
    "analyze_thresholds",
    "PerformanceBenchmark",
    "PerformanceResult",
    "BiometricDataset",
    "DatasetSample",
    "generate_pad_samples",
    "generate_verification_pairs",
    "load_dataset",
    "BenchmarkConfig",
    "default_config",
    "RegressionGateSet",
    "ModelIntegrityResult",
    "assert_embeddings_finite",
    "integrity_passed",
    "verify_model_pins",
]
