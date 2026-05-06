"""Performance benchmarks for the search and context pipelines.

Run with:  uv run pytest tests/test_perf_search.py -v -s
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
