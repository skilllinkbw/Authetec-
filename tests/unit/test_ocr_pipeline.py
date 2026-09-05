"""OCR pipeline tests: adversarial, degraded and malformed inputs.

Image-level degradations are generated synthetically with OpenCV; the
suite verifies the pipeline NEVER crashes and NEVER silently accepts
corrupt data.  All fixtures are SYNTHETIC/TEST-ONLY.
"""

from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from app.engines.ocr_pipeline import (  # noqa: E402
    assess_image_quality,
    extract_text,
    ocr_engine_status,
    preprocess_for_ocr,
)
from app.engines.mrz import compute_check_digit, extract_mrz_from_text, validate_mrz  # noqa: E402


def _make_png(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _sharp_document(w=640, h=400) -> "np.ndarray":
    """A synthetic document: white background, black text-like bars."""
    img = np.full((h, w), 235, dtype=np.uint8)
    for y in range(40, h - 40, 24):
        cv2.rectangle(img, (30, y), (w - 30, y + 10), 30, -1)
    return img


def _valid_td1_lines():
    dnc = str(compute_check_digit("D23145890"))
    dbc = str(compute_check_digit("740812"))
    ec = str(compute_check_digit("120415"))
    l1 = "I<UTOD23145890" + dnc + "<" * 15
    l2 = "740812" + dbc + "F" + "120415" + ec + "D<<" + "<" * 11 + "6"
    l3 = "ERIKSSON<<ANNA<MARIA<<<<<<<<<<"
    return [l1, l2, l3]


class TestEngineStatus:
    def test_status_reports_engines(self):
        status = ocr_engine_status()
        assert isinstance(status, dict)
        assert "pytesseract" in status and "pypdf" in status and "cv2" in status
        assert status["cv2"] is True  # required by this test module

    def test_extract_text_reports_unavailable_engine(self):
        if ocr_engine_status().get("pytesseract"):
            pytest.skip("pytesseract installed; unavailable-engine path not testable")
        out = extract_text(_make_png(_sharp_document()), "image/png")
        assert out.text == ""
        assert out.engine_available is False
        assert any("pytesseract" in n for n in out.notes)

    def test_extract_text_empty_content(self):
        out = extract_text(b"", "image/png")
        assert out.has_text is False
        assert "empty content" in out.error


class TestImageQualitySignals:
    def test_sharp_image_has_no_quality_issues(self):
        q = assess_image_quality(_make_png(_sharp_document()))
        assert q.assessed is True
        assert q.quality_score == 1.0
        assert q.issues == []

    def test_blurred_image_flagged(self):
        img = cv2.GaussianBlur(_sharp_document(), (31, 31), 12)
        q = assess_image_quality(_make_png(img))
        assert q.assessed is True
        assert "likely_blur" in q.issues
        assert q.quality_score < 1.0

    def test_glare_flagged(self):
        img = _sharp_document()
        img[0:60, :] = 255  # bright glare band
        q = assess_image_quality(_make_png(img))
        assert "possible_glare" in q.issues

    def test_low_resolution_flagged(self):
        q = assess_image_quality(_make_png(_sharp_document(64, 32)))
        assert "low_resolution" in q.issues

    def test_undecodable_image_flagged_not_crash(self):
        q = assess_image_quality(b"not an image at all")
        assert q.assessed is False
        assert "undecodable_image" in q.issues
        assert q.quality_score == 0.0

    def test_jpeg_compression_survives(self):
        ok, buf = cv2.imencode(".jpg", _sharp_document(),
                               [cv2.IMWRITE_JPEG_QUALITY, 15])
        assert ok
        q = assess_image_quality(buf.tobytes())
        assert q.assessed is True  # decoded; artifacts may or may not flag


class TestPreprocessing:
    def test_preprocess_returns_image(self):
        img = preprocess_for_ocr(_make_png(_sharp_document()))
        assert img is not None
        assert img.ndim == 2  # grayscale

    def test_preprocess_upscales_small_images(self):
        small = _sharp_document(120, 80)
        img = preprocess_for_ocr(_make_png(small))
        assert img.shape[0] >= 160 and img.shape[1] >= 240

    def test_preprocess_undecodable_returns_none(self):
        assert preprocess_for_ocr(b"garbage") is None

    def test_rotated_input_still_processed(self):
        img = _sharp_document()
        rot = cv2.getRotationMatrix2D((320, 200), 7, 1.0)
        img = cv2.warpAffine(img, rot, (640, 400),
                             borderMode=cv2.BORDER_REPLICATE)
        out = preprocess_for_ocr(_make_png(img))
        assert out is not None  # must not crash; deskew is best-effort


class TestTextAdversarialMrz:
    """Character-level attacks on MRZ lines (post-OCR text path)."""

    def _td3_lines(self):
        dnc = str(compute_check_digit("L898902C3"))
        dbc = str(compute_check_digit("740812"))
        ec = str(compute_check_digit("120415"))
        l1 = ("P<UTOERIKSSON<<ANNA<MARIA").ljust(44, "<")
        opt = "<" * 14
        oc = str(compute_check_digit(opt))
        final = str(compute_check_digit(
            "L898902C3" + dnc + "740812" + dbc + "120415" + ec + opt + oc))
        l2 = "L898902C3" + dnc + "UTO" + "740812" + dbc + "F" + "120415" + ec + opt + oc + final
        assert len(l1) == 44 and len(l2) == 44
        return [l1, l2]

    def test_valid_mrz_survives_extraction(self):
        text = "header\n" + "\n".join(self._td3_lines()) + "\nfooter"
        lines = extract_mrz_from_text(text)
        assert len(lines) == 2
        assert validate_mrz(lines).is_valid

    def test_altered_character_rejected(self):
        lines = self._td3_lines()
        lines[1] = lines[1][:5] + ("M" if lines[1][5] != "M" else "N") + lines[1][6:]
        r = validate_mrz(extract_mrz_from_text("\n".join(lines)))
        assert not r.is_valid

    def test_inserted_character_breaks_structure(self):
        lines = self._td3_lines()
        lines[1] = lines[1] + "X"  # 45 chars — structural failure
        r = validate_mrz(extract_mrz_from_text("\n".join(lines)))
        assert not r.is_valid

    def test_removed_character_breaks_structure(self):
        lines = self._td3_lines()
        lines[0] = lines[0][:-1]  # 43 chars
        r = validate_mrz(extract_mrz_from_text("\n".join(lines)))
        assert not r.is_valid

    def test_malformed_random_text_yields_nothing_valid(self):
        r = validate_mrz(extract_mrz_from_text("##########\n@@@@@@@@@@@@\n!!!!"))
        assert not r.is_valid

    def test_suspicious_optional_data_flagged_by_composite(self):
        # Planted data in a composite-covered field must fail the composite.
        lines = _valid_td1_lines()
        lines[0] = lines[0][:15] + "SECRET12345678" + lines[0][29:]
        r = validate_mrz(lines)
        assert not r.is_valid

    def test_inconsistent_identity_fields_reported(self):
        # Sex in MRZ vs declared sex is cross-checked by the engine layer
        # (see test_cross_checks.py); here the MRZ must still expose fields.
        r = validate_mrz(_valid_td1_lines())
        assert r.fields.get("sex") == "F"

    def test_noisy_ocr_never_crashes(self):
        rng = np.random.default_rng(7)
        for _ in range(20):
            junk = "".join(rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"))
                           for _ in range(int(rng.integers(1, 60))))
            extract_mrz_from_text(junk)
            validate_mrz([junk])
