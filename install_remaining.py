#!/usr/bin/env python3
"""Install remaining packages in background."""
import subprocess, sys

packages = [
    "pandas",
    "scikit-learn",
    "pillow",
    "lightgbm",
    "shap",
    "opencv-python-headless",
    "redis",
    "celery",
]

for pkg in packages:
    print(f"Installing {pkg}...", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-input", "--only-binary", ":all:", pkg],
        capture_output=True, text=True, timeout=600
    )
    if result.returncode == 0:
        print(f"  OK: {pkg}", flush=True)
    else:
        print(f"  FAILED: {pkg}", flush=True)
        print(f"  stderr: {result.stderr[-300:]}", flush=True)

print("All packages processed.", flush=True)
