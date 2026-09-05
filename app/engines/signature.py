"""
Signature Engine (Signature Guard)
==================================

Enrollment, secure vault, comparison, similarity scoring, and watchlist
alerting.  Uses OpenCV-based shape/slant analysis.  An image-similarity
score is never presented as legal proof of authorship.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from app.core.config import get_settings
from app.infrastructure.vector_store import get_vector_store, VectorPoint
from app.models.risk import Decision, EngineResult, Severity, Signal
from app.services.evidence import get_evidence_engine

logger = logging.getLogger("authetec.signature")
SIG_COLLECTION = "signatures"


@dataclass
class SignatureSample:
    image_bytes: bytes
    label: str = ""
    owner_id: str = ""
    tenant_id: str = "default"
    monitored: bool = False


def _to_gray_ndarray(image_bytes: bytes) -> Optional[np.ndarray]:
    try:
        import cv2
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None


def _extract_signature_features(gray: np.ndarray) -> Optional[np.ndarray]:
    """
    Extract a normalised feature vector from a signature image.

    Pipeline (mirrors classic offline signature verification):
      1. Binarise (Otsu) and crop to ink bounding box.
      2. Resize to a fixed canvas (128x64).
      3. Compute: ink density, slant angle, aspect ratio, stroke-width
         proxy, and a coarse 8x4 grid density map.
    Returns a fixed-length float vector or None if the image is blank.
    """
    try:
        import cv2
        # Otsu binarisation — ink becomes white (255) on black (0)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ys, xs = np.where(binary > 0)
        if len(xs) < 10:
            return None
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        crop = binary[y0:y1 + 1, x0:x1 + 1]

        # Resize preserving aspect to fixed canvas
        canvas = np.zeros((64, 128), dtype=np.uint8)
        ch, cw = crop.shape
        scale = min(128 / cw, 64 / ch)
        resized = cv2.resize(crop, (max(1, int(cw * scale)), max(1, int(ch * scale))))
        rh, rw = resized.shape
        oy, ox = (64 - rh) // 2, (128 - rw) // 2
        canvas[oy:oy + rh, ox:ox + rw] = resized

        ink = (canvas > 0).astype(np.float32)
        total_ink = float(ink.sum())

        # Global features
        ink_density = total_ink / ink.size
        aspect = cw / max(ch, 1)
        ys2, xs2 = np.where(canvas > 0)
        # Slant: covariance of coordinates
        slant = 0.0
        if len(xs2) > 10:
            cov = np.cov(np.vstack([xs2, ys2]))
            if cov[0, 1] != 0 and cov[0, 0] != 0:
                slant = float(cov[0, 1] / (cov[0, 0] * cov[1, 1]) ** 0.5)
        # Stroke width proxy: perimeter vs ink area
        contours, _ = cv2.findContours(canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        perimeter = float(sum(cv2.arcLength(c, True) for c in contours))
        stroke_width = total_ink / max(perimeter, 1.0)

        # 8x4 grid density map
        grid = []
        gh, gw = 64 // 4, 128 // 8
        for r in range(4):
            for c in range(8):
                cell = ink[r * gh:(r + 1) * gh, c * gw:(c + 1) * gw]
                grid.append(float(cell.sum()) / max(total_ink, 1.0))

        feats = np.array([ink_density, aspect, slant, stroke_width] + grid, dtype=np.float32)
        # L2 normalise
        norm = np.linalg.norm(feats)
        return feats / norm if norm > 0 else None
    except Exception:
        return None


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _b64_decode(image_b64: str) -> bytes:
    """Decode a base64 image payload (data URLs already stripped upstream)."""
    import base64
    import binascii
    try:
        return base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError("image_b64 is not valid base64") from e


class SignatureEngine:
    """
    Signature Guard — enrollment, verification and watchlist alerting.

    Enrolled reference signatures are stored as normalised shape feature
    vectors in the configured vector store; raw images are only referenced
    through the evidence store (content-addressed object URI, never inline).

    An image-similarity score is a similarity signal, NOT legal proof of
    authorship — decisions are advisory and always explainable.
    """

    MODEL_VERSION = "signature-shape-v0.1"
    SIM_CLEAR = 0.85    # similarity at or above this => CLEAR
    SIM_REVIEW = 0.60   # similarity at or above this => REVIEW, below => BLOCK

    def __init__(self, store=None, evidence=None) -> None:
        self._settings = get_settings()
        self._store = store or get_vector_store()
        self._evidence = evidence or get_evidence_engine()

    # ── enrollment ────────────────────────────────────────────────
    def enroll(self, sample: SignatureSample, *, tenant_id: Optional[str] = None) -> EngineResult:
        t0 = time.perf_counter()
        tenant = tenant_id or sample.tenant_id or "default"
        gray = _to_gray_ndarray(sample.image_bytes)
        feats = _extract_signature_features(gray) if gray is not None else None
        if feats is None:
            logger.info("Signature enrollment rejected: blank/unreadable image")
            return EngineResult(
                engine="signature", risk_score=0.5, confidence=0.2,
                decision=Decision.REVIEW,
                reasons=["Image is blank or unreadable; no signature features extracted"],
                model_version=self.MODEL_VERSION,
                processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            )

        signature_id = uuid.uuid4().hex
        self._store.upsert(SIG_COLLECTION, [
            VectorPoint(
                id=signature_id,
                vector=feats.tolist(),
                payload={
                    "tenant_id": tenant,
                    "owner_id": sample.owner_id,
                    "label": sample.label,
                    "monitored": bool(sample.monitored),
                    "model_version": self.MODEL_VERSION,
                },
            )
        ])
        content_hash = hashlib.sha256(sample.image_bytes).hexdigest()
        evidence = self._evidence.store(
            tenant_id=tenant,
            storage_uri=f"objects/{tenant}/signatures/{content_hash}",
            content_type="image/*",
            purpose="signature enrollment reference",
            metadata={"sha256": content_hash, "owner_id": sample.owner_id},
        )

        result = EngineResult(
            engine="signature", risk_score=0.0, confidence=0.9,
            decision=Decision.CLEAR,
            signals=[Signal("enrolled", 1.0, 1.0, "Reference signature enrolled", "signature")],
            reasons=["Reference signature enrolled successfully"],
            model_version=self.MODEL_VERSION,
            processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            extra={
                "signature_id": signature_id,
                "sha256": content_hash,
                "stored_evidence_id": evidence.evidence_id,
                "monitored": bool(sample.monitored),
            },
        )
        self._audit(tenant, "signature.enroll", sample.owner_id, result)
        return result

    # ── verification ──────────────────────────────────────────────
    def verify(self, sample: SignatureSample, *, reference_id: str = "",
               tenant_id: Optional[str] = None) -> EngineResult:
        t0 = time.perf_counter()
        tenant = tenant_id or sample.tenant_id or "default"
        gray = _to_gray_ndarray(sample.image_bytes)
        feats = _extract_signature_features(gray) if gray is not None else None
        if feats is None:
            return EngineResult(
                engine="signature", risk_score=0.5, confidence=0.2,
                decision=Decision.REVIEW,
                reasons=["Image is blank or unreadable; no signature features extracted"],
                model_version=self.MODEL_VERSION,
                processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            )

        hits = self._store.search(
            SIG_COLLECTION, feats.tolist(), top_k=5,
            filter_={"tenant_id": tenant, "owner_id": sample.owner_id},
        )
        reference = None
        if reference_id:
            reference = next((h for h in hits if h.id == reference_id), None)
            if reference is None:
                return EngineResult(
                    engine="signature", risk_score=0.4, confidence=0.3,
                    decision=Decision.REVIEW,
                    reasons=[f"Reference signature '{reference_id}' not found for this owner"],
                    model_version=self.MODEL_VERSION,
                    processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
                    extra={"signature_id": reference_id},
                )
        elif hits:
            reference = hits[0]

        if reference is None:
            return EngineResult(
                engine="signature", risk_score=0.4, confidence=0.3,
                decision=Decision.REVIEW,
                reasons=["No reference signature enrolled for this owner"],
                model_version=self.MODEL_VERSION,
                processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            )

        similarity = max(0.0, min(1.0, reference.score))
        anomaly = round(1.0 - similarity, 4)

        if similarity >= self.SIM_CLEAR:
            decision = Decision.CLEAR
            reason = f"Signature similarity {similarity:.2f} matches reference"
        elif similarity >= self.SIM_REVIEW:
            decision = Decision.REVIEW
            reason = f"Signature similarity {similarity:.2f} inconclusive; manual review advised"
        else:
            decision = Decision.BLOCK
            reason = f"Signature similarity {similarity:.2f} does not match reference"

        result = EngineResult(
            engine="signature",
            risk_score=anomaly,
            confidence=round(0.5 + 0.5 * similarity, 4),
            decision=decision,
            signals=[
                Signal("signature_similarity", similarity, 0.60,
                       "Shape-feature cosine similarity vs reference", "signature"),
                Signal("signature_anomaly", anomaly, 0.40,
                       "Derived anomaly (1 - similarity)", "signature"),
            ],
            reasons=[reason],
            model_version=self.MODEL_VERSION,
            processing_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            extra={
                "signature_id": reference.id,
                "reference_label": reference.payload.get("label", ""),
                "monitored": bool(reference.payload.get("monitored", False)),
            },
        )

        if decision != Decision.CLEAR and reference.payload.get("monitored"):
            self._alert(tenant, sample.owner_id, decision, anomaly, reference.id)

        self._audit(tenant, "signature.verify", sample.owner_id, result)
        return result

    # ── cross-cutting ─────────────────────────────────────────────
    def _alert(self, tenant: str, owner_id: str, decision: Decision,
               anomaly: float, reference_id: str) -> None:
        try:
            from app.services.alerts import get_alert_engine
            get_alert_engine().create(
                tenant_id=tenant,
                alert_type="signature_anomaly",
                severity=Severity.HIGH if decision == Decision.BLOCK else Severity.MEDIUM,
                risk_score=anomaly,
                source="signature",
                message=(f"Signature mismatch for owner {owner_id} "
                         f"(similarity gap {anomaly:.2f}, decision {decision.value})"),
                metadata={"owner_id": owner_id, "signature_id": reference_id},
            )
        except Exception as e:
            logger.debug("signature alert skipped: %s", e)

    def _audit(self, tenant: str, event_type: str, owner_id: str,
               result: EngineResult) -> None:
        try:
            from app.services.audit import get_audit_logger
            get_audit_logger().log(
                event_type=event_type,
                tenant_id=tenant,
                resource_type="signature",
                resource_id=result.extra.get("signature_id", owner_id),
                action=event_type.split(".")[1],
                result=result.decision.value.lower(),
                metadata={"risk_score": result.risk_score,
                          "decision": result.decision.value},
            )
        except Exception as e:
            logger.debug("audit skipped: %s", e)

        return result

