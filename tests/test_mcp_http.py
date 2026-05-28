"""Tests for MCP HTTP server."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def mcp_http_client(tmp_vault: Path):
    """Create a test client with MCP streamable HTTP (lifespan active)."""
    from cortex.mcp.http_server import create_mcp_app

    loop = asyncio.new_event_loop()
    with patch("cortex.search.qmd.QMDSearch._run", new_callable=AsyncMock, return_value=""):
        starlette_app = loop.run_until_complete(create_mcp_app(tmp_vault))
    loop.close()

    with TestClient(starlette_app, base_url="http://localhost") as client:
        yield client


MCP_ACCEPT = "application/json, text/event-stream"


def _init_mcp_session(client: TestClient) -> dict[str, str]:
    """Initialize an MCP session and return session headers."""
    init_resp = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "clientInfo": {"name": "test", "version": "0.1"},
                "capabilities": {},
            },
        },
        headers={"Accept": MCP_ACCEPT},
    )
    session_id = init_resp.headers.get("mcp-session-id")
    headers: dict[str, str] = {"Accept": MCP_ACCEPT}
    if session_id:
        headers["mcp-session-id"] = session_id

    client.post(
        "/",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=headers,
    )
    return headers


class TestMCPHttpServer:
    def test_create_mcp_app_returns_starlette_app(self, tmp_vault: Path):
        from cortex.mcp.http_server import create_mcp_app
        from starlette.applications import Starlette

        loop = asyncio.new_event_loop()
        with patch("cortex.search.qmd.QMDSearch._run", new_callable=AsyncMock, return_value=""):
            app = loop.run_until_complete(create_mcp_app(tmp_vault))
        loop.close()
        assert isinstance(app, Starlette)

    def test_mcp_endpoint_exists(self, mcp_http_client: TestClient):
        """The / endpoint should accept POST requests (MCP protocol)."""
        response = mcp_http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "clientInfo": {"name": "test", "version": "0.1"},
                    "capabilities": {},
                },
            },
            headers={"Accept": MCP_ACCEPT},
        )
        assert response.status_code == 200

    def test_mcp_lists_tools(self, mcp_http_client: TestClient):
        """After initialize, list_tools should return our 9 vault tools."""
        headers = _init_mcp_session(mcp_http_client)

        list_resp = mcp_http_client.post(
            "/",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=headers,
        )
        assert list_resp.status_code == 200

        data = list_resp.json()
        tool_names = [t["name"] for t in data.get("result", {}).get("tools", [])]
        assert "vault_read" in tool_names
        assert "vault_write" in tool_names
        assert "vault_search" in tool_names
        assert "vault_link" in tool_names
        assert "vault_context" in tool_names
        assert "vault_ingest" in tool_names
        assert "vault_compile" in tool_names
        assert "vault_feedback" in tool_names
        assert "vault_list_feedbacks" in tool_names
        assert len(tool_names) == 9


class TestMCPHttpToolCalls:
    def test_vault_read_via_http(self, mcp_http_client: TestClient):
        """vault_read should return note content via HTTP transport."""
        headers = _init_mcp_session(mcp_http_client)

        resp = mcp_http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "vault_read",
                    "arguments": {"path": "wiki/transformers.md"},
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        content_list = data.get("result", {}).get("content", [])
        assert len(content_list) > 0
        text = json.loads(content_list[0]["text"])
        assert text["title"] == "Transformer Architecture"

    def test_vault_write_via_http(self, mcp_http_client: TestClient, tmp_vault: Path):
        """vault_write should create a note via HTTP transport."""
        headers = _init_mcp_session(mcp_http_client)

        resp = mcp_http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "vault_write",
                    "arguments": {
                        "path": "wiki/http-test.md",
                        "content": "# HTTP Test\n\nCreated via MCP HTTP.",
                    },
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert (tmp_vault / "wiki" / "http-test.md").exists()

    def test_vault_ingest_via_http(self, mcp_http_client: TestClient, tmp_vault: Path):
        """vault_ingest should write raw content via HTTP transport."""
        headers = _init_mcp_session(mcp_http_client)

        resp = mcp_http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "vault_ingest",
                    "arguments": {
                        "content": "Raw HTTP content.",
                        "filename": "http-ingest.txt",
                    },
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert (tmp_vault / "raw" / "http-ingest.txt").exists()


class TestMCPIngestBase64:
    def test_vault_ingest_base64_via_http(self, mcp_http_client: TestClient, tmp_vault: Path):
        """vault_ingest with content_base64 should decode and write binary content."""
        import base64

        headers = _init_mcp_session(mcp_http_client)
        raw_bytes = b"<html><body><h1>Base64</h1></body></html>"
        b64 = base64.b64encode(raw_bytes).decode()

        resp = mcp_http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "vault_ingest",
                    "arguments": {
                        "filename": "b64-test.html",
                        "content_base64": b64,
                    },
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert (tmp_vault / "raw" / "b64-test.html").exists()
        assert (tmp_vault / "raw" / "b64-test.html").read_bytes() == raw_bytes


class TestMainAppMCPMount:
    def test_mcp_mounted_on_fastapi(self, tmp_vault: Path):
        """The FastAPI app should have MCP mounted at /mcp."""
        import contextlib
        from cortex.graph.builder import build_graph
        from cortex.graph.engine import GraphEngine
        from cortex.search.qmd import QMDSearch
        from cortex.vault.reader import scan_vault
        from cortex.mcp.http_server import create_fastmcp_server, mount_mcp_on_app

        from fastapi import FastAPI
        from fastapi.testclient import TestClient as FastAPITestClient
        from cortex.api.routes import router

        loop = asyncio.new_event_loop()

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        loop.run_until_complete(graph.load())
        notes = scan_vault(tmp_vault)

        with patch("cortex.search.qmd.QMDSearch._run", new_callable=AsyncMock, return_value=""):
            mcp_server = loop.run_until_complete(create_fastmcp_server(tmp_vault))

        @contextlib.asynccontextmanager
        async def lifespan(app):
            mcp_app = mount_mcp_on_app(app, mcp_server)
            async with mcp_app.router.lifespan_context(mcp_app):
                yield

        test_app = FastAPI(title="Cortex Test", lifespan=lifespan)
        test_app.include_router(router, prefix="/api/v1")
        test_app.state.graph = loop.run_until_complete(
            build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)
        )
        test_app.state.vault_path = tmp_vault
        test_app.state.qmd = QMDSearch(tmp_vault, "qmd")
        loop.close()

        with FastAPITestClient(test_app, base_url="http://localhost") as client:
            health = client.get("/api/v1/health")
            assert health.status_code == 200

            mcp_resp = client.post(
                "/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "clientInfo": {"name": "test", "version": "0.1"},
                        "capabilities": {},
                    },
                },
                headers={"Accept": MCP_ACCEPT},
            )
            assert mcp_resp.status_code == 200


class TestSharedServices:
    def test_create_fastmcp_server_accepts_prebuilt_services(self, tmp_vault: Path):
        """create_fastmcp_server should accept a services dict to avoid duplicate init."""
        from cortex.graph.builder import build_graph
        from cortex.search.qmd import QMDSearch
        from cortex.search.qmd_cache import CachedQMDSearch
        from cortex.search.qmd_debounce import DebouncedQMDUpdate
        from cortex.compiler.compiler import KnowledgeCompiler
        from cortex.vault.reader import scan_vault
        from cortex.mcp.http_server import create_fastmcp_server

        loop = asyncio.new_event_loop()
        notes = scan_vault(tmp_vault)
        graph = loop.run_until_complete(
            build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)
        )
        qmd = CachedQMDSearch(QMDSearch(tmp_vault, "qmd"))
        services = {
            "vault_path": tmp_vault,
            "graph": graph,
            "qmd": qmd,
            "qmd_debounce": DebouncedQMDUpdate(qmd),
            "compiler": KnowledgeCompiler(tmp_vault),
        }

        with patch("cortex.search.qmd.QMDSearch._run", new_callable=AsyncMock, return_value=""):
            mcp = loop.run_until_complete(create_fastmcp_server(tmp_vault, services=services))
        loop.close()

        assert mcp is not None

    def test_create_fastmcp_server_fallback_uses_async_scan(self, tmp_vault: Path):
        """When no services passed, fallback should use scan_vault_async, not sync scan."""
        from cortex.mcp.http_server import create_fastmcp_server

        loop = asyncio.new_event_loop()
        scan_patch = patch(
            "cortex.mcp.http_server.scan_vault_async",
            new_callable=AsyncMock, return_value=[],
        )
        with patch("cortex.search.qmd.QMDSearch._run", new_callable=AsyncMock, return_value=""):
            with scan_patch as mock_async:
                with patch("cortex.mcp.http_server.build_graph", new_callable=AsyncMock) as mock_bg:
                    mock_bg.return_value = AsyncMock()
                    mock_bg.return_value.graph = MagicMock()
                    loop.run_until_complete(create_fastmcp_server(tmp_vault))
                    mock_async.assert_awaited_once()
        loop.close()

    def test_create_fastmcp_server_reuses_graph_instance(self, tmp_vault: Path):
        """When services are passed, MCP must use the same graph — not build a new one."""
        from cortex.graph.builder import build_graph
        from cortex.search.qmd import QMDSearch
        from cortex.search.qmd_cache import CachedQMDSearch
        from cortex.search.qmd_debounce import DebouncedQMDUpdate
        from cortex.compiler.compiler import KnowledgeCompiler
        from cortex.vault.reader import scan_vault
        from cortex.mcp.http_server import create_fastmcp_server

        loop = asyncio.new_event_loop()
        notes = scan_vault(tmp_vault)
        graph = loop.run_until_complete(
            build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)
        )
        qmd = CachedQMDSearch(QMDSearch(tmp_vault, "qmd"))
        services = {
            "vault_path": tmp_vault,
            "graph": graph,
            "qmd": qmd,
            "qmd_debounce": DebouncedQMDUpdate(qmd),
            "compiler": KnowledgeCompiler(tmp_vault),
        }

        with patch("cortex.search.qmd.QMDSearch._run", new_callable=AsyncMock, return_value=""):
            with patch("cortex.mcp.http_server.build_graph") as mock_build:
                loop.run_until_complete(create_fastmcp_server(tmp_vault, services=services))
                mock_build.assert_not_called()
        loop.close()
