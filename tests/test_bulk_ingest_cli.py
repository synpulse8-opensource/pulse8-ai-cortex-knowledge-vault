"""Tests for the cortex-bulk-ingest CLI entry point."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from scripts.bulk_ingest import build_parser, run_cli


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for subdir in ["raw", "wiki", ".cortex"]:
        (vault / subdir).mkdir(parents=True)
    (vault / ".cortex" / "graph.json").write_text('{"nodes": [], "edges": []}')
    return vault


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    src = tmp_path / "inbox"
    src.mkdir()
    (src / "paper.txt").write_text("Content")
    return src


class TestBuildParser:
    """CLI argument parsing."""

    def test_source_required(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_source_parsed(self, source_dir: Path) -> None:
        parser = build_parser()
        args = parser.parse_args(["--source", str(source_dir)])
        assert args.source == str(source_dir)

    def test_defaults(self, source_dir: Path) -> None:
        parser = build_parser()
        args = parser.parse_args(["--source", str(source_dir)])
        assert args.concurrency == 4
        assert args.force is False
        assert args.dry_run is False

    def test_all_flags(self, source_dir: Path) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "--source", str(source_dir),
            "--concurrency", "8",
            "--force",
            "--dry-run",
        ])
        assert args.concurrency == 8
        assert args.force is True
        assert args.dry_run is True


class TestRunCli:
    """run_cli() wires argparse to BulkIngestor.run()."""

    async def test_run_cli_creates_ingestor_and_runs(
        self, tmp_vault: Path, source_dir: Path
    ) -> None:
        mock_result = {
            "copied": ["paper.txt"],
            "skipped": [],
            "compiled": ["wiki/paper.md"],
            "dry_run": False,
        }

        with patch("scripts.bulk_ingest.BulkIngestor") as mock_cls:
            instance = mock_cls.return_value
            instance.run = AsyncMock(return_value=mock_result)

            await run_cli([
                "--source", str(source_dir),
                "--concurrency", "2",
            ], vault_path=tmp_vault)

            mock_cls.assert_called_once_with(
                vault_path=tmp_vault,
                source_dir=source_dir,
                concurrency=2,
                force=False,
                dry_run=False,
            )
            instance.run.assert_awaited_once()

    async def test_run_cli_passes_force_and_dry_run(
        self, tmp_vault: Path, source_dir: Path
    ) -> None:
        with patch("scripts.bulk_ingest.BulkIngestor") as mock_cls:
            instance = mock_cls.return_value
            instance.run = AsyncMock(return_value={"copied": [], "skipped": [], "compiled": [], "dry_run": True})

            await run_cli([
                "--source", str(source_dir),
                "--force",
                "--dry-run",
            ], vault_path=tmp_vault)

            mock_cls.assert_called_once_with(
                vault_path=tmp_vault,
                source_dir=source_dir,
                concurrency=4,
                force=True,
                dry_run=True,
            )

    async def test_run_cli_validates_source_dir(self, tmp_vault: Path) -> None:
        with pytest.raises(SystemExit):
            await run_cli(["--source", "/nonexistent/path"], vault_path=tmp_vault)
