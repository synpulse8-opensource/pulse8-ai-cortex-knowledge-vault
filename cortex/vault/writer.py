"""Note writer with provenance tracking and frontmatter merging."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import frontmatter as fm

from cortex.vault.models import Note
from cortex.vault.reader import read_note


def merge_frontmatter(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Deep merge frontmatter. Incoming overrides but never deletes existing keys."""
    merged = dict(existing)
    merged.update(incoming)
    return merged


def inject_provenance(
    frontmatter: dict[str, Any],
    authored_by: str,
    model: Optional[str] = None,
    confidence: Optional[float] = None,
) -> dict[str, Any]:
    """Set provenance fields on frontmatter."""
    result = dict(frontmatter)
    result["authored_by"] = authored_by
    result["updated_at"] = datetime.now(timezone.utc).isoformat()

    if "created_at" not in result:
        result["created_at"] = datetime.now(timezone.utc).isoformat()

    if model is not None:
        result["model"] = model
    if confidence is not None:
        result["confidence"] = confidence

    return result


def write_note(
    path: Path,
    vault_root: Path,
    content: str,
    frontmatter: Optional[dict[str, Any]] = None,
    mode: str = "upsert",
    authored_by: str = "human",
    model: Optional[str] = None,
) -> Note:
    """Write a note to the vault with provenance tracking.

    Modes:
        create: error if file exists
        update: error if file doesn't exist, merge frontmatter
        upsert: create or update
    """
    if frontmatter is None:
        frontmatter = {}

    if mode == "create" and path.exists():
        raise FileExistsError(f"Note already exists: {path}")
    if mode == "update" and not path.exists():
        raise FileNotFoundError(f"Note not found: {path}")

    existing_fm: dict[str, Any] = {}
    if path.exists():
        post = fm.load(str(path))
        existing_fm = dict(post.metadata)

    merged = merge_frontmatter(existing_fm, frontmatter)
    final_fm = inject_provenance(merged, authored_by, model=model)

    path.parent.mkdir(parents=True, exist_ok=True)

    post = fm.Post(content, **final_fm)
    path.write_text(fm.dumps(post))

    return read_note(path, vault_root)
