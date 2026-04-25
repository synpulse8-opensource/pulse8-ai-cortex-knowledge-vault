from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cortex.vault.models import EdgeType


@pytest.fixture
async def context_services(tmp_vault: Path):
    """Set up graph and QMD for context window tests."""
    from cortex.graph.engine import GraphEngine
    from cortex.graph.builder import build_graph
    from cortex.vault.reader import scan_vault
    from cortex.search.qmd import QMDSearch

    notes = scan_vault(tmp_vault)
    graph = await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)
    qmd = QMDSearch(tmp_vault, "qmd")

    return {
        "vault_root": tmp_vault,
        "graph": graph,
        "searcher": qmd,
    }


class TestBuildContextWindow:
    @pytest.mark.asyncio
    async def test_returns_context_window(self, context_services):
        from cortex.graph.context import build_context_window
        from cortex.vault.models import ContextWindow

        mock_results = [
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer"},
        ]

        with patch.object(context_services["searcher"], "search", new_callable=AsyncMock, return_value=mock_results):
            result = await build_context_window(
                query="transformer architecture",
                **context_services,
            )
            assert isinstance(result, ContextWindow)

    @pytest.mark.asyncio
    async def test_includes_seed_notes(self, context_services):
        from cortex.graph.context import build_context_window

        mock_results = [
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer"},
        ]

        with patch.object(context_services["searcher"], "search", new_callable=AsyncMock, return_value=mock_results):
            result = await build_context_window(
                query="transformer",
                **context_services,
            )
            paths = [n.path for n in result.notes]
            assert "wiki/transformers.md" in paths

    @pytest.mark.asyncio
    async def test_expands_via_bfs(self, context_services):
        from cortex.graph.context import build_context_window

        mock_results = [
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer"},
        ]

        with patch.object(context_services["searcher"], "search", new_callable=AsyncMock, return_value=mock_results):
            result = await build_context_window(
                query="transformer",
                max_depth=2,
                **context_services,
            )
            paths = [n.path for n in result.notes]
            assert "wiki/attention-mechanisms.md" in paths

    @pytest.mark.asyncio
    async def test_collects_edges_between_results(self, context_services):
        from cortex.graph.context import build_context_window

        mock_results = [
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer"},
        ]

        with patch.object(context_services["searcher"], "search", new_callable=AsyncMock, return_value=mock_results):
            result = await build_context_window(
                query="transformer",
                **context_services,
            )
            assert result.total_edges_explored >= 0

    @pytest.mark.asyncio
    async def test_respects_max_notes(self, context_services):
        from cortex.graph.context import build_context_window

        mock_results = [
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer"},
        ]

        with patch.object(context_services["searcher"], "search", new_callable=AsyncMock, return_value=mock_results):
            result = await build_context_window(
                query="transformer",
                max_notes=1,
                **context_services,
            )
            assert len(result.notes) <= 1

    @pytest.mark.asyncio
    async def test_empty_search_returns_empty_context(self, context_services):
        from cortex.graph.context import build_context_window

        with patch.object(context_services["searcher"], "search", new_callable=AsyncMock, return_value=[]):
            result = await build_context_window(
                query="nonexistent topic",
                **context_services,
            )
            assert len(result.notes) == 0

    @pytest.mark.asyncio
    async def test_uses_explicit_search_mode(self, context_services):
        """build_context_window should pass the mode argument to searcher.search."""
        from cortex.graph.context import build_context_window

        mock_results = [
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer"},
        ]

        with patch.object(
            context_services["searcher"], "search",
            new_callable=AsyncMock, return_value=mock_results,
        ) as mock_search:
            await build_context_window(
                query="transformer",
                mode="keyword",
                **context_services,
            )
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs.get("mode") == "keyword"

    @pytest.mark.asyncio
    async def test_default_mode_is_hybrid(self, context_services):
        """Without an explicit mode, build_context_window should default to hybrid."""
        from cortex.graph.context import build_context_window

        mock_results = []

        with patch.object(
            context_services["searcher"], "search",
            new_callable=AsyncMock, return_value=mock_results,
        ) as mock_search:
            await build_context_window(
                query="transformer",
                **context_services,
            )
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs.get("mode") == "hybrid"

    @pytest.mark.asyncio
    async def test_detects_contradictions(self, context_services):
        from cortex.graph.context import build_context_window
        from cortex.vault.models import Edge

        graph = context_services["graph"]
        await graph.add_edge(Edge(
            source="wiki/transformers.md",
            target="wiki/attention-mechanisms.md",
            edge_type=EdgeType.CONTRADICTS,
        ))

        mock_results = [
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer"},
        ]

        with patch.object(context_services["searcher"], "search", new_callable=AsyncMock, return_value=mock_results):
            result = await build_context_window(
                query="transformer",
                **context_services,
            )
            assert len(result.contradictions) >= 1
