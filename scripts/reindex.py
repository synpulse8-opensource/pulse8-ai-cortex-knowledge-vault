"""Rebuild graph and QMD index from scratch."""
from __future__ import annotations

import asyncio
import logging

from cortex.config import settings
from cortex.graph.builder import build_graph
from cortex.search.qmd import QMDSearch
from cortex.vault.index import rebuild_index
from cortex.vault.reader import scan_vault

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    vault_path = settings.vault_path
    notes = scan_vault(vault_path)
    logger.info("Found %d notes", len(notes))

    graph = await build_graph(notes, vault_path / ".cortex" / "graph.json", vault_path)
    stats = await graph.get_stats()
    logger.info(
        "Graph: %d nodes, %d edges, %d orphans",
        stats["total_nodes"],
        stats["total_edges"],
        stats["orphans"],
    )

    try:
        qmd = QMDSearch(vault_path, settings.qmd_bin)
        await qmd.initialize()
        logger.info("QMD index updated")
    except Exception:
        logger.warning("QMD initialization failed — skipping search index")

    await rebuild_index(vault_path)
    logger.info("Vault index rebuilt")


if __name__ == "__main__":
    asyncio.run(main())
