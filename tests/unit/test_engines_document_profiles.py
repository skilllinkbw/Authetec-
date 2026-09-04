"""Unit tests for document profiles and liveness/PAD engine."""

from __future__ import annotations

import base64

import pytest

from app.engines.document_profiles import (
    DocumentProfile,
    DocumentRule,
    FieldRule,
    _drivers_licence_fields,
    _national_id_fields,
    _passport_fields,
    get_profile,
    get_profile_or_default,
    list_profiles,
    register_profile,
)
from app.engines.liveness import (
    DeterministicLivenessDetector,
    LivenessResult,
    PadMethod,
    PresentationAttack,
    get_liveness_detector,
    set_liveness_detector,
)


class TestFieldRules:
    def test_passport_fields(self):
        fields = _passport_fields()
        assert len(fields) >= 7
        names = [f.name for f in fields]
        assert "document_number" in names
        assert "surname" in names
        assert "nationality" in names

    def test_national_id_fields(self):
        fields = _national_id_fields()
        names = [f.name for f in fields]
        assert "document_number" in names
        assert "surname" in names

    def test_drivers_licence_fields(self):
        fields = _drivers_licence_fields()
        names = [f.name for f in fields]
        assert "licence_number" in names
        assert "vehicle_class" in names


class TestProfileRegistry:
    def test_get_passport_bw(self):
        profile = get_profile("passport", "BW")
        assert profile is not None
        assert profile.country_code == "BW"
        assert profile.mrz_supported is True
        assert profile.mrz_type == "TD3"
        assert profile.validated is True

    def test_get_passport_us(self):
        profile = get_profile("passport", "US")
        assert profile is not None
        assert profile.country_code == "US"

    def test_get_national_id_bw(self):
        profile = get_profile("national_id", "BW")
        assert profile is not None
        assert profile.validated is False  # UNVALIDATED
        assert "UNVALIDATED" in profile.notes

    def test_get_unknown_country_falls_back(self):
        profile = get_profile_or_default("passport", "ZZ")
        assert profile is not None
        assert profile.country_code == "ZZ"
        assert profile.validated is False

    def test_get_unknown_type_falls_back(self):
        profile = get_profile_or_default("spaceship_id", "BW")
        assert profile is not None
        assert profile.validated is False

    def test_register_custom_profile(self):
        custom = DocumentProfile(
            document_type="passport",
            country_code="XX",
            country_name="Testland",
            fields=_passport_fields(),
            mrz_supported=True,
            mrz_type="TD3",
            notes="Custom test profile",
            validated=False,
        )
        register_profile(custom)
        retrieved = get_profile("passport", "XX")
        assert retrieved is not None
        assert retrieved.country_name == "Testland"

    def test_list_profiles(self):
        profiles = list_profiles()
        assert len(profiles) >= 6  # at least the built-in profiles


class TestLivenessDetector:
    PNG_1PX = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )

    def test_deterministic_detector_returns_result(self):
        detector = DeterministicLivenessDetector()
        result = detector.check(self.PNG_1PX)
        assert isinstance(result, LivenessResult)
        assert 0.0 <= result.confidence <= 1.0

    def test_deterministic_detector_rejects_empty(self):
        detector = DeterministicLivenessDetector()
        result = detector.check(b"not an image at all")
        # cv2 returns None for undecodable, detector should return non-live
        assert result.is_live is False

    def test_deterministic_detector_method_is_passive(self):
        detector = DeterministicLivenessDetector()
        result = detector.check(self.PNG_1PX)
        assert result.method == PadMethod.PASSIVE

    def test_singleton(self):
        detector = get_liveness_detector()
        assert get_liveness_detector() is detector

    def test_set_detector_overrides_singleton(self):
        original = get_liveness_detector()
        new_detector = DeterministicLivenessDetector(threshold=0.5)
        set_liveness_detector(new_detector)
        assert get_liveness_detector() is new_detector
        # Restore
        set_liveness_detector(original)
