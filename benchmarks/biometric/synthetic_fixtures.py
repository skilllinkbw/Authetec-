"""Synthetic biometric fixture generation for pipeline self-testing.

SYNTHETIC ONLY.  These fixtures exist so the benchmark pipeline can be
exercised end-to-end in CI.  They are NOT real-world evidence and must
never be presented as such: any report produced from them must state
``data_source: synthetic``.

Images are procedural mock faces: deterministic per subject, visually
distinct across subjects, with mild intra-subject perturbation so
genuine similarity exceeds impostor similarity for the deterministic
embedder.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DEFAULT_OUT_DIR = Path("benchmarks/biometric/data/synthetic")


def _subject_image(rng: np.random.Generator, seed: int,
                   size: int = 96) -> np.ndarray:
    """Deterministic per-subject procedural face.

    Geometry, scale and brightness are drawn from a per-subject RNG so
    different subjects are clearly separated while the deterministic
    embedder yields high within-subject similarity.
    """

    def pupil(im: np.ndarray, cx: int, cy: int, r: int) -> None:
        yy, xx = np.ogrid[:im.shape[0], :im.shape[1]]
        im[(xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2] = 30

    im = np.zeros((size, size, 3), np.uint8)
    # Subject-specific parameters
    head_r = size * float(0.30 + 0.14 * rng.random())
    cx = size / 2 + int(rng.integers(-8, 9))
    cy = size / 2 + int(rng.integers(-6, 7))
    skin = int(rng.integers(120, 215))
    hair = int(rng.integers(15, 90))
    mask = np.zeros((size, size), bool)
    yy, xx = np.ogrid[:size, :size]
    mask[(xx - cx) ** 2 + (yy - cy) ** 2 <= head_r ** 2] = True
    im[mask] = (skin,) * 3
    hair_zone = (xx - cx) ** 2 + (yy - (cy - size * 0.12)) ** 2 <= head_r ** 2
    im[hair_zone] = (hair,) * 3
    # Eyes + brows (subject-specific offsets and spacing)
    ex = int(cx + rng.integers(-12, 13))
    ey = int(cy - size * 0.14)
    spacing = int(14 + rng.integers(8, 17))
    pupil(im, ex - spacing, ey, 5)
    pupil(im, ex + spacing, ey, 5)
    im[ey - 9, ex - spacing - 8:ex + spacing + 8] = 20
    # Mouth
    my = ey + int(size * 0.16)
    im[my:my + 3, ex - size // 8:ex + size // 8] = 50
    im = im.astype(np.float32)
    im += rng.normal(0, 4.0, im.shape).astype(np.float32)  # grain
    # Per-subject colour cast
    im[..., 0] = im[..., 0] * float(0.85 + 0.3 * rng.random())
    im[..., 2] = im[..., 2] * float(0.85 + 0.3 * rng.random())
    return np.clip(im, 0, 255).astype(np.uint8)


def _augment(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Mild intra-subject perturbation (pose/brightness/shift)."""
    import cv2
    img = img.astype(np.float32)
    img *= float(0.85 + 0.3 * rng.random())
    dx, dy = int(rng.integers(-3, 4)), int(rng.integers(-3, 4))
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    img = cv2.warpAffine(img, m, (img.shape[1], img.shape[0]))
    return np.clip(img, 0, 255).astype(np.uint8)


def _attack_variant(img: np.ndarray, kind: str, rng: np.random.Generator,
                    quality: int = 62) -> np.ndarray:
    """Degradation model approximating screen/reprint capture effects."""
    import cv2
    if kind == "print":
        g = cv2.GaussianBlur(img, (5, 5), 1.2)
        g = np.clip(g.astype(np.float32) * 0.82, 0, 255).astype(np.uint8)
        return g
    if kind == "screen":
        # Moire-ish pattern
        yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
        moire = ((np.sin(xx / 5.0) + np.cos(yy / 5.0)) * 12).astype(np.float32)
        out = np.clip(img.astype(np.float32) + moire[..., None], 0, 255)
        return out.astype(np.uint8)
    # replay: re-encode twice
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    decoded = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    ok2, buf2 = cv2.imencode(
        ".jpg", decoded, [cv2.IMWRITE_JPEG_QUALITY, quality - 10])
    return cv2.imdecode(buf2, cv2.IMREAD_COLOR)


def create_synthetic_dataset(
    *,
    n_subjects: int = 6,
    captures_per_subject: int = 4,
    attacks_per_subject: int = 2,
    out_dir: Path = DEFAULT_OUT_DIR,
    seed: int = 42,
) -> Path:
    """Generate a synthetic dataset and return its manifest path."""
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_filename = "manifest.json"
    # Write a guard so raw image data is never accidentally tracked.
    (out_dir / ".gitignore").write_text("*\n", encoding="utf-8")

    samples: list = []
    for sid in range(n_subjects):
        sub = f"s{sid:04d}"
        sub_rng = np.random.default_rng(seed * 1000 + sid)
        base = _subject_image(sub_rng, seed)
        for cap in range(captures_per_subject):
            img = _augment(_subject_image(sub_rng, seed), sub_rng)
            fname = out_dir / f"{sub}_bona{cap}.png"
            cv2.imwrite(str(fname), img)
            samples.append({
                "subject_id": sub,
                "path": fname.name,
                "split": "eval",
                "label": 1,
                "attack_type": "",
            })
        for at in range(attacks_per_subject):
            kind = ("print", "screen", "replay")[at % 3]
            img = _attack_variant(base, kind, sub_rng)
            fname = out_dir / f"{sub}_attack{at}_{kind}.jpg"
            cv2.imwrite(str(fname), img)
            samples.append({
                "subject_id": sub,
                "path": fname.name,
                "split": "eval",
                "label": 0,
                "attack_type": kind,
            })

    manifest = {
        "name": "synthetic-fixture",
        "version": "1.0.0",
        "source": "generated by benchmarks.biometric.synthetic_fixtures "
                  "(deterministic procedural images, no real identities)",
        "license": "synthetic - no real biometric data",
        "permitted_usage": "pipeline self-test only; NOT real-world evidence",
        "notes": ("SYNTHETIC DATA. Never report as real-world validation. "
                  "Identities are procedurally generated mock faces."),
        "samples": samples,
    }
    manifest_path = out_dir / manifest_filename
    manifest_path.write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path