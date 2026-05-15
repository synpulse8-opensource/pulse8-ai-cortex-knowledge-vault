"""FastMCP HTTP server and Starlette/FastAPI integration."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Route

from cortex.compiler.compiler import KnowledgeCompiler
from cortex.config import settings
from cortex.graph.builder import build_graph
from cortex.graph.context import build_context_window
from cortex.graph.engine import GraphEngine
from cortex.mcp.tools import (
    handle_vault_compile,
    handle_vault_ingest,
    handle_vault_link,
    handle_vault_read,
    handle_vault_search,
    handle_vault_write,
)
from cortex.search.qmd import QMDSearch
from cortex.search.qmd_cache import CachedQMDSearch
from cortex.search.qmd_debounce import DebouncedQMDUpdate
from cortex.search.qmd_http import QMDHttpSearch
from cortex.vault.reader import scan_vault_async

logger = logging.getLogger(__name__)


def _build_auth():
    """Build an OIDCProxy auth provider when auth_method is ``oidc``."""
    if not settings.auth_is_oidc:
        return None

    if not settings.oidc_enabled:
        return None

    from fastmcp.server.auth.oidc_proxy import OIDCProxy

    config_url = settings.oidc_config_url

    root_url = (
        settings.oidc_base_url or f"http://localhost:{settings.mcp_sse_port}"
    ).rstrip("/")
    base_url = root_url + "/mcp"

    return OIDCProxy(
        config_url=config_url,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        base_url=base_url,
        issuer_url=root_url,
        forward_resource=False,
        verify_id_token=True,
        required_scopes=["openid", "profile", "email"],
        extra_authorize_params={"scope": "openid profile email"},
        extra_token_params={"scope": "openid profile email"},
    )


async def create_fastmcp_server(
    vault_path: Path,
    services: dict | None = None,
) -> FastMCP:
    """Create a FastMCP server with all Cortex tools registered.

    When *services* is provided the server reuses existing graph, QMD, and
    compiler instances so the MCP endpoint shares state with the REST API
    (and the vault watcher).  When omitted the server bootstraps its own
    services -- useful for standalone ``create_mcp_app()`` deployments.
    """
    auth = _build_auth()

    # this is to fix suppress logging from FastMCP
    os.environ.setdefault("FASTMCP_LOG_LEVEL", "CRITICAL")

    mcp = FastMCP(
        "PULSE8.ai Cortex",
        auth=auth,
    )

    if auth:
        logger.info(
            "MCP OIDC auth enabled — tenant=%s, client_id=%s",
            settings.oidc_tenant_id,
            settings.oidc_client_id,
        )
    else:
        logger.info("MCP auth disabled — all MCP endpoints are unauthenticated")

    if services is None:
        graph = GraphEngine(vault_path / ".cortex" / "graph.json")
        await graph.load()
        notes = await scan_vault_async(vault_path)
        graph = await build_graph(notes, vault_path / ".cortex" / "graph.json", vault_path)

        if settings.qmd_url:
            raw_qmd = QMDHttpSearch(base_url=settings.qmd_url)
        else:
            raw_qmd = QMDSearch(vault_path, settings.qmd_bin)
        try:
            await raw_qmd.initialize()
        except Exception:
            logger.warning("QMD initialization failed — search will be unavailable")
        qmd = CachedQMDSearch(raw_qmd)

        compiler = KnowledgeCompiler(vault_path)
        qmd_debounce = DebouncedQMDUpdate(qmd)

        services = {
            "vault_path": vault_path,
            "graph": graph,
            "qmd": qmd,
            "qmd_debounce": qmd_debounce,
            "compiler": compiler,
        }

    @mcp.tool()
    async def vault_read(path: str) -> str:
        """Read a note by path. Returns frontmatter, content, and graph edges."""
        logger.info("MCP tool=vault_read path=%s", path)
        result = await handle_vault_read(path=path, **services)
        return json.dumps(result, indent=2, default=str)

    @mcp.tool()
    async def vault_write(
        path: str,
        content: str,
        frontmatter: Optional[dict] = None,
        mode: str = "upsert",
        authored_by: str = "human",
        model: Optional[str] = None,
    ) -> str:
        """Create or update a note with provenance tracking. Updates graph and index."""
        logger.info("MCP tool=vault_write path=%s mode=%s authored_by=%s", path, mode, authored_by)
        result = await handle_vault_write(
            path=path,
            content=content,
            frontmatter=frontmatter,
            mode=mode,
            authored_by=authored_by,
            model=model,
            **services,
        )
        return json.dumps(result, indent=2, default=str)

    @mcp.tool()
    async def vault_search(
        query: str,
        mode: str | None = None,
        collection: Optional[str] = None,
        top_k: int = 10,
    ) -> str:
        """Search the vault via QMD (keyword, semantic, or hybrid). Enriched with graph edges."""
        logger.info("MCP tool=vault_search query=%r mode=%s top_k=%d", query, mode, top_k)
        result = await handle_vault_search(
            query=query, mode=mode, collection=collection, top_k=top_k, **services
        )
        return json.dumps(result, indent=2, default=str)

    @mcp.tool()
    async def vault_link(
        action: str,
        source: Optional[str] = None,
        target: Optional[str] = None,
        edge_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Create, query, or delete typed edges in the knowledge graph."""
        logger.info("MCP tool=vault_link action=%s source=%s target=%s edge_type=%s", action, source, target, edge_type)
        result = await handle_vault_link(
            action=action,
            source=source,
            target=target,
            edge_type=edge_type,
            metadata=metadata,
            **services,
        )
        return json.dumps(result, indent=2, default=str)

    @mcp.tool()
    async def vault_context(
        query: str, max_notes: int = 8, max_depth: int = 2
    ) -> str:
        """Build a context window: search, graph BFS expansion, ranked subgraph with contradictions."""
        logger.info("MCP tool=vault_context query=%r max_notes=%d max_depth=%d", query, max_notes, max_depth)
        result = await build_context_window(
            query=query,
            searcher=services["qmd"],
            graph=services["graph"],
            vault_root=services["vault_path"],
            max_notes=max_notes,
            max_depth=max_depth,
            mode=settings.qmd_search_mode,
        )
        response = {
            "notes": [
                {"path": n.path, "title": n.title, "content": n.content[:500]}
                for n in result.notes
            ],
            "edges": [
                {"source": e.source, "target": e.target, "edge_type": e.edge_type.value}
                for e in result.edges
            ],
            "contradictions": result.contradictions,
            "total_nodes_explored": result.total_nodes_explored,
            "total_edges_explored": result.total_edges_explored,
        }
        return json.dumps(response, indent=2)

    @mcp.tool()
    async def vault_ingest(
        filename: str,
        content: Optional[str] = None,
        content_base64: Optional[str] = None,
        source_type: str = "text",
        auto_compile: bool = True,
    ) -> str:
        """Ingest a raw source. Accepts text via content or binary via content_base64."""
        logger.info(
            "MCP tool=vault_ingest filename=%s source_type=%s auto_compile=%s",
            filename, source_type, auto_compile,
        )
        import base64

        file_bytes = None
        if content_base64:
            file_bytes = base64.b64decode(content_base64)

        result = await handle_vault_ingest(
            filename=filename,
            content=content,
            file_bytes=file_bytes,
            source_type=source_type,
            auto_compile=auto_compile,
            **services,
        )
        return json.dumps(result, indent=2, default=str)

    @mcp.tool()
    async def vault_compile(
        force: bool = False,
        path: Optional[str] = None,
    ) -> str:
        """Compile unprocessed raw sources into wiki articles via LLM.

        Use *force* to recompile all sources regardless of enrichment status.
        Use *path* to limit compilation to a single raw file.
        """
        logger.info("MCP tool=vault_compile force=%s path=%s", force, path)
        result = await handle_vault_compile(force=force, path=path, **services)
        return json.dumps(result, indent=2, default=str)

    return mcp


