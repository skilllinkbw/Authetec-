"""Unit tests for the MRZ validation engine (ICAO 9303).

Test MRZ data is generated programmatically from the ICAO check-digit
algorithm (verified against published vectors) so fixtures are always
self-consistent. Tamper tests prove that altered fields fail validation.
"""

from __future__ import annotations

import pytest

from app.engines.mrz import (
    MrzValidationResult,
    compute_check_digit,
    detect_mrz_type,
    extract_mrz_from_text,
    validate_check_digit,
    validate_mrz,
)


def _td3(docnum="L898902C3", nat="UTO", dob="740812", sex="F",
         exp="120415", optional="<<"):
    """Build a self-consistent TD3 (passport) MRZ: 2 lines x 44 chars."""
    line1 = ("P<UTO" + "ERIKSSON<<ANNA<MARIA").ljust(44, "<")
    dnc, dbc, ec = (str(compute_check_digit(x)) for x in (docnum, dob, exp))
    nat_field = nat.ljust(3, "<")
    opt = optional.replace("<", "")[:14].ljust(14, "<")
    oc = str(compute_check_digit(opt))
    final = str(compute_check_digit(docnum + dnc + dob + dbc + exp + ec + opt + oc))
    line2 = docnum + dnc + nat_field + dob + dbc + sex + exp + ec + opt + oc + final
    assert len(line1) == 44 and len(line2) == 44
    return [line1, line2]


def _td1(docnum="D23145890", issuer="D<<", nat="D<<", dob="740812",
         sex="F", exp="120415", name="ERIKSSON<<ANNA<MARIA"):
    """Build a TD1 (ID card) MRZ: 3 lines x 30 chars."""
    dnc, dbc, ec = (str(compute_check_digit(x)) for x in (docnum, dob, exp))
    line1 = ("I<" + issuer.ljust(3, "<") + docnum + dnc).ljust(30, "<")
    line2 = (dob + dbc + sex + exp + ec + nat.ljust(3, "<")).ljust(30, "<")
    line3 = name.ljust(30, "<")
    assert len(line1) == 30 and len(line2) == 30 and len(line3) == 30
    return [line1, line2, line3]


def _td2(docnum="L898902C3", nat="UTO", dob="740812", sex="F", exp="120415"):
    """Build a TD2 MRZ: 2 lines x 36 chars."""
    line1 = ("P<UTO" + "ERIKSSON<<ANNA<MARIA").ljust(36, "<")
    dnc, dbc, ec = (str(compute_check_digit(x)) for x in (docnum, dob, exp))
    line2 = (docnum + dnc + nat.ljust(3, "<") + dob + dbc + sex + exp + ec).ljust(36, "<")
    assert len(line1) == 36 and len(line2) == 36
    return [line1, line2]


class TestCheckDigitAlgorithm:
    """ICAO 9303 check-digit algorithm against published vectors."""

    def test_document_number_vector(self):
        assert compute_check_digit("L898902C3") == 6

    def test_dob_vector(self):
        assert compute_check_digit("740812") == 2

    def test_expiry_vector(self):
        assert compute_check_digit("120415") == 9

    def test_td1_document_number_vector(self):
        # ICAO TD1 sample: D23145890 -> 7
        assert compute_check_digit("D23145890") == 7

    def test_filler_counts_as_zero(self):
        assert compute_check_digit("<<<") == 0

    def test_validate_check_digit(self):
        assert validate_check_digit("L898902C3", "6") is True
        assert validate_check_digit("L898902C3", "5") is False
        assert validate_check_digit("L898902C3", "<") is False  # non-digit never valid


class TestDetectMrzType:
    def test_td3(self):
        assert detect_mrz_type(_td3()) == "TD3"

    def test_td1(self):
        lines = _td1()
        assert all(len(l) == 30 for l in lines)
        assert detect_mrz_type(lines) == "TD1"

    def test_td2(self):
        lines = _td2()
        assert all(len(l) == 36 for l in lines)
        assert detect_mrz_type(lines) == "TD2"

    def test_empty(self):
        assert detect_mrz_type([]) == "unknown"

    def test_unknown(self):
        assert detect_mrz_type(["SHORT LINE"]) == "unknown"


