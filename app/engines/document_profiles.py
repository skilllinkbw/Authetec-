"""
Document Profiles
=================
Defines document-type profiles for passport, national ID, and driver's
licence verification. Each profile describes the fields, validation rules,
and document structure so the verification engine can adapt per document
type and country.

This is the foundation for a country-profile architecture: new countries
and document types can be added without rewriting the verification engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class FieldRule:
    """A single field extraction and validation rule."""
    name: str
    required: bool = True
    pattern: Optional[str] = None
    min_length: int = 1
    max_length: int = 100
    checksum: bool = False
    description: str = ""


@dataclass
class DocumentRule:
    """Alias for FieldRule — used in profile definitions."""
    name: str
    required: bool = True
    pattern: Optional[str] = None
    min_length: int = 1
    max_length: int = 100
    checksum: bool = False
    description: str = ""


@dataclass
class DocumentProfile:
    """
    A document profile defines everything the verification engine needs
    to know about a document type from a specific country.
    """
    document_type: str
    country_code: str
    country_name: str
    fields: List[FieldRule] = field(default_factory=list)
    mrz_supported: bool = False
    mrz_type: str = ""
    barcode_supported: bool = False
    qr_supported: bool = False
    nfc_emrtd: bool = False
    has_expiry: bool = True
    has_dob: bool = True
    has_nationality: bool = True
    face_region: Optional[Tuple[float, float, float, float]] = None
    notes: str = ""
    validated: bool = True


# ── Field Rule Builders ───────────────────────────────────────────────

def _passport_fields() -> List[FieldRule]:
    """Standard ICAO 9303 passport fields."""
    return [
        FieldRule("document_number", required=True, pattern=r"^[A-Z0-9]{6,12}$",
                  max_length=12, checksum=False,
                  description="Alphanumeric document number"),
        FieldRule("surname", required=True, min_length=1, max_length=40,
                  description="Holder surname as printed"),
        FieldRule("given_names", required=True, min_length=1, max_length=60,
                  description="Holder given names"),
        FieldRule("nationality", required=True, pattern=r"^[A-Z]{3}$",
                  max_length=3, description="ISO 3166-1 alpha-3 nationality code"),
        FieldRule("date_of_birth", required=True, pattern=r"^\d{2}[01]\d[0-3]\d$",
                  max_length=6, checksum=False,
                  description="YYMMDD format"),
        FieldRule("sex", required=True, pattern=r"^[MFX]$",
                  max_length=1, description="M, F, or X"),
        FieldRule("expiry_date", required=True, pattern=r"^\d{2}[01]\d[0-3]\d$",
                  max_length=6, checksum=False,
                  description="YYMMDD format"),
        FieldRule("personal_number", required=False, max_length=14,
                  description="Optional personal number (check digit varies)"),
    ]


def _national_id_fields() -> List[FieldRule]:
    """Generic national ID fields (customize per country)."""
    return [
        FieldRule("document_number", required=True, min_length=4, max_length=20,
                  description="National ID number"),
        FieldRule("surname", required=True, min_length=1, max_length=40,
                  description="Holder surname"),
        FieldRule("given_names", required=True, min_length=1, max_length=60,
                  description="Holder given names"),
        FieldRule("date_of_birth", required=True, max_length=20,
                  description="Date of birth (format varies by country)"),
        FieldRule("sex", required=False, max_length=1,
                  description="Sex/gender if present"),
        FieldRule("nationality", required=False, max_length=3,
                  description="Nationality if present"),
        FieldRule("expiry_date", required=False, max_length=20,
                  description="Expiry date if present"),
    ]


def _drivers_licence_fields() -> List[FieldRule]:
    """Generic driver's licence fields."""
    return [
        FieldRule("licence_number", required=True, min_length=4, max_length=20,
                  description="Licence number"),
        FieldRule("surname", required=True, min_length=1, max_length=40,
                  description="Holder surname"),
        FieldRule("given_names", required=True, min_length=1, max_length=60,
                  description="Holder given names"),
        FieldRule("date_of_birth", required=True, max_length=20,
                  description="Date of birth"),
        FieldRule("issue_date", required=False, max_length=20,
                  description="Issue date"),
        FieldRule("expiry_date", required=True, max_length=20,
                  description="Expiry date"),
        FieldRule("vehicle_class", required=False, max_length=20,
                  description="Vehicle class/category"),
        FieldRule("address", required=False, max_length=200,
                  description="Address if present"),
    ]

    has_dob: bool = True
    has_nationality: bool = True
    face_region: Optional[Tuple[float, float, float, float]] = None
    notes: str = ""
    validated: bool = True

