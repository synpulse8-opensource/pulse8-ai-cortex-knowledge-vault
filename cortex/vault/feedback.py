"""Feedback note creation, listing, and deletion."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cortex.graph.engine import GraphEngine
from cortex.notify.teams import notify_new_feedback
from cortex.vault.models import Edge, EdgeType
from cortex.vault.reader import read_note, resolve_wikilink
from cortex.vault.writer import write_note

_PREVIEW_MAX = 120


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_feedback_path(vault_root: Path, now: datetime | None = None) -> Path:
    """Return an unused path under feedback/ with UTC datetime filename."""
    ts = now or _utc_now()
    base = ts.strftime("%Y-%m-%dT%H-%M-%S")
    feedback_dir = vault_root / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)

    candidate = feedback_dir / f"{base}.md"
    if not candidate.exists():
        return candidate

    n = 2
    while True:
        candidate = feedback_dir / f"{base}-{n}.md"
        if not candidate.exists():
            return candidate
        n += 1


def _validate_related_paths(vault_root: Path, related_paths: list[str]) -> None:
    missing = []
    for rel in related_paths:
        p = vault_root / rel
        if not p.exists() or not p.is_file() or p.suffix.lower() != ".md":
            missing.append(rel)
    if missing:
        raise ValueError(f"related_paths not found: {', '.join(missing)}")


def _preview(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_PREVIEW_MAX]
    return ""


async def _add_graph_edges(
    graph: GraphEngine,
    note_path: str,
    tags: list[str],
    related_paths: list[str],
    wikilinks: list[str],
    vault_root: Path,
) -> None:
    for tag in tags:
        tag_id = f"tag:{tag}"
        if not graph.graph.has_node(tag_id):
            graph.graph.add_node(tag_id, node_type="tag", title=tag)
        await graph.add_edge(
            Edge(source=note_path, target=tag_id, edge_type=EdgeType.TAGGED_WITH)
        )

    for target in related_paths:
        await graph.add_edge(
            Edge(source=note_path, target=target, edge_type=EdgeType.LINKS_TO)
        )

    for link in wikilinks:
        resolved = resolve_wikilink(link, vault_root)
        if resolved and resolved not in related_paths:
            await graph.add_edge(
                Edge(source=note_path, target=resolved, edge_type=EdgeType.LINKS_TO)
            )


async def create_feedback(
    vault_root: Path,
    graph: GraphEngine,
    qmd_debounce: Any,
    content: str,
    tags: Optional[list[str]] = None,
    related_paths: Optional[list[str]] = None,
    authored_by: str = "human",
) -> dict[str, Any]:
    """Create a feedback note with graph edges and QMD debounce."""
    if not content or not content.strip():
        raise ValueError("content is required")

    tags = tags or []
    related_paths = related_paths or []
    _validate_related_paths(vault_root, related_paths)

    now = _utc_now()
    path = generate_feedback_path(vault_root, now=now)
    title = f"Feedback {now.strftime('%Y-%m-%dT%H:%M:%SZ')}"

    frontmatter = {
        "type": "feedback",
        "title": title,
        "status": "OPEN",
        "tags": tags,
        "related_paths": related_paths,
    }

    note = write_note(
        path=path,
        vault_root=vault_root,
        content=content.strip(),
        frontmatter=frontmatter,
        mode="create",
        authored_by=authored_by,
    )

    async with graph.batch():
        await graph.add_note_node(note)
        await _add_graph_edges(
            graph, note.path, tags, related_paths, note.wikilinks, vault_root
        )

    if qmd_debounce is not None:
        qmd_debounce.schedule()

    created_at = note.frontmatter.get("created_at")
    feedback_status = str(note.frontmatter.get("status") or "OPEN")

    await notify_new_feedback(
        path=note.path,
        title=note.title,
        content=content.strip(),
        tags=tags,
        related_paths=related_paths,
        status=feedback_status,
        authored_by=authored_by,
        created_at=str(created_at) if created_at else None,
    )

    return {
        "path": note.path,
        "title": note.title,
        "created_at": created_at,
        "authored_by": note.provenance.authored_by,
        "tags": tags,
        "related_paths": related_paths,
        "status": feedback_status,
    }


def list_feedbacks(vault_root: Path) -> list[dict[str, Any]]:
    """Return metadata for all feedback notes, newest first."""
    feedback_dir = vault_root / "feedback"
    if not feedback_dir.is_dir():
        return []

    items: list[dict[str, Any]] = []
    for md_file in sorted(feedback_dir.glob("*.md"), reverse=True):
        note = read_note(md_file, vault_root)
        items.append({
            "path": note.path,
            "created_at": note.frontmatter.get("created_at"),
            "authored_by": note.provenance.authored_by,
            "preview": _preview(note.content),
            "tags": note.tags,
            "related_paths": note.frontmatter.get("related_paths", []),
        })
    return items


async def read_feedback(
    vault_root: Path,
    graph: GraphEngine,
    filename: str,
) -> dict[str, Any]:
    """Read one feedback note with graph edges."""
    path = vault_root / "feedback" / filename
    note = read_note(path, vault_root)
    edges = await graph.get_edges(note.path)
    return {
        "path": note.path,
        "title": note.title,
        "content": note.content,
        "frontmatter": note.frontmatter,
        "node_type": note.node_type.value,
        "tags": note.tags,
        "related_paths": note.frontmatter.get("related_paths", []),
        "edges": [
            {"source": e.source, "target": e.target, "edge_type": e.edge_type.value}
            for e in edges
        ],
    }


async def delete_feedback(
    vault_root: Path,
    graph: GraphEngine,
    qmd_debounce: Any,
    filename: str,
) -> dict[str, Any]:
    """Delete a feedback file and remove its graph node."""
    path = vault_root / "feedback" / filename
    if not path.exists():
        raise FileNotFoundError(f"Feedback not found: feedback/{filename}")

    rel_path = str(path.relative_to(vault_root))
    path.unlink()
    await graph.remove_note_node(rel_path)

    if qmd_debounce is not None:
        qmd_debounce.schedule()

    return {"status": "deleted", "path": rel_path}
