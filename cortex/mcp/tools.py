"""Tool handler implementations shared by MCP and REST surfaces."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from cortex.compiler.compiler import KnowledgeCompiler
from cortex.graph.engine import GraphEngine
from cortex.log.audit import log_operation
from cortex.search.qmd import QMDSearch
from cortex.vault.index import rebuild_index
from cortex.vault.models import Edge, EdgeType
from cortex.vault.reader import read_note, scan_vault
from cortex.vault.writer import write_note

logger = logging.getLogger(__name__)


async def handle_vault_read(
    path: str,
    vault_path: Path,
    graph: GraphEngine,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Read a note by path. Returns frontmatter, content, and edges."""
    try:
        note = read_note(vault_path / path, vault_path)
        edges = await graph.get_edges(note.path)
        edge_dicts = [
            {
                "source": e.source,
                "target": e.target,
                "edge_type": e.edge_type.value,
            }
            for e in edges
        ]
        await log_operation(vault_path, "mcp", "vault:read", f"Read {path}")
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
    except FileNotFoundError:
        return {"error": f"Note not found: {path}"}
    except Exception as e:
        logger.exception("vault:read error")
        return {"error": str(e)}


async def handle_vault_write(
    path: str,
    content: str,
    vault_path: Path,
    graph: GraphEngine,
    frontmatter: Optional[dict[str, Any]] = None,
    mode: str = "upsert",
    authored_by: str = "human",
    model: Optional[str] = None,
    qmd: Optional[Any] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create or update a note. Updates graph and vault index."""
    try:
        note = write_note(
            path=vault_path / path,
            vault_root=vault_path,
            content=content,
            frontmatter=frontmatter,
            mode=mode,
            authored_by=authored_by,
            model=model,
        )

        await graph.add_note_node(note)

        for tag in note.tags:
            tag_id = f"tag:{tag}"
            if not graph.graph.has_node(tag_id):
                graph.graph.add_node(tag_id, node_type="tag", title=tag)
            await graph.add_edge(
                Edge(source=note.path, target=tag_id, edge_type=EdgeType.TAGGED_WITH)
            )

        from cortex.vault.reader import resolve_wikilink

        for link in note.wikilinks:
            resolved = resolve_wikilink(link, vault_path)
            if resolved:
                await graph.add_edge(
                    Edge(source=note.path, target=resolved, edge_type=EdgeType.LINKS_TO)
                )

        await rebuild_index(vault_path)
        qmd_debounce = kwargs.get("qmd_debounce")
        if qmd_debounce is not None:
            qmd_debounce.schedule()
        elif qmd is not None:
            try:
                await qmd.update()
            except Exception:
                logger.warning("QMD index refresh failed after write")
        await log_operation(vault_path, authored_by, "vault:write", f"Wrote {path}")

        return {
            "path": note.path,
            "title": note.title,
            "status": "written",
        }
    except Exception as e:
        logger.exception("vault:write error")
        return {"error": str(e)}


async def handle_vault_search(
    query: str,
    vault_path: Path,
    graph: GraphEngine,
    qmd: QMDSearch,
    mode: str | None = None,
    collection: Optional[str] = None,
    top_k: int = 10,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Search via QMD and enrich results with graph edges."""
    from cortex.config import settings

    effective_mode = mode or settings.qmd_search_mode
    try:
        raw_results = await qmd.search(query, mode=effective_mode, collection=collection, top_k=top_k)

        paths = [r.get("path", "") for r in raw_results]
        edges_by_path = await graph.get_edges_batch(paths)

        enriched = []
        for r in raw_results:
            path = r.get("path", "")
            edges = edges_by_path.get(path, [])
            edge_dicts = [
                {"source": e.source, "target": e.target, "edge_type": e.edge_type.value}
                for e in edges
            ]
            enriched.append({**r, "edges": edge_dicts})

        await log_operation(vault_path, "mcp", "vault:search", f"Search: {query}")
        return {"query": query, "mode": mode, "results": enriched}
    except Exception as e:
        logger.exception("vault:search error")
        return {"error": str(e)}


async def handle_vault_link(
    action: str,
    vault_path: Path,
    graph: GraphEngine,
    source: Optional[str] = None,
    target: Optional[str] = None,
    edge_type: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Create, query, or delete typed edges in the graph."""
    try:
        if action == "create":
            if not source or not target or not edge_type:
                return {"error": "source, target, and edge_type are required for create"}
            edge = Edge(
                source=source,
                target=target,
                edge_type=EdgeType(edge_type),
                metadata=metadata or {},
            )
            await graph.add_edge(edge)
            await log_operation(vault_path, "mcp", "vault:link", f"Created {edge_type}: {source} → {target}")
            return {"status": "created", "source": source, "target": target, "edge_type": edge_type}

        if action == "query":
            if not source:
                return {"error": "source is required for query"}
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

        if action == "delete":
            if not source or not target or not edge_type:
                return {"error": "source, target, and edge_type are required for delete"}
            await graph.remove_edge(source, target, EdgeType(edge_type))
            await log_operation(vault_path, "mcp", "vault:link", f"Deleted {edge_type}: {source} → {target}")
            return {"status": "deleted", "source": source, "target": target, "edge_type": edge_type}

        return {"error": f"Unknown action: {action}"}

    except Exception as e:
        logger.exception("vault:link error")
        return {"error": str(e)}


async def handle_vault_ingest(
    filename: str,
    vault_path: Path,
    content: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    source_type: str = "text",  # pylint: disable=unused-argument
    auto_compile: bool = True,
    compiler: Optional[KnowledgeCompiler] = None,
    qmd: Optional[Any] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Write raw source to raw/ and optionally trigger compilation.

    Accepts either ``content`` (text) or ``file_bytes`` (binary).
    """
    if content is None and file_bytes is None:
        return {"error": "Either content or file_bytes must be provided"}
    try:
        raw_path = vault_path / "raw" / filename
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if file_bytes is not None:
            raw_path.write_bytes(file_bytes)
        else:
            raw_path.write_text(content)  # type: ignore[arg-type]

        rel_path = f"raw/{filename}"
        await log_operation(vault_path, "mcp", "vault:ingest", f"Ingested {rel_path}")

        result: dict[str, Any] = {
            "path": rel_path,
            "status": "ingested",
            "compiled": False,
        }

        if auto_compile and compiler:
            created = await compiler.ingest_source(raw_path)
            result["compiled"] = True
            result["wiki_articles"] = [str(p.relative_to(vault_path)) for p in created]
            if created:
                await compiler.compile_cross_references(created)

        qmd_debounce = kwargs.get("qmd_debounce")
        if qmd_debounce is not None:
            qmd_debounce.schedule()
        elif qmd is not None:
            try:
                await qmd.update()
            except Exception:
                logger.warning("QMD index refresh failed after ingest")

        return result
    except Exception as e:
        logger.exception("vault:ingest error")
        return {"error": str(e)}


async def handle_vault_compile(
    vault_path: Path,
    compiler: KnowledgeCompiler,
    qmd: Optional[Any] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compile unprocessed raw sources into wiki articles."""
    try:
        existing_sources: set[str] = set()
        wiki_dir = vault_path / "wiki"
        if wiki_dir.exists():
            for note in scan_vault(vault_path):
                sp = note.frontmatter.get("source_path")
                if sp:
                    existing_sources.add(sp)

        raw_dir = vault_path / "raw"
        if not raw_dir.exists():
            return {"status": "no raw directory", "compiled": 0}

        compiled_count = 0
        all_created: list[str] = []
        all_created_paths: list[Path] = []

        for raw_file in sorted(raw_dir.iterdir()):
            if raw_file.is_dir():
                continue
            rel = str(raw_file.relative_to(vault_path))
            if rel not in existing_sources:
                created = await compiler.ingest_source(raw_file)
                compiled_count += 1
                all_created.extend(str(p.relative_to(vault_path)) for p in created)
                all_created_paths.extend(created)

        if all_created_paths:
            await compiler.compile_cross_references(all_created_paths)

        await rebuild_index(vault_path)
        qmd_debounce = kwargs.get("qmd_debounce")
        if qmd_debounce is not None:
            qmd_debounce.schedule()
        elif qmd is not None:
            try:
                await qmd.update()
            except Exception:
                logger.warning("QMD index refresh failed after compile")
        await log_operation(vault_path, "mcp", "vault:compile", f"Compiled {compiled_count} sources")

        return {
            "status": "compiled",
            "sources_compiled": compiled_count,
            "articles_created": all_created,
        }
    except Exception as e:
        logger.exception("vault:compile error")
        return {"error": str(e)}
