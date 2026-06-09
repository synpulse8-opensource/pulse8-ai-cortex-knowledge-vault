"""Resolve vault-relative note paths between QMD search output and the filesystem."""
from __future__ import annotations

import re
from pathlib import Path

from cortex.graph.engine import GraphEngine


def _slug_segment(segment: str) -> str:
    """Kebab-case a single path segment (matches compiler wiki slug rules)."""
    slug = re.sub(r"[^a-z0-9]+", "-", segment.lower()).strip("-")
    return slug or "untitled"


def path_lookup_key(rel_path: str) -> str:
    """Normalize a vault-relative path for fuzzy matching.

    QMD may return kebab-case directory segments (e.g. ``Knowledge-vault/01-Clients``)
    while the vault on disk keeps source folder names (``Knowledge vault/01_Clients``).
    Both forms map to the same lookup key.
    """
    parts: list[str] = []
    for part in rel_path.split("/"):
        if not part:
            continue
        if part.endswith(".md") and "." in part:
            stem, suffix = part.rsplit(".", 1)
            parts.append(f"{_slug_segment(stem)}.{suffix}")
        else:
            parts.append(_slug_segment(part))
    return "/".join(parts)


def build_path_index_from_graph(graph: GraphEngine) -> dict[str, str]:
    """Map normalized path keys to graph node ids (canonical vault-relative paths)."""
    index: dict[str, str] = {}
    for node_id in graph.graph.nodes:
        node = str(node_id)
        if not node.endswith(".md"):
            continue
        index[path_lookup_key(node)] = node
    return index


def resolve_note_path(
    path: str,
    vault_root: Path,
    *,
    graph: GraphEngine | None = None,
    path_index: dict[str, str] | None = None,
) -> str:
    """Return the filesystem path for a note, resolving QMD-normalized paths when needed."""
    if not path:
        return path

    if (vault_root / path).is_file():
        return path

    index = path_index
    if index is None and graph is not None:
        index = build_path_index_from_graph(graph)
    if index is not None:
        resolved = index.get(path_lookup_key(path))
        if resolved and (vault_root / resolved).is_file():
            return resolved

    stem = Path(path).stem
    if index is not None and stem:
        stem_matches = [p for p in index.values() if Path(p).stem == stem]
        if len(stem_matches) == 1 and (vault_root / stem_matches[0]).is_file():
            return stem_matches[0]

    return path
