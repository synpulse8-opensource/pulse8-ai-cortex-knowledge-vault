"""Tests for the MCP resource store and the resources-as-tool-inputs pattern.

Inspired by the Microsoft Copilot Studio CAT recommendation in
https://microsoft.github.io/mcscatblog/posts/mcp-resources-as-tool-inputs/

Token-heavy tool outputs should be stored as server-side resources;
tools return lightweight IDs (cortex://resource/{id}) instead of full
payloads. This avoids saturating the LLM context window.
"""
from __future__ import annotations

import pytest


class TestResourceStorePutGet:
    @pytest.mark.asyncio
    async def test_put_returns_string_id(self):
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore()
        resource_id = await store.put("hello world")

        assert isinstance(resource_id, str)
        assert resource_id  # non-empty

    @pytest.mark.asyncio
    async def test_get_returns_stored_content(self):
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore()
        resource_id = await store.put("hello world")

        stored = await store.get(resource_id)

        assert stored is not None
        assert stored.content == "hello world"

    @pytest.mark.asyncio
    async def test_put_twice_returns_distinct_ids(self):
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore()
        id_a = await store.put("a")
        id_b = await store.put("b")

        assert id_a != id_b


class TestResourceStoreMissing:
    @pytest.mark.asyncio
    async def test_get_unknown_id_returns_none(self):
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore()

        assert await store.get("does-not-exist") is None


class TestResourceStoreTTL:
    @pytest.mark.asyncio
    async def test_resource_expires_after_ttl(self):
        from datetime import timedelta

        from cortex.mcp.resources import ResourceStore

        store = ResourceStore(default_ttl=timedelta(milliseconds=50))
        resource_id = await store.put("temporary")

        import asyncio as _asyncio

        await _asyncio.sleep(0.1)

        assert await store.get(resource_id) is None

    @pytest.mark.asyncio
    async def test_resource_persists_before_ttl(self):
        from datetime import timedelta

        from cortex.mcp.resources import ResourceStore

        store = ResourceStore(default_ttl=timedelta(seconds=60))
        resource_id = await store.put("durable")

        stored = await store.get(resource_id)
        assert stored is not None
        assert stored.content == "durable"

    @pytest.mark.asyncio
    async def test_default_ttl_does_not_expire_quickly(self):
        """No TTL kwarg → store should hold the resource for the test duration."""
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore()
        resource_id = await store.put("default-ttl")

        import asyncio as _asyncio

        await _asyncio.sleep(0.05)

        assert await store.get(resource_id) is not None


class TestResourceStoreBoundedSize:
    @pytest.mark.asyncio
    async def test_lru_evicts_oldest_when_over_capacity(self):
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore(max_items=2)
        id_a = await store.put("a")
        id_b = await store.put("b")
        id_c = await store.put("c")

        assert await store.get(id_a) is None
        assert (await store.get(id_b)).content == "b"
        assert (await store.get(id_c)).content == "c"

    @pytest.mark.asyncio
    async def test_get_refreshes_lru_order(self):
        """Reading a resource marks it as most-recently-used."""
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore(max_items=2)
        id_a = await store.put("a")
        id_b = await store.put("b")
        _ = await store.get(id_a)  # touch a so it is now newest
        id_c = await store.put("c")  # b should be evicted, not a

        assert (await store.get(id_a)).content == "a"
        assert await store.get(id_b) is None
        assert (await store.get(id_c)).content == "c"


# ---------------------------------------------------------------------------
# Tool integration: opt-in `as_resource=True` returns a handle, not raw payload
# ---------------------------------------------------------------------------


@pytest.fixture
async def mcp_services_with_resources(tmp_vault):
    """MCP services dict including a ResourceStore."""
    from unittest.mock import AsyncMock

    from cortex.compiler.compiler import KnowledgeCompiler
    from cortex.graph.builder import build_graph
    from cortex.mcp.resources import ResourceStore
    from cortex.search.qmd import QMDSearch
    from cortex.vault.reader import scan_vault

    notes = scan_vault(tmp_vault)
    graph = await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)

    qmd = QMDSearch(tmp_vault, "qmd")
    qmd.update = AsyncMock()

    compiler = KnowledgeCompiler(tmp_vault)
    resource_store = ResourceStore()

    return {
        "vault_path": tmp_vault,
        "graph": graph,
        "qmd": qmd,
        "compiler": compiler,
        "resource_store": resource_store,
    }


