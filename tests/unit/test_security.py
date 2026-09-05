"""Unit tests for app.core (security utilities and configuration)."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.security import (
    api_key_fingerprint,
    create_access_token,
    decode_access_token,
    hash_secret,
    structured_error,
    verify_secret,
)


class TestSecretHashing:
    def test_roundtrip(self):
        stored = hash_secret("s3cret-value")
        assert stored.startswith("pbkdf2_sha256$")
        assert verify_secret("s3cret-value", stored)
        assert not verify_secret("wrong-value", stored)

    def test_salts_are_unique(self):
        assert hash_secret("same") != hash_secret("same")

    def test_malformed_stored_value(self):
        assert not verify_secret("x", "not-a-valid-hash")


class TestJwt:
    def test_roundtrip_with_claims(self):
        token = create_access_token("user-1", claims={"tenant": "acme", "role": "analyst"})
        payload = decode_access_token(token)
        assert payload["sub"] == "user-1"
        assert payload["tenant"] == "acme"
        assert payload["role"] == "analyst"
        assert "exp" in payload and "jti" in payload

    def test_invalid_token_rejected(self):
        token = create_access_token("user-1")
        with pytest.raises(Exception):
            decode_access_token(token + "tampered")


class TestApiKeys:
    def test_fingerprint_deterministic(self):
        assert api_key_fingerprint("ak_abc") == api_key_fingerprint("ak_abc")
        assert api_key_fingerprint("ak_abc") != api_key_fingerprint("ak_xyz")
        assert len(api_key_fingerprint("ak_abc")) == 64


class TestStructuredError:
    def test_shape(self):
        err = structured_error("bad_request", "Invalid input", request_id="req-1")
        assert err == {"code": "bad_request", "message": "Invalid input",
                       "request_id": "req-1"}


class TestSettings:
    def test_defaults_are_dev_safe(self):
        s = get_settings()
        assert not s.is_production()
        assert s.risk_clear_threshold < s.risk_review_threshold
        assert s.max_upload_mb > 0
