"""Model-file integrity verification.

Native biometric providers must never silently activate when model
integrity checks fail.  This module verifies SHA-256 pins recorded in
``models/model_pins.json`` against the model files on disk and rejects
NaN/Inf embedding outputs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

MODELS_DIR = Path("models")
PINS_FILE = Path("models/model_pins.json")

# Rough key -> subdirectory mapping for finding model files.  The pins file
# may override this with a "paths" section: {"<key>": "relative/glob"}.
KNOWN_SUBDIRS = {
    "sface": "face_recognition",
    "recognition": "face_recognition",
    "yunet": "face_detection",
    "detection": "face_detection",
}


@dataclass
class ModelIntegrityResult:
    model_key: str
    expected_sha256: str
    status: str          # OK | NOT_FOUND | HASH_MISMATCH
    path: str = ""
    actual_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_key": self.model_key,
            "expected_sha256": self.expected_sha256,
            "status": self.status,
            "path": self.path,
            "actual_sha256": self.actual_sha256,
        }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_pins(pins_path: Path) -> Dict[str, str]:
    if not pins_path.exists():
        return {}
    try:
        data = json.loads(pins_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    # Ignore any optional "paths" metadata; only hash pins are returned.
    return {k: v for k, v in data.items() if isinstance(v, str) and len(v) == 64}


def _find_model_file(models_dir: Path, key: str) -> Optional[Path]:
    key_l = key.lower()
    candidates = [
        models_dir / sub for name, sub in KNOWN_SUBDIRS.items()
        if name in key_l
    ] or [models_dir]
    for base in candidates:
        if not base.is_dir():
            continue
        for child in sorted(base.rglob("*")):
            if child.is_file() and child.suffix.lower() in (
                    ".onnx", ".bin", ".pb", ".tflite"):
                return child
    return None


def verify_model_pins(
    models_dir: Path = MODELS_DIR,
    pins_path: Path = PINS_FILE,
) -> List[ModelIntegrityResult]:
    """Verify every pinned model file against its recorded SHA-256.

    Never raises for a missing file — it returns a NOT_FOUND result so the
    caller can fail safe on the deterministic fallback explicitly.
    """
    pins = _resolve_pins(pins_path)
    models_dir = Path(models_dir)
    results: List[ModelIntegrityResult] = []
    for key, expected in sorted(pins.items()):
        file = _find_model_file(models_dir, key)
        if file is None:
            results.append(ModelIntegrityResult(
                model_key=key, expected_sha256=expected, status="NOT_FOUND"))
            continue
        actual = sha256_file(file)
        status = "OK" if actual == expected.lower() else "HASH_MISMATCH"
        results.append(ModelIntegrityResult(
            model_key=key, expected_sha256=expected, status=status,
            path=str(file), actual_sha256=actual))
    return results


def integrity_passed(results: List[ModelIntegrityResult]) -> bool:
    return bool(results) and all(r.status == "OK" for r in results)


def assert_embeddings_finite(embedding: Any) -> bool:
    """Return False when an embedding contains NaN/Inf (never use it)."""
    try:
        import numpy as np
        arr = np.asarray(embedding, dtype=np.float64)
        return bool(np.all(np.isfinite(arr))) and arr.size > 0
    except Exception:
        return False