"""Audit logging — append operations to .cortex/log.md."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path


def _write_log_entry(log_path: Path, entry: str) -> None:
    """Synchronous helper executed in a thread to avoid blocking the event loop."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


async def log_operation(
    vault_root: Path, consumer: str, tool: str, summary: str
) -> None:
    """Append an entry to .cortex/log.md without blocking the event loop."""
    log_path = vault_root / ".cortex" / "log.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"## [{timestamp}] {tool} | {consumer}\n\n{summary}\n\n"
    await asyncio.to_thread(_write_log_entry, log_path, entry)
