"""Tests for daily-log helper — append-only journal entries in daily/<UTC-date>.md."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest


class TestAppendDailyLogEntry:
    @pytest.mark.asyncio
    async def test_creates_daily_file_with_frontmatter(self, tmp_vault: Path):
        """First entry on a fresh day creates daily/<UTC-date>.md with frontmatter."""
        from cortex.vault.daily_log import append_daily_log_entry

        fixed = datetime(2026, 6, 10, 18, 23, 45, tzinfo=timezone.utc)
        path = await append_daily_log_entry(
            tmp_vault,
            event="vault:write",
            summary="Created wiki/transformers.md",
            now=fixed,
        )

        assert path == tmp_vault / "daily" / "2026-06-10.md"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "type: daily" in content
        assert "title: 2026-06-10" in content
        assert "## [18:23] vault:write | Created wiki/transformers.md" in content

    @pytest.mark.asyncio
    async def test_second_call_same_day_appends(self, tmp_vault: Path):
        """Second entry on the same UTC day appends below the first, preserves frontmatter."""
        from cortex.vault.daily_log import append_daily_log_entry

        t1 = datetime(2026, 6, 10, 9, 5, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 10, 14, 30, tzinfo=timezone.utc)

        await append_daily_log_entry(tmp_vault, "vault:ingest", "First op", now=t1)
        await append_daily_log_entry(tmp_vault, "vault:compile", "Second op", now=t2)

        content = (tmp_vault / "daily" / "2026-06-10.md").read_text(encoding="utf-8")
        assert content.count("type: daily") == 1
        assert "## [09:05] vault:ingest | First op" in content
        assert "## [14:30] vault:compile | Second op" in content
        assert content.index("First op") < content.index("Second op")

    @pytest.mark.asyncio
    async def test_entry_with_wiki_path_emits_wikilink_line(self, tmp_vault: Path):
        """Providing wiki_path adds a [[stem]] wikilink line below the H2 entry."""
        from cortex.vault.daily_log import append_daily_log_entry

        fixed = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        await append_daily_log_entry(
            tmp_vault,
            event="vault:compile",
            summary="Compiled paper",
            wiki_path="wiki/transformers.md",
            now=fixed,
        )

        content = (tmp_vault / "daily" / "2026-06-10.md").read_text(encoding="utf-8")
        assert "## [12:00] vault:compile | Compiled paper" in content
        assert "[[transformers]]" in content

    @pytest.mark.asyncio
    async def test_entry_without_wiki_path_has_no_wikilink(self, tmp_vault: Path):
        """No wiki_path -> no wikilink line emitted."""
        from cortex.vault.daily_log import append_daily_log_entry

        fixed = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        await append_daily_log_entry(
            tmp_vault,
            event="vault:write",
            summary="Manual note",
            now=fixed,
        )

        content = (tmp_vault / "daily" / "2026-06-10.md").read_text(encoding="utf-8")
        assert "[[" not in content
