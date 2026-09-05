"""Biometric dataset ingestion and integrity validation.

Dataset policy:
  - Biometric data is NEVER committed to Git.  Datasets live outside the
    repository or under a Git-ignored directory, referenced by manifest.
  - Identity IDs are pseudonymous (e.g. ``s0001``).  Real names are never
    stored in manifests or logs.
  - The manifest records provenance (source, version, license) so every
    benchmark run knows exactly what data it used.

Manifest JSON schema::

    {
      "name": "dataset-name",
      "version": "1.0.0",
      "source": "https://.... or internal",
      "license": "license identifier",
      "permitted_usage": "research / commercial / ...",
      "notes": "free text",
      "samples": [
        {"subject_id": "s0001", "path": "eval/s0001_01.jpg",
         "split": "eval", "label": 1, "attack_type": "",
         "sha256": "optional-checksum"}
      ]
    }

``label`` is the PAD label: 1 = bona-fide (live), 0 = presentation attack.
``attack_type`` is only meaningful for label 0 (e.g. "print", "screen",
"replay").  Attacks MUST NOT be used as identity-verification samples.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
VALID_SPLITS = {"train", "eval", "val"}
VALID_LABELS = {0, 1}


@dataclass
class DatasetSample:
    subject_id: str
    image_path: Path
    split: str = "eval"
    label: int = 1
    attack_type: str = ""
    checksum_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "path": str(self.image_path),
            "split": self.split,
            "label": self.label,
            "attack_type": self.attack_type,
            "sha256": self.checksum_sha256,
        }


@dataclass
class BiometricDataset:
    name: str
    version: str
    source: str
    license: str
    samples: List[DatasetSample] = field(default_factory=list)
    permitted_usage: str = ""
    notes: str = ""
    manifest_path: Path = Path(".")
    integrity_issues: List[str] = field(default_factory=list)

    def subjects(self) -> List[str]:
        return sorted({s.subject_id for s in self.samples})

    def bonafide_samples(self) -> List[DatasetSample]:
        return [s for s in self.samples if s.label == 1]

    def attack_samples(self) -> List[DatasetSample]:
        return [s for s in self.samples if s.label == 0]

    def stats(self) -> Dict[str, Any]:
        attacks: Dict[str, int] = {}
        for s in self.attack_samples():
            attacks[s.attack_type or "unknown"] = \
                attacks.get(s.attack_type or "unknown", 0) + 1
        return {
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "license": self.license,
            "n_samples": len(self.samples),
            "n_subjects": len(self.subjects()),
            "n_bonafide": len(self.bonafide_samples()),
            "n_attack": len(self.attack_samples()),
            "attack_types": attacks,
            "splits": self._split_counts(),
            "integrity_issues": self.integrity_issues,
        }

    def _split_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for s in self.samples:
            counts[s.split] = counts.get(s.split, 0) + 1
        return counts


def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_image_bytes(path: Path) -> Optional[bytes]:
    """Read image bytes after confirming the file decodes as an image."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
    except Exception:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def load_dataset(manifest_path: str | Path) -> BiometricDataset:
    """Load and validate a dataset manifest; returns a BiometricDataset.

    Raises ValueError on structural problems; records recoverable
    integrity issues (corrupt images, checksum mismatch) in
    ``integrity_issues`` rather than failing the whole run.
    """
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"unreadable manifest {manifest_path}: {e}") from e

    issues = _validate_manifest(manifest)
    if issues:
        raise ValueError("manifest validation failed:\n  " + "\n  ".join(issues))

    base = manifest_path.parent
    samples: List[DatasetSample] = []

    for idx, item in enumerate(manifest["samples"]):
        rel = Path(item["path"])
        abs_path = (base / rel).resolve()
        sample = DatasetSample(
            subject_id=str(item["subject_id"]),
            image_path=abs_path,
            split=str(item.get("split", "eval")),
            label=int(item["label"]),
            attack_type=str(item.get("attack_type", "")),
            checksum_sha256=str(item.get("sha256", "")),
        )

        if not abs_path.exists():
            issues.append(f"sample {idx}: missing file {rel}")
            continue
        if abs_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            issues.append(f"sample {idx}: unsupported format {abs_path.suffix}")
        if read_image_bytes(abs_path) is None:
            issues.append(f"sample {idx}: undecodable image {rel}")
        if sample.label == 0 and not sample.attack_type:
            issues.append(f"sample {idx}: attack sample missing attack_type")
        if sample.checksum_sha256:
            digest = checksum(abs_path)
            if digest != sample.checksum_sha256.lower():
                issues.append(f"sample {idx}: checksum mismatch for {rel}")
        samples.append(sample)

    _check_identity_leakage(samples, issues)
    _check_duplicate_files(samples, issues)

    return BiometricDataset(
        name=str(manifest.get("name", "unnamed")),
        version=str(manifest.get("version", "0.0.0")),
        source=str(manifest.get("source", "")),
        license=str(manifest.get("license", "unknown")),
        samples=samples,
        permitted_usage=str(manifest.get("permitted_usage", "")),
        notes=str(manifest.get("notes", "")),
        manifest_path=manifest_path,
        integrity_issues=list(dict.fromkeys(issues)),
    )


