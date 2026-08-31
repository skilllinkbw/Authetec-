"""
Document Engine
===============

Verifies documents (PDF / JPG / JPEG / PNG) through a staged pipeline:
file validation -> security checks -> OCR -> classification -> metadata
analysis -> visual integrity -> tampering analysis -> fraud scoring.

Implements the *detectable* features it can measure and is explicit about
which physical-security features are NOT verifiable from a digital image.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.models.risk import Decision, EngineResult, Signal
from app.services.evidence import get_evidence_engine

logger = logging.getLogger("authetec.document")

MIN_LENGTH = 64
MAX_LENGTH = 20 * 1024 * 1024  # 20 MB


class DocumentValidationError(ValueError):
    pass


@dataclass
class DocumentInput:
    filename: str
    content: bytes
    declared_content_type: str = ""


def inspect_file_type(content: bytes, declared: str) -> str:
    """Signature-based content-type detection (magic bytes)."""
    if not content:
        raise DocumentValidationError("Empty file")
    if content[:4] == b"%PDF":
        return "application/pdf"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:2] == b"II" or content[:2] == b"MM":
        return "image/tiff"
    # Executable / archive signatures to reject outright
    if content[:2] == b"MZ":
        raise DocumentValidationError("Executable files are not allowed")
    if content[:4] in (b"PK\x03\x04", b"Rar!", b"7z\xbc\xaf"):
        raise DocumentValidationError("Archive files are not allowed")
    raise DocumentValidationError(f"Unsupported file type (declared: {declared or 'unknown'})")


def validate_document(content: bytes, declared: str = "") -> str:
    if len(content) < MIN_LENGTH:
        raise DocumentValidationError("File too small to be a valid document")
    if len(content) > MAX_LENGTH:
        raise DocumentValidationError("File exceeds 20 MB upload limit")
    return inspect_file_type(content, declared)


def _ocr_text(content: bytes, content_type: str) -> str:
    """Best-effort OCR.  Returns '' if no OCR engine is installed."""
    if content_type == "application/pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages[:5])
        except Exception as e:
            logger.debug("PDF text extraction failed: %s", e)
            return ""
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(content, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return ""
        try:
            import pytesseract  # required for OCR on images
            return pytesseract.image_to_string(img) or ""
        except ImportError:
            return ""
    except Exception as e:
        logger.debug("Image OCR unavailable: %s", e)
        return ""


def _tampering_heuristics(img_bytes: bytes) -> Dict[str, float]:
    """Detectable manipulation signals via JPEG/PNG re-compression checks."""
    signals: Dict[str, float] = {"ela_value": 0.0, "metadata_anomaly": 0.0}
    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(img_bytes))
        img.load()
        if img.format in ("JPEG", "PNG"):
            # Re-compress and measure deviation (Error Level Analysis proxy)
            out = _io.BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=95)
            recompressed = out.getvalue()
            if img_bytes and len(img_bytes) > 100:
                ratio = len(recompressed) / len(img_bytes)
                # Unusual compression ratio may indicate prior edits
                signals["ela_value"] = round(max(0.0, min(1.0, abs(ratio - 1.0) * 10)), 4)

        exif = img.getexif()
        if not exif:
            signals["metadata_anomaly"] = 0.3  # stripped metadata is suspicious
        return signals
    except Exception as e:
        logger.debug("Tampering heuristics skipped: %s", e)
        return signals
def _classify_document(text: str, filename: str) -> Dict[str, Any]:
    """Heuristic document classifier (keyword-based)."""
    text_l = text.lower()
    hints = {
        "passport": ["passport", "passeport"],
        "national_id": ["national id", "identity card", "aadhaar", "nric", "identity number"],
        "driver_license": ["driver licence", "driver license"],
        "bank_statement": ["bank statement", "account statement", "statement period"],
        "birth_certificate": ["birth certificate", "date of birth"],
        "certificate": ["certificate", "diploma", "degree"],
    }
    scores = {k: 0 for k in hints}
    for doc_type, keywords in hints.items():
        for kw in keywords:
            if kw in text_l:
                scores[doc_type] += 1
    fname_l = filename.lower()
    for doc_type in hints:
        if doc_type.replace("_", "") in fname_l.replace("_", "").replace("-", ""):
            scores[doc_type] += 1
    total_words = max(len(text_l.split()), 1)
    best = max(scores, key=scores.get)
    return {
        "classification": best if scores[best] > 0 else "unknown",
        "scores": scores,
        "page_agreement": round(min(max(total_words / 500.0, 0.0), 1.0), 4),
    }


class DocumentEngine:
    """Document verification engine."""

    MODEL_VERSION = "document-heuristics-v0.1-benchmark"

    def __init__(self, tenant_id: str = "default") -> None:
        self._settings = get_settings()
        self._tenant_id = tenant_id
        self._evidence = get_evidence_engine()

    def verify(
        self,
        doc: DocumentInput,
        *,
        tenant_id: Optional[str] = None,
        expected_type: str = "",
    ) -> EngineResult:
        t0 = time.perf_counter()
        tid = tenant_id or self._tenant_id
        steps: List[str] = []

        # 1) File validation + security checks
        content_type = validate_document(doc.content, doc.declared_content_type)
        steps.append("file_validation")
        content_hash = hashlib.sha256(doc.content).hexdigest()

        # 2) OCR
        text = _ocr_text(doc.content, content_type)
        steps.append("ocr")

        # 3) Classification
        classification = _classify_document(text, doc.filename)
        steps.append("classification")

        # 4) Metadata / visual integrity / tampering
        tamper = _tampering_heuristics(doc.content)
        steps.append("visual_integrity")

        # 5) Fraud scoring (rule-based, explicit and explainable)
        reasons: List[str] = []
        signals: List[Signal] = []
        score = 0.0

        if content_type == "application/pdf" and not text.strip():
            score += 0.25
            reasons.append("PDF has no extractable text layer (may be scanned or image-only)")
            signals.append(Signal("pdf_no_text", 1.0, 0.25, "No extractable text", "document"))
        else:
            signals.append(Signal("pdf_no_text", 0.0, 0.25, "Text layer present", "document"))

        obj = classification["classification"]
        if expected_type and obj != expected_type and obj != "unknown":
            score += 0.30
            reasons.append(f"Classified as '{obj}' but expected '{expected_type}'")
        signals.append(Signal("classification", score / 0.30 if score > 0.3 else 0.0,
                              0.30, obj, "document"))

        ela = tamper.get("ela_value", 0.0)
        meta = tamper.get("metadata_anomaly", 0.0)
        score += ela * 0.30 + meta * 0.15
        if ela > 0.05:
            reasons.append("Re-compression deviation detected (possible prior edit)")
        if meta > 0.0:
            reasons.append("Metadata absent (possible re-save or stripping)")
        signals.append(Signal("ela_value", ela, 0.30, "Error-level analysis signal", "document"))
        signals.append(Signal("metadata_anomaly", meta, 0.15, "Metadata anomaly signal", "document"))

        score = min(score, 1.0)
        confidence = 0.55 + 0.45 * classification["page_agreement"]
        decision = Decision.CLEAR if score < self._settings.risk_clear_threshold else (
            Decision.REVIEW if score < self._settings.risk_review_threshold else Decision.BLOCK
        )
        if not reasons:
            reasons.append("No detectable visual/document anomalies")

        evidence = self._evidence.store(
            tenant_id=tid,
            storage_uri=f"objects/{tid}/documents/{content_hash}",
            content_type=content_type,
            purpose="document verification input",
            metadata={"sha256": content_hash, "filename": doc.filename},
        )

        return EngineResult(
            engine="document",
            risk_score=round(score, 4),
            confidence=round(confidence, 4),
            decision=decision,
            signals=signals,
            reasons=reasons + [f"steps={','.join(steps)}"],
            model_version=self.MODEL_VERSION,
            processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            evidence=[],
            extra={"sha256": content_hash, "classification": classification,
                   "tampering": tamper, "stored_evidence_id": evidence.evidence_id},
        )