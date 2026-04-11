from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cortex.api.routes import router
from cortex.config import settings
from cortex.graph.builder import build_graph
from cortex.graph.engine import GraphEngine
from cortex.mcp.http_server import create_fastmcp_server
from cortex.search.qmd import QMDSearch
from cortex.vault.reader import scan_vault
from cortex.vault.watcher import VaultWatcher

logger = logging.getLogger(__name__)

_mcp_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mcp_server

    vault_path = settings.vault_path
    app.state.vault_path = vault_path

    graph = GraphEngine(vault_path / ".cortex" / "graph.json")
    await graph.load()
    notes = scan_vault(vault_path)
    app.state.graph = await build_graph(
        notes, vault_path / ".cortex" / "graph.json", vault_path
    )

    qmd = QMDSearch(vault_path, settings.qmd_bin)
    try:
        await qmd.initialize()
    except Exception:
        logger.warning("QMD initialization failed — search will be unavailable")
    app.state.qmd = qmd

    _mcp_server = await create_fastmcp_server(vault_path)
    app.mount("/mcp", _mcp_server.streamable_http_app())
    logger.info("MCP streamable HTTP endpoint mounted at /mcp")

    watcher = VaultWatcher(vault_path, app.state.graph)
    await watcher.start()

    async with _mcp_server.session_manager.run():
        yield

    await watcher.stop()


app = FastAPI(title="Cortex", version="0.1.0", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
