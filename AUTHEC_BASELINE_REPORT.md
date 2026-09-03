# AutheTec — Baseline Report

**Date:** 2026-09-03
**Branch:** `authetec-foundation-review`
**Baseline commit:** `deb0ad4` (working tree clean before modifications)

## Initial state

- Clean working tree; branch in sync with `origin/authetec-foundation-review`.
- Production implementation is a layered FastAPI backend (`app/`:
  routers → services → engines → infrastructure), a React + Vite + TypeScript
  frontend (`frontend/`), a Supabase schema (`db/schema.sql`), and a benchmark
  framework (`benchmarks/`). The two root HTML files are legacy prototype
  material and are not part of the production architecture.

## Baseline test results (before any modification)

| Check | Result |
|---|---|
| Backend tests (`python -m pytest tests`) | **65 passed, 0 failed, 0 skipped**, 1 deprecation warning from `fastapi.testclient` (upstream, not project code) |
| Backend determinism | Suite run 3× with identical results |
| Frontend tests (`npm test` / vitest) | **13 passed** (2 files: client, ui) |
| Frontend build (`npm run build`) | PASS (tsc --noEmit + vite build) |
| Coverage tooling | Not configured in repo (no coverage config present) — reported as a gap |

## Baseline architecture observations

- Engines present: document, signature, payment, unified risk.
- **Gap identified:** the unified risk engine weights a `face` source
  (`DEFAULT_SOURCE_WEIGHTS["face"] = 0.15`) but no face verification engine
  existed. This is the capability gap addressed in this improvement pass.
- Security posture at baseline: API-key fingerprint auth, JWT utilities,
  correlation-id middleware, security headers, sliding-window rate limiter,
  sensitive-data log filter, production startup secret enforcement.

## Pre-modification security scan

| Pattern | Result |
|---|---|
| Hardcoded secrets / API keys | None found in production code |
| `eval` / `exec` / `pickle.load` / `shell=True` in `app/` | None |
| SQL string concatenation | None found (Supabase client usage) |
| HTTP client usage (SSRF surface) | None in `app/`; only dev-time scripts call GitHub URLs |
| `subprocess` usage | Only in repo-maintenance helper scripts (argument-list form, no user input) |

## Scope of this improvement pass

1. New **face verification engine** (`app/engines/face.py`) with strict
   separation of similarity / liveness / identity consistency and fail-safe
   decision policy.
2. New **face verification API endpoint** (`POST /api/v1/verification/faces`).
3. **21 new tests** (unit + API integration, including failure injection).
4. New **face benchmark harness** (`benchmarks/face/`) producing FAR/FRR/EER
   threshold sweeps on clearly-labelled SYNTHETIC data.
5. Security, test, benchmark, architecture, and release-readiness reports.
