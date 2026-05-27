"""Bulk ingestor: scan source dir, dedup via SHA-256 manifest, copy to raw/, batch compile."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from cortex.compiler.compiler import KnowledgeCompiler
from cortex.compiler import ingest_manifest
from cortex.vault.index import rebuild_index

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = ingest_manifest.MANIFEST_FILENAME
MANIFEST_SKIP_FILENAME = ingest_manifest.MANIFEST_SKIP_FILENAME


class BulkIngestor:
    """Ingest files from a local directory into the vault in bulk.

    Scans a source directory, copies new files to ``raw/``, compiles them with
    bounded concurrency, then rebuilds the index once. The SHA-256 manifest
    in ``.cortex/ingest-manifest.json`` records successfully compiled raw
    files immediately after each compile so progress survives interruption.
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
        return ingest_manifest.manifest_path(self.vault_path)

    @property
    def skip_manifest_path(self) -> Path:
        return ingest_manifest.skip_manifest_path(self.vault_path)

    def scan(self) -> list[Path]:
        """Return sorted list of files in the source directory (non-recursive)."""
        return sorted(f for f in self.source_dir.iterdir() if f.is_file())

    def hash_file(self, path: Path) -> str:
        """Compute SHA-256 hash of a file, returned as ``sha256:<hex>``."""
        return ingest_manifest.hash_file(path)

    def load_manifest(self) -> dict[str, str]:
        """Load the ingest manifest from disk, returning ``{}`` if missing."""
        return ingest_manifest.load_manifest(self.vault_path)

    def save_manifest(self, manifest: dict[str, str]) -> None:
        """Persist the ingest manifest to disk."""
        ingest_manifest.save_manifest(self.vault_path, manifest)

    def load_skip_manifest(self) -> dict[str, dict[str, str]]:
        """Load the skip/failure manifest from disk, returning ``{}`` if missing."""
        return ingest_manifest.load_skip_manifest(self.vault_path)

    def save_skip_manifest(self, skip_manifest: dict[str, dict[str, str]]) -> None:
        """Persist the skip/failure manifest to disk."""
        ingest_manifest.save_skip_manifest(self.vault_path, skip_manifest)

    def copy_new_files(self) -> tuple[list[Path], list[Path]]:
        """Copy new source files to ``raw/``, skipping files already compiled.

        Dedup uses the ingest manifest, which records hashes only after a
        successful compile. Copying alone does not update the manifest.

        Returns (copied, skipped) lists of source paths.
        """
        files = self.scan()
        manifest = self.load_manifest()
        known_hashes = set[str](manifest.values())

        copied: list[Path] = []
        skipped: list[Path] = []

        for src_file in files:
            file_hash = self.hash_file(src_file)

            if not self.force and file_hash in known_hashes:
                skipped.append(src_file)
                logger.info("Skipping (already compiled): %s", src_file.name)
                if not self.dry_run:
                    self.record_skipped_file(
                        src_file,
                        "already compiled",
                        file_hash=file_hash,
                    )
                continue

            copied.append(src_file)
            if not self.dry_run:
                dest = self.vault_path / "raw" / src_file.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src_file.resolve() != dest.resolve():
                    shutil.copy2(src_file, dest)
                    logger.info("Copied: %s -> raw/%s", src_file.name, src_file.name)
                else:
                    logger.info("Already in raw/: %s", src_file.name)

        return copied, skipped

    def record_compiled_file(self, raw_path: Path) -> None:
        """Record one successfully compiled raw file in the ingest manifest."""
        ingest_manifest.record_compiled_file(self.vault_path, raw_path)

    def record_skipped_file(
        self,
        path: Path,
        reason: str,
        *,
        file_hash: str | None = None,
    ) -> None:
        """Record one skipped or compile-failed file in the skip manifest."""
        ingest_manifest.record_skipped_file(
            self.vault_path,
            path,
            reason,
            file_hash=file_hash,
        )

    async def compile_batch(self, raw_paths: list[Path]) -> list[Path]:
        """Compile a batch of raw files with bounded concurrency.

        Returns the list of created wiki paths.
        """
        if not raw_paths:
            return []

        compiler = KnowledgeCompiler(self.vault_path)
        semaphore = asyncio.Semaphore(self.concurrency)
        manifest_lock = asyncio.Lock()
        all_created: list[Path] = []
        total = len(raw_paths)

        async def _compile_one(idx: int, raw_path: Path) -> list[Path]:
            async with semaphore:
                logger.info("[%d/%d] Compiling %s...", idx + 1, total, raw_path.name)
                try:
                    created = await compiler.ingest_source(raw_path, force=self.force)
                except Exception as exc:
                    logger.exception("Failed to compile %s", raw_path.name)
                    async with manifest_lock:
                        self.record_skipped_file(raw_path, f"compile failed: {exc}")
                    return []
                if not created:
                    return []
                async with manifest_lock:
                    self.record_compiled_file(raw_path)
                return created

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
