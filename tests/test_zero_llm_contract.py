"""Contract tests for deterministic-first (zero-LLM) operation.

These pin the architectural guarantee that with CORTEX_LLM_BACKEND=none the
full ingest -> note -> graph pipeline works with no LLM client constructed
and no network call attempted. The LLM is an optional enrichment pass, not
a dependency.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_zero_llm_ingest_builds_note_and_graph(tmp_vault: Path, monkeypatch):
    """With backend=none: ingest converts, note is written, structure edges build."""
    from cortex.compiler.compiler import KnowledgeCompiler
    from cortex.config import settings
    from cortex.graph.builder import build_graph
    from cortex.vault.models import EdgeType
    from cortex.vault.reader import scan_vault

    monkeypatch.setattr(settings, "llm_backend", "none")
    monkeypatch.setattr(settings, "llm_api_key", "sk-or-key-that-must-not-be-used")

    raw = tmp_vault / "raw" / "structured-note.md"
    raw.write_text(
        "---\ntags: [governance]\n---\n"
        "# Structured Note\n\n"
        "Relates to [[transformers]] directly.\n"
    )

    with patch("openai.OpenAI") as sync_client, patch("openai.AsyncOpenAI") as async_client:
        compiler = KnowledgeCompiler(tmp_vault)
        created = await compiler.ingest_source(raw)
        await compiler.compile_cross_references(created)

        # The zero-LLM guarantee: no client is ever constructed.
        sync_client.assert_not_called()
        async_client.assert_not_called()

    assert len(created) == 1
    wiki_note = created[0]
    assert wiki_note.exists()
    assert "[[transformers]]" in wiki_note.read_text()

    # Deterministic structure extraction builds a useful graph without an LLM:
    # wikilinks -> LINKS_TO, tags -> TAGGED_WITH, source_path -> DERIVED_FROM.
    notes = scan_vault(tmp_vault)
    graph = await build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)

    wiki_rel = str(wiki_note.relative_to(tmp_vault))
    edge_types = {
        (data.get("edge_type"), target)
        for _, target, data in graph.graph.out_edges(wiki_rel, data=True)
    }
    assert (EdgeType.LINKS_TO.value, "wiki/transformers.md") in edge_types
    assert (EdgeType.DERIVED_FROM.value, "raw/structured-note.md") in edge_types


@pytest.mark.asyncio
async def test_zero_llm_note_carries_no_model_provenance(tmp_vault: Path, monkeypatch):
    """Notes compiled without an LLM must not claim model provenance."""
    import frontmatter as fm

    from cortex.compiler.compiler import KnowledgeCompiler
    from cortex.config import settings

    monkeypatch.setattr(settings, "llm_backend", "none")

    compiler = KnowledgeCompiler(tmp_vault)
    created = await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")

    post = fm.load(str(created[0]))
    assert post.metadata["authored_by"] == "markitdown"
    assert "model" not in post.metadata
    assert post.metadata["enrichment_status"] == "incomplete"
