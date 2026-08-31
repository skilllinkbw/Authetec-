"""Pytest configuration: isolate settings and singletons per test session."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the repo root is importable regardless of invocation directory.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Test-time configuration BEFORE any app module imports settings.
os.environ.setdefault("AUTHETEC_ENV", "test")
os.environ.setdefault("AUTHETEC_JWT_SECRET", "test-secret-not-for-production-0123456789ab")
os.environ.setdefault("AUTHETEC_VECTOR_BACKEND", "memory")
os.environ.setdefault("SUPABASE_URL", "")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "")
