"""
Alert Engine
============

Centralized alert generation with provider-agnostic dispatch.  Providers
(email/SMS/webhook) are pluggable; nothing is hard-coded to a single
provider.  In development without providers configured, alerts are
recorded and a log line is emitted.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from app.models.risk import Severity

logger = logging.getLogger("authetec.alerts")

ALERT_TYPES = {
    "document_fraud", "signature_anomaly", "signature_appearance",
    "face_mismatch", "liveness_failure", "image_manipulation",
    "fake_social_profile", "payment_fraud", "device_anomaly",
    "identity_anomaly", "watchlist_event", "risk_threshold_event",
}


@dataclass
class Alert:
    alert_id: str
    tenant_id: str
    type: str
    severity: Severity
    risk_score: float
    source: str
    evidence_ids: List[str] = field(default_factory=list)
    message: str = ""
    status: str = "OPEN"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


ProviderFn = Callable[[Alert], bool]


class AlertEngine:
    """Registry of dispatch providers + alert store.

    In development (no Supabase configured) alerts live in memory only.
    When Supabase is available, alerts are persisted to the ``alerts``
    table (see ``db/schema.sql``) and the in-memory list acts as cache.
    """

    def __init__(self, providers: Optional[Dict[str, ProviderFn]] = None) -> None:
        self.providers: Dict[str, ProviderFn] = providers or {}
        self._alerts: List[Alert] = []
        self.configured: Dict[str, bool] = {}
        self._sb = None
        try:
            from app.infrastructure.supabase import get_supabase
            sb = get_supabase()
            if sb.available:
                self._sb = sb
        except Exception:
            self._sb = None

    @property
    def persistence_enabled(self) -> bool:
        return self._sb is not None

    def _persist_insert(self, alert: Alert) -> None:
        if not self._sb:
            return
        try:
            self._sb.insert("alerts", [{
                "alert_id": alert.alert_id,
                "tenant_id": alert.tenant_id,
                "type": alert.type,
                "severity": alert.severity.value,
                "risk_score": alert.risk_score,
                "source": alert.source,
                "evidence_ids": alert.evidence_ids,
                "message": alert.message,
                "status": alert.status,
                "created_at": alert.created_at,
                "metadata": alert.metadata,
                "assigned_to": alert.assigned_to or "",
                "analyst_notes": alert.notes,
            }])
        except Exception as e:
            logger.warning("Alert persistence failed: %s (kept in memory)", e)

    def _persist_status(self, alert: Alert) -> None:
        if not self._sb:
            return
        try:
            self._sb.update(
                "alerts",
                {"status": alert.status,
                 "acknowledged_at": alert.acknowledged_at,
                 "resolved_at": alert.resolved_at,
                 "assigned_to": alert.assigned_to or "",
                 "analyst_notes": alert.notes},
                alert_id=alert.alert_id,
            )
        except Exception as e:
            logger.warning("Alert status persistence failed: %s", e)

    def register_provider(self, name: str, fn: ProviderFn) -> None:
        self.providers[name] = fn

    def health(self) -> Dict[str, Any]:
        return {
            "providers": list(self.providers.keys()),
            "configured": self.configured,
            "persistence_enabled": self.persistence_enabled,
            "open_alerts": sum(1 for a in self._alerts if a.status == "OPEN"),
        }

    def create(
        self,
        *,
        tenant_id: str,
        alert_type: str,
        severity: Severity,
        risk_score: float,
        source: str,
        evidence_ids: Optional[List[str]] = None,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        if alert_type not in ALERT_TYPES:
            raise ValueError(f"Unsupported alert type: {alert_type}")

        alert = Alert(
            alert_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            type=alert_type,
            severity=severity,
            risk_score=float(risk_score),
            source=source,
            evidence_ids=evidence_ids or [],
            message=message or f"{severity.value} {alert_type.replace('_', ' ')} risk {risk_score:.2f}",
            metadata=metadata or {},
        )
        self._alerts.append(alert)
        self._persist_insert(alert)

        logger.warning("ALERT [%s] %s tenant=%s score=%.2f source=%s",
                       severity.value, alert.alert_id, tenant_id, risk_score, source)

        delivered = []
        for name, fn in self.providers.items():
            try:
                ok = fn(alert)
                delivered.append({"provider": name, "delivered": bool(ok)})
            except Exception as e:
                logger.error("Alert provider %s failed: %s", name, e)
                delivered.append({"provider": name, "delivered": False, "error": str(e)})
        alert.metadata["delivered"] = delivered
        return alert

    def acknowledge(self, alert_id: str, tenant_id: str) -> Optional[Alert]:
        for a in self._alerts:
            if a.alert_id == alert_id and a.tenant_id == tenant_id:
                a.status = "ACKNOWLEDGED"
                a.acknowledged_at = datetime.now(timezone.utc).isoformat()
                self._persist_status(a)
                return a
        return None

    def resolve(self, alert_id: str, tenant_id: str) -> Optional[Alert]:
        for a in self._alerts:
            if a.alert_id == alert_id and a.tenant_id == tenant_id:
                a.status = "RESOLVED"
                a.resolved_at = datetime.now(timezone.utc).isoformat()
                self._persist_status(a)
                return a
        return None

    def assign(self, alert_id: str, tenant_id: str, assignee: str) -> Optional[Alert]:
        """Assign an open case to an analyst or work queue."""
        for a in self._alerts:
            if a.alert_id == alert_id and a.tenant_id == tenant_id:
                a.assigned_to = assignee
                if a.status == "OPEN":
                    a.status = "ACKNOWLEDGED"
                    a.acknowledged_at = a.acknowledged_at or datetime.now(timezone.utc).isoformat()
                self._persist_status(a)
                return a
        return None

    def add_note(self, alert_id: str, tenant_id: str,
                 text: str, author: str = "analyst") -> Optional[Alert]:
        """Append an immutable analyst note (author + text + timestamp)."""
        for a in self._alerts:
            if a.alert_id == alert_id and a.tenant_id == tenant_id:
                a.notes.append({
                    "author": author,
                    "text": text,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                self._persist_status(a)
                return a
        return None

    def list(self, tenant_id: str, limit: int = 50, status: Optional[str] = None) -> List[Alert]:
        out = [a for a in self._alerts if a.tenant_id == tenant_id]
        if status:
            out = [a for a in out if a.status == status]
        return list(reversed(out[-limit:]))


_engine: Optional[AlertEngine] = None


def get_alert_engine() -> AlertEngine:
    global _engine
    if _engine is None:
        _engine = AlertEngine()
    return _engine