"""
Audit Logging Service
=====================

Writes tamper-evident audit entries.  In development when no Supabase is
configured, entries are buffered in memory and are NOT persisted - the
service reports that persistence is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.security import new_correlation_id

logger = logging.getLogger("authetec.audit")

# Event catalog documented in the API docs and SQL schema.
EVENT_TYPES = {
    "auth.login", "auth.logout", "auth.failed",
    "authorization.check", "authorization.denied",
    "document.verify", "signature.verify", "signature.enroll",
    "face.verify", "media.analyze", "identity.verify",
    "social.monitor", "social.alert",
    "payment.score", "fraud.decision",
    "alert.created", "alert.acknowledged", "alert.resolved",
    "case.created", "case.updated",
    "config.change", "model.register", "model.approve",
    "api.access", "api.key.created", "api.key.revoked",
    "admin.action", "evidence.stored", "evidence.accessed",
}


class AuditLogger:
    """Append-only audit log with chained hashes for tamper evidence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chain: List[Dict[str, Any]] = []
        self._last_hash = "0" * 64
        self._persist_enabled = False
        try:
            from app.infrastructure.supabase import get_supabase
            self._sb = get_supabase()
            self._persist_enabled = self._sb.available
        except Exception:
            self._sb = None

    @property
    def persist_enabled(self) -> bool:
        return self._persist_enabled

    def log(
        self,
        *,
        event_type: str,
        actor_id: str = "system",
        tenant_id: str = "system",
        resource_type: str = "",
        resource_id: str = "",
        action: str = "",
        correlation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        result: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an audit entry.

        ``metadata`` may contain only low-sensitivity, non-payload data.
        Never pass passwords, tokens, biometric data, or document content.
        """
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown audit event type: {event_type}")

        meta_json = json.dumps(metadata or {}, sort_keys=True, default=str)
        entry = {
            "event_id": new_correlation_id(),
            "event_type": event_type,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id or new_correlation_id(),
            "request_id": request_id,
            "result": result,
            "metadata": (metadata or {}),
            "prev_hash": self._last_hash,
        }
        entry["hash"] = self._hash_entry(entry)

        with self._lock:
            self._last_hash = entry["hash"]
            self._chain.append(entry)

        if self._persist_enabled:
            try:
                row = {k: v for k, v in entry.items() if k != "hash"}
                # chain hash stored separately to keep metadata clean
                self._sb.insert("audit_events", [{**row, "entry_hash": entry["hash"]}])
            except Exception as e:
                logger.warning("Audit persistence failed: %s (entry kept in memory)", e)

        logger.info("audit event=%s tenant=%s actor=%s result=%s",
                    event_type, tenant_id, actor_id, result)
        return entry

    def _hash_entry(self, entry: Dict[str, Any]) -> str:
        blob = json.dumps(entry, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def recent(self, limit: int = 20, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            entries = self._chain
        if tenant_id:
            entries = [e for e in entries if e["tenant_id"] == tenant_id]
        return list(reversed(entries[-limit:]))

    def verify_chain(self) -> bool:
        """Check the hash chain integrity of the in-memory buffer."""
        with self._lock:
            chain = list(self._chain)
            last = "0" * 64
        for idx, entry in enumerate(chain):
            expected = {
                k: v for k, v in entry.items() if k != "hash"
            }
            expected["prev_hash"] = last
            blob = json.dumps(expected, sort_keys=True, default=str)
            if hashlib.sha256(blob.encode()).hexdigest() != entry["hash"]:
                return False
            last = entry["hash"]
        return True


_logger_instance: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = AuditLogger()
    return _logger_instance