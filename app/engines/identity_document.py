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
from app.engines.ocr_pipeline import assess_image_quality, extract_text
from app.engines.cross_checks import run_cross_checks
from app.engines.document_profiles import get_profile_or_default
from app.models.risk import Decision, EngineResult, Signal
from app.services.evidence import get_evidence_engine

logger = logging.getLogger("authetec.identity_document")

MODEL_VERSION = "identity-doc-1.1"

# Replay detection: bounded in-process map of (tenant, sha256) -> first
# seen timestamp.  Correct for single-worker deployments only; a
# Redis-backed store is required for multi-worker/multi-node (tracked in
# AUTHEC_PRODUCTION_HARDENING_REPORT).  No biometric/personal data is
# stored here — only the content digest the engine already computes.
_REPLAY_WINDOW_SECONDS = 3600.0
_REPLAY_MAX_ENTRIES = 50_000
_replay_cache: Dict[str, float] = {}


def _check_replay(tenant_id: str, content_hash: str) -> bool:
    """Return True if this exact document content was seen recently."""
    import time as _time
    key = f"{tenant_id}:{content_hash}"
    now = _time.monotonic()
    if len(_replay_cache) > _REPLAY_MAX_ENTRIES:
        _replay_cache.clear()
    seen = _replay_cache.get(key)
    _replay_cache[key] = now
    return seen is not None and (now - seen) < _REPLAY_WINDOW_SECONDS


@dataclass
class IdentityDocumentInput:
    filename: str
    content: bytes
    declared_content_type: str = ""
    document_type: str = "auto"
    country_code: str = ""
    # Optional visual-zone data declared by the user; when provided it is
    # cross-checked against the MRZ (generic checks only).
    declared_fields: Optional[Dict[str, str]] = None


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

        # 2) Image quality assessment (deterministic signals)
        quality = assess_image_quality(doc.content)
        if not quality.assessed:
            score += 0.25
            reasons.append("Document image could not be decoded for quality checks")
            signals.append(Signal("image_undecodable", 1.0, 0.25,
                                  "Image undecodable", "identity_document"))
        else:
            for issue in quality.issues:
                score += 0.10
                reasons.append(f"Document image quality issue: {issue}")
                signals.append(Signal(f"image_quality_{issue}", 0.8, 0.10,
                                      issue, "identity_document"))
            if not quality.issues:
                signals.append(Signal("image_quality_ok", 0.0, 0.05,
                                      "No image-quality issues detected",
                                      "identity_document"))

        # 3) OCR — structured outcome distinguishes engine-missing,
        #    decode-failure and no-text so the pipeline cannot fail open.
        ocr = extract_text(doc.content, content_type)
        text = ocr.text
        if not ocr.has_text:
            if not ocr.engine_available:
                score += 0.30
                reasons.append(
                    "No OCR engine installed on this deployment — document "
                    "contents could not be verified")
                signals.append(Signal("ocr_engine_unavailable", 1.0, 0.30,
                                      "; ".join(ocr.notes) or "no OCR engine",
                                      "identity_document"))
            elif ocr.error:
                score += 0.25
                reasons.append(f"OCR failed: {ocr.error}")
                signals.append(Signal("ocr_failed", 1.0, 0.25,
                                      ocr.error, "identity_document"))
            else:
                signals.append(Signal("ocr_no_text", 0.5, 0.10,
                                      "OCR produced no text", "identity_document"))
                score += 0.10

        # 4) Document type detection
        detected_type = doc.document_type
        if detected_type == "auto":
            detected_type = "unknown"

        # 5) MRZ extraction and validation
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

        # 6) MRZ <-> declared visual-zone consistency (generic checks)
        if mrz_result and mrz_result.is_valid and doc.declared_fields:
            inconsistencies = run_cross_checks(doc.declared_fields,
                                               mrz_result.fields)
            for inc in inconsistencies:
                score += 0.25
                reasons.append(f"Field inconsistency ({inc.field}): {inc.reason}")
                signals.append(Signal(
                    f"cross_check_{inc.field}", 0.9, 0.25,
                    inc.reason, "identity_document"))
            if not inconsistencies:
                signals.append(Signal("cross_checks_passed", 0.0, 0.05,
                                      "Declared fields consistent with MRZ",
                                      "identity_document"))

        # 7) Replay / duplicate-submission detection (content digest only)
        if _check_replay(tid, content_hash):
            score += 0.20
            reasons.append("Identical document content submitted repeatedly "
                           "(possible replay)")
            signals.append(Signal("document_replay", 0.8, 0.20,
                                  content_hash, "identity_document"))

        # 8) Document profile
        country = doc.country_code or "XX"
        if country == "XX" and mrz_result and mrz_result.fields:
            issuer = mrz_result.fields.get("issuer", "")
            if issuer:
                country = issuer
        profile = get_profile_or_default(detected_type, country)
        # 9) Expiry check from MRZ
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

        # 9) Profile validation warning
        if not profile.validated:
            reasons.append(f"Document profile UNVALIDATED for {detected_type}:{country}")
            signals.append(Signal("profile_unvalidated", 0.5, 0.15,
                                   "Profile rules are unvalidated", "identity_document"))
            score += 0.10

        # 10) Decision
        score = min(score, 1.0)
        confidence = 0.6 if (mrz_result and mrz_result.is_valid) else 0.35
        decision = Decision.CLEAR if score < self._settings.risk_clear_threshold else (
            Decision.REVIEW if score < self._settings.risk_review_threshold else Decision.BLOCK
        )
        if not reasons:
            reasons.append("No identity document anomalies detected")

        # 11) Store evidence
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
            reasons=reasons + [f"steps=file_validation,quality,ocr,mrz,profile,decision"],
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
                "image_quality": {
                    "assessed": quality.assessed,
                    "quality_score": quality.quality_score,
                    "issues": quality.issues,
                },
                "ocr": {
                    "engine": ocr.engine,
                    "engine_available": ocr.engine_available,
                    "has_text": ocr.has_text,
                },
            },
        )
