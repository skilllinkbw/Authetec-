"""
Cross-Field Consistency Checks (generic document security)
==========================================================

Generic, country-agnostic verification mechanisms that compare data
DECLARED by a user (visual zone typed into a form) against data EXTRACTED
from the machine-readable zone.  Also provides date/expiry sanity checks.

DESIGN BOUNDARY: these functions contain NO country-specific rules.
National document profiles live in document_profiles.py and remain
clearly separated.  Nothing here fabricates government validation rules.

Honesty note: a match proves textual consistency only — it is not
evidence that the document is genuine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Inconsistency:
    """One detected mismatch between declared and MRZ data."""

    field: str
    declared: str
    mrz: str
    reason: str


_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def _norm_token(value: str) -> str:
    """Uppercase, keep alphanumerics only (MRZ transliteration tolerance)."""
    return _NON_ALNUM.sub("", (value or "").upper())


def _norm_name(value: str) -> str:
    """MRZ name field: '<' is a space; '<<' separates primary/secondary."""
    v = (value or "").upper().replace("<<", " ").replace("<", " ")
    tokens = [t for t in (_NON_ALNUM.sub("", part) for part in v.split()) if t]
    return " ".join(tokens)


def _date_candidates(value: str) -> set:
    """All plausible YYMMDD encodings of a declared date string.

    Accepts common ISO/visual formats (YYYY-MM-DD, YYYY/MM/DD, DDMMYYYY,
    YYYYMMDD, YYMMDD).  Returns the set of 6-digit encodings to compare
    against the MRZ date field.  Empty set if unparseable.
    """
    v = re.sub(r"[^0-9]", "", (value or ""))
    cands = set()
    if len(v) == 8:
        cands.add(v[2:8])                      # YYYYMMDD -> YYMMDD
        cands.add(v[6:8] + v[2:4] + v[0:2])    # DDMMYYYY -> YYMMDD
        cands.add(v[6:8] + v[0:2] + v[2:4])    # MMDDYYYY -> YYMMDD
    elif len(v) == 6:
        cands.add(v)
    return cands


def check_name(declared: str, mrz_name: str) -> Optional[Inconsistency]:
    """Name comparison, order-insensitive across the surname separator.

    ICAO 9303 stores surname first, then '<<', then given names; visual
    zones commonly print given names first.  Without country-specific
    rules the surname/given-name split is NOT knowable generically, so a
    mismatch is reported only when the name-token MULTISETS differ
    (order or punctuation alone is not evidence of inconsistency).
    """
    a = _norm_name(declared).split()
    b = _norm_name(mrz_name).split()
    if a and b and sorted(a) != sorted(b):
        return Inconsistency("name", declared, mrz_name,
                             "declared name does not match MRZ name")
    return None


def check_document_number(declared: str, mrz_number: str) -> Optional[Inconsistency]:
    a, b = _norm_token(declared), _norm_token(mrz_number)
    if a and b and a != b:
        return Inconsistency("document_number", declared, mrz_number,
                             "declared document number does not match MRZ")
    return None


def check_nationality(declared: str, mrz_nationality: str) -> Optional[Inconsistency]:
    a, b = _norm_token(declared), _norm_token(mrz_nationality)
    if a and b and a != b:
        return Inconsistency("nationality", declared, mrz_nationality,
                             "declared nationality does not match MRZ")
    return None


def check_sex(declared: str, mrz_sex: str) -> Optional[Inconsistency]:
    a = (declared or "").strip().upper()[:1]
    b = (mrz_sex or "").strip().upper()[:1]
    if a and b and a != b:
        return Inconsistency("sex", declared, mrz_sex,
                             "declared sex does not match MRZ")
    return None


def check_date_of_birth(declared: str, mrz_dob: str) -> Optional[Inconsistency]:
    """DOB mismatch: declared date has no encoding equal to the MRZ date."""
    cands = _date_candidates(declared)
    mrz = re.sub(r"[^0-9]", "", mrz_dob or "")
    if cands and len(mrz) == 6 and mrz not in cands:
        return Inconsistency("date_of_birth", declared, mrz_dob,
                             "declared date of birth does not match MRZ")
    return None


def check_expiry(declared: str, mrz_expiry: str,
                 now: Optional[datetime] = None) -> List[Inconsistency]:
    """Expiry consistency + expired-document detection."""
    issues: List[Inconsistency] = []
    now = now or datetime.now()
    mrz = re.sub(r"[^0-9]", "", mrz_expiry or "")
    if len(mrz) == 6 and mrz.isdigit():
        cands = _date_candidates(declared) if declared else set()
        if cands and mrz not in cands:
            issues.append(Inconsistency(
                "expiry_date", declared, mrz_expiry,
                "declared expiry date does not match MRZ"))
        # ICAO 9303 stores 2-digit years; century interpretation is
        # document-type specific, so BOTH readings are computed and the
        # inconsistency is flagged only when both are in the past.
        try:
            yy, mm, dd = int(mrz[0:2]), int(mrz[2:4]), int(mrz[4:6])
            candidates = (datetime(2000 + yy, mm, dd),
                          datetime(1900 + yy, mm, dd))
            if all(c < now for c in candidates):
                issues.append(Inconsistency(
                    "expiry_date", declared, mrz_expiry,
                    "document expiry date has passed"))
        except ValueError:
            pass  # structurally invalid date is caught by MRZ validation
    return issues


def run_cross_checks(declared: Dict[str, str],
                     mrz_fields: Dict[str, str],
                     now: Optional[datetime] = None) -> List[Inconsistency]:
    """Run every applicable consistency check.

    Only compares fields present on BOTH sides; missing data is never
    reported as a mismatch (absence is not evidence of fraud).
    """
    issues: List[Inconsistency] = []
    check_map = (
        ("name", check_name),
        ("document_number", check_document_number),
        ("nationality", check_nationality),
        ("sex", check_sex),
        ("date_of_birth", check_date_of_birth),
    )
    for field_name, fn in check_map:
        d = declared.get(field_name, "")
        m = mrz_fields.get(field_name, "")
        if d and m:
            found = fn(d, m)
            if found:
                issues.append(found)
    d_exp = declared.get("expiry_date", "")
    m_exp = mrz_fields.get("expiry_date", "")
    if d_exp and m_exp:
        issues.extend(check_expiry(d_exp, m_exp, now))
    return issues
