"""Tests for the graph query surface: paths, impact, explain.

Path queries over the typed graph power regulatory impact analysis:
"what connects this regulation to our products" (vault_path), "what is
downstream of this note" (vault_impact), "explain this entity" (vault_explain).
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _write_chain(vault: Path) -> None:
    """policy -> procedure -> control chain, plus an unrelated island note."""
    (vault / "wiki" / "policy.md").write_text(
        "---\ntitle: Data Retention Policy\ntags: [governance]\n---\n"
        "# Data Retention Policy\n\nImplemented by [[procedure]].\n"
    )
    (vault / "wiki" / "procedure.md").write_text(
        "---\ntitle: Archival Procedure\n---\n"
        "# Archival Procedure\n\nEnforced through [[control]].\n"
    )
    (vault / "wiki" / "control.md").write_text(
        "---\ntitle: Backup Control\n---\n# Backup Control\n\nDetails.\n"
    )
    (vault / "wiki" / "island.md").write_text(
        "---\ntitle: Unrelated Island\n---\n# Unrelated Island\n\nNo links.\n"
    )


async def _build(tmp_vault: Path):
    from cortex.graph.builder import build_graph
    from cortex.vault.reader import scan_vault

    notes = scan_vault(tmp_vault)
    return await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)


class TestFindPaths:
    @pytest.mark.asyncio
    async def test_direct_path(self, tmp_vault: Path):
        graph = await _build(tmp_vault)
        paths = await graph.find_paths(
            "wiki/transformers.md", "wiki/attention-mechanisms.md"
        )
        assert paths
        assert paths[0]["nodes"] == [
            "wiki/transformers.md",
            "wiki/attention-mechanisms.md",
        ]
        step = paths[0]["edges"][0]
        assert step["edge_type"] == "links_to"
        assert step["origin"] == "extracted"

    @pytest.mark.asyncio
    async def test_multi_hop_path(self, tmp_vault: Path):
        _write_chain(tmp_vault)
        graph = await _build(tmp_vault)
        paths = await graph.find_paths("wiki/policy.md", "wiki/control.md")
        assert paths
        assert paths[0]["nodes"] == [
            "wiki/policy.md",
            "wiki/procedure.md",
            "wiki/control.md",
        ]

    @pytest.mark.asyncio
    async def test_no_path_returns_empty(self, tmp_vault: Path):
        _write_chain(tmp_vault)
        graph = await _build(tmp_vault)
        paths = await graph.find_paths("wiki/policy.md", "wiki/island.md")
        assert paths == []

    @pytest.mark.asyncio
    async def test_tag_hubs_do_not_create_paths(self, tmp_vault: Path):
        """Shared tags must not connect otherwise-unrelated notes (hub noise)."""
        (tmp_vault / "wiki" / "other-ml.md").write_text(
            "---\ntitle: Other ML Note\ntags: [ml]\n---\n# Other ML\n\nNothing.\n"
        )
        graph = await _build(tmp_vault)
        # transformers is tagged ml, other-ml is tagged ml — but there is no
        # real link between them, so no path should be reported.
        paths = await graph.find_paths("wiki/transformers.md", "wiki/other-ml.md")
        assert paths == []


class TestImpact:
    @pytest.mark.asyncio
    async def test_impact_walks_upstream_dependents(self, tmp_vault: Path):
        """Notes linking (directly or transitively) to the target are impacted."""
        _write_chain(tmp_vault)
        graph = await _build(tmp_vault)
        impacted = await graph.impact("wiki/control.md")
        by_path = {i["path"]: i for i in impacted}
        assert by_path["wiki/procedure.md"]["depth"] == 1
        assert by_path["wiki/policy.md"]["depth"] == 2
        assert "wiki/island.md" not in by_path

    @pytest.mark.asyncio
    async def test_impact_respects_max_depth(self, tmp_vault: Path):
        _write_chain(tmp_vault)
        graph = await _build(tmp_vault)
        impacted = await graph.impact("wiki/control.md", max_depth=1)
        paths = {i["path"] for i in impacted}
        assert "wiki/procedure.md" in paths
        assert "wiki/policy.md" not in paths
