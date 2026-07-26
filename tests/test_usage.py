"""Tests for the outcome-memory loop: usage counters and curation report."""
from __future__ import annotations

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


class TestCurationReport:
    async def _graph(self, tmp_vault: Path):
        from cortex.graph.builder import build_graph
        from cortex.vault.reader import scan_vault

        return await build_graph(
            scan_vault(tmp_vault), tmp_vault / ".cortex" / "graph.json", tmp_vault
        )

    @pytest.mark.asyncio
    async def test_report_buckets_reads_and_never_read(self, tmp_vault: Path):
        from cortex.vault.curation import build_curation_report
        from cortex.vault.usage import record_read

        graph = await self._graph(tmp_vault)
        await record_read(tmp_vault, "wiki/transformers.md")
        await record_read(tmp_vault, "wiki/transformers.md")

        report = await build_curation_report(tmp_vault, graph)

        most_read = {e["path"]: e["reads"] for e in report["most_read"]}
        assert most_read["wiki/transformers.md"] == 2
        assert "wiki/attention-mechanisms.md" in report["never_read"]
        assert "wiki/transformers.md" not in report["never_read"]

    @pytest.mark.asyncio
    async def test_report_flags_stale_notes(self, tmp_vault: Path):
        from cortex.vault.curation import build_curation_report

        graph = await self._graph(tmp_vault)
        # Fixture transformers.md has created_at 2026-04-11 and no updated_at.
        report = await build_curation_report(tmp_vault, graph, stale_days=30)
        stale_paths = {e["path"] for e in report["stale"]}
        assert "wiki/transformers.md" in stale_paths

        fresh_report = await build_curation_report(tmp_vault, graph, stale_days=100000)
        assert {e["path"] for e in fresh_report["stale"]} == set()

    @pytest.mark.asyncio
    async def test_report_flags_contradicted_notes(self, tmp_vault: Path):
        from cortex.vault.curation import build_curation_report
        from cortex.vault.feedback import create_feedback

        graph = await self._graph(tmp_vault)
        await create_feedback(
            vault_root=tmp_vault,
            graph=graph,
            qmd_debounce=None,
            content="This note's claim was wrong and has been corrected.",
            related_paths=["wiki/transformers.md"],
            outcome="corrected",
        )

        report = await build_curation_report(tmp_vault, graph)
        contradicted = {e["path"] for e in report["contradicted"]}
        assert "wiki/transformers.md" in contradicted

    def test_report_rest_endpoint(self, tmp_vault: Path):
        # Reuses the app_client wiring from test_api via a local import to
        # avoid duplicating the fixture.
        import asyncio

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from cortex.api.routes import router
        from cortex.graph.builder import build_graph
        from cortex.vault.reader import scan_vault

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.state.vault_path = tmp_vault
        loop = asyncio.new_event_loop()
        app.state.graph = loop.run_until_complete(
            build_graph(
                scan_vault(tmp_vault), tmp_vault / ".cortex" / "graph.json", tmp_vault
            )
        )
        loop.close()

        client = TestClient(app)
        response = client.get("/api/v1/curation/report")
        assert response.status_code == 200
        data = response.json()
        for key in ("most_read", "never_read", "stale", "contradicted"):
            assert key in data
