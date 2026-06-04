"""MCP stdio server — tool definitions and request dispatch."""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from cortex.compiler.compiler import KnowledgeCompiler
from cortex.config import settings
from cortex.graph.builder import build_graph
from cortex.graph.engine import GraphEngine
from cortex.mcp.tools import (
    handle_vault_compile,
    handle_vault_feedback,
    handle_vault_list_feedbacks,
    handle_vault_ingest,
    handle_vault_link,
    handle_vault_read,
    handle_vault_search,
    handle_vault_write,
)
from cortex.search.qmd import QMDSearch
from cortex.search.qmd_cache import CachedQMDSearch
from cortex.search.qmd_http import QMDHttpSearch
from cortex.vault.reader import scan_vault

logger = logging.getLogger(__name__)

app = Server("cortex")

_services: dict[str, Any] = {}


def _tool_definitions() -> list[Tool]:
    return [
        Tool(
            name="vault_read",
            description="Read a note by path. Returns frontmatter, content, and graph edges.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to note in vault"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="vault_write",
            description="Create or update a note with provenance tracking. Updates graph and index.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path for the note"},
                    "content": {"type": "string", "description": "Markdown content body"},
                    "frontmatter": {"type": "object", "description": "YAML frontmatter as dict"},
                    "mode": {"type": "string", "enum": ["create", "update", "upsert"], "default": "upsert"},
                    "authored_by": {"type": "string", "default": "human"},
                    "model": {"type": "string", "description": "LLM model name if AI-authored"},
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="vault_search",
            description="Search the vault via QMD (keyword, semantic, or hybrid). Enriched with graph edges.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "mode": {
                        "type": "string",
                        "enum": ["keyword", "semantic", "hybrid"],
                        "default": "hybrid",
                    },
                    "collection": {
                        "type": "string",
                        "description": "Limit to collection (wiki, agents, sessions, daily)",
                    },
                    "top_k": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="vault_link",
            description="Create, query, or delete typed edges in the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "query", "delete"]},
                    "source": {"type": "string", "description": "Source node path"},
                    "target": {"type": "string", "description": "Target node path"},
                    "edge_type": {
                        "type": "string",
                        "enum": [
                            "links_to", "authored_by", "contradicts",
                            "derived_from", "supersedes", "memory_of",
                            "tagged_with",
                        ],
                    },
                    "metadata": {"type": "object"},
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="vault_feedback",
            description="Submit user feedback. Saved under feedback/ with tags and links to related notes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Feedback text"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags",
                    },
                    "related_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional vault paths to link (must exist)",
                    },
                    "authored_by": {
                        "type": "string",
                        "default": "human",
                        "description": "Author display name (e.g. user email or full name)",
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="vault_list_feedbacks",
            description=(
                "List feedback notes in the vault (metadata only: path, preview, "
                "tags, related_paths, authored_by)."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="vault_context",
            description="Build a context window: search → graph BFS expansion → ranked subgraph with contradictions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for seeding context"},
                    "max_notes": {"type": "integer", "default": 8},
                    "max_depth": {"type": "integer", "default": 2},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="vault_ingest",
            description="Ingest a raw source. Write to raw/ and optionally trigger LLM compilation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Raw source content"},
                    "filename": {"type": "string", "description": "Filename for the raw source"},
                    "source_type": {"type": "string", "enum": ["text", "pdf", "url"], "default": "text"},
                    "auto_compile": {"type": "boolean", "default": True},
                },
                "required": ["content", "filename"],
            },
        ),
        Tool(
            name="vault_compile",
            description="Compile unprocessed raw sources into wiki articles via LLM.",
            inputSchema={
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "default": False,
                        "description": "Recompile all sources regardless of enrichment status",
                    },
                    "path": {
                        "type": "string",
                        "description": "Limit to a single raw file (relative to vault root)",
                    },
                },
            },
        ),
    ]


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available Cortex tools."""
    return _tool_definitions()


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch an incoming tool call to the appropriate handler."""
    handlers = {
        "vault_read": handle_vault_read,
        "vault_write": handle_vault_write,
        "vault_search": handle_vault_search,
        "vault_link": handle_vault_link,
        "vault_ingest": handle_vault_ingest,
        "vault_compile": handle_vault_compile,
        "vault_feedback": handle_vault_feedback,
        "vault_list_feedbacks": handle_vault_list_feedbacks,
    }

    handler = handlers.get(name)
    if not handler:
        if name == "vault_context":
            from cortex.graph.context import build_context_window

            result = await build_context_window(
                query=arguments.get("query", ""),
                searcher=_services["qmd"],
                graph=_services["graph"],
                vault_root=_services["vault_path"],
                max_notes=arguments.get("max_notes", 8),
                max_depth=arguments.get("max_depth", 2),
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
            return [TextContent(type="text", text=json.dumps(response, indent=2))]

        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    result = await handler(**arguments, **_services)
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def run_stdio() -> None:
    """Initialize services and start MCP stdio server."""
    vault_path = settings.vault_path

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

    _services.update({
        "vault_path": vault_path,
        "graph": graph,
        "qmd": qmd,
        "compiler": compiler,
    })

    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())
