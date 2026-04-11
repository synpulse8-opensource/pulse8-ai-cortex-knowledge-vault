from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import frontmatter

from cortex.vault.models import NodeType, Note, Provenance

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def extract_wikilinks(content: str) -> list[str]:
    """Extract wikilink targets from markdown content."""
    return _WIKILINK_RE.findall(content)


def infer_node_type(path: str, fm: dict[str, Any]) -> NodeType:
    """Determine the NodeType from path conventions and frontmatter."""
    if "type" in fm:
        try:
            return NodeType(fm["type"])
        except ValueError:
            pass

    if path.startswith("raw/"):
        return NodeType.RAW_SOURCE
    if path.endswith(".agent.md"):
        return NodeType.AGENT_DEF
    if path.endswith(".memory.md"):
        return NodeType.MEMORY
    if path.endswith(".session.md"):
        return NodeType.SESSION

    return NodeType.NOTE


def read_note(path: Path, vault_root: Path) -> Note:
    """Read a .md file, parse frontmatter, extract wikilinks and metadata."""
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {path}")

    post = frontmatter.load(str(path))
    fm: dict[str, Any] = dict(post.metadata)
    content: str = post.content
    rel_path = str(path.relative_to(vault_root))

    title = fm.get("title")
    if not title:
        heading_match = _HEADING_RE.search(content)
        if heading_match:
            title = heading_match.group(1).strip()
        else:
            title = path.stem

    wikilinks = extract_wikilinks(content)
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    node_type = infer_node_type(rel_path, fm)

    provenance = Provenance(
        authored_by=fm.get("authored_by", "human"),
        model=fm.get("model"),
        confidence=fm.get("confidence"),
        source_path=fm.get("source_path"),
    )

    return Note(
        path=rel_path,
        title=title,
        content=content,
        frontmatter=fm,
        node_type=node_type,
        provenance=provenance,
        wikilinks=wikilinks,
        tags=tags,
    )


def scan_vault(vault_root: Path) -> list[Note]:
    """Recursively find all .md files in the vault, skipping .cortex/."""
    notes: list[Note] = []
    for md_file in sorted(vault_root.rglob("*.md")):
        rel = md_file.relative_to(vault_root)
        if rel.parts[0] == ".cortex":
            continue
        try:
            notes.append(read_note(md_file, vault_root))
        except Exception:
            continue
    return notes


def resolve_wikilink(link: str, vault_root: Path) -> str | None:
    """Find a matching .md file by name. Search wiki/ first, then other dirs."""
    search_dirs = ["wiki", "agents", "sessions", "daily"]

    for subdir in search_dirs:
        candidate = vault_root / subdir / f"{link}.md"
        if candidate.exists():
            return str(candidate.relative_to(vault_root))

    for md_file in vault_root.rglob("*.md"):
        rel = md_file.relative_to(vault_root)
        if rel.parts[0] == ".cortex":
            continue
        if md_file.stem == link:
            return str(rel)

    return None
