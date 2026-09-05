"""
OCR Pipeline (hardened)
=======================

Central, auditable OCR / document-extraction pipeline shared by the
document and identity-document engines.  It replaces the two duplicated
``_ocr_text`` implementations and adds what the review found missing:

  * explicit OCR-engine availability introspection (no silent fail-open)
  * image quality assessment: blur, glare, shadow, contrast, resolution
  * preprocessing: grayscale, small-image upscaling, deskew
  * structured failure handling (engine-missing vs no-text vs OCR-error)

HONESTY NOTE: the quality heuristics below are deterministic image
statistics, NOT a validated document-quality model.  They are suitable
as risk *signals* only.  No OCR accuracy figure may be claimed on their
basis; see benchmarks/evaluation/ocr_benchmark.py (SYNTHETIC/TEST-ONLY).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("authetec.ocr")

# Quality thresholds — chosen conservatively, calibrated on SYNTHETIC
# data only.  They must be re-calibrated on real document data before
# production use.
MIN_USEFUL_WIDTH = 300
MIN_USEFUL_HEIGHT = 200
BLUR_VARIANCE_FLOOR = 35.0   # Laplacian variance below this => likely blur
GLARE_BRIGHT_RATIO = 0.02    # fraction of near-saturated pixels => glare
SHADOW_DARK_RATIO = 0.35     # fraction of near-black pixels => heavy shadow
LOW_CONTRAST_STD = 28.0      # grayscale std-dev below this => low contrast


@dataclass
class ImageQuality:
    """Deterministic image-quality assessment of a document photo/scan."""

    width: int = 0
    height: int = 0
    blur_variance: float = 0.0          # raw Laplacian variance
    glare_ratio: float = 0.0            # fraction of near-saturated pixels
    shadow_ratio: float = 0.0           # fraction of near-black pixels
    contrast_std: float = 0.0           # grayscale std deviation
    issues: List[str] = field(default_factory=list)
    assessed: bool = False              # False if image could not be decoded

    @property
    def quality_score(self) -> float:
        """0.0 (unusable) .. 1.0 (clean), from counted issues."""
        if not self.assessed:
            return 0.0
        return round(max(0.0, 1.0 - 0.25 * len(self.issues)), 4)


@dataclass
class OcrOutcome:
    """Structured result of a best-effort text extraction."""

    text: str = ""
    engine: str = "none"                # "pypdf" | "pytesseract" | "none"
    engine_available: bool = False      # was ANY engine importable?
    error: str = ""                     # engine ran but failed, if any
    notes: List[str] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


def ocr_engine_status() -> Dict[str, bool]:
    """Report which OCR/text engines are importable in this environment.

    Used to distinguish "OCR produced nothing" from "OCR was impossible"
    — collapsing the two is what allowed the old pipeline to fail open.
    """
    status: Dict[str, bool] = {}
    for name, import_stmt in (
        ("pytesseract", "import pytesseract"),
        ("pypdf", "import pypdf"),
        ("cv2", "import cv2"),
    ):
        try:
            exec(compile(import_stmt, "<ocr_status>", "exec"), {})  # noqa: S102
            status[name] = True
        except Exception:
            status[name] = False
    return status


def assess_image_quality(image_bytes: bytes) -> ImageQuality:
    """Deterministic quality signals for a document image.

    Never raises: an undecodable image yields ``assessed=False`` with a
    ``undecodable_image`` issue, which callers must treat as a risk
    signal rather than silently ignoring.
    """
    q = ImageQuality()
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            q.issues.append("undecodable_image")
            return q
        q.assessed = True
        h, w = img.shape[:2]
        q.width, q.height = int(w), int(h)

        if w < MIN_USEFUL_WIDTH or h < MIN_USEFUL_HEIGHT:
            q.issues.append("low_resolution")

        q.blur_variance = float(cv2.Laplacian(img, cv2.CV_64F).var())
        if q.blur_variance < BLUR_VARIANCE_FLOOR:
            q.issues.append("likely_blur")

        q.glare_ratio = float((img >= 250).sum()) / float(w * h)
        if q.glare_ratio > GLARE_BRIGHT_RATIO:
            q.issues.append("possible_glare")

        q.shadow_ratio = float((img <= 10).sum()) / float(w * h)
        if q.shadow_ratio > SHADOW_DARK_RATIO:
            q.issues.append("heavy_shadow")

        q.contrast_std = float(img.std())
        if q.contrast_std < LOW_CONTRAST_STD:
            q.issues.append("low_contrast")
    except Exception as e:  # quality assessment must never break the pipeline
        logger.debug("image quality assessment failed: %s", e)
        q.issues.append("quality_assessment_error")
    return q


def preprocess_for_ocr(image_bytes: bytes):
    """Return a preprocessed grayscale ndarray, or None if undecodable.

    Steps (deliberately minimal and standard):
      1. decode
      2. upscale if below the useful resolution floor (x2, cubic)
      3. deskew via min-area rectangle angle (clipped to +/-10 degrees)
    """
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        h, w = img.shape[:2]
        if w < MIN_USEFUL_WIDTH or h < MIN_USEFUL_HEIGHT:
            img = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        try:
            pts = cv2.findNonZero(cv2.bitwise_not(img))
            if pts is not None:
                angle = cv2.minAreaRect(pts)[-1]
                if angle > 45:
                    angle -= 90
                if abs(angle) > 0.5 and abs(angle) <= 10:
                    rot = cv2.getRotationMatrix2D(
                        (img.shape[1] / 2, img.shape[0] / 2), angle, 1.0)
                    img = cv2.warpAffine(
                        img, rot, (img.shape[1], img.shape[0]),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_REPLICATE)
        except Exception:
            pass  # deskew is best-effort only
        return img
    except Exception:
        return None


def extract_text(content: bytes, content_type: str) -> OcrOutcome:
    """Best-effort structured text extraction (PDF text layer or OCR).

    Consolidates the previously duplicated ``_ocr_text`` helpers and
    reports WHY no text was produced so callers can fail closed.
    """
    outcome = OcrOutcome()
    if not content:
        outcome.error = "empty content"
        return outcome

    if content_type == "application/pdf":
        try:
            from pypdf import PdfReader  # noqa: F401
        except ImportError:
            outcome.notes.append("pypdf not installed: PDF text layer unavailable")
            return outcome
        try:
            import io as _io
            from pypdf import PdfReader
            reader = PdfReader(_io.BytesIO(content))
            outcome.text = "\n".join(
                page.extract_text() or "" for page in reader.pages[:5])
            outcome.engine = "pypdf"
            outcome.engine_available = True
        except Exception as e:
            outcome.error = f"pdf text extraction failed: {e}"
        return outcome

    # Image path: decode + preprocess + OCR.
    try:
        import cv2  # noqa: F401
    except ImportError:
        outcome.notes.append("cv2 not installed: image decode unavailable")
        return outcome

    if not ocr_engine_status().get("pytesseract"):
        outcome.notes.append("pytesseract not installed: image OCR unavailable")
        return outcome

    try:
        import pytesseract
        img = preprocess_for_ocr(content)
        outcome.engine = "pytesseract"
        outcome.engine_available = True
        if img is None:
            outcome.error = "image could not be decoded"
            return outcome
        outcome.text = pytesseract.image_to_string(img) or ""
    except Exception as e:
        outcome.error = f"ocr failed: {e}"
    return outcome
