# AutheTec — Test Report

**Date:** 2026-09-03
**Branch:** `authetec-foundation-review`

## Backend Tests

**Command:** `python -m pytest tests -v`
**Result:** **125 passed, 0 failed, 0 skipped** (9.43s)

### Test Breakdown

| Test File | Count | Coverage Area |
|---|---|---|
| `tests/integration/test_api.py` | 23 | Startup, audit, evidence, rate limiting, root/health, payments, documents, signatures, risk, alerts |
| `tests/integration/test_face_api.py` | 7 | Face verification endpoint: same face clears, different face flagged, liveness, failed liveness never clears, no biometric echo, malformed base64 rejected, missing fields rejected, undecodable image fails safe |
| `tests/integration/test_security_ai_api.py` | 5 | AI security screening: benign clears, suspicious blocked, invalid rejected, external signals, low risk clears |
| `tests/unit/test_engines_document.py*` | ~12 | Document verification engine |
| `tests/unit/test_engines_payment.py*` | ~10 | Payment fraud engine |
| `tests/unit/test_engines_risk.py*` | ~10 | Risk aggregation engine |
| `tests/unit/test_engines_signature.py*` | ~6 | Signature enrollment/verification |
| `tests/unit/test_engines_face.py` | 8 | Face verification engine: embedder, threshold, liveness, identity consistency, fail-safe, policy floors |
| `tests/unit/test_engines_social.py` | 10 | Social trust engine: benign clears, new account risk, machine username, disposable email, identity mismatch, external signals, protected attributes excluded, determinism, low activity, explainability |
| `tests/unit/test_ai_security.py` | 10 | AI security monitor: injection patterns, secret detection, validation, model integrity, telemetry |
| `tests/unit/test_security.py` | 7 | Secret hashing, JWT, API keys, structured errors, settings |
| `tests/unit/test_services.py` | 7 | Audit hash chaining, alerts CRUD + tenant isolation, evidence, model registry |

*Exact counts from baseline; total verified at 125 passed.

### Failure Injection Tests

The suite explicitly tests graceful failure:

- **Face:** malformed base64 → 400; valid base64 but not an image → fail-safe REVIEW; failed liveness → never CLEAR; missing fields → 422.
- **Documents:** executable upload → 400; empty upload → 400.
- **AI Security:** prompt-injection patterns detected; credential-shaped content flagged; oversized input rejected; unregistered model blocked.
- **Social:** brand-new account raises risk; machine-generated username flagged; disposable email + unverified signals detected; identity mismatch adds risk.
- **Alerts:** unknown alert → 404; cross-tenant access → 404/403.
- **Rate limiting:** enforced with 429 + Retry-After.

## Frontend Tests

**Command:** `cd frontend && npm test -- --run`
**Result:** **13 passed, 0 failed** (2 files: client.test.ts, ui.test.tsx)

## Frontend Build

**Command:** `cd frontend && npm run build`
**Result:** PASS (tsc --noEmit + vite build, 2.61s)

## Determinism

The backend test suite was run multiple times during development with identical results (125 passed each run), confirming deterministic behavior.

## Warnings

- 1 deprecation warning from `fastapi.testclient` (upstream Starlette deprecation of `httpx`; not project code).

## Coverage

Coverage tooling is not configured in the repo (no coverage config present). This is a known gap documented for future work.