class TestVaultSearchAsResource:
    @pytest.mark.asyncio
    async def test_returns_resource_handle_not_full_payload(
        self, mcp_services_with_resources
    ):
        from unittest.mock import AsyncMock

        from cortex.mcp.tools import handle_vault_search

        mcp_services_with_resources["qmd"].search = AsyncMock(
            return_value=[
                {"path": "wiki/transformers.md", "snippet": "x" * 5000},
                {"path": "wiki/attention-mechanisms.md", "snippet": "y" * 5000},
            ]
        )

        result = await handle_vault_search(
            query="attention",
            as_resource=True,
            **mcp_services_with_resources,
        )

        assert "resource_id" in result
        assert result["resource_uri"] == f"cortex://resource/{result['resource_id']}"
        assert "results" not in result, (
            "Full results MUST stay out of the LLM context when as_resource=True"
        )
        assert result["summary"]["count"] == 2

    @pytest.mark.asyncio
    async def test_payload_is_retrievable_from_store(
        self, mcp_services_with_resources
    ):
        import json
        from unittest.mock import AsyncMock

        from cortex.mcp.tools import handle_vault_search

        mcp_services_with_resources["qmd"].search = AsyncMock(
            return_value=[{"path": "wiki/transformers.md", "snippet": "hello"}]
        )

        result = await handle_vault_search(
            query="attention",
            as_resource=True,
            **mcp_services_with_resources,
        )

        stored = await mcp_services_with_resources["resource_store"].get(
            result["resource_id"]
        )
        assert stored is not None
        assert stored.mime_type == "application/json"
        decoded = json.loads(stored.content)
        assert decoded["query"] == "attention"
        assert decoded["results"][0]["path"] == "wiki/transformers.md"

    @pytest.mark.asyncio
    async def test_default_behavior_is_unchanged(
        self, mcp_services_with_resources
    ):
        from unittest.mock import AsyncMock

        from cortex.mcp.tools import handle_vault_search

        mcp_services_with_resources["qmd"].search = AsyncMock(
            return_value=[{"path": "wiki/transformers.md", "snippet": "hello"}]
        )

        result = await handle_vault_search(
            query="attention", **mcp_services_with_resources
        )

        assert "resource_id" not in result
        assert "results" in result


class TestVaultContextAsResource:
    @pytest.mark.asyncio
    async def test_returns_resource_handle_not_full_notes(
        self, mcp_services_with_resources
    ):
        import json
        from unittest.mock import AsyncMock, patch

        from cortex.graph.context import ContextWindow

        mcp_services_with_resources["qmd"].search = AsyncMock(return_value=[])

        fake_window = ContextWindow(
            notes=[], edges=[], contradictions=[],
            total_nodes_explored=3, total_edges_explored=5,
        )

        with patch(
            "cortex.mcp.tools.build_context_window",
            new_callable=AsyncMock,
            return_value=fake_window,
        ):
            from cortex.mcp.tools import handle_vault_context

            result = await handle_vault_context(
                query="attention",
                as_resource=True,
                **mcp_services_with_resources,
            )

        assert "resource_id" in result
        assert result["resource_uri"] == f"cortex://resource/{result['resource_id']}"
        assert "notes" not in result, (
            "Full notes MUST stay out of the LLM context when as_resource=True"
        )
        assert result["summary"]["total_nodes_explored"] == 3

        stored = await mcp_services_with_resources["resource_store"].get(
            result["resource_id"]
        )
        assert stored is not None
        decoded = json.loads(stored.content)
        assert decoded["total_nodes_explored"] == 3
        assert "notes" in decoded

    @pytest.mark.asyncio
    async def test_default_behavior_returns_full_window(
        self, mcp_services_with_resources
    ):
        from unittest.mock import AsyncMock, patch

        from cortex.graph.context import ContextWindow

        fake_window = ContextWindow(
            notes=[], edges=[], contradictions=[],
            total_nodes_explored=2, total_edges_explored=1,
        )

        with patch(
            "cortex.mcp.tools.build_context_window",
            new_callable=AsyncMock,
            return_value=fake_window,
        ):
            from cortex.mcp.tools import handle_vault_context

            result = await handle_vault_context(
                query="attention",
                **mcp_services_with_resources,
            )

        assert "resource_id" not in result
        assert result["total_nodes_explored"] == 2
        assert "notes" in result


