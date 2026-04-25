from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from cortex.graph.engine import GraphEngine
from cortex.log.audit import log_operation
from cortex.search.qmd import QMDSearch
from cortex.vault.index import rebuild_index
from cortex.vault.models import Edge, EdgeType
from cortex.vault.reader import read_note, resolve_wikilink, scan_vault
from cortex.vault.writer import write_note

router = APIRouter()


class WriteNoteBody(BaseModel):
    content: str
    frontmatter: Optional[dict[str, Any]] = None
    mode: str = "upsert"
    authored_by: str = "human"
    model: Optional[str] = None


class CreateLinkBody(BaseModel):
    source: str
    target: str
    edge_type: str
    metadata: Optional[dict[str, Any]] = None


class IngestBody(BaseModel):
    content: str
    filename: str
    source_type: str = "text"
    auto_compile: bool = False


def get_vault_path(request: Request):
    return request.app.state.vault_path


def get_graph(request: Request) -> GraphEngine:
    return request.app.state.graph


def get_qmd(request: Request) -> QMDSearch:
    return request.app.state.qmd


def get_qmd_debounce(request: Request):
    return request.app.state.qmd_debounce


@router.get("/health")
async def health():
    return {"status": "healthy"}


@router.get("/notes/{path:path}")
async def read_note_endpoint(path: str, request: Request):
    vault_path = get_vault_path(request)
    graph = get_graph(request)

    try:
        note = read_note(vault_path / path, vault_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")

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


@router.put("/notes/{path:path}")
async def write_note_endpoint(path: str, body: WriteNoteBody, request: Request):
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

        return {"path": note.path, "title": note.title, "status": "written"}

    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"Note already exists: {path}")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")


@router.get("/search")
async def search_endpoint(
    q: str,
    request: Request,
    mode: str | None = None,
    collection: Optional[str] = None,
    top_k: int = 10,
):
    from cortex.config import settings

    vault_path = get_vault_path(request)
    graph = get_graph(request)
    qmd = get_qmd(request)
    effective_mode = mode or settings.qmd_search_mode

    raw_results = await qmd.search(q, mode=effective_mode, collection=collection, top_k=top_k)

    enriched = []
    for r in raw_results:
        path = r.get("path", "")
        edges = await graph.get_edges(path)
        edge_dicts = [
            {"source": e.source, "target": e.target, "edge_type": e.edge_type.value}
            for e in edges
        ]
        enriched.append({**r, "edges": edge_dicts})

    await log_operation(vault_path, "api", "vault:search", f"Search: {q}")
    return {"query": q, "mode": mode, "results": enriched}


@router.post("/links")
async def create_link_endpoint(body: CreateLinkBody, request: Request):
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


@router.get("/links")
async def query_links_endpoint(
    source: str,
    request: Request,
    edge_type: Optional[str] = None,
):
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


@router.delete("/links/{source:path}")
async def delete_link_endpoint(
    source: str,
    request: Request,
    target: str = "",
    edge_type: str = "",
):
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


@router.get("/graph/stats")
async def graph_stats_endpoint(request: Request):
    graph = get_graph(request)
    return await graph.get_stats()


@router.post("/ingest")
async def ingest_endpoint(body: IngestBody, request: Request):
    vault_path = get_vault_path(request)
    qmd_debounce = get_qmd_debounce(request)

    raw_path = vault_path / "raw" / body.filename
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(body.content)

    rel_path = f"raw/{body.filename}"
    await log_operation(vault_path, "api", "vault:ingest", f"Ingested {rel_path}")

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


@router.post("/compile")
async def compile_endpoint(request: Request):
    vault_path = get_vault_path(request)
    qmd_debounce = get_qmd_debounce(request)

    existing_sources: set[str] = set()
    for note in scan_vault(vault_path):
        sp = note.frontmatter.get("source_path")
        if sp:
            existing_sources.add(sp)

    raw_dir = vault_path / "raw"
    if not raw_dir.exists():
        return {"status": "no raw directory", "compiled": 0}

    from cortex.compiler.compiler import KnowledgeCompiler

    compiler = KnowledgeCompiler(vault_path)
    compiled_count = 0
    all_created: list[str] = []

    for raw_file in sorted(raw_dir.iterdir()):
        if raw_file.is_dir():
            continue
        rel = str(raw_file.relative_to(vault_path))
        if rel not in existing_sources:
            created = await compiler.ingest_source(raw_file)
            compiled_count += 1
            all_created.extend(str(p.relative_to(vault_path)) for p in created)

    await rebuild_index(vault_path)
    qmd_debounce.schedule()
    await log_operation(vault_path, "api", "vault:compile", f"Compiled {compiled_count} sources")

    return {
        "status": "compiled",
        "sources_compiled": compiled_count,
        "articles_created": all_created,
    }
