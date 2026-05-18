"""Bulk ingestor: scan source dir, dedup via SHA-256 manifest, copy to raw/, batch compile."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
from pathlib import Path

from cortex.compiler.compiler import KnowledgeCompiler
from cortex.vault.index import rebuild_index

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "ingest-manifest.json"


class BulkIngestor:
    """Ingest files from a local directory into the vault in bulk.

    Scans a source directory, deduplicates via a SHA-256 manifest stored
    in ``.cortex/ingest-manifest.json``, copies new files to ``raw/``,
    compiles them with bounded concurrency, then rebuilds the index once.
    """

    def __init__(
        self,
        vault_path: Path,
        source_dir: Path,
        concurrency: int = 4,
        force: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.vault_path = vault_path
        self.source_dir = source_dir
        self.concurrency = concurrency
        self.force = force
        self.dry_run = dry_run

    @property
    def manifest_path(self) -> Path:
        return self.vault_path / ".cortex" / MANIFEST_FILENAME

    def scan(self) -> list[Path]:
        """Return sorted list of files in the source directory (non-recursive)."""
        return sorted(f for f in self.source_dir.iterdir() if f.is_file())

    def hash_file(self, path: Path) -> str:
        """Compute SHA-256 hash of a file, returned as ``sha256:<hex>``."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"

    def load_manifest(self) -> dict[str, str]:
        """Load the ingest manifest from disk, returning ``{}`` if missing."""
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text())

    def save_manifest(self, manifest: dict[str, str]) -> None:
        """Persist the ingest manifest to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2))

    def copy_new_files(self) -> tuple[list[Path], list[Path]]:
        """Copy new source files to ``raw/``, skipping duplicates via manifest.

        Returns (copied, skipped) lists of source paths.
        """
        files = self.scan()
        manifest = self.load_manifest()
        known_hashes = set(manifest.values())

        copied: list[Path] = []
        skipped: list[Path] = []

        for src_file in files:
            file_hash = self.hash_file(src_file)
            raw_rel = f"raw/{src_file.name}"

            if not self.force and file_hash in known_hashes:
                skipped.append(src_file)
                logger.info("Skipping (duplicate): %s", src_file.name)
                continue

            copied.append(src_file)
            if not self.dry_run:
                dest = self.vault_path / "raw" / src_file.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src_file.resolve() != dest.resolve():
                    shutil.copy2(src_file, dest)
                    logger.info("Copied: %s -> %s", src_file.name, raw_rel)
                else:
                    logger.info("Already in raw/: %s", src_file.name)
                manifest[raw_rel] = file_hash

        if not self.dry_run:
            self.save_manifest(manifest)

        return copied, skipped

    async def compile_batch(self, raw_paths: list[Path]) -> list[Path]:
        """Compile a batch of raw files with bounded concurrency.

        Returns the list of created wiki paths.
        """
        if not raw_paths:
            return []

        compiler = KnowledgeCompiler(self.vault_path)
        semaphore = asyncio.Semaphore(self.concurrency)
        all_created: list[Path] = []
        total = len(raw_paths)

        async def _compile_one(idx: int, raw_path: Path) -> list[Path]:
            async with semaphore:
                logger.info("[%d/%d] Compiling %s...", idx + 1, total, raw_path.name)
                try:
                    return await compiler.ingest_source(raw_path)
                except Exception:
                    logger.exception("Failed to compile %s", raw_path.name)
                    return []

        tasks = [_compile_one(i, p) for i, p in enumerate(raw_paths)]
        results = await asyncio.gather(*tasks)
        for created in results:
            all_created.extend(created)

        if all_created:
            await compiler.compile_cross_references(all_created)

        return all_created

    async def reindex(self) -> None:
        """Rebuild vault index after bulk operations."""
        await rebuild_index(self.vault_path)
        logger.info("Vault index rebuilt")

    async def run(self) -> dict:
        """Execute the full bulk ingest pipeline.

        Returns a summary dict with counts and paths.
        """
        logger.info("Scanning source directory: %s", self.source_dir)
        copied, skipped = self.copy_new_files()
        logger.info("Copied %d files, skipped %d duplicates", len(copied), len(skipped))

        if self.dry_run:
            return {
                "copied": [f.name for f in copied],
                "skipped": [f.name for f in skipped],
                "compiled": [],
                "dry_run": True,
            }

        raw_paths = [self.vault_path / "raw" / f.name for f in copied]
        created = await self.compile_batch(raw_paths)
        await self.reindex()

        return {
            "copied": [f.name for f in copied],
            "skipped": [f.name for f in skipped],
            "compiled": [str(p.relative_to(self.vault_path)) for p in created],
            "dry_run": False,
        }