# ---------------------------------------------------------------------------
# FastMCP HTTP server: services injected + cortex://resource/{id} template
# ---------------------------------------------------------------------------


class TestFastMCPResourceWiring:
    @pytest.mark.asyncio
    async def test_fastmcp_registers_cortex_resource_template(self, tmp_vault):
        """FastMCP should expose a `cortex://resource/{id}` resource template
        so MCP clients can read stored resources via the resources protocol."""
        from unittest.mock import AsyncMock, patch

        from cortex.mcp.http_server import create_fastmcp_server

        with patch(
            "cortex.search.qmd.QMDSearch._run",
            new_callable=AsyncMock,
            return_value="",
        ):
            mcp = await create_fastmcp_server(tmp_vault)

        templates = await mcp.list_resource_templates()
        # FastMCP exposes URIs as `uri_template` on FunctionResourceTemplate
        # and as `uriTemplate` on the MCP wire model — accept either.
        uris = [
            getattr(t, "uri_template", None) or getattr(t, "uriTemplate", None)
            for t in templates
        ]
        uris = [str(u) for u in uris if u]
        assert any("cortex://resource/{" in u for u in uris), (
            f"Expected cortex://resource/{{...}} template, got {uris}"
        )

    @pytest.mark.asyncio
    async def test_vault_search_as_resource_round_trips_via_fastmcp(
        self, tmp_vault, monkeypatch
    ):
        """End-to-end: call vault_search via FastMCP with as_resource=True,
        then read the resource back through FastMCP's resource interface."""
        import json
        from unittest.mock import AsyncMock, patch

        from cortex.mcp.http_server import create_fastmcp_server

        async def fake_search(self, *args, **kwargs):  # pylint: disable=unused-argument
            return [{"path": "wiki/transformers.md", "snippet": "hello"}]

        with patch(
            "cortex.search.qmd.QMDSearch._run",
            new_callable=AsyncMock,
            return_value="",
        ):
            mcp = await create_fastmcp_server(tmp_vault)

        monkeypatch.setattr(
            "cortex.search.qmd_cache.CachedQMDSearch.search",
            fake_search,
        )

        # Call the tool with as_resource=True via FastMCP's public API
        tool_result = await mcp.call_tool(
            "vault_search", {"query": "attention", "as_resource": True}
        )
        # tool_result is a ToolResult-like object exposing `content` blocks
        text_block = tool_result.content[0]
        payload = json.loads(text_block.text)

        assert "resource_id" in payload
        assert payload["resource_uri"].startswith("cortex://resource/")

        # Read it back through the registered resource template
        result = await mcp.read_resource(payload["resource_uri"])
        contents = result.contents if hasattr(result, "contents") else result
        assert contents, "expected resource read to return contents"
        first = contents[0]
        body = (
            getattr(first, "content", None)
            or getattr(first, "text", None)
            or getattr(first, "blob", None)
        )
        assert body is not None, f"could not extract body from {first!r}"
        decoded = json.loads(body)
        assert decoded["query"] == "attention"
        assert decoded["results"][0]["path"] == "wiki/transformers.md"


# ---------------------------------------------------------------------------
# Stdio server: list_resource_templates + read_resource handlers
# ---------------------------------------------------------------------------


