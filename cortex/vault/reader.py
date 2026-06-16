"""Markdown note reader, vault scanner, and wikilink resolver."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import frontmatter

from cortex.vault.layout import is_raw_path, wikilink_search_dirs
from cortex.vault.models import NodeType, Note, Provenance

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def extract_wikilinks(content: str) -> list[str]:
    """Extract wikilink targets from markdown content."""
    return _WIKILINK_RE.findall(content)


def normalize_tags(raw: Any) -> list[str]:
    """Coerce frontmatter tags to a flat list of non-empty strings.

    Compiler LLM enrichment and YAML indentation mistakes can produce nested
    tag lists (e.g. [["avaloq", "config"]]). Callers assume list[str] and use
    ", ".join(note.tags), which raises TypeError on nested values.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]

    tags: list[str] = []

    def _append(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                tags.append(stripped)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                _append(item)
            return
        if isinstance(value, (int, float, bool)):
            tags.append(str(value))

    if isinstance(raw, (list, tuple)):
        for item in raw:
            _append(item)
    else:
        _append(raw)

    return tags


def infer_node_type(path: str, fm: dict[str, Any]) -> NodeType:
    """Determine the NodeType from path conventions and frontmatter."""
    if "type" in fm:
        try:
            return NodeType(fm["type"])
        except ValueError:
            pass

    if is_raw_path(path):
        return NodeType.RAW_SOURCE
    if path.startswith("agents/"):
        return NodeType.AGENT_DEF
    if path.startswith("sessions/"):
        return NodeType.SESSION
    if path.startswith("daily/"):
        return NodeType.DAILY
    if path.endswith(".agent.md"):
        return NodeType.AGENT_DEF
    if path.endswith(".memory.md"):
        return NodeType.MEMORY
    if path.endswith(".session.md"):
        return NodeType.SESSION
    if path.startswith("feedback/"):
        return NodeType.FEEDBACK

    return NodeType.NOTE


def read_note(path: Path, vault_root: Path) -> Note:
    """Read a .md file, parse frontmatter, extract wikilinks and metadata."""
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"Path is a directory, not a note: {path}")
    if path.suffix.lower() != ".md":
        raise ValueError(f"Path is not a markdown note: {path}")

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
    tags = normalize_tags(fm.get("tags", []))

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


async def scan_vault_async(vault_root: Path) -> list[Note]:
    """Async version of scan_vault that offloads file I/O to a thread pool."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    md_files = sorted(
        f for f in vault_root.rglob("*.md")
        if f.relative_to(vault_root).parts[0] != ".cortex"
    )

    def _read(path: Path) -> Note | None:
        try:
            return read_note(path, vault_root)
        except Exception:
            return None

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        futures = [loop.run_in_executor(pool, _read, f) for f in md_files]
        results = await asyncio.gather(*futures)

    return [n for n in results if n is not None]


def build_wikilink_index(vault_root: Path) -> dict[str, str]:
    """Build a stem-to-relative-path map for all .md files in the vault.

    Priority: wiki/ > agents/ > sessions/ > daily/ > other dirs.
    First match wins for duplicate stems.
    """
    search_dirs = wikilink_search_dirs()
    index: dict[str, str] = {}

    for subdir in search_dirs:
        d = vault_root / subdir
        if d.is_dir():
            for md_file in sorted(d.rglob("*.md")):
                stem = md_file.stem
                if stem not in index:
                    index[stem] = str(md_file.relative_to(vault_root))

    for md_file in sorted(vault_root.rglob("*.md")):
        rel = md_file.relative_to(vault_root)
        if rel.parts[0] in (".cortex", *search_dirs):
            continue
        stem = md_file.stem
        if stem not in index:
            index[stem] = str(rel)

    return index


def resolve_wikilink(link: str, vault_root: Path, _index: dict[str, str] | None = None) -> str | None:
    """Find a matching .md file by name. Uses pre-built index when available."""
    if _index is not None:
        return _index.get(link)

    search_dirs = wikilink_search_dirs()

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
