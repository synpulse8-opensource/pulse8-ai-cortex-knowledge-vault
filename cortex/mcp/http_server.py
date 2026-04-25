from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount

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
from cortex.vault.reader import scan_vault

logger = logging.getLogger(__name__)


async def create_fastmcp_server(vault_path: Path) -> FastMCP:
    """Create a FastMCP server with all Cortex tools registered."""
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost:*", "127.0.0.1:*", "localhost", "127.0.0.1"],
    )
    mcp = FastMCP(
        "PULSE8.ai Cortex",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        host=settings.mcp_sse_host,
        port=settings.mcp_sse_port,
        transport_security=security,
    )

    graph = GraphEngine(vault_path / ".cortex" / "graph.json")
    await graph.load()
    notes = scan_vault(vault_path)
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
        result = await build_context_window(
            query=query,
            searcher=services["qmd"],
            graph=services["graph"],
            vault_root=services["vault_path"],
            max_notes=max_notes,
            max_depth=max_depth,
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
        content: str,
        filename: str,
        source_type: str = "text",
        auto_compile: bool = False,
    ) -> str:
        """Ingest a raw source. Write to raw/ and optionally trigger LLM compilation."""
        result = await handle_vault_ingest(
            content=content,
            filename=filename,
            source_type=source_type,
            auto_compile=auto_compile,
            **services,
        )
        return json.dumps(result, indent=2, default=str)

    @mcp.tool()
    async def vault_compile() -> str:
        """Compile unprocessed raw sources into wiki articles via LLM."""
        result = await handle_vault_compile(**services)
        return json.dumps(result, indent=2, default=str)

    return mcp


async def create_mcp_app(vault_path: Path) -> Starlette:
    """Create a standalone Starlette app with MCP streamable HTTP at root."""
    mcp = await create_fastmcp_server(vault_path)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp.session_manager.run():
            yield

    return Starlette(
        routes=[Mount("/", app=mcp.streamable_http_app())],
        lifespan=lifespan,
    )


def mount_mcp_on_app(app: FastAPI, mcp: FastMCP) -> None:
    """Mount a FastMCP server on an existing FastAPI app at /mcp.

    Wraps the app's existing lifespan to also run the MCP session manager.
    """
    from fastapi import FastAPI as _FastAPI

    original_lifespan = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def combined_lifespan(a: _FastAPI):
        async with mcp.session_manager.run():
            if original_lifespan:
                async with original_lifespan(a) as state:
                    yield state
            else:
                yield

    app.router.lifespan_context = combined_lifespan
    app.mount("/mcp", mcp.streamable_http_app())
