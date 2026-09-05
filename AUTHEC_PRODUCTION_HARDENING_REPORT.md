# AUTHeTEC — Production Hardening Report (Phase 1)

**Branch:** `authetec-production-hardening`
**Starting commit:** `b53b7859801882c69397c5cc9e2456bd98b515cc` (verified baseline)
**Date:** 2026-09-04

This report records Phase 1 security hardening with measured evidence only.
Implemented ≠ Validated ≠ Production-ready. Nothing here claims production
readiness without independent validation.

---

## 1. Baseline

| Item | Value |
|---|---|
| Baseline commit | `b53b7859801882c69397c5cc9e2456bd98b515cc` |
| Baseline branch | `authetec-foundation-review` (local = remote, clean tree) |
| Backend tests | 183 passed / 0 failed |
| Frontend tests | 13 passed / 0 failed |
| Build | PASS |
| Production status | NOT READY |

## 2. Branch

New branch created from the exact baseline commit (no history rewrite):

- `authetec-production-hardening` HEAD = `0facbd9` at report time (remote sync: see §8).
- All work is committed in 5 logical checkpoints; no force-push, no reset, no
  rebase, no deletion of the verified baseline.

## 3. Changes

| # | Commit | Area | Summary |
|---|---|---|---|
| 1 | `235eb9b` | MRZ | ICAO 9303 TD1/TD2 **composite check-digit validation** (per-field, composite, filler `<`, tamper rejection) + regression/malformed/tampering tests |
| 2 | `690a461` | OCR | Hardened OCR pipeline: preprocessing, image normalisation, quality signals (blur/glare/low-res/compression), confidence + failure handling; degraded/adversarial input tests; **synthetic/test-only** benchmark harness |
| 3 | `3dfa2c2` | Documents | Generic MRZ↔visual-zone cross-checks (dates, doc numbers, nationality, name, expiry, alteration, replay detection); country rules kept separate |
| 4 | `89ed5f9` | Face + PAD | Pluggable `FaceDetector` / `FaceAligner` / `FaceEmbedder` provider interfaces; audit-only image-quality signals; PAD hard time budget (timeout/error/hang never "live"); provider-injection tests |
| 5 | `0facbd9` | API security | Streaming 20 MB upload cap at the API boundary (oversized-body defence before full buffering) |

### 3.1 Finding / Root cause / Fix / Tests / Evidence (per change)

**Change 1 — TD1/TD2 composite check digits**
- Finding: TD1/TD2 individual check digits validated, composite check digits were not.
- Root cause: composite validation was implemented only for the TD3 lines.
- Fix: TD1/TD2 composite check-digit validation using ICAO 9303 Part 3 field
  boundaries, check-digit positions, 7-3-1 weighting, ICAO character→value
  conversion, filler `<` handling; tampered composite fields are rejected;
  fields without check digits never claim a check-digit result.
- Tests: regression vectors (e.g. doc number `D23145890→7`), malformed inputs,
  tampered fields, filler-padded fields.
- Evidence: `tests/unit/test_engines_mrz.py` (all pass; see §5).

**Change 2 — OCR hardening**
- Finding: the extraction path was a thin wrapper with no structured quality
  signals, no confidence/failure model, and no benchmark harness.
- Root cause: OCR was best-effort text with a single fallback path.
- Fix: `ocr_pipeline.py` (preprocessing, normalisation, cropping/rotation
  handling, character normalisation, field extraction, confidence + failure
  handling); `assess_image_quality()` for blur/glare/low-res/compression;
  repeatable `benchmarks/evaluation/ocr_benchmark.py` with character accuracy,
  field accuracy, MRZ validity, false acceptance/rejection, processing
  failures — explicitly **synthetic/test-only**.
- Tests: `test_ocr_pipeline.py`, `test_ocr_benchmark.py`.
- Evidence: tests pass; benchmark reports carry the synthetic label; no
  real-world accuracy percentages are claimed anywhere.

**Change 3 — Document verification (generic mechanisms)**
- Finding: no generic MRZ↔visual-zone/date/document-number/nationality/name/
  expiry consistency checks or replay detection.
- Root cause: verification scored profiles and MRZ locally without cross-field
  consistency.
- Fix: `cross_checks.py` generic checks wired into `identity_document.py`;
  Botswana-specific rules remain in `document_profiles.py` and are
  **UNVALIDATED** — no government rules fabricated.
- Tests: `test_cross_checks.py`, `test_engines_identity_document.py`.

**Change 4 — Face verification architecture & PAD**
- Finding: face matching used a deterministic fallback embedder (not production
  biometric verification — truth preserved); no detector/aligner integration
  boundary; PAD `check()` had no time budget and no explicit fail-safe contract.
- Root cause: single-embedder design; PAD ran synchronously.
- Fix: `FaceDetector`/`FaceAligner` protocols + engine wiring (applied only when
  injected; deterministic fallback path unchanged); `LivenessDetector` protocol
  with `timeout_s`; hard time budget where timeout/error/hang is **never**
  reported live; `LivenessResult.timed_out`/`audit_id` audit fields;
  `is_live` guaranteed to be a real `bool`.
