"""Tests for vault filesystem watcher."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from watchfiles import Change


class TestVaultWatcher:
    def test_watcher_can_be_instantiated(self, tmp_vault: Path):
        from cortex.vault.watcher import VaultWatcher
        from cortex.graph.engine import GraphEngine

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        watcher = VaultWatcher(tmp_vault, graph)
        assert watcher.vault_root == tmp_vault

    def test_vault_root_resolved_to_absolute(self, tmp_vault: Path, monkeypatch):
        """Relative vault_root must be resolved so watchfiles absolute paths match."""
        from cortex.vault.watcher import VaultWatcher
        from cortex.graph.engine import GraphEngine

        monkeypatch.chdir(tmp_vault.parent)
        relative = Path(tmp_vault.name)

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        watcher = VaultWatcher(relative, graph)
        assert watcher.vault_root.is_absolute()
        assert watcher.vault_root == tmp_vault

    @pytest.mark.asyncio
    async def test_handle_changes_batch_persists_once(self, tmp_vault: Path):
        """Multiple graph updates in one batch should produce a single disk write."""
        from cortex.vault.watcher import VaultWatcher
        from cortex.graph.engine import GraphEngine

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        await graph.load()

        watcher = VaultWatcher(tmp_vault, graph)
        with patch.object(graph, "_persist", new_callable=AsyncMock) as mock_persist:
            async with graph.batch():
                await watcher._handle_change(tmp_vault / "wiki" / "transformers.md")
                await watcher._handle_change(tmp_vault / "wiki" / "attention-mechanisms.md")

            assert mock_persist.await_count == 1

        assert graph.graph.has_node("wiki/transformers.md")
        assert graph.graph.has_node("wiki/attention-mechanisms.md")

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

    def test_watch_filter_excludes_cortex_dir(self, tmp_vault: Path):
        """awatch must use a filter that rejects .cortex paths at the watchfiles level."""
        from cortex.vault.watcher import VaultWatcher
        from cortex.graph.engine import GraphEngine

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        watcher = VaultWatcher(tmp_vault, graph)

        cortex_dir = tmp_vault / ".cortex"
        assert watcher._watch_filter(Change.modified, str(cortex_dir / "graph.json")) is False
        assert watcher._watch_filter(Change.modified, str(cortex_dir / "index.md")) is False
        assert watcher._watch_filter(Change.modified, str(cortex_dir / "log.md")) is False

        assert watcher._watch_filter(Change.modified, str(tmp_vault / "wiki" / "note.md")) is True
        assert watcher._watch_filter(Change.modified, str(tmp_vault / "agents" / "scout.md")) is True

    def test_watch_filter_rejects_non_markdown(self, tmp_vault: Path):
        """awatch filter should also reject non-.md files."""
        from cortex.vault.watcher import VaultWatcher
        from cortex.graph.engine import GraphEngine

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        watcher = VaultWatcher(tmp_vault, graph)

        assert watcher._watch_filter(Change.modified, str(tmp_vault / "wiki" / "image.png")) is False
        assert watcher._watch_filter(Change.modified, str(tmp_vault / ".DS_Store")) is False
        assert watcher._watch_filter(Change.modified, str(tmp_vault / "wiki" / "note.md")) is True
