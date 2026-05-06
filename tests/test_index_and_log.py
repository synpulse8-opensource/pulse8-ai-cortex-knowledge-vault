"""Tests for vault index and audit log."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestRebuildIndex:
    @pytest.mark.asyncio
    async def test_creates_index_file(self, tmp_vault: Path):
        from cortex.vault.index import rebuild_index

        await rebuild_index(tmp_vault)
        index_path = tmp_vault / ".cortex" / "index.md"
        assert index_path.exists()

    @pytest.mark.asyncio
    async def test_index_contains_note_count(self, tmp_vault: Path):
        from cortex.vault.index import rebuild_index

        await rebuild_index(tmp_vault)
        content = (tmp_vault / ".cortex" / "index.md").read_text()
        assert "notes total" in content

    @pytest.mark.asyncio
    async def test_index_has_wiki_section(self, tmp_vault: Path):
        from cortex.vault.index import rebuild_index

        await rebuild_index(tmp_vault)
        content = (tmp_vault / ".cortex" / "index.md").read_text()
        assert "## Wiki" in content

    @pytest.mark.asyncio
    async def test_index_has_agents_section(self, tmp_vault: Path):
        from cortex.vault.index import rebuild_index

        await rebuild_index(tmp_vault)
        content = (tmp_vault / ".cortex" / "index.md").read_text()
        assert "## Agents" in content

    @pytest.mark.asyncio
    async def test_index_lists_notes(self, tmp_vault: Path):
        from cortex.vault.index import rebuild_index

        await rebuild_index(tmp_vault)
        content = (tmp_vault / ".cortex" / "index.md").read_text()
        assert "Transformer Architecture" in content

    @pytest.mark.asyncio
    async def test_index_includes_tags(self, tmp_vault: Path):
        from cortex.vault.index import rebuild_index

        await rebuild_index(tmp_vault)
        content = (tmp_vault / ".cortex" / "index.md").read_text()
        assert "ml" in content


    @pytest.mark.asyncio
    async def test_accepts_prescanned_notes(self, tmp_vault: Path):
        from cortex.vault.index import rebuild_index
        from cortex.vault.reader import scan_vault

        notes = scan_vault(tmp_vault)
        await rebuild_index(tmp_vault, notes=notes)
        content = (tmp_vault / ".cortex" / "index.md").read_text()
        assert "Transformer Architecture" in content

    @pytest.mark.asyncio
    async def test_prescanned_matches_rescan(self, tmp_vault: Path):
        from cortex.vault.index import rebuild_index
        from cortex.vault.reader import scan_vault

        await rebuild_index(tmp_vault)
        from_rescan = (tmp_vault / ".cortex" / "index.md").read_text()

        notes = scan_vault(tmp_vault)
        await rebuild_index(tmp_vault, notes=notes)
        from_prescanned = (tmp_vault / ".cortex" / "index.md").read_text()

        assert from_rescan == from_prescanned


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_log_creates_file(self, tmp_vault: Path):
        from cortex.log.audit import log_operation

        await log_operation(tmp_vault, "claude", "vault:write", "Created test note")
        log_path = tmp_vault / ".cortex" / "log.md"
        assert log_path.exists()

    @pytest.mark.asyncio
    async def test_log_appends_entry(self, tmp_vault: Path):
        from cortex.log.audit import log_operation

        await log_operation(tmp_vault, "claude", "vault:write", "First operation")
        await log_operation(tmp_vault, "human", "vault:read", "Second operation")
        content = (tmp_vault / ".cortex" / "log.md").read_text()
        assert "First operation" in content
        assert "Second operation" in content

    @pytest.mark.asyncio
    async def test_log_contains_timestamp(self, tmp_vault: Path):
        from cortex.log.audit import log_operation

        await log_operation(tmp_vault, "test", "vault:search", "Test search")
        content = (tmp_vault / ".cortex" / "log.md").read_text()
        assert "202" in content  # year prefix

    @pytest.mark.asyncio
    async def test_log_contains_tool_and_consumer(self, tmp_vault: Path):
        from cortex.log.audit import log_operation

        await log_operation(tmp_vault, "copilot", "vault:context", "Context query")
        content = (tmp_vault / ".cortex" / "log.md").read_text()
        assert "vault:context" in content
        assert "copilot" in content

    @pytest.mark.asyncio
    async def test_log_creates_directory(self, tmp_path: Path):
        from cortex.log.audit import log_operation

        vault = tmp_path / "new-vault"
        vault.mkdir()
        await log_operation(vault, "test", "test", "test")
        assert (vault / ".cortex" / "log.md").exists()

    @pytest.mark.asyncio
    async def test_log_does_not_block_event_loop(self, tmp_vault: Path):
        """log_operation must offload file I/O so it never blocks the loop."""
        from unittest.mock import patch, AsyncMock
        from cortex.log.audit import log_operation

        with patch("cortex.log.audit.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = None
            await log_operation(tmp_vault, "test", "vault:search", "perf test")
            mock_thread.assert_awaited_once()
