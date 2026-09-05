"""
Model integrity verification.

All third-party model files must be:
    * explicitly installed (never auto-downloaded at runtime), and
    * verified against a pinned SHA-256 before use.

The canonical manifest lives in ``app/biometric/models/manifest.py``; this
module provides the low-level helpers used by the provider adapters.

Integrity verification is fail-closed: an unpinned hash is treated as
"not verified", which makes the model unavailable to production paths.
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional


def sha256_file(path: str, chunk: int = 1024 * 1024) -> str:
    """SHA-256 of a file's bytes (streamed, memory-safe)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def is_model_installed(path: str) -> bool:
    """True if the file exists and is non-empty."""
    try:
        return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def expected_sha256(model_key: str) -> str:
    """Pinned SHA-256 for a model key from the manifest; '' if unpinned."""
    try:
        from app.biometric.models.manifest import model_manifest
        entry = model_manifest().get(model_key, {})
        return str(entry.get("sha256", "") or "")
    except Exception:
        return ""


def verify_model_integrity(path: str, model_key: str) -> bool:
    """Fail-closed integrity check: file present AND hash pinned AND match."""
    if not is_model_installed(path):
        return False
    expected = expected_sha256(model_key)
    if not expected:
        return False
    try:
        return sha256_file(path).lower() == expected.lower()
    except Exception:
        return False