"""Verify the Authetec FastAPI application builds and imports cleanly."""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from main import app  # noqa: E402

print("Startup OK")
schema = app.openapi()
print(f"OpenAPI paths registered: {len(schema['paths'])}")
for p in sorted(schema["paths"]):
    methods = ",".join(m.upper() for m in schema["paths"][p])
    print(f"  {methods:12s} {p}")