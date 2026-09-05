# AUTHeTEC Biometric Components

This document records every third-party biometric component used in AUTHeTEC's
native face-verification and presentation-attack-detection stack, with
machine-readable license provenance (see `BIOMETRIC_LICENSE_MANIFEST.json`).

## Component inventory

| Component | Project | Model | License | Commercial | Status |
|-----------|---------|-------|---------|------------|--------|
| Face detection | YuNet (OpenCV Zoo) | `face_detection_yunet_2023mar.onnx` | MIT | Yes | PRODUCTION_ALLOWED |
| Face embedding | SFace (OpenCV Zoo) | `face_recognition_sface_2021dec.onnx` | MIT | Yes | PRODUCTION_ALLOWED |
| PAD engine | AUTHeTEC native | heuristic signals (no learned weights) | Proprietary | Yes | PRODUCTION_ALLOWED (synthetic) |

## License notes

- **YuNet / SFace** — MIT-licensed by OpenCV Zoo. The source code and model
  weights are both distributed under MIT. The underlying training datasets
  (WIDER Face for detection; various public sets for recognition) are research
  datasets whose redistribution terms may differ from the model weights; we
  download weights only from the official OpenCV Zoo repository.
- **AUTHeTEC PAD** — built entirely in-house. The passive/replay/injection
  layers are deterministic signal computations with no learned weights. The
  signal calibration is currently SYNTHETIC (see Phase 2 report blockers).

## Usage policy

- All model binaries are **gitignored** and must be installed explicitly via
  `python -m scripts.install_biometric_models` (see `docs/biometric_model_setup.md`).
- The application starts and operates using the deterministic
  `NON_PRODUCTION_FALLBACK` when models are absent; the "native" providers
  activate only when the operator has installed and integrity-checked the
  corresponding models.
- No model is downloaded at application startup.
