"""Tool handler implementations shared by MCP and REST surfaces."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from cortex.compiler.compiler import KnowledgeCompiler
from cortex.graph.context import build_context_window
from cortex.graph.engine import GraphEngine
from cortex.log.audit import log_operation
from cortex.search.qmd import QMDSearch
from cortex.vault.index import rebuild_index
from cortex.vault.models import Edge, EdgeType
from cortex.vault.paths import build_path_index_from_graph, resolve_note_path
from cortex.vault.layout import raw_dir, raw_rel, wiki_dir
from cortex.vault.reader import read_note, scan_vault
from cortex.vault.daily_log import append_daily_log_entry
from cortex.vault.writer import write_note

# Paths whose writes should NOT mirror into daily/ (avoid self-reference loops
# and noise from internal/feedback files which have their own logs).
_DAILY_LOG_EXCLUDED_PREFIXES = ("daily/", "feedback/", ".cortex/")


def _should_log_to_daily(rel_path: str) -> bool:
    return not rel_path.startswith(_DAILY_LOG_EXCLUDED_PREFIXES)

logger = logging.getLogger(__name__)

# Copilot Studio (and some other MCP clients) reject tool responses above a
# hard payload size. Keep returns comfortably under it.
#
# Max bytes for a single tool's JSON-encoded response. Copilot Studio's
# connector payload limit is 5 MB on public-cloud plans (450 KB on GCC gov);
# see https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-quotas
# We cap at 4 MB to leave headroom for transport/encoding overhead under the
# 5 MB ceiling. If deploying to a GCC tenant, drop this to ~400_000.
_MAX_PAYLOAD_BYTES = 4_000_000


def _truncate_strings(obj: Any, cap: int) -> Any:
    """Recursively cap every string value in a JSON-like structure to *cap* chars.

    Walks dicts and lists; any string longer than *cap* is cut and suffixed
    with "…[truncated]". Non-string scalars (int/float/bool/None) pass through
    unchanged. Dict/list structure is preserved — only string *values* shrink.

    Example
    -------
    >>> _truncate_strings(
    ...     {"title": "RFP", "content": "abcdefghij", "score": 0.9,
    ...      "tags": ["alpha-very-long", "ok"]},
    ...     cap=5,
    ... )
    {'title': 'RFP',                       # ≤ cap, untouched
     'content': 'abcde…[truncated]',       # 10 chars → cut to 5 + suffix
     'score': 0.9,                         # non-string, untouched
     'tags': ['alpha…[truncated]', 'ok']}  # list walked element-wise
    """
    if isinstance(obj, str):
        return obj if len(obj) <= cap else obj[:cap] + "…[truncated]"
    if isinstance(obj, dict):
        return {k: _truncate_strings(v, cap) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_strings(v, cap) for v in obj]
    return obj


def _enforce_payload_size(payload: dict[str, Any], limit: int = _MAX_PAYLOAD_BYTES) -> dict[str, Any]:
    """Guarantee the JSON-encoded payload stays under *limit* bytes.

    Some MCP clients (Copilot Studio) reject tool responses above a hard size.
    Strategy:
      1. If the payload already serializes under *limit*, return it as-is.
      2. Otherwise retry with progressively tighter per-string caps
         (100000 → 50000 → 20000 → 5000 → 2000 → 500). First one that fits
         wins, and the result is flagged ``_truncated: True``. The high first
         steps mean a payload only slightly over the limit loses very little.
      3. If even a 500-char cap is too big (e.g. thousands of results), give
         up on the data and return an error+hint so the client gets a small,
         valid response instead of one it would reject outright.

    Example — payload over the limit (limit shown small for illustration)
    --------------------------------------------------------------------
    Input  (≈ 5KB, limit=120 bytes):
        {"query": "rfp",
         "results": [{"path": "a.md", "content": "<4000-char blob>"},
                     {"path": "b.md", "content": "<4000-char blob>"}]}

    Output (fits after the first cap that gets under the limit):
        {"query": "rfp",
         "results": [{"path": "a.md", "content": "<capped chars>…[truncated]"},
                     {"path": "b.md", "content": "<capped chars>…[truncated]"}],
         "_truncated": True}

    Example — fits immediately, returned unchanged
    ----------------------------------------------
    Input:  {"query": "rfp", "results": []}
    Output: {"query": "rfp", "results": []}          # no _truncated flag

    Example — still too big even at 500 chars (e.g. 10k results)
    -----------------------------------------------------------
    Output: {"error": "payload too large",
             "hint": "retry with as_resource=True, a smaller top_k/max_notes, or fewer results"}
    """
    import json as _json

    if len(_json.dumps(payload, default=str)) <= limit:
        return payload
    # Step down gently from a generous cap so a payload only slightly over the
    # 4 MB limit loses as little as possible; tighten further only if needed.
    for cap in (100_000, 50_000, 20_000, 5_000, 2_000, 500):
        trimmed = _truncate_strings(payload, cap)
        if len(_json.dumps(trimmed, default=str)) <= limit:
            trimmed["_truncated"] = True
            return trimmed
    return {
        "error": "payload too large",
        "hint": "retry with as_resource=True, a smaller top_k/max_notes, or fewer results",
    }


async def handle_vault_read(
    path: str,
    vault_path: Path,
    graph: GraphEngine,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Read a note by path. Returns frontmatter, content, and edges.

    The response is passed through ``_enforce_payload_size`` so it stays under
    the MCP client payload limit. ``**_kwargs`` absorbs any extra client args
    (e.g. a ``max_chars`` sent by older clients) without erroring.
    """
    try:
        path = resolve_note_path(path, vault_path, graph=graph)
        # Offloaded: file I/O + YAML parse would otherwise block the event
        # loop and serialize concurrent MCP requests.
        note = await asyncio.to_thread(read_note, vault_path / path, vault_path)
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
        return _enforce_payload_size({
            "path": note.path,
            "title": note.title,
            "content": note.content,
            "frontmatter": note.frontmatter,
            "node_type": note.node_type.value,
            "wikilinks": note.wikilinks,
            "tags": note.tags,
            "edges": edge_dicts,
        })
    except FileNotFoundError:
        return {"error": f"Note not found: {path}"}
    except IsADirectoryError:
        return {"error": f"Path is a directory, not a note: {path}"}
    except ValueError as e:
        return {"error": str(e)}
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

        return {
            "path": note.path,
            "title": note.title,
            "status": "written",
        }
    except Exception as e:
        logger.exception("vault:write error")
        return {"error": str(e)}