_PROFILES: Dict[str, DocumentProfile] = {}


def register_profile(profile: DocumentProfile) -> None:
    key = f"{profile.document_type}:{profile.country_code}"
    _PROFILES[key] = profile


def get_profile(document_type: str, country_code: str) -> Optional[DocumentProfile]:
    return _PROFILES.get(f"{document_type}:{country_code}")


def list_profiles() -> List[DocumentProfile]:
    return list(_PROFILES.values())


def get_profile_or_default(document_type: str, country_code: str) -> DocumentProfile:
    profile = get_profile(document_type, country_code)
    if profile:
        return profile
    if document_type == "passport":
        return DocumentProfile(
            document_type="passport", country_code=country_code, country_name="Generic",
            fields=_passport_fields(), mrz_supported=True, mrz_type="TD3",
            notes="Generic passport profile (unvalidated for this country)", validated=False,
        )
    elif document_type == "national_id":
        return DocumentProfile(
            document_type="national_id", country_code=country_code, country_name="Generic",
            fields=_national_id_fields(),
            notes="Generic national ID profile (unvalidated for this country)", validated=False,
        )
    elif document_type == "drivers_licence":
        return DocumentProfile(
            document_type="drivers_licence", country_code=country_code, country_name="Generic",
            fields=_drivers_licence_fields(),
            notes="Generic driver's licence profile (unvalidated for this country)", validated=False,
        )
    return DocumentProfile(
        document_type=document_type, country_code=country_code, country_name="Generic",
        fields=[], notes="Unknown document type (unvalidated)", validated=False,
    )

register_profile(DocumentProfile(
    document_type="passport", country_code="BW", country_name="Botswana",
    fields=_passport_fields(), mrz_supported=True, mrz_type="TD3", nfc_emrtd=True,
    face_region=(0.05, 0.1, 0.35, 0.45),
    notes="Botswana ePassport (ICAO 9303 TD3, NFC/eMRTD capable)",
))

register_profile(DocumentProfile(
    document_type="passport", country_code="US", country_name="United States",
    fields=_passport_fields(), mrz_supported=True, mrz_type="TD3", nfc_emrtd=True,
    face_region=(0.05, 0.1, 0.35, 0.45),
    notes="US ePassport (ICAO 9303 TD3, NFC/eMRTD capable)",
))

register_profile(DocumentProfile(
    document_type="passport", country_code="GB", country_name="United Kingdom",
    fields=_passport_fields(), mrz_supported=True, mrz_type="TD3", nfc_emrtd=True,
    face_region=(0.05, 0.1, 0.35, 0.45),
    notes="UK ePassport (ICAO 9303 TD3, NFC/eMRTD capable)",
))

register_profile(DocumentProfile(
    document_type="national_id", country_code="BW", country_name="Botswana",
    fields=_national_id_fields(), mrz_supported=False, barcode_supported=True,
    has_expiry=False, face_region=(0.1, 0.15, 0.3, 0.4),
    notes="Botswana Omang (national ID). Validation rules are UNVALIDATED.",
    validated=False,
))

register_profile(DocumentProfile(
    document_type="national_id", country_code="US", country_name="United States",
    fields=_national_id_fields(), mrz_supported=False, barcode_supported=True,
    has_expiry=True, face_region=(0.1, 0.15, 0.3, 0.4),
    notes="US state-issued ID. Format varies by state.", validated=False,
))

register_profile(DocumentProfile(
    document_type="drivers_licence", country_code="BW", country_name="Botswana",
    fields=_drivers_licence_fields(), mrz_supported=False, barcode_supported=True,
    face_region=(0.1, 0.15, 0.3, 0.4),
    notes="Botswana driver's licence. Validation rules are UNVALIDATED.",
    validated=False,
))

register_profile(DocumentProfile(
    document_type="drivers_licence", country_code="US", country_name="United States",
    fields=_drivers_licence_fields(), mrz_supported=False, barcode_supported=True,
    face_region=(0.1, 0.15, 0.3, 0.4),
    notes="US driver's licence. Format varies by state; AAMVA standard.",
    validated=False,
))

register_profile(DocumentProfile(
    document_type="drivers_licence", country_code="GB", country_name="United Kingdom",
    fields=_drivers_licence_fields(), mrz_supported=False, barcode_supported=True,
    face_region=(0.1, 0.15, 0.3, 0.4),
    notes="UK driving licence (DVLA photocard).", validated=False,
))
