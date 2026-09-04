# AUTHEtec Critical Security Review — Phase 2

**Baseline commit:** `215bdea` (verified foundation — preserved)
**Review date:** 2026-09-04
**Reviewer:** Independent security/QA pass over the implementation delivered on top of the foundation.

This review is evidence-based. Every finding lists reproduction, root cause, fix and the
regression test that proves the fix. No synthetic accuracy numbers are promoted to real-world
claims anywhere in this document.

---

## 1. Verification of the Foundation

| Gate | Result |
|---|---|
| Backend tests at baseline (`215bdea`) | 125 passed, 0 failed |
| Frontend tests at baseline | 13 passed, 0 failed |
| Frontend build at baseline | PASS |
| Working tree at start | clean (except pre-existing untracked `_tracked.txt`) |
| Remote divergence | none — local HEAD == origin/authetec-foundation-review |

## 2. Findings

### SEC-002-01 — MRZ composite check digit was implemented incorrectly (HIGH — FIXED)

- **Component:** `app/engines/mrz.py` (TD3 validation)
- **Severity:** HIGH
- **Reproduction:** A valid ICAO 9303 TD3 MRZ with filler `<` characters in the optional-data
  field failed the composite check; conversely, a forged MRZ whose optional field had been
  modified could pass because the composite was computed over a *stripped* string, shifting
  every weight after position 28.
- **Expected behaviour:** The TD3 composite check digit is computed over the RAW optional-data
  field (fillers count as value 0 but still consume a weight position), per ICAO 9303 Part 3.
- **Actual behaviour:** `optional.replace("<", "")` was applied before composite computation.
- **Root cause:** Field normalisation was applied to data used as check-digit input.
- **Fix:** Parser now retains `optional_raw`; composite is computed over
  `docnum+check+DOB+check+expiry+check+optional_raw+optional_check`.
  Verified: canonical vectors `L898902C3→6`, `740812→2`, `120415→9`.
- **Regression tests:** `test_valid_td3_passes`, `test_tampered_composite_fails`,
  `test_tampered_document_number_fails`, `test_tampered_expiry_fails`, `test_tampered_dob_fails`.

### SEC-002-02 — TD1 field positions were wrong (MEDIUM — FIXED)

- **Component:** `app/engines/mrz.py` (TD1 parser)
- **Severity:** MEDIUM
- **Reproduction:** The document number was read as `l1[5:30]` (9-char field plus optional
  data) and its check digit read from `l2[0]`, so ID-card MRZs could not be validated correctly.
- **Expected behaviour (verified against published ICAO vectors):**
  doc number `l1[5:14]`, its check `l1[14]`, DOB `l2[0:6]`, DOB check `l2[6]`,
  sex `l2[7]`, expiry `l2[8:14]`, expiry check `l2[14]`, nationality `l2[15:18]`.
- **Fix:** Parser corrected; verified with `D23145890→7`, `740812→2`, `120415→9`.
- **Known limitation (documented, not fixed):** The TD1/TD2 *composite* check digit is parsed
  but NOT validated — its exact field coverage could not be independently verified from
  primary sources during this pass. Individual document-number, DOB and expiry check digits
  ARE fully validated for TD1/TD2. Flagged as a gap in AUTHEC_RELEASE_READINESS.
- **Regression tests:** `TestValidateTd1.test_valid_td1`, `test_td1_tampered_doc_number_fails`,
  `TestValidateTd2.test_td2_structure_and_fields`, `test_td2_invalid_check_digits_flagged`.

### SEC-002-03 — MRZ-only forgery limits are now explicit (LOW — DOCUMENTED)

- Nationality, sex and optional data carry **no** ICAO check digits. `validate_mrz` therefore
  cannot detect their alteration and does not pretend to:
  `test_nationality_tampering_is_not_check_digit_protected` pins this behaviour so future
  changes cannot silently claim checksum protection where none exists.
- `identity_document.py` adds +0.40 risk and never returns CLEAR when MRZ validation fails,
  so OCR plausibility alone cannot produce a CLEAR decision.

### SEC-002-04 — Identity-document tests exercised the wrong code path (MEDIUM — FIXED)

- **Component:** `tests/unit/test_engines_identity_document.py`
- **Reproduction:** The `PNG_1PX` fixture base64 was truncated, producing a payload below the
  64-byte minimum. `verify()` returned the early `BLOCK` path (`extra={"error": ...}`), so six
  tests raised `KeyError: 'document_type'` — meaning the actual verification pipeline was
  **never covered** by those tests.
- **Fix:** Fixture corrected to the full valid 1×1 PNG (72 bytes), same as
  `test_engines_document.py`. The six tests now exercise OCR→MRZ→profile→decision.
- **Regression test:** the corrected suite itself (183 backend tests pass).

### SEC-002-05 — Duplicate imports / dead code in verification router (LOW — FIXED)

- `app/api/v1/verification.py` imported `DocumentEngine`/`SignatureEngine` twice.
  Removed; no behavioural change.

### SEC-002-06 — Obsolete prototype HTML removed from the repository (INFO)

- `Authetec and compliance.html` and `Authetec full code.html` (remote prototype/benchmark
  artifacts, not referenced by backend or frontend) deleted via normal commit. No force-push,
  no history rewrite.

## 3. New Security-Relevant Capability Now Under Test

- `app/engines/mrz.py` — deterministic ICAO 9303 MRZ validator (TD1/TD2/TD3), 34 unit tests
  including five tamper-detection regressions.
- `app/engines/document_profiles.py` — country/document-type profiles. Botswana national-ID
  and driver-licence rules are explicitly marked `validated=False` / `UNVALIDATED`; no
  government validation rules were invented.
- `app/engines/identity_document.py` — unified identity-document engine: file validation
  (magic-byte, size limits, executable/archive rejection) → OCR → MRZ → profile → expiry →
  fail-safe decision. BLOCK decisions raise alerts server-side.
- `app/engines/liveness.py` — pluggable PAD abstraction. The bundled deterministic detector
  is labelled NOT production liveness detection in its own output.

## 4. Remaining Risks (not fixed in this pass)

1. OCR is best-effort (pytesseract/pypdf if installed) — no adversarial OCR benchmark
   (rotation/blur/glare) has been run. REAL-WORLD VALIDATION NOT YET ESTABLISHED.
2. TD1/TD2 composite check digits not validated (see SEC-002-02).
3. Face verification still uses the deterministic fallback embedder — explicitly NOT
   production biometric verification; no real model integrated yet.
4. Liveness detector is a labelled deterministic fallback, not a PAD system.
5. NFC/eMRTD is declared in profiles as a *capability flag* only — no chip verification is
   implemented and none is claimed.

## 5. Final Test Gate (this pass)

| Gate | Result |
|---|---|
| Backend (pytest) | **183 passed, 0 failed** (baseline 125; +58 new) |
| Frontend (vitest) | **13 passed, 0 failed** |
| Frontend production build (tsc + vite) | **PASS** |
| MRZ tamper-detection regressions | 5/5 pass |

## 6. Release Decision

**NOT READY** — unchanged from the foundation review. Biometric verification still uses a
synthetic embedder, no real PAD system is integrated, OCR robustness is unbenchmarked, and
TD1/TD2 composite validation is incomplete. Synthetic test passes do not constitute
real-world validation.

