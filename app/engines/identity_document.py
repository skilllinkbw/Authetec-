"""
Identity Document Engine
========================
Unified engine for verifying identity documents (passports, national IDs,
driver's licences) using document profiles and the MRZ validator.
"""

from __future__ import annotations

import hashlib
import io
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.engines.document import validate_document, DocumentValidationError
from app.engines.mrz import validate_mrz, extract_mrz_from_text
from app.engines.document_profiles import get_profile_or_default
from app.models.risk import Decision, EngineResult, Signal
from app.services.evidence import get_evidence_engine

logger = logging.getLogger("authetec.identity_document")

MODEL_VERSION = "identity-doc-1.0"


@dataclass
class IdentityDocumentInput:
    filename: str
    content: bytes
    declared_content_type: str = ""
    document_type: str = "auto"
    country_code: str = ""


def _ocr_text(content: bytes, content_type: str) -> str:
    """Best-effort OCR. Returns '' if no OCR engine is installed."""
    if content_type == "application/pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages[:5])
        except Exception:
            return ""
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(content, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return ""
        try:
            import pytesseract
            return pytesseract.image_to_string(img) or ""
        except ImportError:
            return ""
    except Exception:
        return ""


def _detect_document_type(text: str, filename: str) -> str:
    """Simple keyword-based document type detection."""
    text_lower = (text + " " + filename).lower()
    if "passport" in text_lower or "p<" in text_lower:
        return "passport"
    if "national" in text_lower and "id" in text_lower:
        return "national_id"
    if "licence" in text_lower or "license" in text_lower or "dl" in text_lower:
        return "drivers_licence"
    if "identity" in text_lower or "id card" in text_lower:
        return "national_id"
    return "unknown"


def _classify_from_mrz(fields: Dict[str, str]) -> str:
    """Infer document type from MRZ fields."""
    doc_type_raw = fields.get("document_type", "")
    if "P" in doc_type_raw.upper():
        return "passport"
    if "I" in doc_type_raw.upper() or "ID" in doc_type_raw.upper():
        return "national_id"
    if "DL" in doc_type_raw.upper() or "D" in doc_type_raw.upper():
        return "drivers_licence"
    return "unknown"


class IdentityDocumentEngine:
    """Unified identity document verification engine."""

    def __init__(self, tenant_id: str = "system"):
        self._tenant_id = tenant_id
        self._evidence = get_evidence_engine()
        self._settings = get_settings()

    def verify(self, doc: IdentityDocumentInput, tenant_id: str = "") -> EngineResult:
        """Verify an identity document."""
        t0 = time.perf_counter()
        tid = tenant_id or self._tenant_id
        signals: List[Signal] = []
        reasons: List[str] = []
        score = 0.0

        # 1) File validation
        try:
            content_type = validate_document(doc.content, doc.declared_content_type)
        except DocumentValidationError as e:
            return EngineResult(
                engine="identity_document",
                risk_score=1.0,
                confidence=0.95,
                decision=Decision.BLOCK,
                signals=[Signal("file_validation_failed", 1.0, 1.0, str(e), "identity_document")],
                reasons=[f"File validation failed: {e}"],
                model_version=MODEL_VERSION,
                processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
                evidence=[],
                extra={"error": str(e)},
            )

        content_hash = hashlib.sha256(doc.content).hexdigest()

        # 2) OCR
        text = _ocr_text(doc.content, content_type)

        # 3) Document type detection
        detected_type = doc.document_type
        if detected_type == "auto":
            detected_type = "unknown"

        # 4) MRZ extraction and validation
        mrz_result = None
        mrz_lines = extract_mrz_from_text(text)
        if mrz_lines:
            mrz_result = validate_mrz(mrz_lines)
            if mrz_result.is_valid:
                signals.append(Signal("mrz_valid", 0.0, 0.20,
                                       "MRZ structure and check digits valid", "identity_document"))
                if mrz_result.fields:
                    mrz_doc_type = _classify_from_mrz(mrz_result.fields)
                    if mrz_doc_type != "unknown":
                        detected_type = mrz_doc_type
                        signals.append(Signal("document_type_from_mrz", 0.0, 0.05,
                                               detected_type, "identity_document"))
            else:
                score += 0.40
                reasons.append(f"MRZ validation failed: {'; '.join(mrz_result.issues[:3])}")
                signals.append(Signal("mrz_invalid", 0.8, 0.40,
                                       f"MRZ issues: {len(mrz_result.issues)}", "identity_document"))
        else:
            signals.append(Signal("mrz_not_found", 0.3, 0.15,
                                   "No MRZ found in OCR text", "identity_document"))
            score += 0.10

        # 5) Document profile
        country = doc.country_code or "XX"
        if country == "XX" and mrz_result and mrz_result.fields:
            issuer = mrz_result.fields.get("issuer", "")
            if issuer:
                country = issuer
        profile = get_profile_or_default(detected_type, country)
        # 6) Expiry check from MRZ
        if mrz_result and mrz_result.fields:
            expiry = mrz_result.fields.get("expiry_date", "")
            if expiry and len(expiry) == 6 and expiry.isdigit():
                try:
                    year = 2000 + int(expiry[0:2])
                    month = int(expiry[2:4])
                    day = int(expiry[4:6])
                    from datetime import datetime
                    expiry_date = datetime(year, month, day)
                    if expiry_date < datetime.now():
                        score += 0.30
                        reasons.append("Document appears expired")
                        signals.append(Signal("document_expired", 1.0, 0.30,
                                               f"Expired: {expiry}", "identity_document"))
                    else:
                        signals.append(Signal("document_not_expired", 0.0, 0.10,
                                               f"Expiry: {expiry}", "identity_document"))
                except (ValueError, OverflowError):
                    signals.append(Signal("expiry_parse_error", 0.3, 0.05,
                                           f"Could not parse expiry: {expiry}", "identity_document"))

        # 7) Profile validation warning
        if not profile.validated:
            reasons.append(f"Document profile UNVALIDATED for {detected_type}:{country}")
            signals.append(Signal("profile_unvalidated", 0.5, 0.15,
                                   "Profile rules are unvalidated", "identity_document"))
            score += 0.10

        # 8) Decision
        score = min(score, 1.0)
        confidence = 0.6 if (mrz_result and mrz_result.is_valid) else 0.35
        decision = Decision.CLEAR if score < self._settings.risk_clear_threshold else (
            Decision.REVIEW if score < self._settings.risk_review_threshold else Decision.BLOCK
        )
        if not reasons:
            reasons.append("No identity document anomalies detected")

        # 9) Store evidence
        evidence = self._evidence.store(
            tenant_id=tid,
            storage_uri=f"objects/{tid}/identity/{content_hash}",
            content_type=content_type,
            purpose="identity document verification",
            metadata={"sha256": content_hash, "filename": doc.filename,
                      "document_type": detected_type},
        )

        return EngineResult(
            engine="identity_document",
            risk_score=round(score, 4),
            confidence=round(confidence, 4),
            decision=decision,
            signals=signals,
            reasons=reasons + [f"steps=file_validation,ocr,classification,mrz,profile,decision"],
            model_version=MODEL_VERSION,
            processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            evidence=[],
            extra={
                "sha256": content_hash,
                "document_type": detected_type,
                "country_code": country,
                "profile_validated": profile.validated,
                "mrz_valid": mrz_result.is_valid if mrz_result else None,
                "mrz_type": mrz_result.mrz_type if mrz_result else None,
                "extracted_fields_count": len(mrz_result.fields) if mrz_result else 0,
                "stored_evidence_id": evidence.evidence_id,
            },
        )
