"""Tests for edge provenance (lineage) stamping and the trace query.

Every edge carries an `origin` label in its metadata:
  - "extracted": deterministic structure extraction (wikilinks/tags/frontmatter)
  - "inferred":  LLM cross-referencing (carries model id)
  - "manual":    created via vault_link / REST by a human or agent
"""
from __future__ import annotations

from pathlib import Path

import pytest


async def _build(tmp_vault: Path):
    from cortex.graph.builder import build_graph
    from cortex.vault.reader import scan_vault

    notes = scan_vault(tmp_vault)
    return await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)


class TestExtractedOrigin:
    @pytest.mark.asyncio
    async def test_wikilink_edges_stamped_extracted(self, tmp_vault: Path):
        graph = await _build(tmp_vault)
        edges = await graph.get_edges("wiki/transformers.md", direction="out")
        links = [e for e in edges if e.edge_type.value == "links_to"]
        assert links, "fixture should produce links_to edges"
        for e in links:
            assert e.metadata.get("origin") == "extracted"

    @pytest.mark.asyncio
    async def test_tag_and_derived_edges_stamped_extracted(self, tmp_vault: Path):
        graph = await _build(tmp_vault)
        edges = await graph.get_edges("wiki/transformers.md", direction="out")
        by_type = {e.edge_type.value: e for e in edges}
        assert by_type["tagged_with"].metadata.get("origin") == "extracted"
        assert by_type["derived_from"].metadata.get("origin") == "extracted"


class TestManualOrigin:
    @pytest.mark.asyncio
    async def test_vault_link_create_stamped_manual(self, tmp_vault: Path):
        from cortex.mcp.tools import handle_vault_link

        graph = await _build(tmp_vault)
        result = await handle_vault_link(
            action="create",
            vault_path=tmp_vault,
            graph=graph,
            source="wiki/transformers.md",
            target="wiki/attention-mechanisms.md",
            edge_type="supersedes",
        )
        assert result["status"] == "created"

        edges = await graph.get_edges("wiki/transformers.md", direction="out")
        manual = [e for e in edges if e.edge_type.value == "supersedes"]
        assert manual[0].metadata.get("origin") == "manual"

    @pytest.mark.asyncio
    async def test_vault_link_preserves_caller_metadata(self, tmp_vault: Path):
        from cortex.mcp.tools import handle_vault_link

        graph = await _build(tmp_vault)
        await handle_vault_link(
            action="create",
            vault_path=tmp_vault,
            graph=graph,
            source="wiki/transformers.md",
            target="wiki/attention-mechanisms.md",
            edge_type="supersedes",
            metadata={"reason": "newer revision"},
        )
        edges = await graph.get_edges("wiki/transformers.md", direction="out")
        manual = [e for e in edges if e.edge_type.value == "supersedes"]
        assert manual[0].metadata["reason"] == "newer revision"
        assert manual[0].metadata["origin"] == "manual"
