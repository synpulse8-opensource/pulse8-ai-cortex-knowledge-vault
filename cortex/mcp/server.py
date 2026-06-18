"""MCP stdio server — tool definitions and request dispatch."""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ResourceTemplate, TextContent, Tool

from cortex.compiler.compiler import KnowledgeCompiler
from cortex.config import settings
from cortex.graph.builder import build_graph
from cortex.graph.engine import GraphEngine
from cortex.mcp.resources import ResourceStore
from cortex.mcp.tools import (
    handle_vault_compile,
    handle_vault_context,
    handle_vault_feedback,
    handle_vault_list_feedbacks,
    handle_vault_ingest,
    handle_vault_link,
    handle_vault_read,
    handle_vault_resource_read,
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
                    "as_resource": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return a server-side resource handle "
                            "(cortex://resource/{id}) instead of inlining "
                            "the full results — use for token-heavy queries."
                        ),
                    },
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
                    "as_resource": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return a server-side resource handle "
                            "(cortex://resource/{id}) instead of inlining "
                            "the full context window — use for large graphs."
                        ),
                    },
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
            name="vault_resource_read",
            description=(
                "Read a server-stored resource by ID. Fallback for MCP "
                "clients that do not expose the resources protocol "
                "natively. Accepts either the bare hex ID or the full "
                "cortex://resource/{id} URI."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": "Resource ID or cortex://resource/{id} URI",
                    },
                },
                "required": ["resource_id"],
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
        "vault_context": handle_vault_context,
        "vault_ingest": handle_vault_ingest,
        "vault_compile": handle_vault_compile,
        "vault_feedback": handle_vault_feedback,
        "vault_list_feedbacks": handle_vault_list_feedbacks,
        "vault_resource_read": handle_vault_resource_read,
    }

    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    result = await handler(**arguments, **_services)
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


@app.list_resource_templates()
async def list_resource_templates() -> list[ResourceTemplate]:
    """Advertise the cortex://resource/{id} template to MCP clients."""
    return [
        ResourceTemplate(
            uriTemplate="cortex://resource/{resource_id}",
            name="cortex-resource",
            description=(
                "Read a server-stored resource produced by a Cortex tool "
                "(e.g. vault_search or vault_context invoked with "
                "as_resource=True). Keeps token-heavy payloads out of the "
                "LLM context window until they are actually needed."
            ),
            mimeType="application/json",
        ),
    ]


_CORTEX_RESOURCE_PREFIX = "cortex://resource/"


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Resolve a cortex://resource/{id} URI from the in-memory store."""
    if not isinstance(uri, str):
        uri = str(uri)
    if not uri.startswith(_CORTEX_RESOURCE_PREFIX):
        return json.dumps({"error": f"Unsupported resource URI: {uri}"})

    resource_id = uri[len(_CORTEX_RESOURCE_PREFIX):]
    store: ResourceStore | None = _services.get("resource_store")
    if store is None:
        return json.dumps({"error": "Resource store not configured"})

    stored = await store.get(resource_id)
    if stored is None:
        return json.dumps({"error": f"Resource not found: {resource_id}"})
    return stored.content


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
    resource_store = ResourceStore.from_settings(settings)

    _services.update({
        "vault_path": vault_path,
        "graph": graph,
        "qmd": qmd,
        "compiler": compiler,
        "resource_store": resource_store,
    })

    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())
