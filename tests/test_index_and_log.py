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
