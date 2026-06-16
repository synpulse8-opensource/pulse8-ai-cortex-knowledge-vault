"""Vault index builder — auto-generates .cortex/index.md."""
from __future__ import annotations

import asyncio
from pathlib import Path

from cortex.vault.layout import index_bucket_for_path, index_path, index_section_keys
from cortex.vault.models import Note
from cortex.vault.reader import scan_vault_async


def _write_index_file(index_path: Path, content: str) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(content)


async def rebuild_index(vault_root: Path, notes: list[Note] | None = None) -> None:
    """Rebuild .cortex/index.md from vault contents.

    Accepts pre-scanned notes to avoid a redundant full vault scan.
    """
    idx_path = index_path(vault_root)
    if notes is None:
        notes = await scan_vault_async(vault_root)

    sections: dict[str, list[str]] = {key: [] for key in index_section_keys()}

    for note in notes:
        rel = note.path
        bucket = index_bucket_for_path(rel)
        if bucket in sections:
            tags = ", ".join(note.tags) if note.tags else ""
            tag_suffix = f" — {tags}" if tags else ""
            sections[bucket].append(
                f"- [[{note.title}]] ({rel}){tag_suffix}"
            )

    lines = [
        "# Cortex Vault Index\n",
        f"_Auto-generated. {len(notes)} notes total._\n",
    ]

    for section, items in sections.items():
        if items:
            lines.append(f"\n## {section.title()}\n")
            lines.extend(sorted(items))

    await asyncio.to_thread(_write_index_file, idx_path, "\n".join(lines))
