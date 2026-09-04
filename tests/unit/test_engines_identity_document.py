"""Unit tests for the Identity Document Engine."""

from __future__ import annotations

import base64

import pytest

from app.engines.identity_document import IdentityDocumentEngine, IdentityDocumentInput
from app.engines.document import DocumentValidationError

# Valid 1x1 red-pixel PNG (72 bytes) — same fixture as test_engines_document.py
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class TestIdentityDocumentEngine:
    def test_verify_produces_result(self):
        engine = IdentityDocumentEngine(tenant_id="test")
        result = engine.verify(
            IdentityDocumentInput(
                filename="passport.png",
                content=PNG_1PX,
                declared_content_type="image/png",
                document_type="passport",
                country_code="BW",
            ),
            tenant_id="test",
        )
        assert result.engine == "identity_document"
        assert 0.0 <= result.risk_score <= 1.0
        assert result.decision.value in ("CLEAR", "REVIEW", "BLOCK")

    def test_passport_profile_used(self):
        engine = IdentityDocumentEngine(tenant_id="test")
        result = engine.verify(
            IdentityDocumentInput(
                filename="passport.png",
                content=PNG_1PX,
                document_type="passport",
                country_code="BW",
            ),
            tenant_id="test",
        )
        assert result.extra["document_type"] == "passport"
        assert result.extra["country_code"] == "BW"

    def test_national_id_profile_used(self):
        engine = IdentityDocumentEngine(tenant_id="test")
        result = engine.verify(
            IdentityDocumentInput(
                filename="id.png",
                content=PNG_1PX,
                document_type="national_id",
                country_code="BW",
            ),
            tenant_id="test",
        )
        assert result.extra["document_type"] == "national_id"
        assert result.extra["country_code"] == "BW"

    def test_drivers_licence_profile_used(self):
        engine = IdentityDocumentEngine(tenant_id="test")
        result = engine.verify(
            IdentityDocumentInput(
                filename="licence.png",
                content=PNG_1PX,
                document_type="drivers_licence",
                country_code="US",
            ),
            tenant_id="test",
        )
        assert result.extra["document_type"] == "drivers_licence"
        assert result.extra["country_code"] == "US"

    def test_result_is_explainable(self):
        engine = IdentityDocumentEngine(tenant_id="test")
        result = engine.verify(
            IdentityDocumentInput(
                filename="passport.png",
                content=PNG_1PX,
                document_type="passport",
                country_code="BW",
            ),
            tenant_id="test",
        )
        assert result.reasons
        assert result.signals
        assert all(hasattr(s, "name") for s in result.signals)

    def test_unknown_country_uses_generic_profile(self):
        engine = IdentityDocumentEngine(tenant_id="test")
        result = engine.verify(
            IdentityDocumentInput(
                filename="passport.png",
                content=PNG_1PX,
                document_type="passport",
                country_code="ZZ",
            ),
            tenant_id="test",
        )
        assert result.extra["profile_validated"] is False

    def test_unknown_document_type(self):
        engine = IdentityDocumentEngine(tenant_id="test")
        result = engine.verify(
            IdentityDocumentInput(
                filename="doc.png",
                content=PNG_1PX,
                document_type="unknown_type",
                country_code="BW",
            ),
            tenant_id="test",
        )
        assert result.extra["document_type"] == "unknown_type"

    def test_evidence_stored(self):
        engine = IdentityDocumentEngine(tenant_id="test")
        result = engine.verify(
            IdentityDocumentInput(
                filename="passport.png",
                content=PNG_1PX,
                document_type="passport",
                country_code="BW",
            ),
            tenant_id="test",
        )
        assert result.extra["stored_evidence_id"]

    def test_processing_time_recorded(self):
        engine = IdentityDocumentEngine(tenant_id="test")
        result = engine.verify(
            IdentityDocumentInput(
                filename="passport.png",
                content=PNG_1PX,
                document_type="passport",
                country_code="BW",
            ),
            tenant_id="test",
        )
        assert result.processing_time_ms > 0
