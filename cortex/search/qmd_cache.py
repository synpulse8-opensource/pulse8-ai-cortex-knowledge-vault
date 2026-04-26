"""TTL search-result cache wrapper for QMD backends."""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class CachedQMDSearch:
    """Transparent caching wrapper around any QMD search backend.

    Caches search results keyed by (query, mode, collection, top_k).
    The cache is fully invalidated on ``update()`` or after ``ttl_seconds``.
    """

    def __init__(self, inner: Any, ttl_seconds: float = 30.0) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._cache: dict[tuple, tuple[float, list[dict]]] = {}

    async def initialize(self) -> None:
        """Delegate initialization to the inner backend."""
        await self._inner.initialize()

    async def update(self) -> None:
        """Invalidate cache and delegate update to the inner backend."""
        self._cache.clear()
        await self._inner.update()

    async def search(
        self,
        query: str,
        mode: str = "hybrid",
        collection: str | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        """Return cached results or delegate to the inner backend."""
        key = (query, mode, collection, top_k)
        now = time.monotonic()

        cached = self._cache.get(key)
        if cached is not None:
            ts, results = cached
            if now - ts < self._ttl:
                return results

        results = await self._inner.search(
            query, mode=mode, collection=collection, top_k=top_k
        )
        self._cache[key] = (now, results)
        return results

    async def close(self) -> None:
        """Close the inner backend if it supports it."""
        if hasattr(self._inner, "close"):
            await self._inner.close()
