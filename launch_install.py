#!/usr/bin/env python3
"""Truly detached background installer - survives parent timeout."""
import subprocess, sys, os

# Use CREATE_NEW_PROCESS_GROUP to detach from parent
packages = [
    "scipy", "joblib", "pandas", "scikit-learn",
    "pillow", "lightgbm", "shap",
    "opencv-python-headless", "redis", "celery",
]

# Build a single batch command
cmd = f'{sys.executable} -m pip install --no-input --only-binary :all: {" ".join(packages)} > install_full_log.txt 2>&1'

proc = subprocess.Popen(
    ["cmd", "/c", cmd],
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    cwd=r"C:\Users\DELL\Documents\GitHub\Authetec-"
)
print(f"Launched installer PID={proc.pid}")
