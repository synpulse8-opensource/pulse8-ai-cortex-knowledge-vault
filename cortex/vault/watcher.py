"""Filesystem watcher — keeps graph and index in sync on vault changes."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from watchfiles import Change, awatch

from cortex.graph.engine import GraphEngine
from cortex.vault.layout import raw_dir, watcher_skip_top_dirs
from cortex.vault.index import rebuild_index
from cortex.vault.models import Edge, EdgeType
from cortex.vault.reader import read_note, resolve_wikilink

logger = logging.getLogger(__name__)


class VaultWatcher:
    """Watch vault filesystem for changes and keep graph/index in sync."""

    # POSIX NAME_MAX is commonly 255 bytes for a single path component.
    # We stay below that to avoid OSError: [Errno 36] File name too long
    # when resolving wikilinks by trying candidate filenames like "{link}.md".
    _MAX_WIKILINK_FILENAME_BYTES = 240

    def __init__(self, vault_root: Path, graph: GraphEngine) -> None:
        self.vault_root = vault_root.resolve()
        self.graph = graph
        self._task: asyncio.Task | None = None
        self._cortex_dir = str(self.vault_root / ".cortex")
        self._raw_dir = str(raw_dir(self.vault_root))
        self._skip_top_dirs = watcher_skip_top_dirs()

    def _watch_filter(self, _change: Change, path: str) -> bool:
        """Filter for watchfiles: only accept .md files outside .cortex/ and raw/."""
        if path.startswith(self._cortex_dir):
            return False
        if path.startswith(self._raw_dir):
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
                async with self.graph.batch():
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
        if rel.parts[0] in self._skip_top_dirs:
            return

        try:
            rel_path = str(rel)
            if self.graph.graph.has_node(rel_path):
                await self.graph.remove_note_node(rel_path)

            note = read_note(path, self.vault_root)
            await self.graph.add_note_node(note)

            for link in note.wikilinks:
                if len(f"{link}.md".encode("utf-8")) > self._MAX_WIKILINK_FILENAME_BYTES:
                    logger.debug(
                        "Skipping wikilink resolution (filename too long): %s (%d bytes)",
                        link,
                        len(f"{link}.md".encode("utf-8")),
                    )
                    continue
                try:
                    resolved = resolve_wikilink(link, self.vault_root)
                except OSError:
                    logger.exception("Skipping wikilink resolution due to OS error: %s", link)
                    continue
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
