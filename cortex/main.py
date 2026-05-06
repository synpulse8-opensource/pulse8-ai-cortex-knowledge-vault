"""FastAPI application entry-point and lifespan management."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cortex.api.routes import router
from cortex.config import settings
from cortex.graph.builder import build_graph
from cortex.graph.engine import GraphEngine
from cortex.mcp.http_server import create_fastmcp_server
from cortex.search.qmd import QMDSearch
from cortex.search.qmd_cache import CachedQMDSearch
from cortex.search.qmd_http import QMDHttpSearch
from cortex.search.qmd_debounce import DebouncedQMDUpdate
from cortex.search.qmd_refresh import periodic_qmd_refresh
from cortex.vault.reader import scan_vault_async
from cortex.vault.watcher import VaultWatcher

logger = logging.getLogger(__name__)

_mcp_server = None  # pylint: disable=invalid-name


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mcp_server

    vault_path = settings.vault_path
    app.state.vault_path = vault_path

    graph = GraphEngine(vault_path / ".cortex" / "graph.json")
    await graph.load()
    notes = await scan_vault_async(vault_path)
    app.state.graph = await build_graph(
        notes, vault_path / ".cortex" / "graph.json", vault_path
    )

    if settings.qmd_url:
        raw_qmd = QMDHttpSearch(base_url=settings.qmd_url)
        logger.info("Using QMD HTTP client at %s", settings.qmd_url)
    else:
        raw_qmd = QMDSearch(vault_path, settings.qmd_bin)
    try:
        await raw_qmd.initialize()
    except Exception:
        logger.warning("QMD initialization failed — search will be unavailable")
    qmd = CachedQMDSearch(raw_qmd)
    app.state.qmd = qmd
    app.state.qmd_debounce = DebouncedQMDUpdate(qmd)

    from cortex.compiler.compiler import KnowledgeCompiler

    shared_services = {
        "vault_path": vault_path,
        "graph": app.state.graph,
        "qmd": qmd,
        "qmd_debounce": app.state.qmd_debounce,
        "compiler": KnowledgeCompiler(vault_path),
    }
    _mcp_server = await create_fastmcp_server(vault_path, services=shared_services)
    app.mount("/mcp", _mcp_server.streamable_http_app())
    logger.info("MCP streamable HTTP endpoint mounted at /mcp (shared services)")

    watcher = VaultWatcher(vault_path, app.state.graph)
    await watcher.start()

    refresh_task = None
    if settings.qmd_refresh_interval_seconds > 0 and not settings.qmd_url:
        refresh_task = asyncio.create_task(
            periodic_qmd_refresh(qmd, settings.qmd_refresh_interval_seconds)
        )
        logger.info(
            "Periodic QMD refresh enabled every %ds",
            settings.qmd_refresh_interval_seconds,
        )
    elif settings.qmd_url:
        logger.info(
            "Periodic QMD refresh skipped — QMD container manages its own timer"
        )

    async with _mcp_server.session_manager.run():
        yield

    if refresh_task is not None:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
    await watcher.stop()


app = FastAPI(title="PULSE8.ai Cortex", version="0.2.0", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
