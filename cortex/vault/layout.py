"""Vault directory layout — configurable raw/wiki folder names per deployment."""
from __future__ import annotations

import re
from pathlib import Path

from cortex.config import settings

# Fixed auxiliary folders (not configurable in v1)
AUX_CONTENT_DIRS = ("agents", "sessions", "daily", "feedback")


def raw_dir_name() -> str:
    return settings.vault_raw_dir


def wiki_dir_name() -> str:
    return settings.vault_wiki_dir


def raw_dir(vault_root: Path) -> Path:
    return vault_root / settings.vault_raw_dir


def wiki_dir(vault_root: Path) -> Path:
    return vault_root / settings.vault_wiki_dir


def index_path(vault_root: Path) -> Path:
    """Path to the auto-generated vault index (.cortex/index.md)."""
    return vault_root / ".cortex" / "index.md"


def slug_from_stem(stem: str) -> str:
    """Convert a filename stem to a kebab-case slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or "untitled"


def wiki_dest_for_raw(vault_root: Path, raw_path: Path) -> Path:
    """Map a raw vault file to its wiki note path (mirror subdirs, kebab-case stem)."""
    rel = raw_path.relative_to(raw_dir(vault_root))
    wiki_name = f"{slug_from_stem(rel.stem)}.md"
    if rel.parent == Path("."):
        return wiki_dir(vault_root) / wiki_name
    return wiki_dir(vault_root) / rel.parent / wiki_name


def raw_rel(filename: str) -> str:
    """Vault-relative path for a file directly under the raw directory (no subdirs)."""
    return f"{settings.vault_raw_dir}/{filename}"


def vault_rel(vault_root: Path, path: Path) -> str:
    """Vault-relative path for any file or directory under the vault root."""
    return str(path.relative_to(vault_root))


def wiki_rel(filename: str) -> str:
    return f"{settings.vault_wiki_dir}/{filename}"


def is_raw_path(rel_path: str) -> bool:
    """True when a vault-relative path is under the configured raw directory."""
    prefix = f"{settings.vault_raw_dir}/"
    return rel_path == settings.vault_raw_dir or rel_path.startswith(prefix)


def wikilink_search_dirs() -> list[str]:
    """Directory search order for wikilink resolution (wiki dir first)."""
    return [settings.vault_wiki_dir, *AUX_CONTENT_DIRS]


def watcher_skip_top_dirs() -> frozenset[str]:
    """Top-level vault dirs ignored by VaultWatcher (not indexed as notes)."""
    return frozenset({".cortex", settings.vault_raw_dir})


def qmd_named_collections() -> list[str]:
    """QMD collection names for markdown content (excludes raw sources)."""
    return [settings.vault_wiki_dir, *AUX_CONTENT_DIRS]


def index_section_keys() -> list[str]:
    """Section keys for .cortex/index.md generation."""
    return [
        settings.vault_wiki_dir,
        *AUX_CONTENT_DIRS,
        settings.vault_raw_dir,
    ]


def index_bucket_for_path(rel_path: str) -> str:
    """Map a note path to an index.md section bucket."""
    top = rel_path.split("/")[0] if "/" in rel_path else settings.vault_wiki_dir
    if top in index_section_keys():
        return top
    return settings.vault_wiki_dir
