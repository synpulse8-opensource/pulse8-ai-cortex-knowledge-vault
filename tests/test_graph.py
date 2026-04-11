from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex.vault.models import Edge, EdgeType, NodeType, Note, Provenance


def _make_note(path: str, title: str, node_type: NodeType = NodeType.NOTE) -> Note:
    return Note(
        path=path,
        title=title,
        content="",
        frontmatter={},
        node_type=node_type,
        provenance=Provenance(),
    )


class TestGraphEnginePersistence:
    @pytest.mark.asyncio
    async def test_load_empty_creates_graph(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        graph_path = tmp_path / ".cortex" / "graph.json"
        engine = GraphEngine(graph_path)
        await engine.load()
        assert engine.graph.number_of_nodes() == 0
        assert engine.graph.number_of_edges() == 0

    @pytest.mark.asyncio
    async def test_load_existing(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        graph_path = tmp_path / ".cortex" / "graph.json"
        graph_path.parent.mkdir(parents=True)
        graph_path.write_text(json.dumps({
            "nodes": [
                {"id": "wiki/a.md", "attrs": {"node_type": "note", "title": "A"}},
                {"id": "wiki/b.md", "attrs": {"node_type": "note", "title": "B"}},
            ],
            "edges": [
                {"source": "wiki/a.md", "target": "wiki/b.md", "attrs": {"edge_type": "links_to"}},
            ],
        }))

        engine = GraphEngine(graph_path)
        await engine.load()
        assert engine.graph.number_of_nodes() == 2
        assert engine.graph.number_of_edges() == 1

    @pytest.mark.asyncio
    async def test_save_roundtrip(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        graph_path = tmp_path / ".cortex" / "graph.json"
        engine = GraphEngine(graph_path)
        await engine.load()

        note = _make_note("wiki/test.md", "Test")
        await engine.add_note_node(note)

        engine2 = GraphEngine(graph_path)
        await engine2.load()
        assert engine2.graph.has_node("wiki/test.md")


class TestGraphEngineNodes:
    @pytest.mark.asyncio
    async def test_add_note_node(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        note = _make_note("wiki/test.md", "Test")
        await engine.add_note_node(note)
        assert engine.graph.has_node("wiki/test.md")
        assert engine.graph.nodes["wiki/test.md"]["title"] == "Test"

    @pytest.mark.asyncio
    async def test_remove_note_node(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        note = _make_note("wiki/test.md", "Test")
        await engine.add_note_node(note)
        await engine.remove_note_node("wiki/test.md")
        assert not engine.graph.has_node("wiki/test.md")

    @pytest.mark.asyncio
    async def test_remove_nonexistent_node_is_safe(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()
        await engine.remove_note_node("nonexistent")


class TestGraphEngineEdges:
    @pytest.mark.asyncio
    async def test_add_edge(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        await engine.add_note_node(_make_note("wiki/a.md", "A"))
        await engine.add_note_node(_make_note("wiki/b.md", "B"))

        edge = Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.LINKS_TO)
        await engine.add_edge(edge)
        assert engine.graph.has_edge("wiki/a.md", "wiki/b.md")

    @pytest.mark.asyncio
    async def test_remove_edge(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        await engine.add_note_node(_make_note("wiki/a.md", "A"))
        await engine.add_note_node(_make_note("wiki/b.md", "B"))

        edge = Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.LINKS_TO)
        await engine.add_edge(edge)
        await engine.remove_edge("wiki/a.md", "wiki/b.md", EdgeType.LINKS_TO)
        assert not engine.graph.has_edge("wiki/a.md", "wiki/b.md")

    @pytest.mark.asyncio
    async def test_remove_edge_wrong_type_noop(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        await engine.add_note_node(_make_note("wiki/a.md", "A"))
        await engine.add_note_node(_make_note("wiki/b.md", "B"))

        edge = Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.LINKS_TO)
        await engine.add_edge(edge)
        await engine.remove_edge("wiki/a.md", "wiki/b.md", EdgeType.CONTRADICTS)
        assert engine.graph.has_edge("wiki/a.md", "wiki/b.md")

    @pytest.mark.asyncio
    async def test_get_edges_both_directions(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        await engine.add_note_node(_make_note("wiki/a.md", "A"))
        await engine.add_note_node(_make_note("wiki/b.md", "B"))
        await engine.add_note_node(_make_note("wiki/c.md", "C"))

        await engine.add_edge(Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.LINKS_TO))
        await engine.add_edge(Edge(source="wiki/c.md", target="wiki/a.md", edge_type=EdgeType.DERIVED_FROM))

        edges = await engine.get_edges("wiki/a.md")
        assert len(edges) == 2

    @pytest.mark.asyncio
    async def test_get_edges_filter_by_type(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        await engine.add_note_node(_make_note("wiki/a.md", "A"))
        await engine.add_note_node(_make_note("wiki/b.md", "B"))

        await engine.add_edge(Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.LINKS_TO))
        await engine.add_edge(Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.CONTRADICTS))

        edges = await engine.get_edges("wiki/a.md", edge_types=[EdgeType.CONTRADICTS])
        assert len(edges) == 1
        assert edges[0].edge_type == EdgeType.CONTRADICTS

    @pytest.mark.asyncio
    async def test_get_edges_direction_out(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        await engine.add_note_node(_make_note("wiki/a.md", "A"))
        await engine.add_note_node(_make_note("wiki/b.md", "B"))
        await engine.add_note_node(_make_note("wiki/c.md", "C"))

        await engine.add_edge(Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.LINKS_TO))
        await engine.add_edge(Edge(source="wiki/c.md", target="wiki/a.md", edge_type=EdgeType.LINKS_TO))

        edges = await engine.get_edges("wiki/a.md", direction="out")
        assert len(edges) == 1
        assert edges[0].target == "wiki/b.md"


class TestGraphEngineQueries:
    @pytest.mark.asyncio
    async def test_get_contradictions(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        await engine.add_note_node(_make_note("wiki/a.md", "A"))
        await engine.add_note_node(_make_note("wiki/b.md", "B"))

        await engine.add_edge(Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.CONTRADICTS))

        contradictions = await engine.get_contradictions("wiki/a.md")
        assert len(contradictions) == 1

    @pytest.mark.asyncio
    async def test_find_orphans(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        await engine.add_note_node(_make_note("wiki/a.md", "A"))
        await engine.add_note_node(_make_note("wiki/b.md", "B"))
        await engine.add_edge(Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.LINKS_TO))

        orphans = await engine.find_orphans()
        assert "wiki/a.md" in orphans
        assert "wiki/b.md" not in orphans

    @pytest.mark.asyncio
    async def test_get_stats(self, tmp_path: Path):
        from cortex.graph.engine import GraphEngine

        engine = GraphEngine(tmp_path / "graph.json")
        await engine.load()

        await engine.add_note_node(_make_note("wiki/a.md", "A"))
        await engine.add_note_node(_make_note("wiki/b.md", "B"))
        await engine.add_edge(Edge(source="wiki/a.md", target="wiki/b.md", edge_type=EdgeType.LINKS_TO))

        stats = await engine.get_stats()
        assert stats["total_nodes"] == 2
        assert stats["total_edges"] == 1
        assert stats["orphans"] == 1
