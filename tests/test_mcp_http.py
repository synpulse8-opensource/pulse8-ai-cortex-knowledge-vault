"""Tests for MCP HTTP server."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
        """After initialize, list_tools should return our 7 vault tools."""
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
        assert len(tool_names) == 7


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


class TestMainAppMCPMount:
    def test_mcp_mounted_on_fastapi(self, tmp_vault: Path):
        """The FastAPI app should have MCP mounted at /mcp."""
        from cortex.graph.builder import build_graph
        from cortex.graph.engine import GraphEngine
        from cortex.search.qmd import QMDSearch
        from cortex.vault.reader import scan_vault
        from cortex.mcp.http_server import create_fastmcp_server, mount_mcp_on_app

        from fastapi import FastAPI
        from fastapi.testclient import TestClient as FastAPITestClient
        from cortex.api.routes import router

        test_app = FastAPI(title="Cortex Test")
        test_app.include_router(router, prefix="/api/v1")

        loop = asyncio.new_event_loop()

        graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
        loop.run_until_complete(graph.load())
        notes = scan_vault(tmp_vault)
        test_app.state.graph = loop.run_until_complete(
            build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)
        )
        test_app.state.vault_path = tmp_vault
        test_app.state.qmd = QMDSearch(tmp_vault, "qmd")

        with patch("cortex.search.qmd.QMDSearch._run", new_callable=AsyncMock, return_value=""):
            mcp_server = loop.run_until_complete(create_fastmcp_server(tmp_vault))
        mount_mcp_on_app(test_app, mcp_server)
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
