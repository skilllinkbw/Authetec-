#!/usr/bin/env python3
"""Background dependency installer for Authetec."""
import subprocess, sys, time

packages = [
    "numpy",
    "pandas",
    "scikit-learn",
    "pillow",
    "opencv-python-headless",
    "lightgbm",
    "supabase",
    "redis",
    "celery",
    "pytest",
    "pytest-asyncio",
    "shap",
]

for pkg in packages:
    print(f"Installing {pkg}...", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-input", "--prefer-binary", pkg],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0:
        print(f"  OK: {pkg}", flush=True)
    else:
        print(f"  FAILED: {pkg}", flush=True)
        print(f"  stderr: {result.stderr[-200:]}", flush=True)

print("All packages processed.", flush=True)
