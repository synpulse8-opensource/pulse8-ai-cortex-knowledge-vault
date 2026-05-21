"""Tests for the BulkIngestor class."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cortex.compiler.bulk import BulkIngestor


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Create a minimal vault for bulk ingest tests."""
    vault = tmp_path / "vault"
    for subdir in ["raw", "wiki", ".cortex"]:
        (vault / subdir).mkdir(parents=True)
    (vault / ".cortex" / "graph.json").write_text('{"nodes": [], "edges": []}')
    return vault


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Create a source directory with sample files."""
    src = tmp_path / "inbox"
    src.mkdir()
    (src / "paper1.txt").write_text("Content of paper 1")
    (src / "paper2.md").write_text("# Paper 2\n\nContent of paper 2")
    (src / "notes.txt").write_text("Some notes")
    return src


class TestScanSourceDir:
    """BulkIngestor.scan() discovers files in the source directory."""

    def test_scan_finds_all_files(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        files = ingestor.scan()
        assert len(files) == 3
        names = {f.name for f in files}
        assert names == {"paper1.txt", "paper2.md", "notes.txt"}

    def test_scan_ignores_subdirectories(self, tmp_vault: Path, source_dir: Path) -> None:
        (source_dir / "subdir").mkdir()
        (source_dir / "subdir" / "nested.txt").write_text("nested")
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        files = ingestor.scan()
        names = {f.name for f in files}
        assert "nested.txt" not in names

    def test_scan_returns_sorted(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        files = ingestor.scan()
        assert files == sorted(files)


class TestManifestDedup:
    """BulkIngestor uses SHA-256 manifest for deduplication."""

    def test_hash_file_returns_sha256(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        h = ingestor.hash_file(source_dir / "paper1.txt")
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64

    def test_same_content_same_hash(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        (source_dir / "copy.txt").write_text("Content of paper 1")
        assert ingestor.hash_file(source_dir / "paper1.txt") == ingestor.hash_file(source_dir / "copy.txt")

    def test_load_empty_manifest(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        manifest = ingestor.load_manifest()
        assert manifest == {}

    def test_save_and_load_manifest(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        data = {"raw/paper1.txt": "sha256:abc123"}
        ingestor.save_manifest(data)

        loaded = ingestor.load_manifest()
        assert loaded == data

    def test_manifest_path(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        assert ingestor.manifest_path == tmp_vault / ".cortex" / "ingest-manifest.json"


class TestCopyToRaw:
    """BulkIngestor.copy_new_files() copies files to raw/, skipping duplicates."""

    def test_copies_new_files(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        copied, skipped = ingestor.copy_new_files()
        assert len(copied) == 3
        assert len(skipped) == 0
        assert (tmp_vault / "raw" / "paper1.txt").exists()
        assert (tmp_vault / "raw" / "paper2.md").exists()
        assert (tmp_vault / "raw" / "notes.txt").exists()

    def test_skips_already_ingested(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        ingestor.copy_new_files()
        for raw_path in sorted((tmp_vault / "raw").iterdir()):
            ingestor.record_compiled_file(raw_path)

        copied, skipped = ingestor.copy_new_files()
        assert len(copied) == 0
        assert len(skipped) == 3

    def test_updates_manifest_after_compile(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        ingestor.copy_new_files()
        assert ingestor.load_manifest() == {}

        ingestor.record_compiled_file(tmp_vault / "raw" / "paper1.txt")
        manifest = ingestor.load_manifest()
        assert "raw/paper1.txt" in manifest
        assert manifest["raw/paper1.txt"] == ingestor.hash_file(tmp_vault / "raw" / "paper1.txt")

    def test_force_bypasses_manifest(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir, force=True)
        ingestor.copy_new_files()

        copied, skipped = ingestor.copy_new_files()
        assert len(copied) == 3
        assert len(skipped) == 0

    def test_dry_run_does_not_copy(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir, dry_run=True)
        copied, _skipped = ingestor.copy_new_files()
        assert len(copied) == 3
        assert not (tmp_vault / "raw" / "paper1.txt").exists()
        manifest = ingestor.load_manifest()
        assert manifest == {}


class TestCompileBatch:
    """BulkIngestor.compile_batch() compiles raw files with bounded concurrency."""

    async def test_compiles_all_files(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        ingestor.copy_new_files()
        raw_paths = list((tmp_vault / "raw").iterdir())

        mock_ingest = AsyncMock(side_effect=lambda p, **kw: [tmp_vault / "wiki" / f"{p.stem}.md"])
        mock_xref = AsyncMock()

        with patch("cortex.compiler.bulk.KnowledgeCompiler") as mock_cls:
            instance = mock_cls.return_value
            instance.ingest_source = mock_ingest
            instance.compile_cross_references = mock_xref

            created = await ingestor.compile_batch(raw_paths)

        assert mock_ingest.call_count == len(raw_paths)
        assert mock_xref.call_count == 1
        assert len(created) == len(raw_paths)

    async def test_empty_batch_returns_empty(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        created = await ingestor.compile_batch([])
        assert created == []

    async def test_compile_failure_does_not_abort_batch(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)
        ingestor.copy_new_files()
        raw_paths = sorted((tmp_vault / "raw").iterdir())

        call_count = 0

        async def _side_effect(p: Path, **_kw) -> list[Path]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM timeout")
            return [tmp_vault / "wiki" / f"{p.stem}.md"]

        with patch("cortex.compiler.bulk.KnowledgeCompiler") as mock_cls:
            instance = mock_cls.return_value
            instance.ingest_source = AsyncMock(side_effect=_side_effect)
            instance.compile_cross_references = AsyncMock()

            created = await ingestor.compile_batch(raw_paths)

        assert len(created) == len(raw_paths) - 1
        manifest = ingestor.load_manifest()
        assert len(manifest) == len(raw_paths) - 1
        assert f"raw/{raw_paths[0].name}" not in manifest

    async def test_respects_concurrency_limit(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir, concurrency=1)
        ingestor.copy_new_files()
        raw_paths = sorted((tmp_vault / "raw").iterdir())

        with patch("cortex.compiler.bulk.KnowledgeCompiler") as mock_cls:
            instance = mock_cls.return_value
            instance.ingest_source = AsyncMock(
                side_effect=lambda p, **kw: [tmp_vault / "wiki" / f"{p.stem}.md"]
            )
            instance.compile_cross_references = AsyncMock()

            created = await ingestor.compile_batch(raw_paths)

        assert len(created) == len(raw_paths)


class TestRunPipeline:
    """BulkIngestor.run() executes the full pipeline."""

    async def test_full_run(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)

        with patch("cortex.compiler.bulk.KnowledgeCompiler") as mock_cls:
            instance = mock_cls.return_value
            instance.ingest_source = AsyncMock(
                side_effect=lambda p, **kw: [tmp_vault / "wiki" / f"{p.stem}.md"]
            )
            instance.compile_cross_references = AsyncMock()

            result = await ingestor.run()

        assert result["dry_run"] is False
        assert len(result["copied"]) == 3
        assert len(result["skipped"]) == 0
        assert len(result["compiled"]) == 3

    async def test_dry_run_skips_compile_and_reindex(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir, dry_run=True)

        with patch("cortex.compiler.bulk.KnowledgeCompiler") as mock_cls:
            result = await ingestor.run()
            mock_cls.assert_not_called()

        assert result["dry_run"] is True
        assert len(result["copied"]) == 3
        assert result["compiled"] == []

    async def test_run_rebuilds_index(self, tmp_vault: Path, source_dir: Path) -> None:
        ingestor = BulkIngestor(vault_path=tmp_vault, source_dir=source_dir)

        with patch("cortex.compiler.bulk.KnowledgeCompiler") as mock_cls, \
             patch("cortex.compiler.bulk.rebuild_index", new_callable=AsyncMock) as mock_reindex:
            instance = mock_cls.return_value
            instance.ingest_source = AsyncMock(return_value=[])
            instance.compile_cross_references = AsyncMock()

            await ingestor.run()

        mock_reindex.assert_awaited_once_with(tmp_vault)
