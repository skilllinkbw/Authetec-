"""
MRZ Validation Engine (ICAO 9303)
=================================
Deterministic Machine Readable Zone validation.

Supports TD1 (3x30), TD2 (2x36), TD3 (2x44).

This is a deterministic validator — it does NOT perform OCR. It validates
MRZ data that has already been extracted (by OCR or other means).

Check digits follow ICAO 9303 Part 3: weights 7,3,1 repeating;
0-9 -> 0-9, A-Z -> 10-35, '<' -> 0; check digit = sum(value*weight) mod 10.

Composite (final) check digits are validated for ALL document types:
  - TD3: doc number+check, DOB+check, expiry+check, optional data + its
    check (l2[44])                                        (ICAO 9303 Part 4)
  - TD1: doc number+check, optional1, DOB+check, expiry+check,
    optional2 -> check at l2[30]                          (ICAO 9303 Part 5)
  - TD2: doc number+check, DOB+check, expiry+check, optional data ->
    check at l2[36]                                       (ICAO 9303 Part 5)

Raw field values (including '<' fillers) are used in every check-digit
computation: fillers have value 0 but still occupy a weighting position.
Fields that carry no check digit of their own (TD1 name line, optional
data) are never claimed to be individually checksum-protected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

_WEIGHTS = [7, 3, 1]
_FILLER = "<"


def _char_value(c: str) -> int:
    if c == _FILLER:
        return 0
    if c.isdigit():
        return int(c)
    if c.isalpha():
        return ord(c.upper()) - ord("A") + 10
    return 0


def compute_check_digit(text: str) -> int:
    total = 0
    for i, c in enumerate(text):
        total += _char_value(c) * _WEIGHTS[i % len(_WEIGHTS)]
    return total % 10


def validate_check_digit(text: str, expected: str) -> bool:
    if not expected.isdigit():
        return False
    return compute_check_digit(text) == int(expected)


def detect_mrz_type(lines: List[str]) -> str:
    if not lines:
        return "unknown"
    lines = [l.strip() for l in lines if l.strip()]
    if len(lines) == 2:
        n = len(lines[0])
        if n == 44:
            return "TD3"
        if n == 36:
            return "TD2"
        if n == 30:
            return "TD1"
    elif len(lines) == 3 and len(lines[0]) == 30:
        return "TD1"
    return "unknown"


def extract_mrz_from_text(text: str) -> List[str]:
    """Best-effort MRZ line extraction from OCR text."""
    if not text:
        return []
    out: List[str] = []
    for line in text.split("\n"):
        s = line.strip().upper().replace(" ", "")
        if len(s) in (30, 36, 44):
            ok = sum(1 for c in s if c.isalnum() or c == _FILLER)
            if ok / max(len(s), 1) > 0.85:
                out.append(s)
    return out


def _parse_td3(line1: str, line2: str) -> Dict[str, str]:
    """TD3 (passport) — 2 lines x 44 chars."""
    r: Dict[str, str] = {}
    r["document_type"] = line1[0:2].replace(_FILLER, "")
    r["issuer"] = line1[2:5].replace(_FILLER, "")
    r["name"] = line1[5:44].rstrip(_FILLER)
    r["document_number_raw"] = line2[0:9]  # raw: fillers occupy weight positions
    r["document_number"] = line2[0:9].replace(_FILLER, "")
    r["document_number_check"] = line2[9]
    r["nationality"] = line2[10:13].replace(_FILLER, "")
    r["date_of_birth"] = line2[13:19]
    r["date_of_birth_check"] = line2[19]
    r["sex"] = line2[20]
    r["expiry_date"] = line2[21:27]
    r["expiry_check"] = line2[27]
    r["optional_raw"] = line2[28:42]  # kept raw: composite check uses fillers
    r["optional"] = line2[28:42].replace(_FILLER, "")
    r["optional_check"] = line2[42]
    r["final_check"] = line2[43]
    return r


def _validate_td3_fields(f: Dict[str, str]) -> List[str]:
    issues: List[str] = []
    if not validate_check_digit(f["document_number"], f["document_number_check"]):
        issues.append("document_number check digit failed")
    if not validate_check_digit(f["date_of_birth"], f["date_of_birth_check"]):
        issues.append("date_of_birth check digit failed")
    if not validate_check_digit(f["expiry_date"], f["expiry_check"]):
        issues.append("expiry_date check digit failed")
    # Composite (final) check digit over doc number (RAW, incl. fillers) +
    # check + DOB + check + expiry + check + optional data (RAW, fillers
    # count as 0 but occupy weight positions) + its check.  ICAO 9303 Part 4.
    composite = (
        f["document_number_raw"] + f["document_number_check"]
        + f["date_of_birth"] + f["date_of_birth_check"]
        + f["expiry_date"] + f["expiry_check"]
        + f["optional_raw"] + f["optional_check"]
    )
    if not validate_check_digit(composite, f["final_check"]):
        issues.append("final composite check digit failed")
    if f["sex"] not in ("M", "F", "X", _FILLER):
        issues.append(f"invalid sex field: '{f['sex']}'")
    if len(f["nationality"]) != 3:
        issues.append(f"nationality should be a 3-letter code: '{f['nationality']}'")
    if len(f["issuer"]) != 3:
        issues.append(f"issuer should be a 3-letter code: '{f['issuer']}'")
    for k in ("date_of_birth", "expiry_date"):
        if not f[k].isdigit():
            issues.append(f"{k} should be 6 digits: '{f[k]}'")
    return issues


def _parse_td1(lines: List[str]) -> Dict[str, str]:
    """TD1 (ID card) — 3 lines x 30 chars.

    Line 1: doc code (2) | issuer (3) | doc number (9) | check (1) | optional1 (15)
    Line 2: DOB (6) | check (1) | sex (1) | expiry (6) | check (1) |
            nationality (3) | optional2 (11) | composite check (1)
    Line 3: name (30)

    Verified against the ICAO 9303 Part 5 published TD1 sample:
    doc "D23145890" -> check 7 at l1[14]; DOB "740812" -> check 2 at l2[6];
    expiry "120415" -> check 9 at l2[14]; composite check 6 at l2[29].
    """
    l1, l2, l3 = lines[0], lines[1], lines[2]
    r: Dict[str, str] = {}
    r["document_type"] = l1[0:2].replace(_FILLER, "")
    r["issuer"] = l1[2:5].replace(_FILLER, "")
    r["document_number_raw"] = l1[5:14]  # raw: fillers occupy weight positions
    r["document_number"] = l1[5:14].replace(_FILLER, "")
    r["document_number_check"] = l1[14]
    r["optional1_raw"] = l1[15:30]  # raw fillers retained (composite input)
    r["optional"] = l1[15:30].replace(_FILLER, "")
    r["date_of_birth"] = l2[0:6]
    r["date_of_birth_check"] = l2[6]
    r["sex"] = l2[7]
    r["expiry_date"] = l2[8:14]
    r["expiry_check"] = l2[14]
    r["nationality"] = l2[15:18].replace(_FILLER, "")
    r["optional2_raw"] = l2[18:29]  # raw fillers retained (composite input)
    r["optional2"] = l2[18:29].replace(_FILLER, "")
    r["final_check"] = l2[29]
    r["name"] = l3.rstrip(_FILLER)
    return r


def _parse_td2(line1: str, line2: str) -> Dict[str, str]:
    """TD2 — 2 lines x 36 chars."""
    r: Dict[str, str] = {}
    r["document_type"] = line1[0:2].replace(_FILLER, "")
    r["issuer"] = line1[2:5].replace(_FILLER, "")
    r["name"] = line1[5:36].rstrip(_FILLER)
    r["document_number_raw"] = line2[0:9]  # raw: fillers occupy weight positions
    r["document_number"] = line2[0:9].replace(_FILLER, "")
    r["document_number_check"] = line2[9]
    r["nationality"] = line2[10:13].replace(_FILLER, "")
    r["date_of_birth"] = line2[13:19]
    r["date_of_birth_check"] = line2[19]
    r["sex"] = line2[20]
    r["expiry_date"] = line2[21:27]
    r["expiry_check"] = line2[27]
    r["optional_raw"] = line2[28:35]  # raw fillers retained (composite input)
    r["optional"] = line2[28:35].replace(_FILLER, "")
    r["final_check"] = line2[35]  # TD2 composite check digit
    return r


def _validate_common_date_fields(f: Dict[str, str]) -> List[str]:
    """Validate individual field check digits for TD1/TD2.

    The document-number check digit is computed over the RAW field
    (fillers '<' count as 0 but occupy weight positions) per ICAO 9303
    Part 3 — a document number shorter than its field is padded with
    fillers inside the field, so the stripped value would give a wrong
    weighting.  DOB/expiry fields are always 6 digits, raw == stripped.

    Note: fields that do NOT contain check digits (e.g. TD1 name line,
    TD1 optional data 1/2, TD2 optional data as standalone fields) are
    never claimed to be checksum-protected here — they are only covered
    through the composite check digit where ICAO 9303 defines one.
    """
    issues: List[str] = []
    if not validate_check_digit(f["document_number_raw"], f["document_number_check"]):
        issues.append("document_number check digit failed")
    if not validate_check_digit(f["date_of_birth"], f["date_of_birth_check"]):
        issues.append("date_of_birth check digit failed")
    if not validate_check_digit(f["expiry_date"], f["expiry_check"]):
        issues.append("expiry_date check digit failed")
    if f["sex"] not in ("M", "F", "X", _FILLER):
        issues.append(f"invalid sex field: '{f['sex']}'")
    return issues


def _validate_td1_fields(f: Dict[str, str]) -> List[str]:
    """TD1 individual + composite check digits (ICAO 9303 Part 3/5).

    Composite check digit (l2[29]) is computed over:
      document number + its check (l1[6:15])  +
      optional data 1 (l1[16:30])             +
      date of birth + its check (l2[1:7])     +
      date of expiry + its check (l2[9:15])   +
      optional data 2 (l2[19:29])
    Raw field values are used (fillers included as 0-value characters).
    """
    issues = _validate_common_date_fields(f)
    composite = (
        f["document_number_raw"] + f["document_number_check"]
        + f["optional1_raw"]
        + f["date_of_birth"] + f["date_of_birth_check"]
        + f["expiry_date"] + f["expiry_check"]
        + f["optional2_raw"]
    )
    if not validate_check_digit(composite, f["final_check"]):
        issues.append("composite check digit failed")
    return issues


def _validate_td2_fields(f: Dict[str, str]) -> List[str]:
    """TD2 individual + composite check digits (ICAO 9303 Part 3/5).

    Composite check digit (l2[36]) is computed over:
      document number + its check (l2[1:10])  +
      date of birth + its check (l2[14:20])   +
      date of expiry + its check (l2[22:28])  +
      optional data (l2[29:35])
    Raw field values are used (fillers included as 0-value characters).
    """
    issues = _validate_common_date_fields(f)
    composite = (
        f["document_number_raw"] + f["document_number_check"]
        + f["date_of_birth"] + f["date_of_birth_check"]
        + f["expiry_date"] + f["expiry_check"]
        + f["optional_raw"]
    )
    if not validate_check_digit(composite, f["final_check"]):
        issues.append("composite check digit failed")
    return issues


@dataclass
class MrzValidationResult:
    """Result of MRZ validation."""
    mrz_type: str = "unknown"
    fields: Dict[str, str] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    check_digit_valid: bool = False
    structure_valid: bool = False
    raw_lines: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.structure_valid and self.check_digit_valid and not self.issues


def validate_mrz(lines: List[str], expected_type: str = "auto") -> MrzValidationResult:
    """Validate MRZ lines. Does NOT perform OCR — input must be extracted lines."""
    result = MrzValidationResult(raw_lines=list(lines))
    clean = [l.strip().upper().replace(" ", "") for l in lines if l.strip()]
    if not clean:
        result.issues.append("No MRZ lines provided")
        return result

    mrz_type = detect_mrz_type(clean) if expected_type == "auto" else expected_type
    result.mrz_type = mrz_type

    if mrz_type == "TD3":
        if len(clean) < 2:
            result.issues.append("TD3 requires 2 lines")
            return result
        if len(clean[0]) != 44 or len(clean[1]) != 44:
            result.issues.append(
                f"TD3 lines must be 44 chars each, got {len(clean[0])} and {len(clean[1])}")
            return result
        result.structure_valid = True
        result.fields = _parse_td3(clean[0], clean[1])
        result.issues = _validate_td3_fields(result.fields)
    elif mrz_type == "TD1":
        if len(clean) < 3:
            result.issues.append("TD1 requires 3 lines")
            return result
        if any(len(l) != 30 for l in clean[:3]):
            result.issues.append("TD1 lines must be 30 chars each")
            return result
        result.structure_valid = True
        result.fields = _parse_td1(clean[:3])
        result.issues = _validate_td1_fields(result.fields)
    elif mrz_type == "TD2":
        if len(clean) < 2:
            result.issues.append("TD2 requires 2 lines")
            return result
        if len(clean[0]) != 36 or len(clean[1]) != 36:
            result.issues.append("TD2 lines must be 36 chars each")
            return result
        result.structure_valid = True
        result.fields = _parse_td2(clean[0], clean[1])
        result.issues = _validate_td2_fields(result.fields)
    else:
        result.issues.append(f"Unknown MRZ type: {mrz_type}")

    result.check_digit_valid = not any(
        "check digit failed" in issue for issue in result.issues)
    return result
