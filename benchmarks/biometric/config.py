"""Benchmark configuration.

Reproducible benchmark runs need the full configuration recorded.  This
module holds the config surface for the biometric benchmark runner and
serialization helpers so every run's JSON report embeds the exact config.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class BenchmarkConfig:
    """Configuration for one biometric benchmark run."""

    # Dataset + outputs
    manifest_path: Optional[str] = None       # None => synthetic fixture
    output_dir: str = "benchmarks/biometric/reports"
    dataset_name: str = ""
    dataset_version: str = ""

    # Provider selection (mirrors AUTHETEC_PAD_PROVIDER / FACE_PROVIDER)
    provider: str = "deterministic"           # deterministic | native

    # Verification
    threshold: float = 0.62                   # similarity operating point
    max_pairs: int = 400                      # cap on generated pairs (0=all)
    impostor_ratio: float = 1.0               # impostor pairs per genuine pair
    dataset_seed: int = 42

    # Performance
    n_warmup: int = 3
    n_iters: int = 20

    # Regression gates: mapping gate_name -> limit.  Unlisted gates are
    # reported as "CONFIGURATION REQUIRED" (never silently assumed).
    gates: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


def default_config() -> BenchmarkConfig:
    return BenchmarkConfig()


def config_from_dict(data: Dict[str, Any]) -> BenchmarkConfig:
    """Build a BenchmarkConfig from a (possibly partial) dict."""
    allowed = set(BenchmarkConfig.__dataclass_fields__.keys())
    clean = {k: v for k, v in (data or {}).items() if k in allowed}
    cfg = BenchmarkConfig(**clean)
    cfg.gates = {k: float(v) for k, v in (data or {}).get("gates", {}).items()}
    return cfg