async def create_mcp_app(vault_path: Path) -> Starlette:
    """Create a standalone Starlette app with MCP streamable HTTP at root."""
    mcp = await create_fastmcp_server(vault_path)
    return mcp.http_app(
        path="/",
        stateless_http=True,
        json_response=True,
    )


class ApiKeyGuardMiddleware:
    """ASGI middleware that gates MCP access behind a static API key.

    Used instead of OIDCProxy when ``settings.api_key`` is set.  Requests
    without a valid ``x-api-key`` header receive a ``401`` with a plain
    JSON body — no OAuth discovery, no redirect.
    """

    def __init__(self, app, api_key: str):
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            key_value = headers.get(b"x-api-key", b"").decode()
            if key_value != self.api_key:
                from starlette.responses import JSONResponse

                resp = JSONResponse(
                    {"detail": "Missing or invalid x-api-key header"},
                    status_code=401,
                )
                await resp(scope, receive, send)
                return

        await self.app(scope, receive, send)


def mount_mcp_on_app(app: FastAPI, mcp: FastMCP) -> Starlette:
    """Mount a FastMCP server on an existing FastAPI app at /mcp.

    The MCP sub-app is mounted at ``/mcp``.  When auth is enabled, the
    OIDCProxy creates discovery and operational routes that must be
    accessible at the **server root** (not under ``/mcp``).  This
    function extracts those routes and adds them to the parent app.

    Returns the mounted Starlette sub-app so callers can chain its
    lifespan into the parent app's lifespan.
    """
    mcp_app = mcp.http_app(
        path="/",
        stateless_http=True,
        json_response=True,
    )

    if settings.auth_is_apikey and settings.api_key:
        mount_target = ApiKeyGuardMiddleware(mcp_app, settings.api_key)
        app.mount("/mcp", mount_target)
        logger.info("MCP mounted with API-key guard (no OAuth)")
    else:
        app.mount("/mcp", mcp_app)
        if mcp.auth:
            well_known_routes = mcp.auth.get_well_known_routes(mcp_path="/")
            for route in well_known_routes:
                if isinstance(route, Route):
                    app.routes.insert(0, route)
                    logger.info("Root-level discovery route: %s", route.path)

    return mcp_app
