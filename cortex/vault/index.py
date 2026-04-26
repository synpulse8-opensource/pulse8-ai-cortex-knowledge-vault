"""Vault index builder — auto-generates .cortex/index.md."""
from __future__ import annotations

from pathlib import Path

from cortex.vault.models import Note
from cortex.vault.reader import scan_vault


async def rebuild_index(vault_root: Path, notes: list[Note] | None = None) -> None:
    """Rebuild .cortex/index.md from vault contents.

    Accepts pre-scanned notes to avoid a redundant full vault scan.
    """
    index_path = vault_root / ".cortex" / "index.md"
    if notes is None:
        notes = scan_vault(vault_root)

    sections: dict[str, list[str]] = {
        "wiki": [],
        "agents": [],
        "sessions": [],
        "daily": [],
        "raw": [],
    }

    for note in notes:
        rel = note.path
        bucket = rel.split("/")[0] if "/" in rel else "wiki"
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

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines))
