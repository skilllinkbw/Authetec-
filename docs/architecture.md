# Authetec — Production Architecture

AI-powered digital trust & fraud prevention platform. Modular, layered, and
independent of the HTML prototypes (see `docs/prototype_audit.md`).

## Layering

```
Frontend/UI (future, component-based)
        ↓
API  (app/api — FastAPI routers, validation only)
        ↓
Services  (app/services — alerts, audit, evidence, model registry)
        ↓
Engines  (app/engines — document, signature, payment, risk)
        ↓
Infrastructure  (app/infrastructure — Supabase, vector stores)
        ↓
Database / External Providers
```

## Modules

| Path | Responsibility |
|---|---|
| `app/core/config.py` | Environment-driven settings; production refuses to boot without required secrets |
| `app/core/security.py` | JWT, secret hashing (PBKDF2), API-key fingerprints, safe logging, correlation ids |
| `app/common/errors.py` | Error hierarchy + consistent JSON error handlers |
| `app/common/middleware.py` | Correlation-id (`X-Request-ID`) + security headers |
| `app/common/deps.py` | Tenant context + API-key authentication dependencies |
| `app/models/risk.py` | Shared domain contracts: `Signal`, `EvidenceRef`, `EngineResult`, `UnifiedRiskResult` |
| `app/schemas/` | Pydantic v2 request/response contracts for the API |
| `app/engines/document.py` | Document verification: magic-byte validation → OCR → classification → tamper heuristics → scoring |
| `app/engines/signature.py` | Signature Guard: enrollment, similarity verification, watchlist alerting |
| `app/engines/payment.py` | Payment fraud scoring: explainable features → model/rules → thresholds → decision |
| `app/engines/risk.py` | Unified risk aggregation with confidence weighting and provenance |
| `app/services/alerts.py` | Provider-agnostic alert engine (email/SMS/webhook pluggable); optional Supabase persistence with in-memory fallback |
| `app/services/audit.py` | Tamper-evident hash-chained audit log |
| `app/services/evidence.py` | Immutable evidence references (object URIs, never inline payloads) |
| `app/services/model_registry.py` | Model lifecycle: benchmark → approval → production (gated) |
| `app/infrastructure/supabase.py` | Server-side-only Supabase access (service key never leaves the backend) |
| `app/infrastructure/vector_store.py` | Pluggable vector store: memory (dev/test), Chroma, Qdrant |
| `db/schema.sql` | PostgreSQL schema for `audit_events`, `evidence`, `alerts` with indexes and RLS posture |
| `main.py` | ASGI entry point (`uvicorn main:app`) |

## API surface (v1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service banner |
| GET | `/health` | Component health (vector store, database, alerts, model registry) |
| POST | `/api/v1/verification/documents` | Multipart document verification |
| POST | `/api/v1/verification/signatures/enroll` | Enroll reference signature |
| POST | `/api/v1/verification/signatures/verify` | Verify signature vs reference |
| POST | `/api/v1/payments/score` | Transaction fraud scoring |
| POST | `/api/v1/risk/aggregate` | Unified risk aggregation |
| GET | `/api/v1/alerts` | List tenant alerts |
| POST | `/api/v1/alerts/{id}/acknowledge` | Acknowledge alert |
| POST | `/api/v1/alerts/{id}/resolve` | Resolve alert |

Headers: `X-API-Key` (authenticated deployments), `X-Tenant-ID` (tenant context),
`X-Request-ID` (correlation, echoed in responses).

## Security posture

- No secrets in source: everything via environment (`AUTHETEC_*`, `SUPABASE_*`).
- Production startup **fails closed** without `AUTHETEC_JWT_SECRET`,
  `AUTHETEC_API_KEY_SHA256`, and `SUPABASE_SERVICE_ROLE_KEY`.
- API keys: only the SHA-256 fingerprint is configured/stored; raw keys are
  never logged.
- Uploads validated by magic bytes; executables/archives rejected before parsing.
- Security headers on every response; sensitive fields redacted from logs.
- Tenant isolation enforced at engine/service/API layers.
- Rate limiting: sliding window per API key / tenant / client IP
  (`AUTHETEC_RATE_LIMIT_PER_MIN`, default 120/min); health probes exempt.
  In-process limiter — back it with Redis for multi-worker deployments.
- Database access uses RLS-enabled tables (`db/schema.sql`); the service
  role is the only writer and never leaves the backend.

## Running

```bash
pip install -r requirements.txt
copy .env.example .env          # fill in real values
# apply db/schema.sql to Supabase (SQL editor or migration tool)
python main.py                  # dev server on :8000 (docs at /docs)
python -m pytest tests          # backend test suite

# Frontend console (component-based React + Vite)
cd frontend
npm install
npm run dev                     # dev server on :3000, proxies /api -> :8000
npm test -- --run               # frontend unit tests (13)
npm run build                   # tsc --noEmit + vite build (dist/)
```
