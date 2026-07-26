"""REST API route handlers for the Cortex vault."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from cortex.config import settings
from cortex.vault.layout import raw_dir, raw_rel
from cortex.graph.engine import GraphEngine
from cortex.log.audit import log_operation
from cortex.mcp.tools import (
    handle_vault_explain,
    handle_vault_impact,
    handle_vault_path,
    handle_vault_trace,
)
from cortex.search.qmd import QMDSearch
from cortex.vault.daily_log import append_daily_log_entry
from cortex.vault.index import rebuild_index
from cortex.vault.models import Edge, EdgeType
from cortex.vault.paths import build_path_index_from_graph, resolve_note_path
from cortex.vault.reader import read_note, resolve_wikilink
from cortex.vault.writer import write_note

# Mirrors `_DAILY_LOG_EXCLUDED_PREFIXES` in cortex.mcp.tools. Kept in sync
# manually because REST routes do not delegate to the MCP handlers.
_DAILY_LOG_EXCLUDED_PREFIXES = ("daily/", "feedback/", ".cortex/")


def _should_log_to_daily(rel_path: str) -> bool:
    return not rel_path.startswith(_DAILY_LOG_EXCLUDED_PREFIXES)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["vault"])


class WriteNoteBody(BaseModel):
    """Request body for creating or updating a note."""
    content: str
    frontmatter: Optional[dict[str, Any]] = None
    mode: str = "upsert"
    authored_by: str = "human"
    model: Optional[str] = None


class CreateLinkBody(BaseModel):
    """Request body for creating a graph edge."""
    source: str
    target: str
    edge_type: str
    metadata: Optional[dict[str, Any]] = None


class IngestBody(BaseModel):
    """Request body for ingesting a raw source."""
    content: str
    filename: str
    source_type: str = "text"
    auto_compile: bool = True


class BulkIngestBody(BaseModel):
    """Request body for bulk ingestion from a server-local directory."""
    source_dir: str
    concurrency: int = 4
    force: bool = False
    dry_run: bool = False
    prune: bool = True


class FeedbackBody(BaseModel):
    """Request body for creating feedback."""
    content: str
    tags: list[str] | None = None
    related_paths: list[str] | None = None
    authored_by: str | None = None


class TokenExchangeBody(BaseModel):
    """Request body for exchanging an authorization code for tokens."""
    code: str
    redirect_uri: str = ""


def get_vault_path(request: Request):
    """Extract the vault path from application state."""
    return request.app.state.vault_path


def get_graph(request: Request) -> GraphEngine:
    """Extract the graph engine from application state."""
    return request.app.state.graph


def get_qmd(request: Request) -> QMDSearch:
    """Extract the QMD search backend from application state."""
    return request.app.state.qmd


def get_qmd_debounce(request: Request):
    """Extract the debounced QMD updater from application state."""
    return request.app.state.qmd_debounce


@router.get("/health", tags=["health"])
async def health():
    """Liveness probe."""
    return {"status": "healthy"}


@router.get("/login", tags=["auth"])
async def login(redirect_uri: str = ""):
    """Start the Authorization Code Flow.

    Returns the Microsoft Entra ID authorization URL.  The caller should
    open this URL in a browser so the user can authenticate (with MFA if
    required).  After login, Microsoft redirects to the callback endpoint.

    Pass ``redirect_uri`` if the client wants the final redirect to go
    somewhere other than the server's default callback URL.
    """
    if not settings.oidc_enabled:
        raise HTTPException(status_code=501, detail="OIDC authentication is not configured")

    import secrets
    import urllib.parse

    state = secrets.token_urlsafe(32)
    callback = redirect_uri or settings.oidc_redirect_uri
    scope = f"{settings.oidc_client_id}/.default openid profile"

    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "redirect_uri": callback,
        "scope": scope,
        "response_mode": "query",
        "state": state,
    }

    auth_url = f"{settings.oidc_authorize_url}?{urllib.parse.urlencode(params)}"

    return {
        "authorization_url": auth_url,
        "state": state,
        "redirect_uri": callback,
    }


@router.get("/auth/callback", tags=["auth"])
async def auth_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):  # pylint: disable=unused-argument
    """OAuth 2.0 callback endpoint.

    Microsoft redirects here after the user authenticates.  Exchanges
    the authorization code for tokens and returns them.
    """
    if error:
        raise HTTPException(status_code=401, detail=error_description or error)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    if not settings.oidc_enabled:
        raise HTTPException(status_code=501, detail="OIDC authentication is not configured")

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": f"{settings.oidc_client_id}/.default openid profile",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(settings.oidc_token_url, data=data, timeout=15)

    if resp.status_code != 200:
        detail = resp.json().get("error_description", resp.text)
        logger.warning("Token exchange failed: %s", detail)
        raise HTTPException(status_code=401, detail=detail)

    token_data = resp.json()
    return {
        "access_token": token_data.get("access_token"),
        "token_type": token_data.get("token_type", "Bearer"),
        "expires_in": token_data.get("expires_in"),
        "refresh_token": token_data.get("refresh_token"),
        "scope": token_data.get("scope"),
    }


@router.post("/login", tags=["auth"])
async def login_token_exchange(body: TokenExchangeBody):
    """Exchange an authorization code for tokens (programmatic variant).

    Use this when the client already has an authorization code (e.g. from
    a browser redirect) and wants to exchange it server-side.
    """
    if not settings.oidc_enabled:
        raise HTTPException(status_code=501, detail="OIDC authentication is not configured")

    redirect_uri = body.redirect_uri or settings.oidc_redirect_uri

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
        "code": body.code,
        "redirect_uri": redirect_uri,
        "scope": f"{settings.oidc_client_id}/.default openid profile",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(settings.oidc_token_url, data=data, timeout=15)

    if resp.status_code != 200:
        detail = resp.json().get("error_description", resp.text)
        logger.warning("Token exchange failed: %s", detail)
        raise HTTPException(status_code=401, detail=detail)

    token_data = resp.json()
    return {
        "access_token": token_data.get("access_token"),
        "token_type": token_data.get("token_type", "Bearer"),
        "expires_in": token_data.get("expires_in"),
        "refresh_token": token_data.get("refresh_token"),
        "scope": token_data.get("scope"),
    }


@router.get("/notes/{path:path}", tags=["notes"])
async def read_note_endpoint(path: str, request: Request):
    """Read a note by vault-relative path."""
    vault_path = get_vault_path(request)
    graph = get_graph(request)

    try:
        path = resolve_note_path(path, vault_path, graph=graph)
        note = read_note(vault_path / path, vault_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}") from exc
    except IsADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    edges = await graph.get_edges(note.path)
    edge_dicts = [
        {"source": e.source, "target": e.target, "edge_type": e.edge_type.value}
        for e in edges
    ]

    await log_operation(vault_path, "api", "vault:read", f"Read {path}")

    return {
        "path": note.path,
        "title": note.title,
        "content": note.content,
        "frontmatter": note.frontmatter,
        "node_type": note.node_type.value,
        "wikilinks": note.wikilinks,
        "tags": note.tags,
        "edges": edge_dicts,
    }


@router.put("/notes/{path:path}", tags=["notes"])
async def write_note_endpoint(path: str, body: WriteNoteBody, request: Request):
    """Create or update a note with provenance tracking."""
    vault_path = get_vault_path(request)
    graph = get_graph(request)
    qmd_debounce = get_qmd_debounce(request)

    try:
        note = write_note(
            path=vault_path / path,
            vault_root=vault_path,
            content=body.content,
            frontmatter=body.frontmatter,
            mode=body.mode,
            authored_by=body.authored_by,
            model=body.model,
        )

        await graph.add_note_node(note)

        for tag in note.tags:
            tag_id = f"tag:{tag}"
            if not graph.graph.has_node(tag_id):
                graph.graph.add_node(tag_id, node_type="tag", title=tag)
            await graph.add_edge(
                Edge(source=note.path, target=tag_id, edge_type=EdgeType.TAGGED_WITH)
            )

        for link in note.wikilinks:
            resolved = resolve_wikilink(link, vault_path)
            if resolved:
                await graph.add_edge(
                    Edge(source=note.path, target=resolved, edge_type=EdgeType.LINKS_TO)
                )

        await rebuild_index(vault_path)
        qmd_debounce.schedule()
        await log_operation(vault_path, body.authored_by, "vault:write", f"Wrote {path}")

        if _should_log_to_daily(note.path):
            try:
                await append_daily_log_entry(
                    vault_path,
                    event="vault:write",
                    summary=f"Wrote {note.path}",
                    wiki_path=note.path,
                )
            except Exception:
                logger.exception("daily-log append failed for %s", note.path)

        return {"path": note.path, "title": note.title, "status": "written"}

    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"Note already exists: {path}") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}") from exc


@router.get("/search", tags=["search"])
async def search_endpoint(
    q: str,
    request: Request,
    mode: str | None = None,
    collection: Optional[str] = None,
    top_k: int = 10,
    as_resource: bool = False,
):
    """Search the vault via QMD and return graph-enriched results.

    Set ``as_resource=true`` to stash the full payload as a server-side
    MCP resource and receive only ``{resource_id, resource_uri, summary}``
    — see the MCP resources-as-tool-inputs pattern.
    """
    vault_path = get_vault_path(request)
    graph = get_graph(request)
    qmd = get_qmd(request)
    effective_mode = mode or settings.qmd_search_mode

    raw_results = await qmd.search(q, mode=effective_mode, collection=collection, top_k=top_k)

    path_index = build_path_index_from_graph(graph)
    resolved_paths = [
        resolve_note_path(r.get("path", ""), vault_path, path_index=path_index)
        for r in raw_results
    ]
    edges_by_path = await graph.get_edges_batch(resolved_paths)

    enriched = []
    for r, path in zip(raw_results, resolved_paths, strict=True):
        edges = edges_by_path.get(path, [])
        edge_dicts = [
            {"source": e.source, "target": e.target, "edge_type": e.edge_type.value}
            for e in edges
        ]
        enriched.append({**r, "path": path, "edges": edge_dicts})

    await log_operation(vault_path, "api", "vault:search", f"Search: {q}")
    payload = {"query": q, "mode": mode, "results": enriched}

    if as_resource:
        store = getattr(request.app.state, "resource_store", None)
        if store is None:
            raise HTTPException(
                status_code=503,
                detail="Resource store not configured on this server",
            )
        import json as _json

        resource_id = await store.put(
            _json.dumps(payload, default=str),
            mime_type="application/json",
        )
        return {
            "resource_id": resource_id,
            "resource_uri": f"cortex://resource/{resource_id}",
            "summary": {
                "query": q,
                "mode": mode,
                "count": len(enriched),
                "paths": [r["path"] for r in enriched],
            },
        }
    return payload


@router.get("/resources/{resource_id}", tags=["resources"])
async def read_resource_endpoint(resource_id: str, request: Request):
    """Read a server-stored MCP resource produced by an ``as_resource=true``
    tool call. Returns 404 if the ID is unknown or has expired.
    """
    store = getattr(request.app.state, "resource_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Resource store not configured on this server",
        )

    # Accept either the bare ID or the full URI in the path
    rid = resource_id
    if rid.startswith("cortex://resource/"):
        rid = rid[len("cortex://resource/"):]

    stored = await store.get(rid)
    if stored is None:
        raise HTTPException(
            status_code=404,
            detail=f"Resource not found: {rid}",
        )
    return {
        "resource_id": rid,
        "mime_type": stored.mime_type,
        "content": stored.content,
    }


@router.post("/links", tags=["graph"])
async def create_link_endpoint(body: CreateLinkBody, request: Request):
    """Create a typed edge in the knowledge graph."""
    vault_path = get_vault_path(request)
    graph = get_graph(request)

    edge = Edge(
        source=body.source,
        target=body.target,
        edge_type=EdgeType(body.edge_type),
        metadata=body.metadata or {},
    )
    await graph.add_edge(edge)
    await log_operation(
        vault_path, "api", "vault:link",
        f"Created {body.edge_type}: {body.source} → {body.target}",
    )
    return {"status": "created", "source": body.source, "target": body.target, "edge_type": body.edge_type}


@router.get("/links", tags=["graph"])
async def query_links_endpoint(
    source: str,
    request: Request,
    edge_type: Optional[str] = None,
):
    """Query edges from a source node."""
    graph = get_graph(request)
    edge_types = [EdgeType(edge_type)] if edge_type else None
    edges = await graph.get_edges(source, edge_types=edge_types)
    return {
        "source": source,
        "edges": [
            {
                "source": e.source,
                "target": e.target,
                "edge_type": e.edge_type.value,
                "metadata": e.metadata,
            }
            for e in edges
        ],
    }


@router.delete("/links/{source:path}", tags=["graph"])
async def delete_link_endpoint(
    source: str,
    request: Request,
    target: str = "",
    edge_type: str = "",
):
    """Delete a typed edge from the knowledge graph."""
    vault_path = get_vault_path(request)
    graph = get_graph(request)

    if not target or not edge_type:
        raise HTTPException(status_code=400, detail="target and edge_type query params required")

    await graph.remove_edge(source, target, EdgeType(edge_type))
    await log_operation(
        vault_path, "api", "vault:link",
        f"Deleted {edge_type}: {source} → {target}",
    )
    return {"status": "deleted", "source": source, "target": target, "edge_type": edge_type}


@router.get("/graph/stats", tags=["graph"])
async def graph_stats_endpoint(request: Request):
    """Return graph node/edge statistics."""
    graph = get_graph(request)
    return await graph.get_stats()


@router.get("/trace/{path:path}", tags=["graph"])
async def trace_endpoint(path: str, request: Request):
    """Trace a note's lineage: provenance, raw sources, and labeled edges."""
    vault_path = get_vault_path(request)
    graph = get_graph(request)

    result = await handle_vault_trace(path=path, vault_path=vault_path, graph=graph)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/graph/path", tags=["graph"])
