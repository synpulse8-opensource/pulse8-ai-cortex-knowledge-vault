"""Bulk ingestor: scan source dir, dedup via SHA-256 manifest, copy to raw/, batch compile."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

from cortex.compiler.bulk_coordination import (
    LockMode,
    LockScope,
    bulk_ingest_session,
    normalize_source_dir,
    vault_reindex_session,
)
from cortex.compiler.compiler import KnowledgeCompiler
from cortex.compiler import ingest_manifest
from cortex.vault.layout import raw_dir, raw_dir_name, vault_rel, wiki_dest_for_raw, wiki_dir
from cortex.vault.index import rebuild_index

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = ingest_manifest.MANIFEST_FILENAME
MANIFEST_SKIP_FILENAME = ingest_manifest.MANIFEST_SKIP_FILENAME


class BulkIngestor:
    """Ingest files from a local directory into the vault in bulk.

    Scans a source directory, copies new files to the configured raw dir, compiles them with
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
        prune: bool = True,
    ) -> None:
        self.vault_path = vault_path.resolve()
        self.source_dir = normalize_source_dir(source_dir)
        self.concurrency = concurrency
        self.force = force
        self.dry_run = dry_run
        self.prune = prune

    @property
    def manifest_path(self) -> Path:
        return ingest_manifest.manifest_path(self.vault_path)

    @property
    def skip_manifest_path(self) -> Path:
        return ingest_manifest.skip_manifest_path(self.vault_path)

    def scan(self) -> list[Path]:
        """Return sorted list of all files under the source directory (recursive)."""
        return sorted(
            p for p in self.source_dir.rglob("*") if p.is_file()
        )

    def raw_dest_for(self, src_file: Path) -> Path:
        """Map a source file to its destination path under the vault raw directory.

        When ``source_dir`` is already inside ``raw/`` (e.g. ingesting a subtree in
        place), preserve the full path under raw so wiki notes mirror the same tree.
        External inboxes still map as ``raw/<path relative to source_dir>``.
        """
        src = src_file.resolve()
        raw_root = raw_dir(self.vault_path).resolve()
        try:
            src.relative_to(raw_root)
        except ValueError:
            rel = src.relative_to(self.source_dir.resolve())
            return raw_root / rel
        return src

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

    def _prune_scope_prefix(self) -> str:
        """Vault-relative raw prefix owned by this source directory."""
        raw_root = raw_dir(self.vault_path).resolve()
        base = raw_dir_name()
        try:
            rel = self.source_dir.relative_to(raw_root)
            if rel == Path("."):
                return f"{base}/"
            return f"{base}/{rel.as_posix()}/"
        except ValueError:
            return f"{base}/"

    def _present_raw_rels(self) -> set[str]:
        return {vault_rel(self.vault_path, self.raw_dest_for(path)) for path in self.scan()}

    def _remove_empty_parents(self, path: Path, stop: Path) -> None:
        parent = path.parent
        while parent != stop and parent.is_dir():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def prune_removed_files(self) -> list[str]:
        """Remove raw/wiki files tracked in manifests whose sources are gone.

        Returns vault-relative paths removed (raw and wiki).
        """
        if not self.prune:
            return []

        present = self._present_raw_rels()
        scope_prefix = self._prune_scope_prefix()
        manifest = self.load_manifest()
        skip_manifest = self.load_skip_manifest()
        tracked = set(manifest) | set(skip_manifest)

        removed: list[str] = []
        for raw_rel in sorted(tracked):
            if not raw_rel.startswith(scope_prefix):
                continue
            if raw_rel in present:
                continue

            raw_path = self.vault_path / raw_rel
            wiki_path = wiki_dest_for_raw(self.vault_path, raw_path)
            wiki_rel = vault_rel(self.vault_path, wiki_path)

            if self.dry_run:
                removed.append(raw_rel)
                if wiki_path.exists():
                    removed.append(wiki_rel)
                continue

            if wiki_path.exists():
                wiki_path.unlink()
                self._remove_empty_parents(wiki_path, wiki_dir(self.vault_path))

            if raw_path.exists():
                raw_path.unlink()
                self._remove_empty_parents(raw_path, raw_dir(self.vault_path))

            removed.append(raw_rel)
            if wiki_rel not in removed:
                removed.append(wiki_rel)

            ingest_manifest.remove_manifest_entries(self.vault_path, raw_rel)
            logger.info("Pruned removed source %s", raw_rel)

        return removed

    def copy_new_files(self) -> tuple[list[Path], list[Path]]:
        """Copy new source files to ``raw/``, skipping files already compiled.

        Dedup uses the ingest manifest, which records hashes only after a
        successful compile. Copying alone does not update the manifest.

        Returns (copied, skipped) lists of vault raw destination paths.
        """
        files = self.scan()
        copied: list[Path] = []
        skipped: list[Path] = []

        for src_file in files:
            dest = self.raw_dest_for(src_file)
            file_hash = self.hash_file(src_file)
            known_hashes = ingest_manifest.known_content_hashes(self.vault_path)

            if not self.force and file_hash in known_hashes:
                skipped.append(dest)
                logger.info(
                    "Skipping (already compiled): %s",
                    vault_rel(self.vault_path, dest),
                )
                if not self.dry_run:
                    self.record_skipped_file(
                        dest,
                        "already compiled",
                        file_hash=file_hash,
                    )
                continue

            copied.append(dest)
            if not self.dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src_file.resolve() != dest.resolve():
                    shutil.copy2(src_file, dest)
                    logger.info(
                        "Copied: %s -> %s",
                        src_file.relative_to(self.source_dir),
                        vault_rel(self.vault_path, dest),
                    )
                else:
                    logger.info(
                        "Already in %s: %s",
                        raw_dir_name(),
                        dest.relative_to(raw_dir(self.vault_path)),
                    )

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
            wait_start = time.perf_counter()
            async with semaphore:
                acquire_start = time.perf_counter()
                try:
                    file_size = raw_path.stat().st_size
                except OSError:
                    file_size = -1
                logger.info(
                    "[%d/%d] Compiling %s (size=%d bytes, sem_wait=%.3fs)...",
                    idx + 1,
                    total,
                    vault_rel(self.vault_path, raw_path),
                    file_size,
                    acquire_start - wait_start,
                )
                try:
                    ingest_start = time.perf_counter()
                    created = await compiler.ingest_source(raw_path, force=self.force)
                    ingest_elapsed = time.perf_counter() - ingest_start
                except Exception as exc:
                    logger.exception("Failed to compile %s", raw_path.name)
                    async with manifest_lock:
                        self.record_skipped_file(raw_path, f"compile failed: {exc}")
                    return []
                logger.info(
                    "[%d/%d] ingest_source %s took %.3fs (size=%d bytes)",
                    idx + 1,
                    total,
                    vault_rel(self.vault_path, raw_path),
                    ingest_elapsed,
                    file_size,
                )
                if not created:
                    return []
                manifest_start = time.perf_counter()
                async with manifest_lock:
                    self.record_compiled_file(raw_path)
                logger.info(
                    "[%d/%d] record_compiled_file %s took %.3fs",
                    idx + 1,
                    total,
                    vault_rel(self.vault_path, raw_path),
                    time.perf_counter() - manifest_start,
                )
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
        async with vault_reindex_session(self.vault_path):
            await rebuild_index(self.vault_path)
        logger.info("Vault index rebuilt")

    async def run(
        self,
        *,
        lock_mode: LockMode = "wait",
        lock_scope: LockScope = "source",
    ) -> dict:
        """Execute the full bulk ingest pipeline.

        With ``lock_scope='source'`` (default), different ``source_dir`` values may
        run concurrently on the same vault. ``lock_mode='fail'`` rejects a second
        job for the *same* ``source_dir`` while one is active.

        Returns a summary dict with counts and paths.
        """
        async with bulk_ingest_session(
            self.vault_path,
            self.source_dir,
            lock_mode=lock_mode,
            lock_scope=lock_scope,
        ):
            logger.info("Scanning source directory: %s", self.source_dir)
            removed = self.prune_removed_files()
            if removed:
                logger.info("Pruned %d vault paths for removed sources", len(removed))

            copied, skipped = self.copy_new_files()
            logger.info("Copied %d files, skipped %d duplicates", len(copied), len(skipped))

            if self.dry_run:
                return {
                    "copied": [vault_rel(self.vault_path, p) for p in copied],
                    "skipped": [vault_rel(self.vault_path, p) for p in skipped],
                    "compiled": [],
                    "removed": removed,
                    "dry_run": True,
                }

            created = await self.compile_batch(copied)
            await self.reindex()

            return {
                "copied": [vault_rel(self.vault_path, p) for p in copied],
                "skipped": [vault_rel(self.vault_path, p) for p in skipped],
                "compiled": [str(p.relative_to(self.vault_path)) for p in created],
                "removed": removed,
                "dry_run": False,
            }
