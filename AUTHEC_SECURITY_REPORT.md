# AutheTec — Security Report

**Date:** 2026-09-03 · **Scope:** full-repo review + automated pattern scans

## Findings — production code (`app/`, `frontend/src/`)

### PASS (no action required)

| Area | Evidence |
|---|---|
| Hardcoded secrets | None in source; all secrets via environment (`app/core/config.py`). `.env` git-ignored; `.env.example` contains placeholders only |
| Production secret enforcement | Startup hard-fails if `AUTHETEC_JWT_SECRET` / `AUTHETEC_API_KEY_SHA256` missing in production |
| API authentication | SHA-256 fingerprint comparison of `X-API-Key` (constant-time `hmac.compare_digest`); rejects when key supplied but server unconfigured; production refuses boot without a configured fingerprint |
| Password hashing | PBKDF2-SHA256, 100k iterations, per-secret salt |
| JWT | Algorithm allow-list on decode (`algorithms=[configured]`), `jti` claim, expiry |
| SQL injection | No raw SQL string construction; parameterised Supabase client |
| Command injection | No `subprocess` in production code; helpers use argument lists |
| CORS | Explicit origin allow-list, credentials disabled, method/header allow-lists |
| Security headers | `nosniff`, `DENY`, `no-referrer`, `no-store` on every response |
| Rate limiting | Sliding-window limiter, identity precedence key→tenant→IP, 429 + `Retry-After`, flood guard (documented single-worker limitation) |
| File uploads | Magic-byte content sniffing; size limits (20 MB); executable/archive signatures rejected outright |
| Tenant isolation | Tenant context dependency; tenant id header validated (length, control chars); audit entries filtered per tenant |
| PII / biometric leakage | Sensitive-key log redaction filter; face results carry **no** raw images or embeddings; evidence stored as references only |
| Path traversal | No filesystem paths constructed from user input in `app/` |
| Dependency audit | `pip-audit` executed against the environment — see "Dependency audit" below |

### MEDIUM (documented, not blocking)

| ID | Finding | Mitigation status |
|---|---|---|
| M-1 | In-process rate limiter is per-worker; multi-node deployments need a Redis-backed limiter | Documented in code; `REDIS_URL` config already present |
| M-2 | HMAC JWT (HS256) shared secret — asymmetric (RS256/EdDSA) preferred for multi-service trust boundaries | Configurable via `AUTHETEC_JWT_ALGORITHM`; documented |
| M-3 | Liveness checks are caller-supplied on the face endpoint — a malicious caller could submit `passed: true` | Documented limitation; production integration must source PAD signals from a trusted server-side component |
| M-4 | No automated SAST/dependency scanning wired into CI (no CI config present in repo) | pip-audit run manually this pass; CI setup is future work |

### LOW

| ID | Finding |
|---|---|
| L-1 | Dev-time helper scripts in repo root (`install_deps.py`, `restore_files.py`, etc.) use subprocess; they are not part of the runtime and take no user input. Candidates for removal in a cleanup pass |
| L-2 | Coverage tooling not configured |

## Dependency audit

`pip-audit` was run against the installed environment (result recorded in
`AUTHEC_TEST_REPORT.md` at execution time). Environment packages resolve to
current releases for the security-relevant stack (fastapi, pydantic, PyJWT,
cryptography, numpy, scikit-learn). No critical vulnerability was observed
in the packages actually imported by `app/` at audit time.

## New security behaviour added this pass

- `POST /api/v1/verification/faces`: strict base64 validation up-front (400 on
  malformed payloads), engine-level fail-safe (REVIEW, confidence ≤ 0.10) for
  undecodable images, no biometric data persisted or echoed.
- Face decision policy floors: failed liveness or declared identity mismatch
  can never yield CLEAR regardless of similarity score.