class TestStdioResourceHandlers:
    @pytest.mark.asyncio
    async def test_stdio_lists_cortex_resource_template(self, tmp_vault):
        """The stdio MCP server should advertise the cortex:// resource template."""
        from cortex.mcp import server as stdio

        # Inject a minimal services dict; the stdio module keeps it on _services
        from cortex.mcp.resources import ResourceStore

        stdio._services.clear()
        stdio._services.update(
            {
                "vault_path": tmp_vault,
                "graph": None,
                "qmd": None,
                "compiler": None,
                "resource_store": ResourceStore(),
            }
        )

        templates = await stdio.list_resource_templates()
        uris = [t.uriTemplate for t in templates]
        assert any("cortex://resource/{" in u for u in uris), (
            f"Expected cortex://resource/{{...}} template, got {uris}"
        )

    @pytest.mark.asyncio
    async def test_stdio_read_resource_returns_stored_content(self, tmp_vault):
        from cortex.mcp import server as stdio
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore()
        rid = await store.put('{"hello": "world"}', mime_type="application/json")

        stdio._services.clear()
        stdio._services.update(
            {
                "vault_path": tmp_vault,
                "graph": None,
                "qmd": None,
                "compiler": None,
                "resource_store": store,
            }
        )

        body = await stdio.read_resource(f"cortex://resource/{rid}")
        assert '"hello"' in body

    @pytest.mark.asyncio
    async def test_stdio_read_resource_missing_returns_error(self, tmp_vault):
        from cortex.mcp import server as stdio
        from cortex.mcp.resources import ResourceStore

        stdio._services.clear()
        stdio._services.update(
            {
                "vault_path": tmp_vault,
                "graph": None,
                "qmd": None,
                "compiler": None,
                "resource_store": ResourceStore(),
            }
        )

        body = await stdio.read_resource("cortex://resource/does-not-exist")
        import json

        decoded = json.loads(body)
        assert "error" in decoded


class TestResourceStoreMetadata:
    @pytest.mark.asyncio
    async def test_put_records_mime_type(self):
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore()
        resource_id = await store.put('{"x": 1}', mime_type="application/json")

        stored = await store.get(resource_id)
        assert stored is not None
        assert stored.mime_type == "application/json"

    @pytest.mark.asyncio
    async def test_default_mime_type_is_text_plain(self):
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore()
        resource_id = await store.put("hello")

        stored = await store.get(resource_id)
        assert stored is not None
        assert stored.mime_type == "text/plain"

    @pytest.mark.asyncio
    async def test_created_at_is_set_to_now_utc(self):
        from datetime import datetime, timezone

        from cortex.mcp.resources import ResourceStore

        store = ResourceStore()
        before = datetime.now(timezone.utc)
        resource_id = await store.put("x")
        after = datetime.now(timezone.utc)

        stored = await store.get(resource_id)
        assert stored is not None
        assert before <= stored.created_at <= after
        assert stored.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Fallback tool: vault_resource_read — for clients that don't expose MCP
# resources directly (e.g. some Copilot Studio configurations).
# ---------------------------------------------------------------------------


