# AutheTec — Architecture

**Date:** 2026-09-03
**Branch:** `authetec-foundation-review`

## Overview

AutheTec is a production-grade AI trust, fraud-prevention, identity-verification and monitoring platform. The architecture follows a layered design: **routers → services → engines → infrastructure**, with a React + Vite + TypeScript frontend.

```
                 AutheTec API (FastAPI)
                          |
                    Core Layer
              (config, security, middleware, errors)
                          |
              +-----------+-----------+
              |                       |
          Service Layer          Engine Layer
     (alerts, audit, evidence,  (document, signature,
      model_registry, ai_security) payment, face, social,
                                      risk/unified)
                          |
                   Infrastructure
                  (supabase, vector_store)
```

## Backend (`app/`)

### Core (`app/core/`)
- `config.py` — Pydantic settings from environment; production enforces `AUTHETEC_JWT_SECRET` and `AUTHETEC_API_KEY_SHA256`.
- `security.py` — PBKDF2-SHA256 password hashing, JWT encode/decode with algorithm allow-list, SHA-256 API-key fingerprinting via `hmac.compare_digest`.

### Common (`app/common/`)
- `middleware.py` — Correlation-ID propagation, security headers (`nosniff`, `DENY`, `no-referrer`, `no-store`), sliding-window rate limiter with identity precedence (key → tenant → IP).
- `deps.py` — Tenant context dependency; tenant-ID header validated for length and control characters.
- `errors.py` — Structured error response shape used across all endpoints.

### API Layer (`app/api/`)
- `main.py` — FastAPI app factory, exception handler registration, router mounting.
- `v1/verification.py` — Document verification, signature enroll/verify, **face verification** (`POST /api/v1/verification/faces`).
- `v1/payments.py` — Payment fraud scoring.
- `v1/risk.py` — Unified risk aggregation.
- `v1/alerts.py` — Alert/case management (list, acknowledge, resolve, **assign**, **add note**).
- `v1/audit.py` — Audit trail listing.
- `v1/evidence.py` — Evidence storage/retrieval with tenant isolation.
- `v1/social.py` — **Social trust scoring** (`POST /api/v1/social/score`).
- `v1/security.py` — **AI security screening** (`POST /api/v1/security/ai/screen`).
- `v1/health.py` — Health endpoint reporting component status including AI security.

### Engine Layer (`app/engines/`)
- `document.py` — Document verification pipeline: file validation, OCR, field extraction, tamper signals, cross-field consistency, risk decision.
- `signature.py` — Signature enrollment and verification with reference-based matching.
- `payment.py` — Payment/transaction fraud scoring with feature extraction.
- `risk.py` — Unified risk aggregation engine combining signals from all verification sources with configurable weights.
- `face.py` — **Face verification engine** with strict separation of similarity / liveness / identity consistency; pluggable `FaceEmbedder` protocol; deterministic embedder for development; fail-safe REVIEW on undecodable images.
- `social.py` — **Social trust engine**: deterministic, explainable rule-based scoring; protected attributes explicitly excluded; policy floors for high-stakes conditions.

### Service Layer (`app/services/`)
- `alerts.py` — Alert lifecycle (create, acknowledge, resolve, assign, add note); in-memory with optional Supabase persistence; tenant isolation.
- `audit.py` — Hash-chained audit logging with verified event types; mirrors to Supabase `audit_events`.
- `evidence.py` — Evidence store/retrieve with tenant scoping.
- `model_registry.py` — Model versioning with approval workflow (PENDING → APPROVED → PRODUCTION).
- `ai_security.py` — **AI security monitor**: prompt-injection screening, secret-leak detection, input/output validation, model integrity checks, structured telemetry to `ai_security_events` table.

## Frontend (`frontend/`)

React + Vite + TypeScript SPA with a responsive shell layout.

- `src/App.tsx` — Route definitions; added Social and AI Security routes.
- `src/components/layout/AppShell.tsx` — App shell with navigation; added Social Trust and AI Security nav entries.
- `src/components/ui.tsx` — Shared UI components (Badge, Card, ResultPanel, SeverityBadge, etc.).
- `src/lib/api/endpoints.ts` — Typed API client functions.
- `src/pages/` — Dashboard, Documents, Signatures, Payments, Risk, Alerts, Audit, Evidence, Developers, **Social**, **AiSecurity**.

## Database (`db/schema.sql`)

Supabase/PostgreSQL schema with Row Level Security:

- `audit_events` — Hash-chained audit trail (RLS-enabled).
- `evidence` — Evidence records with tenant isolation (RLS-enabled).
- `alerts` — Alert/case records with `assigned_to`, `analyst_notes` (RLS-enabled).
- `ai_security_events` — **Structured AI telemetry** (screening id, scores, signals, verdict, model version); append-only; never stores raw screened text (RLS-enabled).

## Security Model

- API-key fingerprint auth (SHA-256, constant-time comparison).
- JWT with algorithm allow-list, `jti` claim, expiry.
- Per-tenant isolation enforced at service layer and database RLS.
- Rate limiting (sliding-window, per-identity).
- File upload validation: magic-byte sniffing, size limits, executable rejection.
- No raw biometric data stored or echoed in API responses.
- Sensitive-data log redaction filter.

## Trust Engine Data Flow

```
      Document ──┐
      Signature ─┤
      Face ──────┼──→ Risk Aggregator ──→ CLEAR / REVIEW / BLOCK
      Payment ───┤                          │
      Social ────┤                          ├──→ Evidence + Reason
      AI Sec ────┘                          ├──→ Alert (if BLOCK)
                                             └──→ Audit Trail
```


### Infrastructure (`app/infrastructure/`)
- `supabase.py` — Supabase client wrapper; tenant-scoped operations.
- `vector_store.py` — Vector storage abstraction.

### Models and Schemas
- `models/risk.py` — Shared `EngineResult`, `Signal`, `Decision` (CLEAR/REVIEW/BLOCK), `Severity` types.
- `schemas/` — Pydantic request/response models for all endpoints including new `FaceVerifyIn`, `SocialProfileIn`, `AiScreenIn`, `AiScreenOut`, `AlertAssignIn`, `AlertNoteIn`.
