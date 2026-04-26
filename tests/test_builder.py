"""Tests for graph builder."""
from __future__ import annotations

from pathlib import Path

import pytest

from cortex.vault.models import EdgeType


class TestBuildGraph:
    @pytest.mark.asyncio
    async def test_builds_nodes_from_notes(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault
        from cortex.graph.builder import build_graph

        notes = scan_vault(tmp_vault)
        graph_path = tmp_vault / ".cortex" / "graph.json"
        engine = await build_graph(notes, graph_path, tmp_vault)

        assert engine.graph.has_node("wiki/transformers.md")
        assert engine.graph.has_node("wiki/attention-mechanisms.md")
        assert engine.graph.has_node("agents/research-scout.agent.md")

    @pytest.mark.asyncio
    async def test_creates_links_to_edges(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault
        from cortex.graph.builder import build_graph

        notes = scan_vault(tmp_vault)
        engine = await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)

        edges = await engine.get_edges("wiki/transformers.md", edge_types=[EdgeType.LINKS_TO], direction="out")
        targets = [e.target for e in edges]
        assert "wiki/attention-mechanisms.md" in targets

    @pytest.mark.asyncio
    async def test_creates_tagged_with_edges(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault
        from cortex.graph.builder import build_graph

        notes = scan_vault(tmp_vault)
        engine = await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)

        edges = await engine.get_edges("wiki/transformers.md", edge_types=[EdgeType.TAGGED_WITH], direction="out")
        targets = [e.target for e in edges]
        assert "tag:ml" in targets
        assert "tag:architecture" in targets

    @pytest.mark.asyncio
    async def test_creates_derived_from_edges(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault
        from cortex.graph.builder import build_graph

        notes = scan_vault(tmp_vault)
        engine = await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)

        edges = await engine.get_edges("wiki/transformers.md", edge_types=[EdgeType.DERIVED_FROM], direction="out")
        assert len(edges) == 1
        assert edges[0].target == "raw/transformer-paper.txt"

    @pytest.mark.asyncio
    async def test_tag_nodes_created(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault
        from cortex.graph.builder import build_graph

        notes = scan_vault(tmp_vault)
        engine = await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)

        assert engine.graph.has_node("tag:ml")
        assert engine.graph.nodes["tag:ml"]["node_type"] == "tag"

    @pytest.mark.asyncio
    async def test_graph_persisted(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault
        from cortex.graph.builder import build_graph
        from cortex.graph.engine import GraphEngine

        notes = scan_vault(tmp_vault)
        graph_path = tmp_vault / ".cortex" / "graph.json"
        await build_graph(notes, graph_path, tmp_vault)

        engine2 = GraphEngine(graph_path)
        await engine2.load()
        assert engine2.graph.number_of_nodes() > 0
