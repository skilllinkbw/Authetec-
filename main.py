"""Authetec API entry point.

Run:  python main.py            (development server)
      uvicorn main:app          (production, behind a reverse proxy)
"""

from __future__ import annotations

import uvicorn

from app.api.main import create_app  # noqa: F401  (re-exported ASGI app)
from app.core.config import get_settings

app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="127.0.0.1" if settings.is_production() else "0.0.0.0",
        port=8000,
        reload=not settings.is_production(),
        log_level="debug" if settings.debug else "info",
    )
