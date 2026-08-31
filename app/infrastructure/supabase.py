"""
Supabase Access Layer
=====================

Lazy client creation; the app must NEVER use the service key in the
browser.  All server-side operations go through this module so tenant /
RLS behaviour can be switched consistently.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.config import get_settings

logger = logging.getLogger("authetec.supabase")


class SupabaseClient:
    """Thin wrapper around the Supabase Python client (lazy init)."""

    def __init__(self) -> None:
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is None:
            settings = get_settings()
            if not settings.supabase_url or not settings.supabase_service_key:
                raise RuntimeError(
                    "Supabase not configured: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
                )
            from supabase import create_client
            self._client = create_client(settings.supabase_url, settings.supabase_service_key)
        return self._client

    @property
    def available(self) -> bool:
        s = get_settings()
        return bool(s.supabase_url and s.supabase_service_key)

    def table(self, name: str):
        """Return a table reference builder."""
        return self._ensure().table(name)

    def insert(self, table: str, rows: List[Dict[str, Any]] | Dict[str, Any]) -> Any:
        return self.table(table).insert(rows).execute()

    def select(self, table: str, columns: str = "*", **filters: Any) -> Any:
        q = self.table(table).select(columns)
        for k, v in filters.items():
            q = q.eq(k, v)
        return q.execute()

    def update(self, table: str, values: Dict[str, Any], **filters: Any) -> Any:
        q = self.table(table).update(values)
        for k, v in filters.items():
            q = q.eq(k, v)
        return q.execute()

    def delete(self, table: str, **filters: Any) -> Any:
        q = self.table(table).delete()
        for k, v in filters.items():
            q = q.eq(k, v)
        return q.execute()

    def health(self) -> Dict[str, Any]:
        if not self.available:
            return {"configured": False, "reachable": False, "reason": "not configured"}
        try:
            r = self._ensure().postgrest.rest_health()
            return {"configured": True, "reachable": True, "detail": str(r).strip()}
        except Exception as e:
            return {"configured": True, "reachable": False, "reason": str(e)}


_client: Optional[SupabaseClient] = None


def get_supabase() -> SupabaseClient:
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client