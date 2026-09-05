# AutheTec — Architecture

**Date:** 2026-09-04
**Branch:** `authetec-native-biometric-engine`

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
                   ┌──────┴──────┐
                   |             |
            Biometric Stack    Infrastructure
     (detection, alignment,   (supabase, vector_store)
      recognition, pad)
```

## Native Biometric Stack (`app/biometric/`)

Phase 2 introduces AUTHeTEC's **own** biometric technology — no dependency on
AWS Rekognition, FaceTec, Azure Face, Google Cloud Vision, or any other
proprietary hosted provider for core face-recognition or PAD.

The stack is provider-independent: every capability sits behind an interface
(`FaceDetector`, `FaceAligner`, `FaceEmbedder`, `LivenessDetector`) and the
production implementation is selected by configuration, never hard-coded.

```
app/biometric/
├── contracts.py           # shared dataclasses (FaceMatch, QualityVerdict, …)
├── __init__.py            # native engine provider accessors
├── integration.py         # fraud-engine wiring + provider bootstrap
├── detection/
│   ├── base.py            # FaceDetector interface
│   └── yunet.py           # YuNet ONNX face detector
├── alignment/
│   └── landmarks.py       # LandmarkAligner
├── quality/
│   └── gate.py            # FaceQualityGate (blur / brightness / size / saturation)
├── recognition/
│   ├── __init__.py        # native embedder + matcher providers
│   ├── embeddings.py      # embedding contract + build_embedder()
│   ├── sface.py           # SFace ONNX embedder
│   ├── deterministic_embedder.py  # NON_PRODUCTION_FALLBACK
│   ├── matcher.py         # cosine-similarity matcher + threshold calibration
│   └── calibration.py     # FMR/FNMR/EER calibration harness
├── pad/
│   ├── __init__.py        # multi-layer PAD provider
│   ├── engine.py          # MultiLayerPadEngine (safe decision model)
│   ├── passive.py         # texture / spectral / moire / compression signals
│   ├── replay.py          # frame-sequence duplication + timestamp analysis
│   ├── injection.py       # camera-source integrity
│   └── active.py          # randomized challenge-response
├── models/
│   ├── __init__.py        # model manifest accessor
│   └── manifest.py        # version-pinned model metadata + integrity info
└── security/
    ├── __init__.py        # integrity verification
    └── integrity.py       # SHA-256 model-integrity checking
```

### Provider injection

Two environment variables select the production providers at startup
(`app/biometric/integration.py`):

| Variable | Values | Default |
|---|---|---|
| `AUTHETEC_FACE_PROVIDER` | `deterministic` \| `native` | `deterministic` |
| `AUTHETEC_PAD_PROVIDER` | `deterministic` \| `native` | `deterministic` |

`native` activates the AUTHeTEC stack (YuNet + SFace + multi-layer PAD). If
the required models are missing, the bootstrap **fails safe** to the
deterministic `NON_PRODUCTION_FALLBACK` and logs a clear warning — it never
starts a half-configured pipeline.

### Model download policy

- Models are **never** downloaded at application startup or runtime.
- An operator runs `python -m scripts.install_biometric_models` explicitly.
- Every download is verified (size + SHA-256) before acceptance.
- The deterministic fallback works without any models installed.

### Third-party components

| Component | Project | Model | License | Commercial | Status |
|---|---|---|---|---|---|
| Face detection | YuNet (OpenCV Zoo) | `face_detection_yunet_2023mar.onnx` | MIT | Yes | PRODUCTION_ALLOWED |
| Face embedding | SFace (OpenCV Zoo) | `face_recognition_sface_2021dec.onnx` | MIT | Yes | PRODUCTION_ALLOWED |
| PAD engine | AUTHeTEC native | heuristic signals (no learned weights) | Proprietary | Yes | PRODUCTION_ALLOWED (synthetic) |

See `BIOMETRIC_COMPONENTS.md` and `BIOMETRIC_LICENSE_MANIFEST.json` for
machine-readable provenance.

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
- `identity_document.py` — Unified identity-document verification (passport / national ID / driver's licence): image-quality signals, OCR, MRZ validation, generic cross-checks, document-profile rules, fail-safe decision.
- `mrz.py` — ICAO 9303 MRZ parser with full TD1 / TD2 / TD3 check-digit validation: per-field check digits, composite check-digit validation, filler `<` handling, tamper rejection (regression vectors from ICAO 9303 part 3).
- `ocr_pipeline.py` — Shared OCR/extraction pipeline with deterministic image-quality signals (blur, glare, low resolution, compression artifacts) and explicit engine-status/confidence handling. Ships no real-world accuracy claim — see the synthetic benchmark harness.
- `cross_checks.py` — Generic identity-document cross-checks: MRZ ↔ visual-zone consistency, date/document-number/nationality/name consistency, expiry checks, suspicious-alteration and replay detection. Country-specific rules stay in `document_profiles.py`, never mixed into generic checks.
- `document_profiles.py` — Per-country document rules (field rules, expected formats). Botswana rules remain UNVALIDATED; no government rules are invented.
- `signature.py` — Signature enrollment and verification with reference-based matching.
- `payment.py` — Payment/transaction fraud scoring with feature extraction.
- `risk.py` — Unified risk aggregation engine combining signals from all verification sources with configurable weights.
- `face.py` — **Face verification engine** with strict separation of similarity / liveness / identity consistency; pluggable `FaceEmbedder`, `FaceDetector` and `FaceAligner` provider protocols; deterministic embedder for development; audit-only image-quality signals; fail-safe REVIEW on undecodable images. The deterministic embedder is **NOT** production biometric verification.
- `liveness.py` — **Pluggable PAD abstraction**: `LivenessDetector` protocol (challenge + timeout-aware `check`), hard time budget where a hang/timeout/error is never reported as live, audit fields (`timed_out`, `audit_id`), and a deterministic development fallback explicitly labelled non-production in its output.
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
- File upload validation: magic-byte sniffing, size limits, executable rejection; **streaming 20 MB cap at the API boundary** (before the body is fully buffered).
- Template/param validation on `X-Tenant-ID` (length + control-character rejection).
- No raw biometric data stored or echoed in API responses.
- Sensitive-data log redaction filter.

## Capability Status

Implemented, Validated and Production-ready are deliberately distinct. Nothing
in this repository claims production readiness without independent validation:

| Capability | Status |
|---|---|
| ICAO 9303 MRZ parsing & check digits (TD1/TD2/TD3, composite) | Implemented + validated against published ICAO vectors |
| OCR pipeline (extraction + quality signals) | Implemented; accuracy **synthetic/test-only** (labelled) |
| Document cross-checks (MRZ↔visual zone, dates, doc numbers, replay) | Implemented; generic rules only |
| Botswana document rules | **UNVALIDATED** — no government rules fabricated |
| Face similarity (deterministic embedder) | **Synthetic/test-only** — NOT production biometric verification |
| Face provider interfaces (embedder/detector/aligner) | Implemented pluggable boundary; production model NOT bundled |
| Liveness / PAD | Interface + fail-safe fallback implemented; bundled detector **NOT production PAD** |
| Real-world accuracy figures | Not claimed anywhere without a measured validation dataset |

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
