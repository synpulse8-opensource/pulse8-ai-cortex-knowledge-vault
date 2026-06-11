"""Tests for TTL search cache."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


class TestCacheTTLConfig:
    def test_settings_expose_qmd_cache_ttl_with_default(self):
        """CORTEX_QMD_CACHE_TTL_SECONDS must be configurable, defaulting to 30s."""
        from cortex.config import CortexSettings

        assert CortexSettings().qmd_cache_ttl_seconds == 30.0

    def test_cache_uses_configured_ttl(self, monkeypatch):
        """CachedQMDSearch default TTL must come from settings."""
        from cortex.config import settings as app_settings
        from cortex.search.qmd_cache import CachedQMDSearch

        monkeypatch.setattr(app_settings, "qmd_cache_ttl_seconds", 120.0)
        cached = CachedQMDSearch(AsyncMock())
        assert cached._ttl == 120.0


class TestCacheSkipsFailures:
    @pytest.mark.asyncio
    async def test_empty_results_are_not_cached(self):
        """A failed/empty search (e.g. QMD timeout) must not be pinned in the cache."""
        from cortex.search.qmd_cache import CachedQMDSearch

        inner = AsyncMock()
        inner.search = AsyncMock(side_effect=[[], [{"path": "wiki/a.md", "score": 0.9}]])

        cached = CachedQMDSearch(inner, ttl_seconds=300)

        first = await cached.search("transformers", mode="hybrid")
        assert first == []

        second = await cached.search("transformers", mode="hybrid")
        assert second == [{"path": "wiki/a.md", "score": 0.9}]
        assert inner.search.await_count == 2, "empty result must not be served from cache"


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
