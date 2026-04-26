"""Audit logging — append operations to .cortex/log.md."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


async def log_operation(
    vault_root: Path, consumer: str, tool: str, summary: str
) -> None:
    """Append an entry to .cortex/log.md."""
    log_path = vault_root / ".cortex" / "log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"## [{timestamp}] {tool} | {consumer}\n\n{summary}\n\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)