async def graph_path_endpoint(
    source: str, target: str, request: Request, max_paths: int = 3
):
    """Find shortest paths between two notes over the typed graph."""
    result = await handle_vault_path(
        source=source,
        target=target,
        max_paths=max_paths,
        vault_path=get_vault_path(request),
        graph=get_graph(request),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/graph/impact", tags=["graph"])
async def graph_impact_endpoint(path: str, request: Request, max_depth: int = 5):
    """Walk all notes downstream of a note (change-impact analysis)."""
    result = await handle_vault_impact(
        path=path,
        max_depth=max_depth,
        vault_path=get_vault_path(request),
        graph=get_graph(request),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/explain/{path:path}", tags=["graph"])
async def explain_endpoint(path: str, request: Request):
    """Explain a note: summary, provenance, sources, and connections."""
    result = await handle_vault_explain(
        path=path,
        vault_path=get_vault_path(request),
        graph=get_graph(request),
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/ingest", tags=["ingest"])
async def ingest_endpoint(body: IngestBody, request: Request):
    """Ingest a raw source file and optionally compile it."""
    vault_path = get_vault_path(request)
    qmd_debounce = get_qmd_debounce(request)

    raw_path = raw_dir(vault_path) / body.filename
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(body.content)

    rel_path = raw_rel(body.filename)
    await log_operation(vault_path, "api", "vault:ingest", f"Ingested {rel_path}")

    try:
        await append_daily_log_entry(
            vault_path,
            event="vault:ingest",
            summary=f"Ingested {rel_path}",
        )
    except Exception:
        logger.exception("daily-log append failed for ingest %s", rel_path)

    result: dict[str, Any] = {
        "path": rel_path,
        "status": "ingested",
        "compiled": False,
    }

    if body.auto_compile:
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(vault_path)
        created = await compiler.ingest_source(raw_path)
        result["compiled"] = True
        result["wiki_articles"] = [str(p.relative_to(vault_path)) for p in created]

    qmd_debounce.schedule()

    return result


@router.post("/ingest/upload", tags=["ingest"])
async def ingest_upload_endpoint(
    request: Request,
    file: UploadFile = File(...),
    auto_compile: bool = Form(True),
):
    """Ingest a file via multipart upload. Supports any format MarkItDown handles."""
    vault_path = get_vault_path(request)
    qmd_debounce = get_qmd_debounce(request)

    file_bytes = await file.read()
    filename = file.filename or "upload"

    raw_path = raw_dir(vault_path) / filename
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(file_bytes)

    rel_path = raw_rel(filename)
    await log_operation(vault_path, "api", "vault:ingest", f"Ingested {rel_path}")

    try:
        await append_daily_log_entry(
            vault_path,
            event="vault:ingest",
            summary=f"Ingested {rel_path}",
        )
    except Exception:
        logger.exception("daily-log append failed for ingest %s", rel_path)

    result: dict[str, Any] = {
        "path": rel_path,
        "status": "ingested",
        "compiled": False,
    }

    if auto_compile:
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(vault_path)
        created = await compiler.ingest_source(raw_path)
        result["compiled"] = True
        result["wiki_articles"] = [str(p.relative_to(vault_path)) for p in created]

    qmd_debounce.schedule()

    return result


@router.post("/compile", tags=["ingest"], status_code=202)
async def compile_endpoint(request: Request):
    """Start compiling all unprocessed raw sources (runs in background).

    Returns 202 immediately. Only one compile can run at a time.
    Poll GET /compile/status for progress.
    """
    from cortex.compiler.compiler import start_compile

    vault_path = get_vault_path(request)
    qmd_debounce = get_qmd_debounce(request)

    try:
        result = start_compile(vault_path, qmd_debounce)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return result


@router.get("/compile/status", tags=["ingest"])
async def compile_status_endpoint():
    """Check the status of the current or last compile task."""
    from cortex.compiler.compiler import get_compile_status

    return get_compile_status()


@router.post("/bulk-ingest", tags=["ingest"])
async def bulk_ingest_endpoint(body: BulkIngestBody, request: Request):
    """Bulk-ingest files from a server-local directory."""
    from cortex.compiler.bulk import BulkIngestor
    logger.info("Bulk ingest request received: %s", body)

    vault_path = get_vault_path(request)
    source_dir = Path(body.source_dir).resolve()

    if not source_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Source directory does not exist: {body.source_dir}",
        )

    ingestor = BulkIngestor(
        vault_path=vault_path,
        source_dir=source_dir,
        concurrency=body.concurrency,
        force=body.force,
        dry_run=body.dry_run,
        prune=body.prune,
    )

    from cortex.compiler.bulk_coordination import BulkIngestBusyError

    logger.info("Starting bulk ingest with ingestor: %s", ingestor)
    try:
        result = await ingestor.run(lock_mode="fail", lock_scope="source")
    except BulkIngestBusyError as exc:
        target = exc.source_dir or exc.vault_path
        raise HTTPException(
            status_code=409,
            detail=(
                f"Bulk ingest already running for {target}. "
                "Retry after the current job finishes, or use a different source_dir."
            ),
        ) from exc

    logger.info("Bulk ingest result: %s", result)

    await log_operation(
        vault_path, "api", "vault:bulk-ingest",
        f"Bulk ingested from {body.source_dir}: "
        f"{len(result['copied'])} copied, {len(result['skipped'])} skipped",
    )

    return result


@router.get("/feedbacks", tags=["feedback"])
async def list_feedbacks_endpoint(request: Request):
    """List feedback notes (metadata only)."""
    from cortex.vault.feedback import list_feedbacks

    vault_path = get_vault_path(request)
    return {"feedbacks": list_feedbacks(vault_path)}


@router.get("/feedbacks/{filename}", tags=["feedback"])
async def read_feedback_endpoint(filename: str, request: Request):
    """Read a single feedback note with graph edges."""
    from cortex.vault.feedback import read_feedback

    vault_path = get_vault_path(request)
    graph = get_graph(request)
    try:
        return await read_feedback(vault_path, graph, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/feedbacks", tags=["feedback"])
async def create_feedback_endpoint(body: FeedbackBody, request: Request):
    """Create a feedback note."""
    from cortex.auth.identity import author_from_claims
    from cortex.vault.feedback import create_feedback

    vault_path = get_vault_path(request)
    graph = get_graph(request)
    qmd_debounce = get_qmd_debounce(request)

    claims = getattr(request.state, "user_claims", None)
    authored_by = (
        body.authored_by
        or author_from_claims(claims)
        or "api"
    )

    try:
        result = await create_feedback(
            vault_root=vault_path,
            graph=graph,
            qmd_debounce=qmd_debounce,
            content=body.content,
            tags=body.tags,
            related_paths=body.related_paths,
            authored_by=authored_by,
        )
        await log_operation(vault_path, "api", "vault:feedback", f"Feedback {result['path']}")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/feedbacks/{filename}", tags=["feedback"])
async def delete_feedback_endpoint(filename: str, request: Request):
    """Delete a feedback note."""
    from cortex.vault.feedback import delete_feedback

    vault_path = get_vault_path(request)
    graph = get_graph(request)
    qmd_debounce = get_qmd_debounce(request)

    try:
        return await delete_feedback(
            vault_root=vault_path,
            graph=graph,
            qmd_debounce=qmd_debounce,
            filename=filename,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
