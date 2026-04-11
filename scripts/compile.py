"""Compile unprocessed raw sources into wiki articles."""
from __future__ import annotations

import asyncio
import logging

from cortex.compiler.compiler import KnowledgeCompiler
from cortex.config import settings
from cortex.vault.reader import scan_vault

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    vault_path = settings.vault_path
    compiler = KnowledgeCompiler(vault_path)

    existing_sources: set[str] = set()
    for note in scan_vault(vault_path):
        sp = note.frontmatter.get("source_path")
        if sp:
            existing_sources.add(sp)

    raw_dir = vault_path / "raw"
    if not raw_dir.exists():
        logger.info("No raw/ directory found")
        return

    unprocessed = []
    for raw_file in sorted(raw_dir.iterdir()):
        if raw_file.is_dir():
            continue
        rel = str(raw_file.relative_to(vault_path))
        if rel not in existing_sources:
            unprocessed.append(raw_file)

    if not unprocessed:
        logger.info("All raw sources already compiled")
        return

    logger.info("Found %d unprocessed sources", len(unprocessed))

    for source in unprocessed:
        logger.info("Compiling: %s", source.name)
        try:
            created = await compiler.ingest_source(source)
            for path in created:
                logger.info("  Created: %s", path.relative_to(vault_path))
        except Exception:
            logger.exception("Failed to compile %s", source.name)

    from cortex.vault.index import rebuild_index

    await rebuild_index(vault_path)
    logger.info("Vault index rebuilt")


if __name__ == "__main__":
    asyncio.run(main())
