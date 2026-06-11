"""Tests for domain models."""
from __future__ import annotations

from datetime import datetime


def test_node_type_values():
    from cortex.vault.models import NodeType

    assert NodeType.NOTE == "note"
    assert NodeType.AGENT_DEF == "agent_def"
    assert NodeType.MEMORY == "memory"
    assert NodeType.SESSION == "session"
    assert NodeType.RAW_SOURCE == "raw_source"
    assert NodeType.TAG == "tag"


def test_node_type_daily_exists():
    """NodeType.DAILY supports the daily-notes folder convention."""
    from cortex.vault.models import NodeType

    assert NodeType.DAILY == "daily"


def test_edge_type_values():
    from cortex.vault.models import EdgeType

    assert EdgeType.LINKS_TO == "links_to"
    assert EdgeType.AUTHORED_BY == "authored_by"
    assert EdgeType.CONTRADICTS == "contradicts"
    assert EdgeType.DERIVED_FROM == "derived_from"
    assert EdgeType.SUPERSEDES == "supersedes"
    assert EdgeType.MEMORY_OF == "memory_of"
    assert EdgeType.TAGGED_WITH == "tagged_with"


def test_provenance_defaults():
    from cortex.vault.models import Provenance

    p = Provenance()
    assert p.authored_by == "human"
    assert isinstance(p.created_at, datetime)
    assert isinstance(p.updated_at, datetime)
    assert p.model is None
    assert p.confidence is None
    assert p.source_path is None


def test_provenance_custom():
    from cortex.vault.models import Provenance

    p = Provenance(
        authored_by="claude",
        model="claude-sonnet-4",
        confidence=0.95,
        source_path="raw/test.txt",
    )
    assert p.authored_by == "claude"
    assert p.model == "claude-sonnet-4"
    assert p.confidence == 0.95
    assert p.source_path == "raw/test.txt"


def test_note_creation():
    from cortex.vault.models import Note, NodeType, Provenance

    note = Note(
        path="wiki/test.md",
        title="Test Note",
        content="# Test\n\nContent here.",
        frontmatter={"title": "Test Note", "tags": ["test"]},
        node_type=NodeType.NOTE,
        provenance=Provenance(),
        wikilinks=["other-note"],
        tags=["test"],
    )
    assert note.path == "wiki/test.md"
    assert note.title == "Test Note"
    assert note.node_type == NodeType.NOTE
    assert note.wikilinks == ["other-note"]
    assert note.tags == ["test"]


def test_note_default_lists():
    from cortex.vault.models import Note, NodeType, Provenance

    note = Note(
        path="wiki/empty.md",
        title="Empty",
        content="",
        frontmatter={},
        node_type=NodeType.NOTE,
        provenance=Provenance(),
    )
    assert note.wikilinks == []
    assert note.tags == []


def test_edge_creation():
    from cortex.vault.models import Edge, EdgeType

    edge = Edge(
        source="wiki/a.md",
        target="wiki/b.md",
        edge_type=EdgeType.LINKS_TO,
    )
    assert edge.source == "wiki/a.md"
    assert edge.target == "wiki/b.md"
    assert edge.edge_type == EdgeType.LINKS_TO
    assert edge.metadata == {}
    assert edge.created_at  # should be auto-set


def test_search_result():
    from cortex.vault.models import SearchResult, NodeType

    sr = SearchResult(
        path="wiki/result.md",
        title="Result",
        score=0.85,
        snippet="matching text...",
    )
    assert sr.path == "wiki/result.md"
    assert sr.score == 0.85
    assert sr.node_type == NodeType.NOTE
    assert sr.edges == []


def test_context_window():
    from cortex.vault.models import ContextWindow

    cw = ContextWindow(
        notes=[],
        edges=[],
        contradictions=[],
        total_nodes_explored=5,
        total_edges_explored=3,
    )
    assert cw.total_nodes_explored == 5
    assert cw.total_edges_explored == 3
    assert cw.contradictions == []
