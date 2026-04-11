from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Create a temporary vault with sample .md files for testing."""
    vault = tmp_path / "vault"

    for subdir in ["raw", "wiki", "agents", "sessions", "daily", ".cortex"]:
        (vault / subdir).mkdir(parents=True)

    (vault / "wiki" / "transformers.md").write_text(
        "---\n"
        "title: Transformer Architecture\n"
        "tags: [ml, architecture]\n"
        "authored_by: claude-sonnet-4\n"
        "created_at: 2026-04-11T10:00:00Z\n"
        "source_path: raw/transformer-paper.txt\n"
        "---\n"
        "\n"
        "# Transformer Architecture\n"
        "\n"
        "The transformer model replaces recurrence with self-attention.\n"
        "\n"
        "See also: [[attention-mechanisms]]\n"
        "Related: [[rnn-claims]]\n"
    )

    (vault / "wiki" / "attention-mechanisms.md").write_text(
        "---\n"
        "title: Attention Mechanisms\n"
        "tags: [ml, attention]\n"
        "authored_by: human\n"
        "---\n"
        "\n"
        "# Attention Mechanisms\n"
        "\n"
        "Multi-head attention is a key component of [[transformers]].\n"
    )

    (vault / "raw" / "transformer-paper.txt").write_text(
        "Title: Attention Is All You Need\n"
        "\n"
        "The transformer architecture introduces a model based entirely "
        "on attention mechanisms.\n"
    )

    (vault / "agents" / "research-scout.agent.md").write_text(
        "---\n"
        "type: agent\n"
        "name: research-scout\n"
        "---\n"
        "\n"
        "# Research Scout\n"
        "\n"
        "Agent for automated research.\n"
    )

    (vault / "sessions" / "2026-04-11.session.md").write_text(
        "---\n"
        "title: Architecture Review\n"
        "---\n"
        "\n"
        "# Session 2026-04-11\n"
        "\n"
        "Meeting notes here.\n"
    )

    (vault / ".cortex" / "graph.json").write_text('{"nodes": [], "edges": []}')
    (vault / ".cortex" / "log.md").write_text("# Cortex Operation Log\n")
    (vault / ".cortex" / "index.md").write_text("# Cortex Vault Index\n")

    return vault
