# AutheTec — Failure Evidence Register

**Date:** 2026-09-03
**Branch:** `authetec-foundation-review`

## Purpose

This register documents controlled failure scenarios tested during the improvement pass. Authetec follows: "Do not merely explain failures. Show the evidence."

## Failure Scenarios Tested

### Face Verification Failures

| Scenario | Expected Behavior | Actual Behavior | Status |
|---|---|---|---|
| Malformed base64 payload | HTTP 400 with validation error | HTTP 400, `invalid base64 image payload` | PASS |
| Missing required fields | HTTP 422 validation error | HTTP 422 from Pydantic | PASS |
| Valid base64 but undecodable image | Fail-safe REVIEW (confidence ≤ 0.10) | REVIEW decision, `fail_safe: true` | PASS |
| Failed liveness check | Never yields CLEAR | Decision floored to REVIEW | PASS |
| Declared identity mismatch | Never yields CLEAR | Decision floored to REVIEW | PASS |
| Different face (impostor) | Not CLEAR | BLOCK or REVIEW | PASS |

### Document Verification Failures

| Scenario | Expected Behavior | Actual Behavior | Status |
|---|---|---|---|
| Executable file upload | HTTP 400 rejection | HTTP 400, magic-byte rejection | PASS |
| Empty file upload | HTTP 400 rejection | HTTP 400, size validation | PASS |

### AI Security Failures

| Scenario | Expected Behavior | Actual Behavior | Status |
|---|---|---|---|
| Prompt-injection pattern | Detected, elevated score | Injection signal raised | PASS |
| Credential-shaped content | Detected, elevated score | Secret-leak signal raised | PASS |
| Oversize input | Validation failure | `validation_valid: false` | PASS |
| Unregistered model | Blocked from serving | `allowed: false`, `model_not_registered` | PASS |

### Social Trust Failures

| Scenario | Expected Behavior | Actual Behavior | Status |
|---|---|---|---|
| Brand-new account (< 1 day) | Risk raised | Signal raised, policy floor to REVIEW | PASS |
| Machine-generated username | Flagged | Signal raised | PASS |
| Disposable email domain | Flagged (if unverified) | Signal raised | PASS |
| Identity consistency mismatch | Risk raised | Signal raised | PASS |
| Multiple prior suspensions | Policy floor to REVIEW | Floor applied | PASS |

### Alert / Case Management Failures

| Scenario | Expected Behavior | Actual Behavior | Status |
|---|---|---|---|
| Unknown alert ID | HTTP 404 | HTTP 404, `NotFoundError` | PASS |
| Cross-tenant access | HTTP 404 (isolation) | HTTP 404, tenant scoping | PASS |

### API / Infrastructure Failures

| Scenario | Expected Behavior | Actual Behavior | Status |
|---|---|---|---|
| Rate limit exceeded | HTTP 429 + Retry-After | HTTP 429 with header | PASS |
| Unauthorized access | HTTP 401/403 | Auth dependency rejects | PASS |

## Graceful Degradation

All failure scenarios produce structured responses:
- Client errors (4xx) include a structured error shape (`error_code`, `message`).
- Server-side failures degrade gracefully (e.g., alerting failure does not break verification; audit persistence failure degrades to a log line).
- The face engine's fail-safe policy ensures undecodable images result in REVIEW (human review) rather than a crash.
