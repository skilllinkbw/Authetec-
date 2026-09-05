"""
SFace face embedder (OpenCV Zoo, Apache-2.0).

STATUS: PRODUCTION CANDIDATE - model must be explicitly installed
=================================================================

SFace is a compact CNN face-embedding model (128-d) distributed under
Apache-2.0 by OpenCV Zoo.  It runs on CPU via onnxruntime and is small
enough for edge/Android considerations.

Model download policy: never auto-downloaded at startup.  The model must
be explicitly installed and its pinned SHA-256 satisfied; otherwise the
embedder reports ``available() == False`` and ``embed`` returns None
(fail closed).
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

from app.biometric.contracts import BiometricProviderInfo
from app.biometric.recognition.embeddings import EmbeddingValidator
from app.biometric.security.integrity import (
    is_model_installed,
    verify_model_integrity,
)

MODEL_KEY = "sface_recognition"
DEFAULT_MODEL_FILE = "face_recognition_sface_2021dec.onnx"
EMBEDDING_DIM = 128

PROVIDER = BiometricProviderInfo(
    name="opencv-zoo-sface",
    version="2021dec",
    license="Apache-2.0",
    production_grade=True,
    usage_status="PRODUCTION_ALLOWED",
    notes="CNN face embedding (128-d) running on onnxruntime.",
)


def default_sface_path() -> str:
    base = os.getenv("AUTHETEC_MODELS_DIR", os.path.join(os.getcwd(), "models"))
    return os.path.join(base, "face_recognition", DEFAULT_MODEL_FILE)


class SFaceFaceEmbedder:
    """OpenCV Zoo SFace embedder via onnxruntime.

    Usage::

        embedder = SFaceFaceEmbedder()
        if not embedder.available():
            embedder.install_instructions()
        emb = embedder.embed(aligned_face_bytes)   # None on failure
    """

    provider = PROVIDER
    EMBEDDING_DIM = EMBEDDING_DIM

    @property
    def model_version(self) -> str:
        return "sface-2021dec-onnx-128d"

    @property
    def load_error(self) -> str:
        return self._load_error

    def __init__(
        self,
        model_path: Optional[str] = None,
        input_size: int = 112,
        verify_integrity: bool = True,
    ) -> None:
        self._model_path = model_path or default_sface_path()
        self._input_size = int(input_size)
        self._verify_integrity = bool(verify_integrity)
        self._session = None
        self._load_error = ""
        self.validator = EmbeddingValidator(
            expected_dim=EMBEDDING_DIM, require_unit_norm=False)
        self._try_load()

    def _try_load(self) -> None:
        if not is_model_installed(self._model_path):
            return
        if self._verify_integrity and not verify_model_integrity(
                self._model_path, MODEL_KEY):
            self._load_error = (
                "SFace model failed the pinned-SHA integrity check "
                "(fail closed)")
            return
        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(
                self._model_path, providers=["CPUExecutionProvider"])
        except Exception as e:  # pragma: no cover - environment dependent
            self._load_error = f"SFace init failed: {e}"

    def available(self) -> bool:
        return self._session is not None

    def install_instructions(self) -> str:
        return (
            "SFace model is not installed / not verified.\n"
            f"Expected path : {self._model_path}\n"
            "Install command:\n"
            "  python -m scripts.install_biometric_models --embedder sface\n"
            "URL           : https://huggingface.co/opencv/"
            "face_recognition_sface/resolve/main/"
            "face_recognition_sface_2021dec.onnx"
        )

    def embed(self, image_bytes: bytes) -> Optional[np.ndarray]:
        """Unit-normalised 128-d embedding or None (fail closed)."""
        if self._session is None:
            return None
        try:
            import cv2
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                return None
            blob = cv2.resize(
                img, (self._input_size, self._input_size),
                interpolation=cv2.INTER_AREA).astype(np.float32)
            blob = np.transpose(blob, (2, 0, 1))[None, ...]
            std = float(blob.std())
            if std < 1e-6:
                return None
            blob = (blob - float(blob.mean())) / std
            out = self._session.run(
                None, {self._session.get_inputs()[0].name: blob})[0]
            emb = np.asarray(out, dtype=np.float32).ravel()
            norm = float(np.linalg.norm(emb))
            if norm < 1e-9:
                return None
            emb = (emb / norm).astype(np.float32)
            if not self.validator.validate(emb).is_valid:
                return None
            return emb
        except Exception:
            return None