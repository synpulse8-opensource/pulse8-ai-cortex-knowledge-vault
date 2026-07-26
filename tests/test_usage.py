"""Tests for the outcome-memory loop: usage counters and curation report."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestUsageCounters:
    @pytest.mark.asyncio
    async def test_record_read_creates_and_increments(self, tmp_vault: Path):
        from cortex.vault.usage import load_usage, record_read

        await record_read(tmp_vault, "wiki/transformers.md")
        await record_read(tmp_vault, "wiki/transformers.md")
        await record_read(tmp_vault, "wiki/attention-mechanisms.md")

        usage = load_usage(tmp_vault)
        assert usage["wiki/transformers.md"]["reads"] == 2
        assert usage["wiki/attention-mechanisms.md"]["reads"] == 1
        assert usage["wiki/transformers.md"]["last_read"]

    def test_load_usage_missing_file(self, tmp_vault: Path):
        from cortex.vault.usage import load_usage

        assert load_usage(tmp_vault) == {}

    @pytest.mark.asyncio
    async def test_vault_read_records_usage(self, tmp_vault: Path):
        from cortex.graph.builder import build_graph
        from cortex.mcp.tools import handle_vault_read
        from cortex.vault.reader import scan_vault
        from cortex.vault.usage import load_usage

        graph = await build_graph(
            scan_vault(tmp_vault), tmp_vault / ".cortex" / "graph.json", tmp_vault
        )
        await handle_vault_read(
            path="wiki/transformers.md", vault_path=tmp_vault, graph=graph
        )
        usage = load_usage(tmp_vault)
        assert usage["wiki/transformers.md"]["reads"] == 1

    @pytest.mark.asyncio
    async def test_corrupt_usage_file_resets(self, tmp_vault: Path):
        from cortex.vault.usage import load_usage, record_read

        (tmp_vault / ".cortex" / "usage.json").write_text("{broken json")
        await record_read(tmp_vault, "wiki/transformers.md")
        assert load_usage(tmp_vault)["wiki/transformers.md"]["reads"] == 1