- Tests: `test_engines_face.py`, `test_engines_liveness.py` (fail-safe contract,
  hang/timeout, provider injection).
- Evidence: tests pass; bundled embedder/detector remain clearly labelled
  non-production.

**Change 5 — Oversized uploads**
- Finding: the API buffered the entire upload before the engine applied the
  20 MB limit (memory-exhaustion vector).
- Root cause: `await UploadFile.read()` with no cap.
- Fix: `_read_limited()` streaming 1 MB chunks with a 20 MB cap and 400 abort
  before accumulating the body; wired into `/verification/documents` and
  `/verification/identity`.
- Tests: `test_oversized_upload_rejected_at_api_boundary` (20 MB + 1 byte → 400).

## 4. Security review findings

Severity classification below reflects the phase-scoped surface (auth, tenant
isolation, uploads, rate limiting, injection, secrets, biometrics, audit,
logging).

### Critical
- None found in the phase-scoped surface.

### High
| Finding | Status |
|---|---|
| PAD `check()` could block indefinitely on a hung worker (no time budget) | **FIXED** (`89ed5f9`) |
| Oversized uploads fully buffered before size validation | **FIXED** (`0facbd9`) |

### Medium
| Finding | Status |
|---|---|
| `LivenessResult.is_live` could be `numpy.bool_` violating the field contract | **FIXED** (`89ed5f9`) |
| Dead/orphan code path in the PAD check method after refactor | **REMOVED** (review guard, `89ed5f9`) |
| Rate limiter is per-process; multi-node deployment needs a Redis backend | Open (documented future work in `middleware.py`) |

### Low
- Alert-creation failures are swallowed (intentionally non-fatal, logged at debug) — acceptable, noted.
- OCR engine availability degrades gracefully to no-text (explicit failure state).

### Informational
- API keys stored as SHA-256 fingerprints only; raw keys never logged.
- Raw biometric images/embeddings never stored on results or echoed.
- Audit trail is hash-chained with tenant RLS; keeper integrity endpoint validates chains.
- Sensitive-data log redaction filter present.

## 5. Validation (measured results only)

| Suite | Result |
|---|---|
| Full backend suite (after Phase 1) | **254 passed / 0 failed** (207 unit + 47 integration) |
| MRZ regression + verification suites | **126 passed / 0 failed** (MRZ, OCR pipeline, OCR benchmark, cross-checks, identity document, face, liveness) |
| Frontend | **13 passed / 0 failed** |
| Production build (`npm run build`) | **PASS** |
| Working tree | Clean after final checkpoint (before push) |

Baseline backend was 183 tests; the suite grew with the new hardening regression
tests (MRZ TD1/TD2, OCR degraded input, cross-checks, face provider interfaces,
PAD fail-safe, oversized upload). No tests were removed or weakened.

## 6. Phase deliverables

- MRZ: complete ICAO 9303 TD1/TD2/TD3 + composite validation → blocker c resolved (see §7).
- OCR: degraded/adversarial-input tests + repeatable **synthetic** benchmark; no fake accuracy.
- Face: pluggable provider architecture; fallback remains non-production; integration boundary documented.
- PAD: pluggable interface, hard time budget, fail-safe audit, provider injection.
- Documents: generic cross-checks; Botswana rules still unvalidated.
- Security: focused review + concrete fixes (upload cap, PAD timeout).
- Docs: `AUTHEC_ARCHITECTURE.md` updated with capability-status table; this report.

## 7. Remaining blockers (production release)

1. **Real face embedding / PAD production system** — interfaces exist; a validated model + independently validated PAD provider must be integrated and benchmarked.
2. **OCR adversarial robustness validation** — requires a labelled real-world dataset (current benchmark is synthetic/test-only).
3. **Real-world document / biometric dataset validation** — no production accuracy figures may be claimed until this is measured.
4. **Country rule validation (e.g. Botswana)** — document profiles must be validated against government sources before use.

Resolved this phase: _c. TD1/TD2 composite check-digit validation_ — implemented
and regression-tested against ICAO 9303 vectors.

## 8. Git safety & synchronization

- 5 logical commits on `authetec-production-hardening`, all normal commits.
- No `git reset --hard`, no force-push, no history rewrite, no deleted tests.
- Verified baseline commit untouched; release-review report and NOT READY status preserved.
- Pushed to `origin/authetec-production-hardening` (normal push only) and
  re-verified local HEAD == remote HEAD with a clean working tree (see final
  sync note in the response).

## 9. Final status

- Backend: **254 passed / 0 failed**
- Frontend: **13 passed / 0 failed**
- Build: **PASS**
- Production readiness: **NOT READY**

**Final verdict:** *Implemented* is done and measured; *validated* is limited to
the specific test vectors and interfaces exercised here. Production release
remains blocked by the items in §7.