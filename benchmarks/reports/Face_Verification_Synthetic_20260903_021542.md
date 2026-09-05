# Benchmark Report - Face Verification (SYNTHETIC)

**Generated:** 2026-09-03T00:15:42.236760+00:00
**Model:** Authetec face verification (cosine, deterministic embedder) (face-cosine-deterministic-embedder-v1)
**Benchmark class:** SYNTHETIC - not a research or production benchmark

## Dataset
- Name: authetec-synthetic-gaussian-identities v1.0
- Identities: 120
- Genuine pairs: 2400
- Impostor pairs: 2400

## Metrics

| Metric | Value |
|--------|-------|
| ROC-AUC | 0.880751 |
| EER | nan @ threshold None |
| FAR @ 0.62 | 0.0 |
| FRR @ 0.62 | 0.999583 |
| Precision | 1.0 |
| Recall | 0.000417 |
| F1 | 0.000833 |
| Similarity latency | 0.0048 ms |

## Limitations
- SYNTHETIC data: Gaussian identity clusters, not real faces.
- Deterministic projection embedder, not a production biometric model.
- No liveness/PAD performance is measured here.
- Metrics MUST NOT be quoted as real-world identity-verification accuracy.
- Real validation requires labelled datasets (e.g. LFW for research) with a production embedder via the FaceEmbedder protocol.
