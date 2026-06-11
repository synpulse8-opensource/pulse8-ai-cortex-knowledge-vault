"""Daily-log helper — append ingest/write/compile events to `daily/<UTC-date>.md`.

Each call adds one `## [HH:MM] event | summary` H2 block to today's UTC daily
note, creating the file (with `type: daily` frontmatter) if it does not exist.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_write_lock = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _frontmatter(date_str: str, ts_iso: str) -> str:
    return (
        "---\n"
        f"title: {date_str}\n"
        "type: daily\n"
        "tags: [daily-log]\n"
        f"created_at: {ts_iso}\n"
        f"updated_at: {ts_iso}\n"
        "---\n\n"
        f"# {date_str}\n\n"
    )


def _format_entry(
    time_str: str,
    event: str,
    summary: str,
    wiki_stem: Optional[str],
) -> str:
    body = f"## [{time_str}] {event} | {summary}\n\n"
    if wiki_stem:
        body += f"[[{wiki_stem}]]\n\n"
    return body


def _write_or_append(daily_path: Path, frontmatter: str, entry: str) -> None:
    with _write_lock:
        daily_path.parent.mkdir(parents=True, exist_ok=True)
        if not daily_path.exists():
            daily_path.write_text(frontmatter + entry, encoding="utf-8")
            return
        with open(daily_path, "a", encoding="utf-8") as f:
            f.write(entry)


async def append_daily_log_entry(
    vault_root: Path,
    event: str,
    summary: str,
    wiki_path: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Path:
    """Append one daily-log entry to ``daily/<UTC-date>.md``.

    Creates the file with daily-log frontmatter if absent. When ``wiki_path``
    is provided, the entry includes a ``[[wiki-stem]]`` line so the watcher
    (or `vault_write` graph wiring) creates a LINKS_TO edge.
    """
    ts = now or _utc_now()
    date_str = ts.strftime("%Y-%m-%d")
    time_str = ts.strftime("%H:%M")
    ts_iso = _iso(ts)

    daily_path = vault_root / "daily" / f"{date_str}.md"
    wiki_stem = Path(wiki_path).stem if wiki_path else None

    fm_block = _frontmatter(date_str, ts_iso)
    entry = _format_entry(time_str, event, summary, wiki_stem)

    await asyncio.to_thread(_write_or_append, daily_path, fm_block, entry)
    return daily_path
