from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


class TestCachedQMDSearch:
    @pytest.mark.asyncio
    async def test_identical_queries_hit_cache(self):
        """Second identical search should not call the underlying searcher."""
        from cortex.search.qmd_cache import CachedQMDSearch

        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[{"path": "wiki/a.md", "score": 0.9}])
        inner.update = AsyncMock()
        inner.initialize = AsyncMock()

        cached = CachedQMDSearch(inner, ttl_seconds=10)

        r1 = await cached.search("transformers", mode="keyword")
        r2 = await cached.search("transformers", mode="keyword")

        assert r1 == r2
        assert inner.search.await_count == 1

    @pytest.mark.asyncio
    async def test_different_queries_miss_cache(self):
        from cortex.search.qmd_cache import CachedQMDSearch

        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[])
        inner.update = AsyncMock()
        inner.initialize = AsyncMock()

        cached = CachedQMDSearch(inner, ttl_seconds=10)

        await cached.search("transformers", mode="keyword")
        await cached.search("attention", mode="keyword")

        assert inner.search.await_count == 2

    @pytest.mark.asyncio
    async def test_different_modes_miss_cache(self):
        from cortex.search.qmd_cache import CachedQMDSearch

        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[])
        inner.update = AsyncMock()
        inner.initialize = AsyncMock()

        cached = CachedQMDSearch(inner, ttl_seconds=10)

        await cached.search("transformers", mode="keyword")
        await cached.search("transformers", mode="hybrid")

        assert inner.search.await_count == 2

    @pytest.mark.asyncio
    async def test_update_invalidates_cache(self):
        from cortex.search.qmd_cache import CachedQMDSearch

        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[{"path": "wiki/a.md", "score": 0.9}])
        inner.update = AsyncMock()
        inner.initialize = AsyncMock()

        cached = CachedQMDSearch(inner, ttl_seconds=10)

        await cached.search("transformers", mode="keyword")
        await cached.update()
        await cached.search("transformers", mode="keyword")

        assert inner.search.await_count == 2
        inner.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        from cortex.search.qmd_cache import CachedQMDSearch

        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[])
        inner.update = AsyncMock()
        inner.initialize = AsyncMock()

        cached = CachedQMDSearch(inner, ttl_seconds=0.05)

        await cached.search("transformers", mode="keyword")
        await asyncio.sleep(0.1)
        await cached.search("transformers", mode="keyword")

        assert inner.search.await_count == 2

    @pytest.mark.asyncio
    async def test_initialize_delegates(self):
        from cortex.search.qmd_cache import CachedQMDSearch

        inner = AsyncMock()
        inner.initialize = AsyncMock()
        inner.update = AsyncMock()

        cached = CachedQMDSearch(inner, ttl_seconds=10)
        await cached.initialize()

        inner.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_delegates(self):
        from cortex.search.qmd_cache import CachedQMDSearch

        inner = AsyncMock()
        inner.close = AsyncMock()
        inner.update = AsyncMock()
        inner.initialize = AsyncMock()

        cached = CachedQMDSearch(inner, ttl_seconds=10)
        await cached.close()

        inner.close.assert_awaited_once()
