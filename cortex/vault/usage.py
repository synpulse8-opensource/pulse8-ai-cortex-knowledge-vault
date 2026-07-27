"""Note usage counters — which knowledge actually gets used.

Reads are recorded per note in .cortex/usage.json. This feeds the curation
report: heavily used notes deserve freshness attention, never-read notes
are candidates for review or archival.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_USAGE_FILE = "usage.json"


def _usage_path(vault_root: Path) -> Path:
    return vault_root / ".cortex" / _USAGE_FILE


def load_usage(vault_root: Path) -> dict[str, Any]:
    """Return the usage map {note_path: {reads, last_read}}; {} if absent."""
    path = _usage_path(vault_root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("usage.json unreadable, starting fresh")
        return {}


def _record_read_sync(vault_root: Path, note_path: str) -> None:
    usage = load_usage(vault_root)
    entry = usage.setdefault(note_path, {"reads": 0})
    entry["reads"] = int(entry.get("reads", 0)) + 1
    entry["last_read"] = datetime.now(timezone.utc).isoformat()
    path = _usage_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(usage, indent=2))


async def record_read(vault_root: Path, note_path: str) -> None:
    """Increment the read counter for a note. Never raises — usage tracking
    must not break reads."""
    try:
        await asyncio.to_thread(_record_read_sync, vault_root, note_path)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("failed to record usage for %s", note_path)
