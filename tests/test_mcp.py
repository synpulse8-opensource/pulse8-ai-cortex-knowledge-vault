"""Tests for MCP stdio server tools."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
async def mcp_services(tmp_vault: Path):
    """Set up all MCP service dependencies."""
    from cortex.graph.builder import build_graph
    from cortex.vault.reader import scan_vault
    from cortex.search.qmd import QMDSearch
    from cortex.compiler.compiler import KnowledgeCompiler

    notes = scan_vault(tmp_vault)
    graph = await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)

    qmd = QMDSearch(tmp_vault, "qmd")
    qmd.update = AsyncMock()

    compiler = KnowledgeCompiler(tmp_vault)

    return {
        "vault_path": tmp_vault,
        "graph": graph,
        "qmd": qmd,
        "compiler": compiler,
    }


class TestVaultReadTool:
    @pytest.mark.asyncio
    async def test_read_existing_note(self, mcp_services):
        from cortex.mcp.tools import handle_vault_read

        result = await handle_vault_read(
            path="wiki/transformers.md",
            **mcp_services,
        )
        assert result["title"] == "Transformer Architecture"
        assert "content" in result
        assert "frontmatter" in result

    @pytest.mark.asyncio
    async def test_read_nonexistent_returns_error(self, mcp_services):
        from cortex.mcp.tools import handle_vault_read

        result = await handle_vault_read(
            path="wiki/nonexistent.md",
            **mcp_services,
        )
        assert "error" in result


class TestVaultWriteTool:
    @pytest.mark.asyncio
    async def test_write_creates_note(self, mcp_services):
        from cortex.mcp.tools import handle_vault_write

        result = await handle_vault_write(
            path="wiki/new-mcp-note.md",
            content="# MCP Created\n\nContent via MCP.",
            frontmatter={"tags": ["mcp", "test"]},
            **mcp_services,
        )
        assert result["path"] == "wiki/new-mcp-note.md"
        vault_path = mcp_services["vault_path"]
        assert (vault_path / "wiki" / "new-mcp-note.md").exists()

    @pytest.mark.asyncio
    async def test_write_updates_graph(self, mcp_services):
        from cortex.mcp.tools import handle_vault_write

        await handle_vault_write(
            path="wiki/graph-test.md",
            content="# Graph Test\n\nLinks to [[transformers]].",
            **mcp_services,
        )
        graph = mcp_services["graph"]
        assert graph.graph.has_node("wiki/graph-test.md")

    @pytest.mark.asyncio
    async def test_write_refreshes_qmd_index(self, mcp_services):
        from cortex.mcp.tools import handle_vault_write

        with patch.object(mcp_services["qmd"], "update", new_callable=AsyncMock) as mock_update:
            await handle_vault_write(
                path="wiki/qmd-refresh-test.md",
                content="# QMD Refresh\n\nShould trigger index update.",
                **mcp_services,
            )
            mock_update.assert_awaited_once()


class TestVaultSearchTool:
    @pytest.mark.asyncio
    async def test_search_delegates_to_qmd(self, mcp_services):
        from cortex.mcp.tools import handle_vault_search

        mock_results = [
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer"},
        ]

        with patch.object(mcp_services["qmd"], "search", new_callable=AsyncMock, return_value=mock_results):
            result = await handle_vault_search(
                query="transformer",
                **mcp_services,
            )
            assert len(result["results"]) == 1
            assert result["results"][0]["path"] == "wiki/transformers.md"


class TestVaultLinkTool:
    @pytest.mark.asyncio
    async def test_create_link(self, mcp_services):
        from cortex.mcp.tools import handle_vault_link

        result = await handle_vault_link(
            action="create",
            source="wiki/transformers.md",
            target="wiki/attention-mechanisms.md",
            edge_type="contradicts",
            **mcp_services,
        )
        assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_query_links(self, mcp_services):
        from cortex.mcp.tools import handle_vault_link

        result = await handle_vault_link(
            action="query",
            source="wiki/transformers.md",
            **mcp_services,
        )
        assert "edges" in result

    @pytest.mark.asyncio
    async def test_delete_link(self, mcp_services):
        from cortex.mcp.tools import handle_vault_link

        await handle_vault_link(
            action="create",
            source="wiki/transformers.md",
            target="wiki/attention-mechanisms.md",
            edge_type="contradicts",
            **mcp_services,
        )
        result = await handle_vault_link(
            action="delete",
            source="wiki/transformers.md",
            target="wiki/attention-mechanisms.md",
            edge_type="contradicts",
            **mcp_services,
        )
        assert result["status"] == "deleted"


class TestVaultIngestTool:
    @pytest.mark.asyncio
    async def test_ingest_writes_to_raw(self, mcp_services):
        from cortex.mcp.tools import handle_vault_ingest

        result = await handle_vault_ingest(
            content="Some raw content to ingest.",
            filename="test-ingest.txt",
            source_type="text",
            auto_compile=False,
            **mcp_services,
        )
        vault_path = mcp_services["vault_path"]
        assert (vault_path / "raw" / "test-ingest.txt").exists()
        assert result["path"] == "raw/test-ingest.txt"

    @pytest.mark.asyncio
    async def test_ingest_refreshes_qmd_index(self, mcp_services):
        from cortex.mcp.tools import handle_vault_ingest

        with patch.object(mcp_services["qmd"], "update", new_callable=AsyncMock) as mock_update:
            await handle_vault_ingest(
                content="Raw content for QMD refresh test.",
                filename="qmd-refresh-test.txt",
                source_type="text",
                auto_compile=False,
                **mcp_services,
            )
            mock_update.assert_awaited_once()


class TestVaultIngestBinary:
    @pytest.mark.asyncio
    async def test_ingest_writes_binary_file(self, mcp_services):
        """handle_vault_ingest should write raw bytes when file_bytes is provided."""
        from cortex.mcp.tools import handle_vault_ingest

        binary_data = b"\x50\x4b\x03\x04fake-zip-content"

        result = await handle_vault_ingest(
            filename="archive.zip",
            file_bytes=binary_data,
            auto_compile=False,
            **mcp_services,
        )
        vault_path = mcp_services["vault_path"]
        written = (vault_path / "raw" / "archive.zip").read_bytes()
        assert written == binary_data
        assert result["path"] == "raw/archive.zip"

    @pytest.mark.asyncio
    async def test_ingest_binary_with_auto_compile(self, mcp_services):
        """Binary ingest with auto_compile should convert via MarkItDown."""
        from cortex.mcp.tools import handle_vault_ingest

        html_bytes = b"<html><body><h1>Hello</h1><p>World</p></body></html>"

        result = await handle_vault_ingest(
            filename="page.html",
            file_bytes=html_bytes,
            auto_compile=True,
            **mcp_services,
        )
        assert result.get("compiled") is True
        assert len(result.get("wiki_articles", [])) >= 1

    @pytest.mark.asyncio
    async def test_ingest_text_still_works(self, mcp_services):
        """Existing text content ingestion should still work."""
        from cortex.mcp.tools import handle_vault_ingest

        result = await handle_vault_ingest(
            content="Plain text content.",
            filename="note.txt",
            auto_compile=False,
            **mcp_services,
        )
        vault_path = mcp_services["vault_path"]
        assert (vault_path / "raw" / "note.txt").read_text() == "Plain text content."
        assert result["path"] == "raw/note.txt"


class TestCrossReferencesAfterIngest:
    """compile_cross_references should be invoked after ingest when auto_compile is on."""

    @pytest.mark.asyncio
    async def test_ingest_auto_compile_calls_cross_references(self, mcp_services):
        """handle_vault_ingest with auto_compile should call compile_cross_references."""
        from cortex.mcp.tools import handle_vault_ingest

        with patch.object(
            mcp_services["compiler"], "ingest_source",
            new_callable=AsyncMock,
            return_value=[mcp_services["vault_path"] / "wiki" / "test.md"],
        ) as mock_ingest, patch.object(
            mcp_services["compiler"], "compile_cross_references",
            new_callable=AsyncMock,
        ) as mock_xref:
            await handle_vault_ingest(
                content="Raw source text.",
                filename="xref-test.txt",
                auto_compile=True,
                **mcp_services,
            )
            mock_ingest.assert_awaited_once()
            mock_xref.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingest_no_compile_skips_cross_references(self, mcp_services):
        """handle_vault_ingest without auto_compile should NOT call compile_cross_references."""
        from cortex.mcp.tools import handle_vault_ingest

        with patch.object(
            mcp_services["compiler"], "compile_cross_references",
            new_callable=AsyncMock,
        ) as mock_xref:
            await handle_vault_ingest(
                content="Raw source text.",
                filename="no-xref-test.txt",
                auto_compile=False,
                **mcp_services,
            )
            mock_xref.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_compile_calls_cross_references(self, mcp_services):
        """handle_vault_compile should call compile_cross_references after ingesting."""
        from cortex.mcp.tools import handle_vault_compile

        vault_path = mcp_services["vault_path"]
        (vault_path / "raw" / "xref-compile-test.txt").write_text("Content for xref.")

        created_path = vault_path / "wiki" / "xref-compile-test.md"

        with patch.object(
            mcp_services["compiler"], "ingest_source",
            new_callable=AsyncMock,
            return_value=[created_path],
        ), patch.object(
            mcp_services["compiler"], "compile_cross_references",
            new_callable=AsyncMock,
        ) as mock_xref:
            await handle_vault_compile(**mcp_services)
            mock_xref.assert_awaited_once()


class TestVaultCompileTool:
    @pytest.mark.asyncio
    async def test_compile_refreshes_qmd_index(self, mcp_services):
        from cortex.mcp.tools import handle_vault_compile

        vault_path = mcp_services["vault_path"]
        (vault_path / "raw" / "compile-test.txt").write_text("Compile me.")

        with patch.object(mcp_services["qmd"], "update", new_callable=AsyncMock) as mock_update:
            with patch.object(mcp_services["compiler"], "ingest_source", new_callable=AsyncMock, return_value=[]):
                await handle_vault_compile(**mcp_services)
            mock_update.assert_awaited_once()
