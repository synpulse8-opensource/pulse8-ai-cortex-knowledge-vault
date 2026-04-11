from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


class TestVaultWatcher:
    def test_watcher_can_be_instantiated(self, tmp_vault: Path):
        from cortex.vault.watcher import VaultWatcher
        from cortex.graph.engine import GraphEngine

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        watcher = VaultWatcher(tmp_vault, graph)
        assert watcher.vault_root == tmp_vault

    @pytest.mark.asyncio
    async def test_handle_change_reads_note(self, tmp_vault: Path):
        from cortex.vault.watcher import VaultWatcher
        from cortex.graph.engine import GraphEngine

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        await graph.load()

        watcher = VaultWatcher(tmp_vault, graph)
        await watcher._handle_change(tmp_vault / "wiki" / "transformers.md")
        assert graph.graph.has_node("wiki/transformers.md")

    @pytest.mark.asyncio
    async def test_handle_delete_removes_node(self, tmp_vault: Path):
        from cortex.vault.watcher import VaultWatcher
        from cortex.graph.engine import GraphEngine
        from cortex.vault.models import Note, NodeType, Provenance

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        await graph.load()

        note = Note(
            path="wiki/to-delete.md",
            title="Delete Me",
            content="",
            frontmatter={},
            node_type=NodeType.NOTE,
            provenance=Provenance(),
        )
        await graph.add_note_node(note)
        assert graph.graph.has_node("wiki/to-delete.md")

        watcher = VaultWatcher(tmp_vault, graph)
        await watcher._handle_delete("wiki/to-delete.md")
        assert not graph.graph.has_node("wiki/to-delete.md")

    @pytest.mark.asyncio
    async def test_handle_change_skips_cortex_dir(self, tmp_vault: Path):
        from cortex.vault.watcher import VaultWatcher
        from cortex.graph.engine import GraphEngine

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        await graph.load()

        watcher = VaultWatcher(tmp_vault, graph)
        initial_count = graph.graph.number_of_nodes()
        await watcher._handle_change(tmp_vault / ".cortex" / "index.md")
        assert graph.graph.number_of_nodes() == initial_count
