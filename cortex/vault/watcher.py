"""Filesystem watcher — keeps graph and index in sync on vault changes."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from watchfiles import Change, awatch

from cortex.graph.engine import GraphEngine
from cortex.vault.index import rebuild_index
from cortex.vault.models import Edge, EdgeType
from cortex.vault.reader import read_note, resolve_wikilink

logger = logging.getLogger(__name__)


class VaultWatcher:
    """Watch vault filesystem for changes and keep graph/index in sync."""

    def __init__(self, vault_root: Path, graph: GraphEngine) -> None:
        self.vault_root = vault_root.resolve()
        self.graph = graph
        self._task: asyncio.Task | None = None
        self._cortex_dir = str(self.vault_root / ".cortex")

    def _watch_filter(self, _change: Change, path: str) -> bool:
        """Filter for watchfiles: only accept .md files outside .cortex/."""
        if path.startswith(self._cortex_dir):
            return False
        return path.endswith(".md")

    async def start(self) -> None:
        """Start watching the vault directory."""
        self._task = asyncio.create_task(self._watch())
        logger.info("Vault watcher started for %s", self.vault_root)

    async def stop(self) -> None:
        """Stop the watcher task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Vault watcher stopped")

    async def _watch(self) -> None:
        """Main watch loop using watchfiles."""
        try:
            async for changes in awatch(self.vault_root, watch_filter=self._watch_filter):
                for change_type, path_str in changes:
                    path = Path(path_str)
                    rel = path.relative_to(self.vault_root)

                    if change_type in (Change.added, Change.modified):
                        await self._handle_change(path)
                    elif change_type == Change.deleted:
                        await self._handle_delete(str(rel))

                await rebuild_index(self.vault_root)
        except Exception:
            logger.exception("Watcher error")

    async def _handle_change(self, path: Path) -> None:
        """Handle a new or modified .md file."""
        rel = path.relative_to(self.vault_root)
        if rel.parts[0] == ".cortex":
            return

        try:
            note = read_note(path, self.vault_root)
            await self.graph.add_note_node(note)

            for link in note.wikilinks:
                resolved = resolve_wikilink(link, self.vault_root)
                if resolved:
                    await self.graph.add_edge(
                        Edge(
                            source=note.path,
                            target=resolved,
                            edge_type=EdgeType.LINKS_TO,
                        )
                    )

            for tag in note.tags:
                tag_id = f"tag:{tag}"
                if not self.graph.graph.has_node(tag_id):
                    self.graph.graph.add_node(tag_id, node_type="tag", title=tag)
                await self.graph.add_edge(
                    Edge(
                        source=note.path,
                        target=tag_id,
                        edge_type=EdgeType.TAGGED_WITH,
                    )
                )

            logger.info("Updated graph for %s", note.path)
        except Exception:
            logger.exception("Error handling change for %s", path)

    async def _handle_delete(self, rel_path: str) -> None:
        """Handle a deleted .md file."""
        await self.graph.remove_note_node(rel_path)
        logger.info("Removed %s from graph", rel_path)