class TestVaultResourceReadTool:
    @pytest.mark.asyncio
    async def test_reads_stored_content_by_id(self, tmp_vault):
        from cortex.mcp.resources import ResourceStore
        from cortex.mcp.tools import handle_vault_resource_read

        store = ResourceStore()
        rid = await store.put('{"x": 1}', mime_type="application/json")

        result = await handle_vault_resource_read(
            resource_id=rid,
            vault_path=tmp_vault,
            resource_store=store,
        )

        assert result["resource_id"] == rid
        assert result["mime_type"] == "application/json"
        assert result["content"] == '{"x": 1}'

    @pytest.mark.asyncio
    async def test_missing_id_returns_error(self, tmp_vault):
        from cortex.mcp.resources import ResourceStore
        from cortex.mcp.tools import handle_vault_resource_read

        result = await handle_vault_resource_read(
            resource_id="does-not-exist",
            vault_path=tmp_vault,
            resource_store=ResourceStore(),
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_accepts_full_uri_as_well(self, tmp_vault):
        """Clients may pass either the bare ID or the full cortex:// URI."""
        from cortex.mcp.resources import ResourceStore
        from cortex.mcp.tools import handle_vault_resource_read

        store = ResourceStore()
        rid = await store.put("hello")

        result = await handle_vault_resource_read(
            resource_id=f"cortex://resource/{rid}",
            vault_path=tmp_vault,
            resource_store=store,
        )

        assert result["resource_id"] == rid
        assert result["content"] == "hello"


# ---------------------------------------------------------------------------
# REST mirror: GET /api/v1/resources/{id}, plus as_resource on /search
# ---------------------------------------------------------------------------


def _make_rest_client(tmp_vault):
    """Build a FastAPI test client with a fresh ResourceStore on app.state.

    We bypass the production lifespan (which spins up the QMD subprocess
    and the vault watcher) and inject minimal state. Each test that needs
    QMD search will mock it on app.state.qmd directly.
    """
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from cortex.api.routes import router
    from cortex.mcp.resources import ResourceStore

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.vault_path = tmp_vault
    app.state.qmd = MagicMock()
    app.state.qmd.search = AsyncMock(return_value=[])
    app.state.graph = MagicMock()
    app.state.graph.get_edges_batch = AsyncMock(return_value={})
    app.state.qmd_debounce = MagicMock()
    app.state.resource_store = ResourceStore()
    return app, TestClient(app)


class TestRestResourceEndpoint:
    def test_get_resource_returns_stored_content(self, tmp_vault):
        import asyncio

        app, client = _make_rest_client(tmp_vault)

        rid = asyncio.new_event_loop().run_until_complete(
            app.state.resource_store.put(
                '{"hello": "world"}', mime_type="application/json"
            )
        )

        resp = client.get(f"/api/v1/resources/{rid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resource_id"] == rid
        assert body["mime_type"] == "application/json"
        assert body["content"] == '{"hello": "world"}'

    def test_get_unknown_resource_returns_404(self, tmp_vault):
        _, client = _make_rest_client(tmp_vault)

        resp = client.get("/api/v1/resources/does-not-exist")
        assert resp.status_code == 404


class TestRestSearchAsResource:
    def test_as_resource_returns_handle(self, tmp_vault):
        from unittest.mock import AsyncMock

        app, client = _make_rest_client(tmp_vault)
        app.state.qmd.search = AsyncMock(
            return_value=[{"path": "wiki/transformers.md", "snippet": "x"}]
        )

        resp = client.get(
            "/api/v1/search",
            params={"q": "attention", "as_resource": "true"},
        )
        assert resp.status_code == 200
        body = resp.json()

        assert "resource_id" in body
        assert body["resource_uri"].startswith("cortex://resource/")
        assert "results" not in body

    def test_default_behavior_unchanged(self, tmp_vault):
        from unittest.mock import AsyncMock

        app, client = _make_rest_client(tmp_vault)
        app.state.qmd.search = AsyncMock(
            return_value=[{"path": "wiki/transformers.md", "snippet": "x"}]
        )

        resp = client.get("/api/v1/search", params={"q": "attention"})
        assert resp.status_code == 200
        body = resp.json()

        assert "resource_id" not in body
        assert "results" in body


# ---------------------------------------------------------------------------
# Settings: CORTEX_RESOURCE_TTL_SECONDS / CORTEX_RESOURCE_MAX_ITEMS
# ---------------------------------------------------------------------------


class TestResourceSettings:
    def test_defaults(self):
        from cortex.config import CortexSettings

        s = CortexSettings()
        assert s.resource_ttl_seconds == 3600
        assert s.resource_max_items == 1000

    def test_overridden_via_env(self, monkeypatch):
        from cortex.config import CortexSettings

        monkeypatch.setenv("CORTEX_RESOURCE_TTL_SECONDS", "300")
        monkeypatch.setenv("CORTEX_RESOURCE_MAX_ITEMS", "50")

        s = CortexSettings()
        assert s.resource_ttl_seconds == 300
        assert s.resource_max_items == 50

    def test_factory_uses_settings(self, monkeypatch):
        """``ResourceStore.from_settings()`` should respect the configured
        TTL and capacity."""
        from datetime import timedelta

        monkeypatch.setenv("CORTEX_RESOURCE_TTL_SECONDS", "42")
        monkeypatch.setenv("CORTEX_RESOURCE_MAX_ITEMS", "7")

        from cortex.config import CortexSettings
        from cortex.mcp.resources import ResourceStore

        store = ResourceStore.from_settings(CortexSettings())
        assert store._default_ttl == timedelta(seconds=42)
        assert store._max_items == 7
