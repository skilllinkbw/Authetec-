"""
Model registry / manifest.

Describes every optional biometric model file AUTHeTEC can consume.
Models are never bundled in the repository and never downloaded silently;
each entry records where the model comes from, its licence status, and
its pinned SHA-256 (filled only after the operator verifies the download).

``sha256`` intentionally starts empty: integrity checks are FAIL-CLOSED
until the value is pinned by an operator who verified the download.
"""

from __future__ import annotations

from typing import Any, Dict

MODEL_MANIFEST: Dict[str, Dict[str, Any]] = {
    "yunet_face_detection": {
        "model": "face_detection_yunet_2023mar.onnx",
        "task": "face_detection",
        "source": "https://github.com/opencv/opencv_zoo/tree/main/models/"
                  "face_detection_yunet",
        "mirror": "https://huggingface.co/opencv/face_detection_yunet/resolve/"
                  "main/face_detection_yunet_2023mar.onnx",
        "license": "Apache-2.0",
        "commercial_use": "allowed",
        "usage_status": "PRODUCTION_ALLOWED",
        "size_bytes": 232589,
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "install": "python -m scripts.install_biometric_models --detector yunet",
    },
    "sface_recognition": {
        "model": "face_recognition_sface_2021dec.onnx",
        "task": "face_embedding",
        "source": "https://github.com/opencv/opencv_zoo/tree/main/models/"
                  "face_recognition_sface",
        "mirror": "https://huggingface.co/opencv/"
                  "face_recognition_sface/resolve/main/"
                  "face_recognition_sface_2021dec.onnx",
        "license": "Apache-2.0",
        "commercial_use": "allowed",
        "usage_status": "PRODUCTION_ALLOWED",
        "size_bytes": 38696353,
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "install": "python -m scripts.install_biometric_models --embedder sface",
    },
    "arcface_r100_benchmark_only": {
        "model": "ms1mv3_arcface_r100.onnx",
        "task": "face_embedding",
        "source": "https://github.com/deepinsight/insightface (arcface_torch)",
        "license": "research-only (InsightFace model zoo)",
        "commercial_use": "restricted — legal review required",
        "usage_status": "BENCHMARK_ONLY",
        "size_bytes": 244000000,
        "sha256": "",
        "install": "https://github.com/deepinsight/insightface#model-zoo",
    },
}


def model_manifest() -> Dict[str, Dict[str, Any]]:
    """Return the (mutable copy) of the built-in manifest."""
    return {k: dict(v) for k, v in MODEL_MANIFEST.items()}