"""Tests for ingest manifest NFS resilience."""
from __future__ import annotations

import errno
from pathlib import Path
from unittest.mock import patch

import pytest

from cortex.compiler.ingest_manifest import (
    load_skip_manifest,
    record_skipped_file,
    skip_manifest_path,
)


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / ".cortex").mkdir(parents=True)
    return vault


class TestStaleFileHandleResilience:
    def test_load_skip_manifest_retries_stale_read(self, tmp_vault: Path) -> None:
        path = skip_manifest_path(tmp_vault)
        path.write_text(
            '{"raw/example.md": {"reason": "already compiled"}}',
            encoding="utf-8",
        )
        attempts = {"count": 0}
        real_read_text = Path.read_text

        def flaky_read_text(self: Path, encoding: str | None = None) -> str:
            if self == path and attempts["count"] == 0:
                attempts["count"] += 1
                raise OSError(errno.ESTALE, "Stale file handle")
            return real_read_text(self, encoding=encoding)

        with patch.object(Path, "read_text", flaky_read_text):
            data = load_skip_manifest(tmp_vault)

        assert data["raw/example.md"]["reason"] == "already compiled"
        assert attempts["count"] == 1

    def test_load_skip_manifest_returns_empty_after_exhausted_retries(
        self, tmp_vault: Path
    ) -> None:
        path = skip_manifest_path(tmp_vault)
        path.write_text("{}", encoding="utf-8")

        def always_stale(self: Path, encoding: str | None = None) -> str:
            if self == path:
                raise OSError(errno.ESTALE, "Stale file handle")
            return Path.read_text(self, encoding=encoding)

        with patch.object(Path, "read_text", always_stale):
            assert load_skip_manifest(tmp_vault) == {}

    def test_record_skipped_file_survives_stale_read(self, tmp_vault: Path) -> None:
        path = skip_manifest_path(tmp_vault)
        path.write_text("{}", encoding="utf-8")
        raw_path = tmp_vault / "raw2" / "Knowledge vault" / "file.md"
        raw_path.parent.mkdir(parents=True)
        raw_path.write_text("body", encoding="utf-8")
        attempts = {"count": 0}
        real_read_text = Path.read_text

        def flaky_read_text(self: Path, encoding: str | None = None) -> str:
            if self == path and attempts["count"] == 0:
                attempts["count"] += 1
                raise OSError(116, "Stale file handle")
            return real_read_text(self, encoding=encoding)

        with patch.object(Path, "read_text", flaky_read_text):
            record_skipped_file(tmp_vault, raw_path, "already compiled")

        saved = load_skip_manifest(tmp_vault)
        rel = "raw2/Knowledge vault/file.md"
        assert saved[rel]["reason"] == "already compiled"
