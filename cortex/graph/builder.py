"""Knowledge graph builder — creates nodes and edges from scanned notes."""
from __future__ import annotations

from pathlib import Path

from cortex.graph.engine import GraphEngine
from cortex.vault.models import Edge, EdgeType, NodeType, Note
from cortex.vault.reader import build_wikilink_index, resolve_wikilink


async def build_graph(
    notes: list[Note], graph_path: Path, vault_root: Path
) -> GraphEngine:
    """Build or rebuild the knowledge graph from scanned notes.

    1. Add all notes as nodes
    2. Resolve wikilinks → links_to edges
    3. Extract tags → tagged_with edges to tag nodes
    4. Detect source_path → derived_from edges
    """
    engine = GraphEngine(graph_path)
    await engine.load()

    wikilink_index = build_wikilink_index(vault_root)

    # Lineage: everything this builder derives from note structure is
    # deterministic, so it carries origin="extracted".
    extracted = {"origin": "extracted"}

    async with engine.batch():
        for note in notes:
            await engine.add_note_node(note)

        for note in notes:
            for link in note.wikilinks:
                resolved = resolve_wikilink(link, vault_root, _index=wikilink_index)
                if resolved:
                    await engine.add_edge(
                        Edge(
                            source=note.path,
                            target=resolved,
                            edge_type=EdgeType.LINKS_TO,
                            metadata=dict(extracted),
                        )
                    )

            for tag in note.tags:
                tag_id = f"tag:{tag}"
                if not engine.graph.has_node(tag_id):
                    engine.graph.add_node(tag_id, node_type=NodeType.TAG.value, title=tag)
                await engine.add_edge(
                    Edge(
                        source=note.path,
                        target=tag_id,
                        edge_type=EdgeType.TAGGED_WITH,
                        metadata=dict(extracted),
                    )
                )

            source_path = note.frontmatter.get("source_path")
            if source_path:
                if not engine.graph.has_node(source_path):
                    engine.graph.add_node(
                        source_path,
                        node_type=NodeType.RAW_SOURCE.value,
                        title=source_path,
                    )
                await engine.add_edge(
                    Edge(
                        source=note.path,
                        target=source_path,
                        edge_type=EdgeType.DERIVED_FROM,
                        metadata=dict(extracted),
                    )
                )

    return engine
