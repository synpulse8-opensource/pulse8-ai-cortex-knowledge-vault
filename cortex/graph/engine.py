from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from cortex.vault.models import Edge, EdgeType, Note


class GraphEngine:
    """NetworkX wrapper with JSON file persistence."""

    def __init__(self, graph_path: Path) -> None:
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self.graph_path = graph_path

    async def load(self) -> None:
        """Load graph from JSON. Create empty graph if file is missing."""
        if self.graph_path.exists():
            data = json.loads(self.graph_path.read_text())
            for node in data.get("nodes", []):
                self.graph.add_node(node["id"], **node.get("attrs", {}))
            for edge in data.get("edges", []):
                self.graph.add_edge(
                    edge["source"], edge["target"], **edge.get("attrs", {})
                )

    async def save(self) -> None:
        """Persist graph to JSON file."""
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        nodes = [
            {"id": n, "attrs": dict(self.graph.nodes[n])} for n in self.graph.nodes
        ]
        edges = []
        for u, v, key, d in self.graph.edges(data=True, keys=True):
            edges.append({"source": u, "target": v, "attrs": dict(d)})
        data = {"nodes": nodes, "edges": edges}
        self.graph_path.write_text(json.dumps(data, indent=2, default=str))

    async def add_note_node(self, note: Note) -> None:
        """Add a note as a node in the graph."""
        self.graph.add_node(
            note.path,
            node_type=note.node_type.value,
            title=note.title,
            authored_by=note.provenance.authored_by,
        )
        await self.save()

    async def remove_note_node(self, path: str) -> None:
        """Remove a node and all its edges."""
        if self.graph.has_node(path):
            self.graph.remove_node(path)
            await self.save()

    async def add_edge(self, edge: Edge) -> None:
        """Add a typed edge between two nodes."""
        self.graph.add_edge(
            edge.source,
            edge.target,
            edge_type=edge.edge_type.value,
            metadata=edge.metadata,
            created_at=edge.created_at,
        )
        await self.save()

    async def remove_edge(self, source: str, target: str, edge_type: EdgeType) -> None:
        """Remove an edge matching source, target, and edge_type."""
        if not self.graph.has_edge(source, target):
            return
        keys_to_remove = []
        for key, data in self.graph[source][target].items():
            if data.get("edge_type") == edge_type.value:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            self.graph.remove_edge(source, target, key=key)
        if keys_to_remove:
            await self.save()

    async def get_edges(
        self,
        path: str,
        edge_types: list[EdgeType] | None = None,
        direction: str = "both",
    ) -> list[Edge]:
        """Get edges connected to a node, optionally filtered by type and direction."""
        results: list[Edge] = []
        type_values = {et.value for et in edge_types} if edge_types else None

        if direction in ("out", "both"):
            for _, target, data in self.graph.out_edges(path, data=True):
                et = data.get("edge_type", "")
                if type_values and et not in type_values:
                    continue
                results.append(
                    Edge(
                        source=path,
                        target=target,
                        edge_type=EdgeType(et),
                        metadata=data.get("metadata", {}),
                        created_at=data.get("created_at", ""),
                    )
                )

        if direction in ("in", "both"):
            for source, _, data in self.graph.in_edges(path, data=True):
                et = data.get("edge_type", "")
                if type_values and et not in type_values:
                    continue
                results.append(
                    Edge(
                        source=source,
                        target=path,
                        edge_type=EdgeType(et),
                        metadata=data.get("metadata", {}),
                        created_at=data.get("created_at", ""),
                    )
                )

        return results

    async def get_contradictions(self, path: str) -> list[Edge]:
        """Get all contradiction edges for a node."""
        return await self.get_edges(path, edge_types=[EdgeType.CONTRADICTS])

    async def find_orphans(self) -> list[str]:
        """Find nodes with no inbound edges."""
        return [n for n in self.graph.nodes if self.graph.in_degree(n) == 0]

    async def get_stats(self) -> dict:
        """Return graph statistics."""
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "orphans": len(await self.find_orphans()),
        }
