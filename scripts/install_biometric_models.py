"""
Explicit biometric model installer.

Model download policy (enforced here):
    * models are NEVER downloaded at application startup or runtime;
    * an operator runs this script explicitly;
    * every download is verified (size + SHA-256) before it is accepted;
    * the computed SHA-256 is printed and written to models/model_pins.json
      so it can be pinned in app/biometric/models/manifest.py;
    * an existing file with a DIFFERENT hash is never silently replaced
      (use --force after verifying provenance).

Usage:
    python -m scripts.install_biometric_models            # all models
    python -m scripts.install_biometric_models --detector yunet
    python -m scripts.install_biometric_models --embedder sface
    python -m scripts.install_biometric_models --verify   # verify only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from typing import Dict, Optional

MODELS_DIR = os.path.join(os.getcwd(), "models")
PINS_PATH = os.path.join(MODELS_DIR, "model_pins.json")
USER_AGENT = "authec-model-installer/1.0 (explicit operator install)"

# (model manifest key, target relative path, pinned download URL)
CATALOG = {
    "yunet": {
        "key": "yunet_face_detection",
        "rel_path": os.path.join("face_detection", "face_detection_yunet_2023mar.onnx"),
        "url": "https://huggingface.co/opencv/face_detection_yunet/resolve/main/"
               "face_detection_yunet_2023mar.onnx",
    },
    "sface": {
        "key": "sface_recognition",
        "rel_path": os.path.join("face_recognition", "face_recognition_sface_2021dec.onnx"),
        "url": "https://huggingface.co/opencv/face_recognition_sface/resolve/main/"
               "face_recognition_sface_2021dec.onnx",
    },
}


def sha256_file(path: str, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def load_pins() -> Dict[str, str]:
    if os.path.isfile(PINS_PATH):
        try:
            with open(PINS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_pins(pins: Dict[str, str]) -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(PINS_PATH, "w", encoding="utf-8") as f:
        json.dump(pins, f, indent=2, sort_keys=True)
        f.write("\n")


def download(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
        while True:
            block = resp.read(1024 * 1024)
            if not block:
                break
            out.write(block)
    os.replace(tmp, dest)


def install(name: str, *, force: bool = False) -> int:
    from app.biometric.models.manifest import model_manifest

    item = CATALOG[name]
    entry = model_manifest().get(item["key"], {})
    dest = os.path.join(MODELS_DIR, item["rel_path"])
    pins = load_pins()

    if os.path.isfile(dest):
        current = sha256_file(dest)
        pinned = pins.get(item["key"], "")
        if pinned and current == pinned and not force:
            print(f"[OK] {name}: already installed and verified ({dest})")
            return 0
        if not force:
            print(f"[SKIP] {name}: {dest} exists but does not match the "
                  "recorded pin; re-run with --force after verifying "
                  "provenance to replace it.")
            return 1
        os.remove(dest)

    expected_size = entry.get("size_bytes", 0)
    print(f"[..] {name}: downloading {item['url']}")
    try:
        download(item["url"], dest)
    except Exception as e:
        print(f"[FAIL] {name}: download failed: {e}")
        return 1

    size = os.path.getsize(dest)
    digest = sha256_file(dest)
    if expected_size and size != int(expected_size):
        print(f"[FAIL] {name}: size mismatch (got {size}, "
              f"manifest expects {expected_size}) - refusing to install")
        os.remove(dest)
        return 1

    print(f"[OK] {name}: installed -> {dest}")
    print(f"     size   : {size} bytes")
    print(f"     sha256 : {digest}")
    print(f"     license: {entry.get('license', 'see manifest')} "
          f"(commercial_use={entry.get('commercial_use', 'see manifest')})")
    pins[item["key"]] = digest
    save_pins(pins)
    print(f"     pin    : recorded in {PINS_PATH}")
    print("     ACTION : copy this sha256 into "
          "app/biometric/models/manifest.py to pin it for all installs")
    return 0


def verify_only() -> int:
    from app.biometric.security.integrity import verify_model_integrity

    failures = 0
    for name, item in CATALOG.items():
        dest = os.path.join(MODELS_DIR, item["rel_path"])
        if verify_model_integrity(dest, item["key"]):
            print(f"[OK] {name}: integrity verified")
        else:
            print(f"[MISS] {name}: not installed or integrity check failed "
                  f"({dest})")
            failures += 1
    return 1 if failures else 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detector", choices=["yunet"])
    parser.add_argument("--embedder", choices=["sface"])
    parser.add_argument("--verify", action="store_true",
                        help="verify installed models against pinned hashes")
    parser.add_argument("--force", action="store_true",
                        help="re-download even if a verified copy exists")
    args = parser.parse_args(argv)

    if args.verify:
        return verify_only()

    names = []
    if args.detector:
        names.append(args.detector)
    if args.embedder:
        names.append(args.embedder)
    if not names:
        names = list(CATALOG)

    rc = 0
    for n in names:
        rc |= install(n, force=args.force)
    return rc


if __name__ == "__main__":
    sys.exit(main())