async def handle_vault_feedback(
    content: str,
    vault_path: Path,
    graph: GraphEngine,
    tags: Optional[list[str]] = None,
    related_paths: Optional[list[str]] = None,
    qmd_debounce: Any = None,
    authored_by: str = "human",
    **_kwargs: Any,
) -> dict[str, Any]:
    """Create a feedback note with tags, author name, and optional related paths."""
    from cortex.vault.feedback import create_feedback

    try:
        result = await create_feedback(
            vault_root=vault_path,
            graph=graph,
            qmd_debounce=qmd_debounce,
            content=content,
            tags=tags,
            related_paths=related_paths,
            authored_by=authored_by,
        )
        await log_operation(vault_path, "mcp", "vault:feedback", f"Feedback {result['path']}")
        return result
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("vault:feedback error")
        return {"error": str(e)}


async def handle_vault_list_feedbacks(
    vault_path: Path,
    **_kwargs: Any,
) -> dict[str, Any]:
    """List feedback notes (metadata only, newest first)."""
    from cortex.vault.feedback import list_feedbacks

    try:
        feedbacks = list_feedbacks(vault_path)
        await log_operation(
            vault_path, "mcp", "vault:list_feedbacks", f"Listed {len(feedbacks)} feedback(s)"
        )
        return {"feedbacks": feedbacks, "count": len(feedbacks)}
    except Exception as e:
        logger.exception("vault:list_feedbacks error")
        return {"error": str(e)}


