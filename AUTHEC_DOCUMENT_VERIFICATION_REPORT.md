# AutheTec — Document Verification Report

**Date:** 2026-09-03
**Branch:** `authetec-foundation-review`

## Current State

AutheTec's document verification engine (`app/engines/document.py`) implements a layered pipeline:

```
Document Upload
      ↓
Secure File Validation (magic-byte sniffing, size limits, executable rejection)
      ↓
Document Processing
      ↓
Field Extraction
      ↓
Cross-Field Consistency
      ↓
Tamper / Manipulation Signals
      ↓
Risk Decision (CLEAR / REVIEW / BLOCK)
```

## Capabilities

- **File security validation:** MIME type, extension, file signature verification; size limits (20 MB); executable/archive signatures rejected outright.
- **Field extraction:** Structured data extraction from uploaded documents.
- **Cross-field consistency:** Validates that extracted fields agree with each other.
- **Tamper signals:** Detects manipulation indicators.
- **Risk decision:** Produces structured `EngineResult` with risk score, confidence, decision, signals, and evidence references.

## Integration with Face Verification

The face verification endpoint (`POST /api/v1/verification/faces`) supports document-to-selfie consistency checking via the `declared_identity_match` field, enabling cross-reference between document photos and live selfies.

## Known Gaps (Not Fabricated)

The following capabilities are **architecturally supported** but not yet implemented with measured performance:

- **Passport MRZ validation** (ICAO 9303 check-digit rules) — architecture supports it via document profiles; no measured accuracy yet.
- **National ID verification** — document-profile architecture designed for extensibility; no country-specific profiles with measured performance yet.
- **Driver's licence verification** — same extensible architecture; no measured performance yet.
- **OCR field-extraction accuracy** — requires labelled document datasets for measurement.
- **Tamper-detection rates** — requires attack datasets for measurement.
- **NFC/eMRTD chip verification** — architecturally referenced; not implemented.

## Accuracy Policy

No accuracy claim is made for document verification. Any future claim will state:
- The dataset it was measured on
- The metric and value
- The benchmark class (SYNTHETIC / Internal / Research / Production validation)

## Security

- Uploaded documents are validated for malicious content before processing.
- No raw document images are echoed in API responses.
- Document evidence is stored as references, not raw biometric data.
- Tenant isolation prevents cross-tenant document access.
