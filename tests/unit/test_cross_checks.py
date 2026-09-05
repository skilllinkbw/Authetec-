"""Tests for generic cross-field consistency checks (no country rules)."""

from __future__ import annotations

from datetime import datetime

from app.engines.cross_checks import (
    check_date_of_birth,
    check_document_number,
    check_expiry,
    check_name,
    check_nationality,
    check_sex,
    run_cross_checks,
)


MRZ_FIELDS = {
    "name": "ERIKSSON<<ANNA<MARIA",
    "document_number": "D23145890",
    "nationality": "D<<",
    "sex": "F",
    "date_of_birth": "740812",
    "expiry_date": "120415",
}


class TestIndividualChecks:
    def test_matching_name_passes(self):
        assert check_name("Eriksson, Anna Maria", "ERIKSSON<<ANNA<MARIA") is None

    def test_mismatched_name_flagged(self):
        r = check_name("Svendsen, Bo", "ERIKSSON<<ANNA<MARIA")
        assert r is not None and r.field == "name"

    def test_document_number_mismatch(self):
        assert check_document_number("D23145891", "D23145890") is not None
        assert check_document_number("d23145890", "D23145890") is None

    def test_nationality_mismatch(self):
        assert check_nationality("UTO", "D<<") is not None
        assert check_nationality("D", "D<<") is None

    def test_sex_mismatch(self):
        assert check_sex("M", "F") is not None
        assert check_sex("f", "F") is None

    def test_dob_formats_accepted(self):
        # YYYY-MM-DD and DDMMYYYY both encode to 740812.
        assert check_date_of_birth("1974-08-12", "740812") is None
        assert check_date_of_birth("12081974", "740812") is None
        assert check_date_of_birth("740812", "740812") is None

    def test_dob_mismatch(self):
        assert check_date_of_birth("1974-08-13", "740812") is not None

    def test_missing_data_never_a_mismatch(self):
        assert check_name("", "ERIKSSON<<ANNA<MARIA") is None
        assert check_name("Anna", "") is None
        assert check_date_of_birth("", "740812") is None


class TestExpiryChecks:
    def test_future_expiry_not_flagged(self):
        now = datetime(2012, 1, 1)
        issues = check_expiry("2012-04-15", "120415", now=now)
        assert issues == []

    def test_expired_flagged_under_both_century_readings(self):
        now = datetime(2030, 1, 1)
        issues = check_expiry("2012-04-15", "120415", now=now)
        assert any(i.reason == "document expiry date has passed" for i in issues)

    def test_expiry_mismatch(self):
        now = datetime(2012, 1, 1)
        issues = check_expiry("2013-04-15", "120415", now=now)
        assert any("does not match" in i.reason for i in issues)

    def test_ambiguous_two_digit_year_not_false_flagged(self):
        # '9901' reads as 2099 or 1999; with now=2050 both are past ->
        # flagged; with now=2000 at least one reading is future -> only
        # unambiguous expiry is ever reported.
        now = datetime(2000, 1, 1)
        issues = check_expiry("", "990101", now=now)
        assert issues == []


class TestRunCrossChecks:
    def test_consistent_declared_fields_pass(self):
        declared = {
            "name": "Anna Maria Eriksson",
            "document_number": "D23145890",
            "nationality": "D",
            "sex": "F",
            "date_of_birth": "1974-08-12",
            "expiry_date": "2012-04-15",
        }
        issues = run_cross_checks(declared, MRZ_FIELDS,
                                  now=datetime(2012, 1, 1))
        assert issues == []

    def test_tampered_field_detected(self):
        declared = dict(MRZ_FIELDS)
        declared["document_number"] = "X99999999"
        issues = run_cross_checks(declared, MRZ_FIELDS,
                                  now=datetime(2012, 1, 1))
        assert len(issues) == 1
        assert issues[0].field == "document_number"

    def test_multiple_inconsistencies_all_reported(self):
        declared = {
            "name": "Someone Else",
            "sex": "M",
            "date_of_birth": "1999-01-01",
        }
        issues = run_cross_checks(declared, MRZ_FIELDS)
        fields = {i.field for i in issues}
        assert fields == {"name", "sex", "date_of_birth"}

    def test_empty_declared_fields_no_issues(self):
        assert run_cross_checks({}, MRZ_FIELDS) == []
        assert run_cross_checks({"name": ""}, MRZ_FIELDS) == []
