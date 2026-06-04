"""Tests for feedback vault module."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortex.graph.engine import GraphEngine
from cortex.vault.models import NodeType


@pytest.fixture
def feedback_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for sub in ["feedback", "wiki", ".cortex"]:
        (vault / sub).mkdir(parents=True)
    (vault / "wiki" / "target.md").write_text("---\ntitle: Target\n---\n\n# Target\n")
    (vault / ".cortex" / "graph.json").write_text('{"nodes": [], "edges": []}')
    return vault


@pytest.mark.asyncio
async def test_create_feedback_writes_file_and_graph_edges(feedback_vault: Path):
    from cortex.vault.feedback import create_feedback

    graph = GraphEngine(feedback_vault / ".cortex" / "graph.json")
    await graph.load()
    qmd_debounce = MagicMock()
    qmd_debounce.schedule = MagicMock()

    result = await create_feedback(
        vault_root=feedback_vault,
        graph=graph,
        qmd_debounce=qmd_debounce,
        content="Search missed the security events doc.",
        tags=["search-quality"],
        related_paths=["wiki/target.md"],
    )

    assert result["path"].startswith("feedback/")
    assert result["path"].endswith(".md")
    assert result["status"] == "OPEN"
    file_path = feedback_vault / result["path"]
    assert file_path.exists()
    text = file_path.read_text()
    assert "Search missed" in text
    assert "search-quality" in text
    assert graph.graph.has_node(result["path"])
    assert graph.graph.nodes[result["path"]]["node_type"] == NodeType.FEEDBACK.value
    assert graph.graph.has_edge(result["path"], "tag:search-quality")
    assert graph.graph.has_edge(result["path"], "wiki/target.md")
    qmd_debounce.schedule.assert_called_once()


@pytest.mark.asyncio
async def test_create_feedback_calls_teams_notify(feedback_vault: Path, monkeypatch):
    from cortex.config import settings
    from cortex.vault.feedback import create_feedback

    monkeypatch.setattr(settings, "teams_webhook_url", "")

    graph = GraphEngine(feedback_vault / ".cortex" / "graph.json")
    await graph.load()

    with patch(
        "cortex.vault.feedback.notify_new_feedback", new_callable=AsyncMock
    ) as mock_notify:
        await create_feedback(
            vault_root=feedback_vault,
            graph=graph,
            qmd_debounce=MagicMock(),
            content="Notify me",
            tags=["t"],
        )
        mock_notify.assert_awaited_once()
        kwargs = mock_notify.await_args.kwargs
        assert kwargs["content"] == "Notify me"
        assert kwargs["status"] == "OPEN"


@pytest.mark.asyncio
async def test_create_feedback_persists_graph_once(feedback_vault: Path):
    from cortex.vault.feedback import create_feedback

    graph = GraphEngine(feedback_vault / ".cortex" / "graph.json")
    await graph.load()

    with patch.object(graph, "_persist", new_callable=AsyncMock) as mock_persist:
        await create_feedback(
            vault_root=feedback_vault,
            graph=graph,
            qmd_debounce=MagicMock(),
            content="Batch persist test.",
            tags=["t1", "t2"],
            related_paths=["wiki/target.md"],
        )
        assert mock_persist.await_count == 1


@pytest.mark.asyncio
async def test_create_feedback_rejects_invalid_related_path(feedback_vault: Path):
    from cortex.vault.feedback import create_feedback

    graph = GraphEngine(feedback_vault / ".cortex" / "graph.json")
    await graph.load()

    with pytest.raises(ValueError, match="not found"):
        await create_feedback(
            vault_root=feedback_vault,
            graph=graph,
            qmd_debounce=MagicMock(),
            content="Bad link",
            related_paths=["wiki/missing.md"],
        )


@pytest.mark.asyncio
async def test_list_feedbacks_metadata_only(feedback_vault: Path):
    from cortex.vault.feedback import create_feedback, list_feedbacks

    graph = GraphEngine(feedback_vault / ".cortex" / "graph.json")
    await graph.load()

    await create_feedback(
        vault_root=feedback_vault,
        graph=graph,
        qmd_debounce=MagicMock(),
        content="First line preview text.",
        tags=["t1"],
        related_paths=["wiki/target.md"],
        authored_by="jane.doe@example.com",
    )

    items = list_feedbacks(feedback_vault)
    assert len(items) == 1
    item = items[0]
    assert item["path"].startswith("feedback/")
    assert item["authored_by"] == "jane.doe@example.com"
    assert item["preview"] == "First line preview text."
    assert item["tags"] == ["t1"]
    assert item["related_paths"] == ["wiki/target.md"]
    assert "content" not in item


@pytest.mark.asyncio
async def test_delete_feedback(feedback_vault: Path):
    from cortex.vault.feedback import create_feedback, delete_feedback

    graph = GraphEngine(feedback_vault / ".cortex" / "graph.json")
    await graph.load()
    qmd_debounce = MagicMock()

    created = await create_feedback(
        vault_root=feedback_vault,
        graph=graph,
        qmd_debounce=qmd_debounce,
        content="Delete me",
    )
    filename = Path(created["path"]).name

    result = await delete_feedback(
        vault_root=feedback_vault,
        graph=graph,
        qmd_debounce=qmd_debounce,
        filename=filename,
    )
    assert result["status"] == "deleted"
    assert not (feedback_vault / created["path"]).exists()
    assert not graph.graph.has_node(created["path"])
