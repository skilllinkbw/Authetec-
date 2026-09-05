"""
Embedder factory (provider selection).

Selects the face-embedding backend by configuration:

    AUTHETEC_EMBEDDER=sface          -> OpenCV Zoo SFace (PRODUCTION_ALLOWED,
                                        explicit install + integrity check)
    anything else / model missing    -> deterministic fallback
                                        (NON_PRODUCTION_FALLBACK)

The factory never downloads anything and never returns a half-configured
embedder: if the requested model is missing or fails its pinned-SHA
integrity check, the caller gets the clearly-labelled deterministic
fallback (or None with ``required=True``).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from app.biometric.recognition.deterministic_embedder import (
    DeterministicFaceEmbedder,
)
from app.biometric.recognition.sface import SFaceFaceEmbedder

logger = logging.getLogger("authetec.biometric.embedders")

EMBEDDER_ENV = "AUTHETEC_EMBEDDER"
KNOWN_EMBEDDERS = ("deterministic", "sface")


def build_embedder(
    kind: Optional[str] = None,
    *,
    required: bool = False,
) -> Optional[object]:
    """Build the configured face embedder.

    ``required=True`` raises instead of silently falling back - used by
    bootstrap paths that must not degrade without an operator decision.
    """
    kind = (kind or os.getenv(EMBEDDER_ENV, "")).strip().lower()
    if not kind:
        kind = "sface" if SFaceFaceEmbedder().available() else "deterministic"

    if kind == "sface":
        embedder = SFaceFaceEmbedder()
        if embedder.available():
            return embedder
        if required:
            raise RuntimeError(
                "sface embedder requested but unavailable: "
                + embedder.install_instructions())
        logger.warning(
            "sface embedder unavailable - using deterministic fallback "
            "(NON_PRODUCTION_FALLBACK)")
        return DeterministicFaceEmbedder()

    if kind != "deterministic":
        logger.warning("Unknown %s=%r - using deterministic fallback",
                       EMBEDDER_ENV, kind)
    if required:
        raise RuntimeError("deterministic embedder is NON_PRODUCTION_FALLBACK; "
                           "required=True forbids it")
    return DeterministicFaceEmbedder()
