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

    @pytest.mark.asyncio
    async def test_write_appends_daily_log_entry(self, mcp_services):
        """Every vault_write appends an entry to daily/<UTC-date>.md."""
        from datetime import datetime, timezone
        from cortex.mcp.tools import handle_vault_write

        fixed = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        with patch("cortex.vault.daily_log._utc_now", return_value=fixed):
            await handle_vault_write(
                path="wiki/daily-log-test.md",
                content="# Daily log test",
                **mcp_services,
            )

        daily_path = mcp_services["vault_path"] / "daily" / "2026-06-10.md"
        assert daily_path.exists(), "vault_write should create the daily-log file"
        content = daily_path.read_text(encoding="utf-8")
        assert "vault:write" in content
        assert "[[daily-log-test]]" in content

    @pytest.mark.asyncio
    async def test_write_to_daily_folder_does_not_self_mirror(self, mcp_services):
        """Writing to daily/ must NOT trigger a daily-log entry (avoids self-reference)."""
        from datetime import datetime, timezone
        from cortex.mcp.tools import handle_vault_write

        fixed = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
        with patch("cortex.vault.daily_log._utc_now", return_value=fixed):
            await handle_vault_write(
                path="daily/2026-06-10.md",
                content="# Manually edited daily note",
                **mcp_services,
            )

        daily_path = mcp_services["vault_path"] / "daily" / "2026-06-10.md"
        assert daily_path.exists()
        content = daily_path.read_text(encoding="utf-8")
        # The body the user wrote IS there, but no auto-appended `vault:write` mirror entry
        assert "Manually edited daily note" in content
        assert "## [09:00] vault:write" not in content

    @pytest.mark.asyncio
    async def test_write_to_feedback_does_not_mirror(self, mcp_services):
        """Writes to feedback/ should not trigger a daily-log mirror."""
        from datetime import datetime, timezone
        from cortex.mcp.tools import handle_vault_write

        fixed = datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc)
        with patch("cortex.vault.daily_log._utc_now", return_value=fixed):
            await handle_vault_write(
                path="feedback/test-fb.md",
                content="# Feedback note",
                **mcp_services,
            )

        daily_path = mcp_services["vault_path"] / "daily" / "2026-06-10.md"
        assert not daily_path.exists(), "feedback/ writes must not create a daily-log file"


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


class TestVaultFeedbackTool:
    @pytest.mark.asyncio
    async def test_handle_vault_feedback(self, mcp_services):
        from unittest.mock import MagicMock

        from cortex.mcp.tools import handle_vault_feedback

        (mcp_services["vault_path"] / "feedback").mkdir(exist_ok=True)
        qmd_debounce = MagicMock()

        result = await handle_vault_feedback(
            content="MCP search was wrong",
            tags=["mcp"],
            related_paths=["wiki/transformers.md"],
            authored_by="mace.smith@example.com",
            qmd_debounce=qmd_debounce,
            **mcp_services,
        )
        assert result["status"] == "OPEN"
        assert result["path"].startswith("feedback/")
        assert result["authored_by"] == "mace.smith@example.com"

    @pytest.mark.asyncio
    async def test_handle_vault_list_feedbacks(self, mcp_services):
        from unittest.mock import MagicMock

        from cortex.mcp.tools import handle_vault_feedback, handle_vault_list_feedbacks

        (mcp_services["vault_path"] / "feedback").mkdir(exist_ok=True)
        await handle_vault_feedback(
            content="List me",
            tags=["test"],
            related_paths=["wiki/transformers.md"],
            qmd_debounce=MagicMock(),
            **mcp_services,
        )

        result = await handle_vault_list_feedbacks(**mcp_services)
        assert result["count"] >= 1
        assert len(result["feedbacks"]) == result["count"]
        item = result["feedbacks"][0]
        assert item["path"].startswith("feedback/")
        assert item["authored_by"] == "human"
        assert "preview" in item
        assert "content" not in item


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

    @pytest.mark.asyncio
    async def test_ingest_appends_daily_log_entry(self, mcp_services):
        """vault_ingest should append a daily-log entry for the raw ingest."""
        from datetime import datetime, timezone
        from cortex.mcp.tools import handle_vault_ingest

        fixed = datetime(2026, 6, 10, 8, 15, tzinfo=timezone.utc)
        with patch("cortex.vault.daily_log._utc_now", return_value=fixed):
            await handle_vault_ingest(
                content="raw text",
                filename="daily-ingest-test.txt",
                source_type="text",
                auto_compile=False,
                **mcp_services,
            )

        daily_path = mcp_services["vault_path"] / "daily" / "2026-06-10.md"
        assert daily_path.exists()
        content = daily_path.read_text(encoding="utf-8")
        assert "vault:ingest" in content
        assert "raw/daily-ingest-test.txt" in content


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