def _validate_manifest(manifest: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for field_name in ("name", "version", "source", "license"):
        if not manifest.get(field_name):
            issues.append(f"manifest missing required field '{field_name}'")
    samples = manifest.get("samples")
    if not isinstance(samples, list) or not samples:
        issues.append("manifest has no samples")
        return issues
    for idx, item in enumerate(samples):
        if not isinstance(item, dict):
            issues.append(f"sample {idx}: not an object")
            continue
        if not str(item.get("subject_id", "")).strip():
            issues.append(f"sample {idx}: missing subject_id")
        if not str(item.get("path", "")).strip():
            issues.append(f"sample {idx}: missing path")
        if not item.get("path", "").endswith(tuple(SUPPORTED_EXTENSIONS)):
            issues.append(f"sample {idx}: unsupported format '{item.get('path')}'")
        label = item.get("label")
        if label not in VALID_LABELS:
            issues.append(f"sample {idx}: label must be 0 or 1 (got {label!r})")
        if item.get("split", "eval") not in VALID_SPLITS:
            issues.append(f"sample {idx}: invalid split '{item.get('split')}'")
    return issues


def _check_identity_leakage(samples: Sequence[DatasetSample],
                            issues: List[str]) -> None:
    by_subject: Dict[str, set] = {}
    for s in samples:
        by_subject.setdefault(s.subject_id, set()).add(s.split)
    for sid, splits in sorted(by_subject.items()):
        if len(splits) > 1:
            issues.append(
                f"IDENTITY LEAKAGE: subject {sid} appears in splits "
                f"{sorted(splits)}")


def _check_duplicate_files(samples: Sequence[DatasetSample],
                           issues: List[str]) -> None:
    digests: Dict[str, str] = {}
    for s in samples:
        try:
            digest = checksum(s.image_path)
        except OSError:
            continue
        if digest in digests:
            issues.append(
                f"DUPLICATE FILE: {s.image_path.name} identical to "
                f"{digests[digest]}")
        digests[digest] = s.image_path.name


def generate_verification_pairs(
    dataset: BiometricDataset,
    *,
    seed: int = 42,
    max_pairs: int = 0,
    impostor_ratio: float = 1.0,
) -> List[Tuple[bytes, bytes, int]]:
    """Build genuine (label=1) and impostor (label=0) pairs from bona-fide
    samples; returns (image_a, image_b, label) tuples.

    Only bona-fide samples (label=1) are used for identity verification —
    attack samples are never treated as identity samples.
    """
    import random
    rng = random.Random(seed)
    bonafide = dataset.bonafide_samples()
    if len(bonafide) < 2:
        return []

    by_subject: Dict[str, List[DatasetSample]] = {}
    for s in bonafide:
        by_subject.setdefault(s.subject_id, []).append(s)

    pairs: List[Tuple[bytes, bytes, int]] = []
    existing: set = set()

    # Genuine pairs: two different captures of the same subject.
    for sid, subs in by_subject.items():
        if len(subs) < 2:
            continue
        for i in range(len(subs)):
            for j in range(i + 1, len(subs)):
                key = (sid, i, j)
                if key in existing:
                    continue
                existing.add(key)
                a = read_image_bytes(subs[i].image_path)
                b = read_image_bytes(subs[j].image_path)
                if a is not None and b is not None:
                    pairs.append((a, b, 1))

    # Impostor pairs: samples from different subjects (bounded by ratio).
    subjects = sorted(by_subject.keys())
    n_imp = int(len(pairs) * max(0.0, impostor_ratio))
    tried = 0
    while len([p for p in pairs if p[2] == 0]) < n_imp and tried < n_imp * 50:
        tried += 1
        s1, s2 = rng.sample(subjects, 2)
        a = rng.choice(by_subject[s1])
        b = rng.choice(by_subject[s2])
        key = (min(s1, s2), max(s1, s2), a.image_path.name, b.image_path.name)
        if key in existing:
            continue
        existing.add(key)
        ia = read_image_bytes(a.image_path)
        ib = read_image_bytes(b.image_path)
        if ia is not None and ib is not None:
            pairs.append((ia, ib, 0))

    if max_pairs and len(pairs) > max_pairs:
        rng.shuffle(pairs)
        pairs = pairs[:max_pairs]
    return pairs


def generate_pad_samples(
    dataset: BiometricDataset,
    *,
    seed: int = 42,
) -> List[Tuple[bytes, int, str]]:
    """Return (image_bytes, label, attack_type) samples for PAD benchmarking."""
    import random
    rng = random.Random(seed)
    samples: List[Tuple[bytes, int, str]] = []
    for s in dataset.samples:
        if s.label != 1:
            continue
        img = read_image_bytes(s.image_path)
        if img is not None:
            samples.append((img, 1, ""))
    attacks = dataset.attack_samples()
    rng.shuffle(attacks)
    for s in attacks:
        img = read_image_bytes(s.image_path)
        if img is not None:
            samples.append((img, 0, s.attack_type))
    return samples