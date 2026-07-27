"""Curation report — knowledge quality management over the vault.

Aggregates the outcome-memory signals into one report:
  - most_read:    which notes actually get used (from .cortex/usage.json)
  - never_read:   wiki notes no agent or user has ever opened
  - stale:        wiki notes not touched within the freshness window
  - contradicted: notes with contradiction edges or feedback marked corrected
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cortex.graph.engine import GraphEngine
from cortex.vault.feedback import list_feedbacks
from cortex.vault.layout import wiki_dir_name
from cortex.vault.models import EdgeType
from cortex.vault.reader import scan_vault
from cortex.vault.usage import load_usage

_MOST_READ_LIMIT = 10


def _note_age_reference(note) -> datetime | None:
    """Freshness reference: frontmatter updated_at, falling back to created_at.

    Reads frontmatter directly — Provenance fills missing timestamps with
    now(), which would make undated notes look permanently fresh.
    """
    for key in ("updated_at", "created_at"):
        value = note.frontmatter.get(key)
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


async def build_curation_report(
    vault_root: Path,
    graph: GraphEngine,
    stale_days: int = 90,
) -> dict[str, Any]:
    """Build the curation report for all wiki notes."""
    wiki_prefix = f"{wiki_dir_name()}/"
    notes = [n for n in scan_vault(vault_root) if n.path.startswith(wiki_prefix)]
    usage = load_usage(vault_root)

    read_entries = [
        {
            "path": path,
            "reads": entry.get("reads", 0),
            "last_read": entry.get("last_read"),
        }
        for path, entry in usage.items()
        if path.startswith(wiki_prefix)
    ]
    read_entries.sort(key=lambda e: e["reads"], reverse=True)
    never_read = sorted(n.path for n in notes if n.path not in usage)

    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    stale = []
    for note in notes:
        reference = _note_age_reference(note)
        if reference is not None and reference < cutoff:
            stale.append(
                {
                    "path": note.path,
                    "title": note.title,
                    "last_touched": reference.isoformat(),
                }
            )

    contradicted: dict[str, dict[str, Any]] = {}
    edges_by_note = await graph.get_edges_batch(
        [n.path for n in notes], edge_types=[EdgeType.CONTRADICTS]
    )
    for note_path, edges in edges_by_note.items():
        for edge in edges:
            contradicted.setdefault(
                note_path, {"path": note_path, "reasons": []}
            )["reasons"].append(f"contradiction edge {edge.source} → {edge.target}")

    for fb in list_feedbacks(vault_root):
        if fb.get("outcome") != "corrected":
            continue
        for rel in fb.get("related_paths", []):
            if not rel.startswith(wiki_prefix):
                continue
            contradicted.setdefault(rel, {"path": rel, "reasons": []})[
                "reasons"
            ].append(f"feedback {fb['path']} marked corrected")

    return {
        "most_read": read_entries[:_MOST_READ_LIMIT],
        "never_read": never_read,
        "stale": stale,
        "contradicted": sorted(contradicted.values(), key=lambda e: e["path"]),
        "totals": {
            "wiki_notes": len(notes),
            "never_read": len(never_read),
            "stale": len(stale),
            "contradicted": len(contradicted),
        },
    }