async def handle_vault_search(
    query: str,
    vault_path: Path,
    graph: GraphEngine,
    qmd: QMDSearch,
    mode: str | None = None,
    collection: Optional[str] = None,
    top_k: int = 10,
    as_resource: bool = False,
    resource_store: Optional[Any] = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Search via QMD and enrich results with graph edges.

    When *as_resource* is true and a *resource_store* is wired in, the
    full result payload is stashed server-side and the caller receives
    only a lightweight handle — see the MCP resources-as-inputs pattern
    (https://microsoft.github.io/mcscatblog/posts/mcp-resources-as-tool-inputs/).
    """
    from cortex.config import settings

    effective_mode = mode or settings.qmd_search_mode
    try:
        raw_results = await qmd.search(query, mode=effective_mode, collection=collection, top_k=top_k)

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
            # docid is from qmd. It's meaningless to the user.
            enriched.append(
                {k: v for k, v in r.items() if k != "docid"}
                | {"path": path, "edges": edge_dicts}
            )

        await log_operation(vault_path, "mcp", "vault:search", f"Search: {query}")
        payload = {"query": query, "mode": mode, "results": enriched}
        if as_resource and resource_store is not None:
            import json as _json

            resource_id = await resource_store.put(
                _json.dumps(payload, default=str),
                mime_type="application/json",
            )
            return {
                "resource_id": resource_id,
                "resource_uri": f"cortex://resource/{resource_id}",
                "summary": {
                    "query": query,
                    "mode": mode,
                    "count": len(enriched),
                    "paths": [r["path"] for r in enriched],
                },
            }
        return _enforce_payload_size(payload)
    except Exception as e:
        logger.exception("vault:search error")
        return {"error": str(e)}


_CORTEX_RESOURCE_PREFIX = "cortex://resource/"


async def handle_vault_resource_read(
    resource_id: str,
    vault_path: Path,  # pylint: disable=unused-argument
    resource_store: Optional[Any] = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Read a server-stored resource by ID.

    Fallback for MCP clients that don't surface the resources protocol
    as a first-class concept (some Copilot Studio configurations only
    expose tools to the planning layer). Accepts either the bare hex
    ID or the full ``cortex://resource/{id}`` URI.
    """
    if resource_store is None:
        return {"error": "Resource store not configured"}

    rid = resource_id
    if rid.startswith(_CORTEX_RESOURCE_PREFIX):
        rid = rid[len(_CORTEX_RESOURCE_PREFIX):]

    stored = await resource_store.get(rid)
    if stored is None:
        return {"error": f"Resource not found: {rid}"}
    return {
        "resource_id": rid,
        "mime_type": stored.mime_type,
        "content": stored.content,
    }


async def handle_vault_context(
    query: str,
    vault_path: Path,
    graph: GraphEngine,
    qmd: QMDSearch,
    max_notes: int = 8,
    max_depth: int = 2,
    as_resource: bool = False,
    resource_store: Optional[Any] = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Build a context window (search → BFS expand → rank).

    When *as_resource* is true and a *resource_store* is provided, the
    full context window (notes with up to 500-char snippets, edges,
    contradictions) is stored server-side and only a small handle plus
    summary is returned to the caller.
    """
    from cortex.config import settings

    try:
        result = await build_context_window(
            query=query,
            searcher=qmd,
            graph=graph,
            vault_root=vault_path,
            max_notes=max_notes,
            max_depth=max_depth,
            mode=settings.qmd_search_mode,
        )
        payload = {
            "notes": [
                {"path": n.path, "title": n.title, "content": n.content[:500]}
                for n in result.notes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "edge_type": e.edge_type.value,
                }
                for e in result.edges
            ],
            "contradictions": result.contradictions,
            "total_nodes_explored": result.total_nodes_explored,
            "total_edges_explored": result.total_edges_explored,
        }
        if as_resource and resource_store is not None:
            import json as _json

            resource_id = await resource_store.put(
                _json.dumps(payload, default=str),
                mime_type="application/json",
            )
            return {
                "resource_id": resource_id,
                "resource_uri": f"cortex://resource/{resource_id}",
                "summary": {
                    "query": query,
                    "note_count": len(payload["notes"]),
                    "edge_count": len(payload["edges"]),
                    "total_nodes_explored": result.total_nodes_explored,
                    "total_edges_explored": result.total_edges_explored,
                    "paths": [n["path"] for n in payload["notes"]],
                },
            }
        return _enforce_payload_size(payload)
    except Exception as e:
        logger.exception("vault:context error")
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
            # Lineage: edges created through this tool are manual assertions
            # (human or agent), unless the caller explicitly claims otherwise.
            edge_metadata = dict(metadata or {})
            edge_metadata.setdefault("origin", "manual")
            edge = Edge(
                source=source,
                target=target,
                edge_type=EdgeType(edge_type),
                metadata=edge_metadata,
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
        raw_path = raw_dir(vault_path) / filename
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if file_bytes is not None:
            raw_path.write_bytes(file_bytes)
        else:
            raw_path.write_text(content)  # type: ignore[arg-type]

        rel_path = raw_rel(filename)
        await log_operation(vault_path, "mcp", "vault:ingest", f"Ingested {rel_path}")

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
    force: bool = False,
    path: Optional[str] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compile unprocessed raw sources into wiki articles.

    *force* recompiles all sources regardless of enrichment status.
    *path* limits compilation to a single raw file (relative to vault root).
    Sources whose wiki article has ``enrichment_status: incomplete`` are
    always reprocessed even without *force*.
    """
    try:
        completed_sources: set[str] = set()
        incomplete_sources: set[str] = set()
        wiki_root = wiki_dir(vault_path)
        if wiki_root.exists():
            for note in scan_vault(vault_path):
                sp = note.frontmatter.get("source_path")
                if not sp:
                    continue
                status = note.frontmatter.get("enrichment_status")
                if status == "incomplete":
                    incomplete_sources.add(sp)
                else:
                    completed_sources.add(sp)

        raw_root = raw_dir(vault_path)
        if not raw_root.exists():
            return {"status": "no raw directory", "compiled": 0}

        compiled_count = 0
        all_created: list[str] = []
        all_created_paths: list[Path] = []

        if path:
            raw_files = [vault_path / path]
        else:
            raw_files = sorted(
                f for f in raw_root.iterdir() if not f.is_dir()
            )

        for raw_file in raw_files:
            if not raw_file.exists() or raw_file.is_dir():
                continue
            rel = str(raw_file.relative_to(vault_path))
            needs_compile = (
                force
                or rel in incomplete_sources
                or rel not in completed_sources
            )
            if needs_compile:
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
