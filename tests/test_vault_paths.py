"""Tests for QMD ↔ filesystem path resolution."""
from __future__ import annotations

from pathlib import Path

import pytest

from cortex.graph.engine import GraphEngine
from cortex.vault.models import NodeType
from cortex.vault.paths import (
    build_path_index_from_graph,
    path_lookup_key,
    resolve_note_path,
)


class TestPathLookupKey:
    def test_normalizes_spaces_and_underscores(self):
        qmd_path = "wiki2/Knowledge-vault/01-Clients/SCB/foo.md"
        fs_path = "wiki2/Knowledge vault/01_Clients/SCB/foo.md"
        assert path_lookup_key(qmd_path) == path_lookup_key(fs_path)

    def test_unchanged_for_simple_paths(self):
        assert path_lookup_key("wiki/transformers.md") == "wiki/transformers.md"


class TestResolveNotePath:
    def test_exact_path_unchanged(self, tmp_path: Path):
        note = tmp_path / "wiki" / "test.md"
        note.parent.mkdir(parents=True)
        note.write_text("# Test\n")

        assert resolve_note_path("wiki/test.md", tmp_path) == "wiki/test.md"

    def test_resolves_qmd_normalized_path(self, tmp_path: Path):
        rel = "wiki2/Knowledge vault/01_Clients/SCB/scb-sda.md"
        note = tmp_path / rel
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("# SDA\n")

        graph = GraphEngine(tmp_path / ".cortex" / "graph.json")
        graph.graph.add_node(rel, node_type=NodeType.NOTE.value, title="SDA")

        qmd_path = "wiki2/Knowledge-vault/01-Clients/SCB/scb-sda.md"
        assert resolve_note_path(qmd_path, tmp_path, graph=graph) == rel

    @pytest.mark.asyncio
    async def test_search_handler_rewrites_qmd_paths(self, tmp_path: Path):
        from unittest.mock import AsyncMock, MagicMock

        from cortex.mcp.tools import handle_vault_search

        vault_path = tmp_path
        graph = GraphEngine(vault_path / ".cortex" / "graph.json")
        rel = "wiki2/Knowledge vault/01_Clients/SCB/scb-sda.md"
        note_path = vault_path / rel
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("---\ntitle: SDA\n---\n\n# SDA\n")
        graph.graph.add_node(rel, node_type=NodeType.NOTE.value, title="SDA")

        qmd = MagicMock()
        qmd.search = AsyncMock(
            return_value=[
                {
                    "path": "wiki2/Knowledge-vault/01-Clients/SCB/scb-sda.md",
                    "score": 0.9,
                    "snippet": "SDA",
                }
            ]
        )

        result = await handle_vault_search(
            query="SDA",
            vault_path=vault_path,
            graph=graph,
            qmd=qmd,
        )
        assert result["results"][0]["path"] == rel

    @pytest.mark.asyncio
    async def test_read_resolves_qmd_path(self, tmp_path: Path):
        from cortex.mcp.tools import handle_vault_read

        vault_path = tmp_path
        graph = GraphEngine(vault_path / ".cortex" / "graph.json")
        rel = "wiki2/Knowledge vault/01_Clients/SCB/scb-sda.md"
        note_path = vault_path / rel
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("---\ntitle: SDA\n---\n\n# SDA body\n")
        graph.graph.add_node(rel, node_type=NodeType.NOTE.value, title="SDA")

        result = await handle_vault_read(
            path="wiki2/Knowledge-vault/01-Clients/SCB/scb-sda.md",
            vault_path=vault_path,
            graph=graph,
        )
        assert result["path"] == rel
        assert "SDA body" in result["content"]


class TestBuildPathIndexFromGraph:
    def test_maps_normalized_keys(self):
        graph = GraphEngine(Path("/tmp/unused-graph.json"))
        rel = "wiki2/Knowledge vault/01_Clients/foo.md"
        graph.graph.add_node(rel, node_type=NodeType.NOTE.value, title="foo")

        index = build_path_index_from_graph(graph)
        assert index[path_lookup_key("wiki2/Knowledge-vault/01-Clients/foo.md")] == rel
