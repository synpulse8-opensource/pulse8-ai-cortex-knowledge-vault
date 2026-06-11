"""Performance benchmarks for the search and context pipelines.

Run with:  uv run pytest tests/test_perf_search.py -v -s
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortex.vault.models import NodeType, Note, Provenance


def _make_note(path: str, title: str) -> Note:
    return Note(
        path=path,
        title=title,
        content=f"# {title}\n\nContent for {title}.\n",
        frontmatter={"title": title, "tags": ["bench"]},
        node_type=NodeType.NOTE,
        provenance=Provenance(),
    )


def _build_large_vault(tmp_path: Path, n_notes: int = 100) -> Path:
    """Create a vault with *n_notes* wiki articles and cross-links."""
    vault = tmp_path / "vault"
    for d in ["wiki", "raw", ".cortex"]:
        (vault / d).mkdir(parents=True)
    (vault / ".cortex" / "graph.json").write_text('{"nodes": [], "edges": []}')
    (vault / ".cortex" / "log.md").write_text("")

    for i in range(n_notes):
        link_target = f"note-{(i + 1) % n_notes}"
        (vault / "wiki" / f"note-{i}.md").write_text(
            f"---\ntitle: Note {i}\ntags: [bench, group-{i % 10}]\n"
            f"authored_by: benchmark\n---\n\n"
            f"# Note {i}\n\nSee also: [[{link_target}]]\n"
        )
    return vault


@pytest.fixture
def large_vault(tmp_path: Path) -> Path:
    return _build_large_vault(tmp_path, n_notes=100)


@pytest.fixture
async def bench_graph(large_vault: Path):
    from cortex.graph.builder import build_graph
    from cortex.vault.reader import scan_vault

    notes = scan_vault(large_vault)
    graph = await build_graph(
        notes, large_vault / ".cortex" / "graph.json", large_vault
    )
    return graph


class TestSearchBenchmark:
    """Benchmarks that verify search-related operations stay within time budgets."""

    @pytest.mark.asyncio
    async def test_get_edges_batch_100_paths_under_50ms(self, bench_graph):
        """Batch edge fetch for 100 paths should complete quickly (in-memory)."""
        paths = [f"wiki/note-{i}.md" for i in range(100)]

        start = time.perf_counter()
        for _ in range(100):
            await bench_graph.get_edges_batch(paths)
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 100
        print(f"\n  get_edges_batch(100 paths) × 100: {elapsed_ms:.1f}ms total, {avg_ms:.2f}ms avg")
        assert avg_ms < 50, f"get_edges_batch too slow: {avg_ms:.2f}ms avg (budget: 50ms)"

    @pytest.mark.asyncio
    async def test_log_operation_does_not_block_loop(self, large_vault: Path):
        """log_operation should not add measurable event-loop blocking time."""
        from cortex.log.audit import log_operation

        async def concurrent_counter():
            """Tick counter that only runs if the event loop is free."""
            count = 0
            for _ in range(50):
                await asyncio.sleep(0)
                count += 1
            return count

        task = asyncio.create_task(concurrent_counter())

        for i in range(50):
            await log_operation(large_vault, "bench", "vault:search", f"op {i}")

        ticks = await task
        print(f"\n  Event-loop ticks during 50 log_operation calls: {ticks}/50")
        assert ticks >= 40, (
            f"Event loop was starved ({ticks}/50 ticks) — log_operation likely blocking"
        )

    @pytest.mark.asyncio
    async def test_vault_read_offloads_slow_note_parse(self, large_vault: Path, bench_graph):
        """A slow synchronous note parse must not freeze the event loop.

        Simulates a large note (80ms sync parse). If read_note runs on the
        loop thread, a concurrent ticker cannot tick during the parse; when
        offloaded to a thread, the loop stays responsive.
        """
        from cortex.mcp import tools
        from cortex.vault.reader import read_note as real_read_note

        def slow_read(path, vault_root):
            time.sleep(0.08)
            return real_read_note(path, vault_root)

        ticks = 0
        done = False

        async def ticker():
            nonlocal ticks
            while not done:
                await asyncio.sleep(0.005)
                ticks += 1

        task = asyncio.create_task(ticker())
        with patch.object(tools, "read_note", side_effect=slow_read):
            result = await tools.handle_vault_read(
                path="wiki/note-0.md",
                vault_path=large_vault,
                graph=bench_graph,
            )
        done = True
        await task

        assert "error" not in result
        print(f"\n  Ticker progress during 80ms blocked parse: {ticks} ticks")
        assert ticks >= 5, (
            f"Event loop frozen during note parse ({ticks} ticks) — "
            "read_note must be offloaded to a thread"
        )

    @pytest.mark.asyncio
    async def test_build_context_window_under_200ms(self, large_vault: Path, bench_graph):
        """Full context window build should complete in <200ms with mocked QMD."""
        from cortex.graph.context import build_context_window
        from cortex.search.qmd import QMDSearch

        searcher = QMDSearch(large_vault, "qmd")
        mock_results = [
            {"path": f"wiki/note-{i}.md", "score": 1.0 - i * 0.05, "snippet": f"note {i}"}
            for i in range(16)
        ]

        with patch.object(searcher, "search", new_callable=AsyncMock, return_value=mock_results):
            start = time.perf_counter()
            result = await build_context_window(
                query="benchmark",
                searcher=searcher,
                graph=bench_graph,
                vault_root=large_vault,
                max_notes=8,
                max_depth=2,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n  build_context_window: {elapsed_ms:.1f}ms, {len(result.notes)} notes, "
              f"{result.total_nodes_explored} nodes explored")
        assert elapsed_ms < 200, f"Context build too slow: {elapsed_ms:.1f}ms (budget: 200ms)"
        assert len(result.notes) > 0

    @pytest.mark.asyncio
    async def test_vault_search_handler_under_100ms(self, large_vault: Path, bench_graph):
        """handle_vault_search should complete in <100ms with mocked QMD."""
        from cortex.mcp.tools import handle_vault_search

        mock_qmd = AsyncMock()
        mock_qmd.search = AsyncMock(return_value=[
            {"path": f"wiki/note-{i}.md", "score": 0.9 - i * 0.05}
            for i in range(10)
        ])

        start = time.perf_counter()
        result = await handle_vault_search(
            query="benchmark test",
            vault_path=large_vault,
            graph=bench_graph,
            qmd=mock_qmd,
            mode="keyword",
            top_k=10,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n  handle_vault_search: {elapsed_ms:.1f}ms, "
              f"{len(result.get('results', []))} results")
        assert elapsed_ms < 100, f"vault_search too slow: {elapsed_ms:.1f}ms (budget: 100ms)"
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_repeated_searches_reuse_path_index(self, large_vault: Path, bench_graph):
        """Path index must be built once across repeated searches, not per call."""
        from cortex.mcp.tools import handle_vault_search
        from cortex.vault import paths as paths_mod

        mock_qmd = AsyncMock()
        mock_qmd.search = AsyncMock(return_value=[
            {"path": f"wiki/note-{i}.md", "score": 0.9 - i * 0.05}
            for i in range(10)
        ])

        with patch.object(
            paths_mod, "path_lookup_key", wraps=paths_mod.path_lookup_key
        ) as spy:
            for i in range(5):
                await handle_vault_search(
                    query=f"bench-{i}", vault_path=large_vault,
                    graph=bench_graph, qmd=mock_qmd, mode="keyword", top_k=10,
                )
            call_count = spy.call_count

        # 1 index build (~100 nodes) + 10 result-path lookups × 5 searches.
        # Without memoization this would be ≥ 5 × (100 + 10) = 550 calls.
        print(f"\n  path_lookup_key calls across 5 searches: {call_count}")
        assert call_count < 300, (
            f"Path index appears to be rebuilt per search ({call_count} slug calls)"
        )

    @pytest.mark.asyncio
    async def test_concurrent_searches_scale(self, large_vault: Path, bench_graph):
        """10 concurrent searches should not take 10× a single search."""
        from cortex.mcp.tools import handle_vault_search

        mock_qmd = AsyncMock()
        mock_qmd.search = AsyncMock(return_value=[
            {"path": f"wiki/note-{i}.md", "score": 0.9 - i * 0.05}
            for i in range(10)
        ])

        start_single = time.perf_counter()
        await handle_vault_search(
            query="single", vault_path=large_vault,
            graph=bench_graph, qmd=mock_qmd, mode="keyword", top_k=10,
        )
        single_ms = (time.perf_counter() - start_single) * 1000

        start_batch = time.perf_counter()
        await asyncio.gather(*(
            handle_vault_search(
                query=f"concurrent-{i}", vault_path=large_vault,
                graph=bench_graph, qmd=mock_qmd, mode="keyword", top_k=10,
            )
            for i in range(10)
        ))
        batch_ms = (time.perf_counter() - start_batch) * 1000

        ratio = batch_ms / max(single_ms, 0.01)
        print(f"\n  Single search: {single_ms:.1f}ms")
        print(f"  10 concurrent searches: {batch_ms:.1f}ms (ratio: {ratio:.1f}×)")
        assert batch_ms < 500, f"10 concurrent searches too slow: {batch_ms:.1f}ms (budget: 500ms)"


class TestMCPBenchmark:
    """Benchmarks for MCP-specific fixes (shared services, caching, async scan)."""

    @pytest.mark.asyncio
    async def test_shared_services_skips_graph_rebuild(self, large_vault, bench_graph):
        """create_fastmcp_server with pre-built services must not call build_graph."""
        from cortex.mcp.http_server import create_fastmcp_server

        services = {
            "vault_path": large_vault,
            "graph": bench_graph,
            "qmd": AsyncMock(),
            "compiler": MagicMock(),
        }

        with patch(
            "cortex.mcp.http_server.build_graph", new_callable=AsyncMock,
        ) as mock_bg:
            start = time.perf_counter()
            await create_fastmcp_server(large_vault, services=services)
            elapsed_ms = (time.perf_counter() - start) * 1000

            mock_bg.assert_not_awaited()

        print(f"\n  create_fastmcp_server (shared): {elapsed_ms:.1f}ms")
        assert elapsed_ms < 500, (
            f"MCP server creation too slow with shared services: "
            f"{elapsed_ms:.1f}ms (budget: 500ms)"
        )

    @pytest.mark.asyncio
    async def test_fallback_path_does_not_block_loop(self, large_vault):
        """Fallback (no services) must use scan_vault_async, not sync scan."""
        from cortex.mcp.http_server import create_fastmcp_server

        ticks = 0

        async def tick_counter():
            nonlocal ticks
            for _ in range(100):
                await asyncio.sleep(0)
                ticks += 1

        scan_patch = patch(
            "cortex.mcp.http_server.scan_vault_async",
            new_callable=AsyncMock, return_value=[],
        )
        bg_patch = patch(
            "cortex.mcp.http_server.build_graph",
            new_callable=AsyncMock,
        )

        with patch("cortex.search.qmd.QMDSearch._run",
                    new_callable=AsyncMock, return_value=""):
            with scan_patch as mock_scan, bg_patch as mock_bg:
                mock_bg.return_value = AsyncMock()
                mock_bg.return_value.graph = MagicMock()

                task = asyncio.create_task(tick_counter())
                await create_fastmcp_server(large_vault)
                await task

                mock_scan.assert_awaited_once()

        print(f"\n  Event-loop ticks during fallback startup: {ticks}/100")
        assert ticks >= 80, (
            f"Event loop starved during fallback startup ({ticks}/100 ticks)"
        )

    @pytest.mark.asyncio
    async def test_cached_search_faster_on_repeat(self):
        """CachedQMDSearch should serve repeated queries much faster."""
        from cortex.search.qmd_cache import CachedQMDSearch

        inner = AsyncMock()
        inner.search = AsyncMock(return_value=[
            {"path": f"wiki/note-{i}.md", "score": 0.9}
            for i in range(10)
        ])
        cached = CachedQMDSearch(inner)

        await cached.search("test query", mode="hybrid", top_k=10)
        inner.search.assert_awaited_once()

        start = time.perf_counter()
        for _ in range(100):
            await cached.search("test query", mode="hybrid", top_k=10)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert inner.search.await_count == 1
        avg_us = (elapsed_ms / 100) * 1000
        print(f"\n  Cached search hit ×100: {elapsed_ms:.1f}ms total, {avg_us:.0f}µs avg")
        assert elapsed_ms < 10, (
            f"100 cached lookups too slow: {elapsed_ms:.1f}ms (budget: 10ms)"
        )
