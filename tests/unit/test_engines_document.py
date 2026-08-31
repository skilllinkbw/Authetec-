"""Unit tests for the document engine (file validation + verification)."""

from __future__ import annotations

import base64

import pytest

from app.engines.document import (
    DocumentEngine,
    DocumentInput,
    DocumentValidationError,
    validate_document,
)

# Valid 1x1 red-pixel PNG (72 bytes).
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class TestFileValidation:
    def test_accepts_png(self):
        assert validate_document(PNG_1PX, "image/png") == "image/png"

    def test_rejects_empty(self):
        with pytest.raises(DocumentValidationError):
            validate_document(b"")

    def test_rejects_too_small(self):
        with pytest.raises(DocumentValidationError):
            validate_document(b"PK", "application/zip")

    def test_rejects_executable(self):
        with pytest.raises(DocumentValidationError, match="Executable"):
            validate_document(b"MZ" + b"\x00" * 200)

    def test_rejects_archive(self):
        with pytest.raises(DocumentValidationError, match="Archive"):
            validate_document(b"PK\x03\x04" + b"\x00" * 200)

    def test_rejects_unknown_type(self):
        with pytest.raises(DocumentValidationError):
            validate_document(b"X" * 1000, "text/plain")


class TestDocumentEngine:
    def test_verify_produces_result(self):
        result = DocumentEngine(tenant_id="acme").verify(
            DocumentInput(filename="id.png", content=PNG_1PX,
                          declared_content_type="image/png"),
            tenant_id="acme",
        )
        assert result.engine == "document"
        assert 0.0 <= result.risk_score <= 1.0
        assert result.decision.value in ("CLEAR", "REVIEW", "BLOCK")
        assert result.extra["sha256"]
        assert result.extra["stored_evidence_id"]

    def test_engine_result_is_explainable(self):
        result = DocumentEngine(tenant_id="acme").verify(
            DocumentInput(filename="id.png", content=PNG_1PX,
                          declared_content_type="image/png"),
            tenant_id="acme",
        )
        assert result.reasons
        assert all(s.source == "document" for s in result.signals)
