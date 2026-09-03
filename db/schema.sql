-- Authetec — Supabase / PostgreSQL schema (initial)
-- ============================================================
-- Applied to Supabase via SQL editor or migration tooling.
-- Conventions:
--   * Primary keys are TEXT: the Python services generate hex ids
--     (secrets.token_hex / uuid4().hex) which are not UUID literals.
--   * Row Level Security is ENABLED on every table. The service-role
--     key (backend only) bypasses RLS; client-facing access must go
--     through tenant-scoped policies below. Never ship the service
--     key to a browser.
--   * All timestamps are timestamptz (UTC).

-- ── audit_events (append-only, hash-chained) ────────────────────
create table if not exists public.audit_events (
    event_id       text primary key,
    event_type     text not null,
    actor_id       text not null default 'system',
    tenant_id      text not null default 'system',
    resource_type  text not null default '',
    resource_id    text not null default '',
    action         text not null default '',
    timestamp      timestamptz not null default now(),
    correlation_id text,
    request_id     text,
    result         text not null default 'success',
    metadata       jsonb not null default '{}'::jsonb,
    prev_hash      text not null,
    entry_hash     text not null
);

create index if not exists idx_audit_tenant_time
    on public.audit_events (tenant_id, timestamp desc);
create index if not exists idx_audit_correlation
    on public.audit_events (correlation_id);

-- ── evidence (immutable references, never inline payloads) ──────
create table if not exists public.evidence (
    evidence_id  text primary key,
    tenant_id    text not null,
    storage_uri  text not null,
    content_type text not null default '',
    purpose      text not null default '',
    metadata     jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now(),
    unique (tenant_id, storage_uri)
);

create index if not exists idx_evidence_tenant
    on public.evidence (tenant_id, created_at desc);

-- ── alerts ──────────────────────────────────────────────────────
create table if not exists public.alerts (
    alert_id        text primary key,
    tenant_id       text not null,
    type            text not null check (type in (
        'document_fraud', 'signature_anomaly', 'signature_appearance',
        'face_mismatch', 'liveness_failure', 'image_manipulation',
        'fake_social_profile', 'payment_fraud', 'device_anomaly',
        'identity_anomaly', 'watchlist_event', 'risk_threshold_event')),
    severity        text not null check (severity in
        ('info', 'low', 'medium', 'high', 'critical')),
    risk_score      numeric(5, 4) not null check (risk_score between 0 and 1),
    source          text not null,
    evidence_ids    text[] not null default '{}',
    message         text not null default '',
    status          text not null default 'OPEN'
                    check (status in ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')),
    created_at      timestamptz not null default now(),
    acknowledged_at timestamptz,
    resolved_at     timestamptz,
    assigned_to     text not null default '',
    analyst_notes   jsonb not null default '[]'::jsonb,
    metadata        jsonb not null default '{}'::jsonb
);

create index if not exists idx_alerts_tenant_status
    on public.alerts (tenant_id, status, created_at desc);
create index if not exists idx_alerts_assignee
    on public.alerts (assigned_to) where assigned_to <> '';

-- ── ai_security_events (structured AI telemetry, append-only) ──────────
-- Stores screening outcomes (scores, signals, verdict) but NEVER the raw
-- screened text — prompts/outputs are not persisted for privacy reasons.
create table if not exists public.ai_security_events (
    screening_id            text primary key,
    tenant_id               text not null,
    mode                    text not null check (mode in ('prompt', 'output')),
    decision                text not null
                            check (decision in ('CLEAR', 'REVIEW', 'BLOCK')),
    prompt_injection_score  numeric(5, 4) not null
                            check (prompt_injection_score between 0 and 1),
    secret_leak_score       numeric(5, 4) not null
                            check (secret_leak_score between 0 and 1),
    validation_valid        boolean not null default true,
    correlation_id          text not null default '',
    model_version           text not null default '',
    signals                 jsonb not null default '[]'::jsonb,
    created_at              timestamptz not null default now()
);

create index if not exists idx_ai_security_tenant_time
    on public.ai_security_events (tenant_id, created_at desc);
create index if not exists idx_ai_security_decision
    on public.ai_security_events (decision);

-- ── Row Level Security ──────────────────────────────────────────
-- Default posture: DENY all client access. The backend uses the
-- service-role key (bypasses RLS). The example policies below show
-- the intended tenant scoping once Supabase Auth JWTs carry a
-- ``tenant_id`` claim; enable them per deployment after review.

alter table public.audit_events enable row level security;
alter table public.evidence     enable row level security;
alter table public.alerts       enable row level security;
alter table public.ai_security_events enable row level security;

-- Example (review before enabling):
-- create policy tenant_scoped_alerts on public.alerts
--     for select to authenticated
--     using (tenant_id = coalesce(
--         current_setting('request.jwt.claims', true)::json ->> 'tenant_id',
--         ''));