class TestCompileReprocessing:
    """Tests that vault_compile reprocesses incomplete enrichments and supports force/path."""

    @pytest.mark.asyncio
    async def test_compile_reprocesses_incomplete_enrichments(self, mcp_services):
        """Sources with enrichment_status=incomplete should be recompiled."""
        from cortex.mcp.tools import handle_vault_compile

        vault_path = mcp_services["vault_path"]
        (vault_path / "raw" / "incomplete-src.txt").write_text("Raw content.")

        wiki_dir = vault_path / "wiki"
        wiki_dir.mkdir(exist_ok=True)
        (wiki_dir / "incomplete-src.md").write_text(
            "---\ntitle: Incomplete\nsource_path: raw/incomplete-src.txt\n"
            "enrichment_status: incomplete\n---\n\nRaw content.\n"
        )

        created_path = wiki_dir / "incomplete-src.md"
        with patch.object(
            mcp_services["compiler"], "ingest_source",
            new_callable=AsyncMock, return_value=[created_path],
        ) as mock_ingest:
            result = await handle_vault_compile(**mcp_services)
            mock_ingest.assert_awaited_once()

        assert result["sources_compiled"] == 1

    @pytest.mark.asyncio
    async def test_compile_skips_complete_enrichments(self, mcp_services):
        """Sources with enrichment_status=complete should NOT be recompiled."""
        from cortex.mcp.tools import handle_vault_compile

        vault_path = mcp_services["vault_path"]
        (vault_path / "raw" / "complete-src.txt").write_text("Raw content.")

        wiki_dir = vault_path / "wiki"
        wiki_dir.mkdir(exist_ok=True)
        (wiki_dir / "complete-src.md").write_text(
            "---\ntitle: Complete\nsource_path: raw/complete-src.txt\n"
            "enrichment_status: complete\n---\n\nEnriched [[content]].\n"
        )

        with patch.object(
            mcp_services["compiler"], "ingest_source",
            new_callable=AsyncMock, return_value=[],
        ) as mock_ingest:
            result = await handle_vault_compile(**mcp_services)
            mock_ingest.assert_not_awaited()

        assert result["sources_compiled"] == 0

    @pytest.mark.asyncio
    async def test_compile_force_reprocesses_complete(self, mcp_services):
        """force=True should recompile even enrichment_status=complete sources."""
        from cortex.mcp.tools import handle_vault_compile

        vault_path = mcp_services["vault_path"]
        (vault_path / "raw" / "force-src.txt").write_text("Raw content.")

        wiki_dir = vault_path / "wiki"
        wiki_dir.mkdir(exist_ok=True)
        (wiki_dir / "force-src.md").write_text(
            "---\ntitle: Force\nsource_path: raw/force-src.txt\n"
            "enrichment_status: complete\n---\n\nEnriched [[content]].\n"
        )

        created_path = wiki_dir / "force-src.md"
        with patch.object(
            mcp_services["compiler"], "ingest_source",
            new_callable=AsyncMock, return_value=[created_path],
        ) as mock_ingest:
            result = await handle_vault_compile(
                force=True, path="raw/force-src.txt", **mcp_services,
            )
            mock_ingest.assert_awaited_once()

        assert result["sources_compiled"] == 1

    @pytest.mark.asyncio
    async def test_compile_path_filter(self, mcp_services):
        """path param should limit compilation to a specific raw file."""
        from cortex.mcp.tools import handle_vault_compile

        vault_path = mcp_services["vault_path"]
        (vault_path / "raw" / "target.txt").write_text("Target.")
        (vault_path / "raw" / "other.txt").write_text("Other.")

        created_path = vault_path / "wiki" / "target.md"
        with patch.object(
            mcp_services["compiler"], "ingest_source",
            new_callable=AsyncMock, return_value=[created_path],
        ) as mock_ingest:
            result = await handle_vault_compile(
                path="raw/target.txt", **mcp_services,
            )
            mock_ingest.assert_awaited_once()
            actual_path = mock_ingest.call_args[0][0]
            assert actual_path.name == "target.txt"

        assert result["sources_compiled"] == 1