class TestValidateTd3:
    def test_valid_td3_passes(self):
        r = validate_mrz(_td3())
        assert r.structure_valid is True
        assert r.check_digit_valid is True
        assert r.is_valid is True
        assert r.issues == []

    def test_fields_extracted(self):
        r = validate_mrz(_td3())
        f = r.fields
        assert f["document_type"] == "P"
        assert f["issuer"] == "UTO"
        assert f["document_number"] == "L898902C3"
        assert f["nationality"] == "UTO"
        assert f["date_of_birth"] == "740812"
        assert f["sex"] == "F"
        assert f["expiry_date"] == "120415"
        assert "ERIKSSON" in f["name"]

    # ── tamper detection (SEC regression tests) ─────────────────────

    def test_tampered_document_number_fails(self):
        lines = _td3()
        lines[1] = "M" + lines[1][1:]  # altered doc number, same check digit
        r = validate_mrz(lines)
        assert r.check_digit_valid is False
        assert "document_number check digit failed" in r.issues
        assert r.is_valid is False

    def test_tampered_expiry_fails(self):
        lines = _td3()
        lines[1] = lines[1][:21] + "120416" + lines[1][27:]
        r = validate_mrz(lines)
        assert r.check_digit_valid is False
        assert any("expiry_date check digit failed" in i for i in r.issues)

    def test_tampered_dob_fails(self):
        lines = _td3()
        lines[1] = lines[1][:13] + "740813" + lines[1][19:]
        r = validate_mrz(lines)
        assert r.check_digit_valid is False
        assert any("date_of_birth check digit failed" in i for i in r.issues)

    def test_tampered_composite_fails(self):
        lines = _td3()
        # Corrupt optional data without updating the composite check digit
        lines[1] = lines[1][:28] + "X" + lines[1][29:]
        r = validate_mrz(lines)
        assert r.check_digit_valid is False

    def test_invalid_sex_flagged(self):
        lines = _td3(sex="Q")
        r = validate_mrz(lines)
        assert any("invalid sex" in i for i in r.issues)
        assert r.check_digit_valid is True  # sex has no check digit
        assert r.is_valid is False          # but overall validity fails

    def test_bad_nationality_length_flagged(self):
        lines = _td3(nat="UT")
        r = validate_mrz(lines)
        assert any("nationality" in i for i in r.issues)

    def test_nationality_tampering_is_not_check_digit_protected(self):
        # Known limitation: nationality has no ICAO check digit. Altering it
        # cannot be detected by MRZ checksums alone — documented honestly.
        lines = _td3(nat="ZZZ")
        r = validate_mrz(lines)
        assert r.check_digit_valid is True
        assert r.fields["nationality"] == "ZZZ"


class TestValidateTd1:
    def test_valid_td1(self):
        r = validate_mrz(_td1())
        assert r.mrz_type == "TD1"
        assert r.structure_valid is True
        assert r.check_digit_valid is True
        assert r.fields["document_number"] == "D23145890"
        assert r.fields["date_of_birth"] == "740812"
        assert r.fields["expiry_date"] == "120415"
        assert r.fields["sex"] == "F"
        assert "ERIKSSON" in r.fields["name"]

    def test_td1_requires_3_lines(self):
        r = validate_mrz([_td1()[0]], expected_type="TD1")
        assert r.structure_valid is False
        assert any("3 lines" in i for i in r.issues)

    def test_td1_tampered_doc_number_fails(self):
        lines = _td1()
        lines[0] = lines[0][:13] + "1" + lines[0][14:]  # altered last doc digit
        r = validate_mrz(lines)
        assert r.check_digit_valid is False


class TestValidateTd2:
    def test_td2_structure_and_fields(self):
        r = validate_mrz(_td2())
        assert r.mrz_type == "TD2"
        assert r.structure_valid is True
        assert r.check_digit_valid is True
        assert r.fields["document_number"] == "L898902C3"
        assert r.fields["date_of_birth"] == "740812"
        assert r.fields["expiry_date"] == "120415"

    def test_td2_invalid_check_digits_flagged(self):
        lines = _td2()
        lines[1] = lines[1][:9] + "5" + lines[1][10:]  # corrupt doc check digit
        r = validate_mrz(lines)
        assert r.check_digit_valid is False
        assert "document_number check digit failed" in r.issues


class TestStructuralFailures:
    def test_no_lines(self):
        r = validate_mrz([])
        assert r.structure_valid is False
        assert any("No MRZ" in i for i in r.issues)

    def test_wrong_length(self):
        r = validate_mrz(["SHORT", "LINES"], expected_type="TD3")
        assert r.structure_valid is False
        assert any("44 chars" in i for i in r.issues)

    def test_explicit_type_with_wrong_input(self):
        r = validate_mrz(["SHORT"], expected_type="TD3")
        assert r.structure_valid is False

    def test_unknown_type(self):
        r = validate_mrz(["A" * 40])
        assert r.structure_valid is False
        assert any("Unknown MRZ type" in i for i in r.issues)

    def test_noisy_input_never_crashes(self):
        # OCR noise: lowercase, spaces. Normalisation applies; validator
        # must not crash and must never silently pass corrupt data.
        lines = _td3()
        noisy = [l[:10].lower() + l[10:20] + l[20:].replace("<", " < ") for l in lines]
        r = validate_mrz(noisy)
        assert isinstance(r, MrzValidationResult)


class TestExtraction:
    def test_extract_from_text(self):
        lines = _td3()
        text = "Some text\n" + lines[0] + "\n" + lines[1] + "\nMore text"
        assert extract_mrz_from_text(text) == lines

    def test_extract_empty(self):
        assert extract_mrz_from_text("") == []

    def test_extract_no_mrz(self):
        assert extract_mrz_from_text("no mrz here at all") == []

    def test_extract_skips_short_lines(self):
        assert extract_mrz_from_text("P<UTO\nshort\nL898902C36") == []


