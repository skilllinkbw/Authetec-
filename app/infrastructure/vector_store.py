"""
Vector Store Abstraction
========================

Authetec never couples to a single vector database.  A concrete store is
selected via settings; the interface supports upsert / search / delete.

Backends: memory (default, for tests/dev), chroma, qdrant.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from app.core.config import get_settings

logger = logging.getLogger("authetec.vector")


@dataclass
class VectorPoint:
    id: str
    vector: List[float]
    payload: Dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.payload is None:
            self.payload = {}


@dataclass
class VectorSearchHit:
    id: str
    score: float
    payload: Dict[str, Any]


class VectorStore(ABC):
    """Common interface for embedding storage and ANN search."""

    @abstractmethod
    def upsert(self, collection: str, points: Sequence[VectorPoint]) -> None: ...

    @abstractmethod
    def search(self, collection, query, top_k=10, filter_=None): ...

    @abstractmethod
    def delete(self, collection: str, point_ids: Sequence[str]) -> None: ...

    @abstractmethod
    def collection_count(self, collection: str) -> int: ...


class MemoryVectorStore(VectorStore):
    """In-memory brute-force store - for dev/test only, never production."""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, VectorPoint]] = {}

    def _cosine(self, a, b) -> float:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) + 1e-9
        nb = math.sqrt(sum(x * x for x in b)) + 1e-9
        return dot / (na * nb)

    def upsert(self, collection: str, points) -> None:
        coll = self._data.setdefault(collection, {})
        for p in points:
            coll[p.id] = p

    def search(self, collection: str, query, top_k=10, filter_=None):
        coll = self._data.get(collection, {})
        scored = []
        for pid, point in coll.items():
            payload = point.payload or {}
            if filter_ and not all(payload.get(k) == v for k, v in filter_.items()):
                continue
            score = self._cosine(query, point.vector)
            scored.append((score, pid, payload))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [VectorSearchHit(id=p, score=s, payload=pld) for s, p, pld in scored[:top_k]]

    def delete(self, collection: str, point_ids) -> None:
        coll = self._data.get(collection)
        if coll:
            for pid in point_ids:
                coll.pop(pid, None)

    def collection_count(self, collection: str) -> int:
        return len(self._data.get(collection, {}))


class ChromaVectorStore(VectorStore):
    """ChromaDB-backed store (persistent client)."""

    def __init__(self, persist_dir: Optional[str] = None):
        try:
            import chromadb
        except ImportError as e:
            raise RuntimeError("chromadb not installed") from e
        self._client = chromadb.PersistentClient(path=persist_dir or get_settings().chroma_persist_dir)

    def _coll(self, name: str):
        return self._client.get_or_create_collection(name)

    def upsert(self, collection: str, points) -> None:
        ids = [p.id for p in points]
        vectors = [p.vector for p in points]
        metas = [p.payload or {} for p in points]
        self._coll(collection).upsert(ids=ids, embeddings=vectors, metadatas=metas)

    def search(self, collection: str, query, top_k=10, filter_=None):
        where = {k: v for k, v in filter_.items()} if filter_ else None
        res = self._coll(collection).query(
            query_embeddings=[list(query)], n_results=top_k, where=where
        )
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        metas = res.get("metadatas", [[]])[0] or []
        hits = []
        for pid, dist, meta in zip(ids, dists, metas):
            hits.append(VectorSearchHit(id=pid, score=1.0 - float(dist), payload=meta or {}))
        return hits

    def delete(self, collection: str, point_ids) -> None:
        self._coll(collection).delete(ids=list(point_ids))

    def collection_count(self, collection: str) -> int:
        return self._coll(collection).count()


class QdrantVectorStore(VectorStore):
    """Qdrant-backed store."""

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None):
        try:
            from qdrant_client import QdrantClient
        except ImportError as e:
            raise RuntimeError("qdrant-client not installed") from e
        s = get_settings()
        self._client = QdrantClient(url=url or s.qdrant_url, api_key=api_key or s.qdrant_api_key)

    def _size(self, name: str) -> int:
        info = self._client.get_collection(name)
        return info.config.params.vectors.size

    def upsert(self, collection: str, points) -> None:
        from qdrant_client.models import PointStruct
        size = self._size(collection)
        records = [PointStruct(id=p.id, vector=p.vector, payload=p.payload or {})
                   for p in points if len(p.vector) == size]
        if records:
            self._client.upsert(collection_name=collection, points=records)

    def search(self, collection: str, query, top_k=10, filter_=None):
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        q_filter = None
        if filter_:
            q_filter = Filter(must=[FieldCondition(key=k, match=MatchValue(value=v))
                                    for k, v in filter_.items()])
        res = self._client.search(collection_name=collection, query_vector=list(query),
                                  limit=top_k, query_filter=q_filter)
        return [VectorSearchHit(id=r.id, score=float(r.score), payload=r.payload or {}) for r in res]

    def delete(self, collection: str, point_ids) -> None:
        from qdrant_client.models import PointIdsList
        self._client.delete(collection_name=collection, points_selector=PointIdsList(points=list(point_ids)))

    def collection_count(self, collection: str) -> int:
        try:
            return self._client.count(collection_name=collection).count
        except Exception:
            return 0


_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Factory: instantiate the configured backend once per process."""
    global _store_instance
    if _store_instance is not None:
        return _store_instance
    backend = get_settings().vector_store_backend.lower()
    if backend == "chroma":
        try:
            _store_instance = ChromaVectorStore()
            return _store_instance
        except Exception as e:
            logger.warning("Chroma unavailable (%s); falling back to memory", e)
    elif backend == "qdrant":
        try:
            _store_instance = QdrantVectorStore()
            return _store_instance
        except Exception as e:
            logger.warning("Qdrant unavailable (%s); falling back to memory", e)
    _store_instance = MemoryVectorStore()
    return _store_instance