class TestCompileToolSurface:
    """Tests that vault_compile tool definitions expose force/path params."""

    def test_stdio_compile_schema_includes_force_and_path(self):
        """The stdio vault_compile tool should have force and path in its schema."""
        from cortex.mcp.server import _tool_definitions

        tools = _tool_definitions()
        compile_tool = next(t for t in tools if t.name == "vault_compile")
        props = compile_tool.inputSchema["properties"]
        assert "force" in props, "vault_compile missing 'force' param"
        assert props["force"]["type"] == "boolean"
        assert "path" in props, "vault_compile missing 'path' param"
        assert props["path"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_stdio_dispatch_passes_force_and_path(self, mcp_services):
        """The stdio dispatcher should forward force/path to handle_vault_compile."""
        from cortex.mcp.server import _services, call_tool

        _services.update(mcp_services)

        with patch(
            "cortex.mcp.server.handle_vault_compile",
            new_callable=AsyncMock,
            return_value={"status": "compiled", "sources_compiled": 0, "articles_created": []},
        ) as mock_handler:
            await call_tool("vault_compile", {"force": True, "path": "raw/test.txt"})
            mock_handler.assert_awaited_once()
            _, call_kwargs = mock_handler.call_args
            assert call_kwargs.get("force") is True
            assert call_kwargs.get("path") == "raw/test.txt"

    @pytest.mark.asyncio
    async def test_http_compile_accepts_force_and_path(self, tmp_vault: Path):
        """The HTTP vault_compile tool should accept force and path parameters."""
        from cortex.mcp.http_server import create_fastmcp_server

        mock_services = {
            "vault_path": tmp_vault,
            "graph": AsyncMock(),
            "qmd": AsyncMock(),
            "compiler": AsyncMock(),
        }

        mcp = await create_fastmcp_server(tmp_vault, services=mock_services)
        tools = await mcp.list_tools()
        compile_tool = next(t for t in tools if t.name == "vault_compile")
        schema = getattr(compile_tool, "inputSchema", None) or getattr(compile_tool, "parameters", {})
        if callable(getattr(schema, "get", None)):
            params = schema.get("properties", {})
        else:
            params = {}
        assert "force" in params or "force" in str(compile_tool)


class TestStdioServerCaching:
    @pytest.mark.asyncio
    async def test_stdio_server_wraps_qmd_in_cache(self, tmp_vault: Path):
        """run_stdio must wrap the QMD backend in CachedQMDSearch."""
        from cortex.mcp.server import _services, run_stdio
        from cortex.search.qmd_cache import CachedQMDSearch

        with patch("cortex.mcp.server.scan_vault", return_value=[]), \
             patch("cortex.mcp.server.build_graph", new_callable=AsyncMock) as mock_bg, \
             patch("cortex.mcp.server.QMDSearch") as mock_qmd_cls, \
             patch("cortex.mcp.server.stdio_server") as mock_stdio, \
             patch("cortex.mcp.server.settings") as mock_settings:

            mock_settings.vault_path = tmp_vault
            mock_settings.qmd_url = ""
            mock_settings.qmd_bin = "qmd"
            mock_settings.resource_ttl_seconds = 3600
            mock_settings.resource_max_items = 1000

            mock_bg.return_value = AsyncMock()
            mock_qmd_cls.return_value.initialize = AsyncMock()

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_stdio.return_value = mock_ctx

            with patch("cortex.mcp.server.app") as mock_app:
                mock_app.run = AsyncMock()
                mock_app.create_initialization_options = lambda: {}
                await run_stdio()

            assert isinstance(_services["qmd"], CachedQMDSearch)
