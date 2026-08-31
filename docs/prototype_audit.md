# Authetec — Prototype / Reference File Audit

Audit date: 2026-08-30 · Branch: `authetec-foundation-review`

## Files found

| File | Size | Purpose | Runtime dependency | Production dependency | Classification |
|---|---|---|---|---|---|
| `Authetec and compliance.html` | 100,349 bytes (~98 KB) | Static HTML prototype of a compliance dashboard (consent records, risk register, processing activities, audit log UI). Self-contained CSS/JS with mock client-side data. | **None** — not imported, served, or loaded by any runtime code. | **None** — only `restore_files.py` (a dev utility that git-restores the file) mentions it. | **REFERENCE ONLY — SAFE TO EXCLUDE FROM BUILD** |
| `Authetec full code.html` | 111,465 bytes (~109 KB) | Static HTML prototype of the verification UI (document upload, verification flow, toasts, badges). Self-contained CSS/JS with mock client-side data. | **None** — not imported, served, or loaded by any runtime code. | **None** | **REFERENCE ONLY — SAFE TO EXCLUDE FROM BUILD** |
| `Design Authetec logo...jpg` | 86,462 bytes (~84 KB) | Brand/concept artwork; source of the Authetec visual identity. | None | None | **REFERENCE ONLY** (brand identity; `assets/authetec_logo.png` is the production logo asset) |

## Dependency verification

A repository-wide search confirms **zero production imports or runtime references** to either
HTML file. The only reference is `restore_files.py`, a developer utility that restores the
files via `git checkout` — it is not part of the application execution path.

## How the prototypes are used

- The HTML prototypes are treated strictly as **design reference** (terminology, workflows,
  dashboard concepts, alert/verification UX).
- No HTML prototype content is copied into, embedded by, or served from the production
  application. No Python module, API response, WebView, or frontend component loads them.
- Production features (document verification, signature guard, payment fraud scoring,
  alerts, audit) are implemented as modular Python services/engines with their own data
  contracts and tests.

## Policy

- Do **not** delete the prototypes (they are original reference material).
- Do **not** add them to the production execution path.
- A future production frontend must be built from reusable components, not from either file.

## Re-verification (2026-08-31)

Re-audited during the `authetec-foundation-review` continuation:

- All three reference files remain **REFERENCE ONLY**. A repository-wide search
  finds references only in this document and in the developer utility
  `restore_files.py` (git-restore helper, not part of the application).
- Production build verified independent of the prototypes:
  - `python -m pytest tests/` → **65 passed**
  - `npm test -- --run` (frontend) → **13 passed**
  - `npm run build` (frontend: `tsc --noEmit && vite build`) → **succeeds**
  - `python check_startup.py` → FastAPI app boots, **13 OpenAPI paths** registered.
- Large-file check: the two HTML prototypes (~98 KB and ~109 KB) are the only
  unusually large non-node_modules reference files; neither is imported,
  served, or bundled by the API or the Vite frontend (`dist/` bundles contain
  no prototype content).
