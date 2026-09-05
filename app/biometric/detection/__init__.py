"""
AUTHeTEC face detection.

Providers:
    - YuNet (OpenCV DNN)        : production-candidate, model opt-in
    - Haar (OpenCV bundled)     : NON_PRODUCTION_FALLBACK
"""

from app.biometric.detection.base import FaceDetectorBase
from app.biometric.detection.haar import HaarFaceDetector
from app.biometric.detection.yunet import YuNetFaceDetector, default_models_dir


def get_face_detector(require_production: bool = False):
    """Return the best locally available detector.

    If ``require_production`` is True and the YuNet model is not installed
    and integrity-verified, raises ValueError (fail-closed: the pipeline is
    never silently downgraded when a caller requires production grade).
    """
    if require_production:
        yunet = YuNetFaceDetector()
        if yunet.available():
            return yunet
        raise ValueError(
            "No production-grade face detector is installed and verified. "
            + yunet.install_instructions())
    yunet = YuNetFaceDetector()
    if yunet.available():
        return yunet
    return HaarFaceDetector()  # clearly labelled NON_PRODUCTION_FALLBACK


__all__ = [
    "FaceDetectorBase",
    "HaarFaceDetector",
    "YuNetFaceDetector",
    "default_models_dir",
    "get_face_detector",
]