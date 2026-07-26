"""NetworkX-backed graph engine with JSON persistence."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import networkx as nx

from cortex.vault.models import Edge, EdgeType, Note


class GraphEngine:
    """NetworkX wrapper with JSON file persistence."""

    def __init__(self, graph_path: Path) -> None:
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self.graph_path = graph_path
        self._batch_active = False
        self._version = 0

    @property
    def mutation_version(self) -> tuple[int, int, int]:
        """Cheap change token for cache invalidation.

        Combines an explicit counter (bumped by engine mutators) with node and
        edge counts so direct ``engine.graph`` mutations (e.g. tag nodes added
        by builder/watcher) are also detected.
        """
        return (
            self._version,
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )

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

    @asynccontextmanager
    async def batch(self):
        """Defer all save() calls until the block exits, then persist once."""
        self._batch_active = True
        try:
            yield
        finally:
            self._batch_active = False
            await self._persist()

    async def save(self) -> None:
        """Persist graph to JSON file. No-op inside a batch() block."""
        if self._batch_active:
            return
        await self._persist()

    async def _persist(self) -> None:
        """Write graph JSON to disk without blocking the event loop."""
        nodes = [
            {"id": n, "attrs": dict(self.graph.nodes[n])} for n in self.graph.nodes
        ]
        edges = []
        for u, v, _key, d in self.graph.edges(data=True, keys=True):
            edges.append({"source": u, "target": v, "attrs": dict(d)})
        data = {"nodes": nodes, "edges": edges}
        await asyncio.to_thread(self._write_graph_file, data)

    def _write_graph_file(self, data: dict[str, Any]) -> None:
        """Synchronous graph JSON write (runs in a thread pool)."""
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        self.graph_path.write_text(json.dumps(data, indent=2, default=str))

    async def add_note_node(self, note: Note) -> None:
        """Add a note as a node in the graph."""
        self.graph.add_node(
            note.path,
            node_type=note.node_type.value,
            title=note.title,
            authored_by=note.provenance.authored_by,
        )
        self._version += 1
        await self.save()

    async def remove_note_node(self, path: str) -> None:
        """Remove a node and all its edges."""
        if self.graph.has_node(path):
            self.graph.remove_node(path)
            self._version += 1
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

    def _collect_edges(
        self,
        path: str,
        edge_types: list[EdgeType] | None = None,
        direction: str = "both",
    ) -> list[Edge]:
        """Pure in-memory edge lookup (no I/O)."""
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

    async def get_edges(
        self,
        path: str,
        edge_types: list[EdgeType] | None = None,
        direction: str = "both",
    ) -> list[Edge]:
        """Get edges connected to a node, optionally filtered by type and direction."""
        return self._collect_edges(path, edge_types=edge_types, direction=direction)

    async def get_edges_batch(
        self,
        paths: list[str],
        edge_types: list[EdgeType] | None = None,
    ) -> dict[str, list[Edge]]:
        """Fetch edges for multiple paths using a direct loop (all in-memory, no I/O)."""
        return {
            p: self._collect_edges(p, edge_types=edge_types) for p in paths
        }

    def _note_subgraph(self) -> nx.MultiDiGraph:
        """View of the graph without tag hub nodes.

        Tag nodes connect every note sharing a tag, which turns path and
        impact queries into noise — exclude them from traversal.
        """
        note_nodes = [
            n
            for n, data in self.graph.nodes(data=True)
            if data.get("node_type") != "tag"
        ]
        return self.graph.subgraph(note_nodes)

    def _edge_step(self, subgraph: nx.MultiDiGraph, u: str, v: str) -> dict[str, Any]:
        """Describe the edge between two adjacent nodes (either direction)."""
        if subgraph.has_edge(u, v):
            data = next(iter(subgraph[u][v].values()))
            source, target = u, v
        else:
            data = next(iter(subgraph[v][u].values()))
            source, target = v, u
        metadata = data.get("metadata", {}) or {}
        return {
            "source": source,
            "target": target,
            "edge_type": data.get("edge_type", ""),
            "origin": metadata.get("origin", "unknown"),
        }

    async def find_paths(
        self, source: str, target: str, max_paths: int = 3
    ) -> list[dict[str, Any]]:
        """Find shortest paths between two notes (undirected, tag hubs excluded).

        Each path reports the node sequence plus every hop's edge with its
        type and lineage origin, so a path is an auditable chain of
        assertions rather than a bare node list.
        """
        subgraph = self._note_subgraph()
        if source not in subgraph or target not in subgraph:
            return []
        undirected = subgraph.to_undirected(as_view=True)
        try:
            shortest = nx.all_shortest_paths(undirected, source, target)
            node_paths = []
            for node_path in shortest:
                node_paths.append(node_path)
                if len(node_paths) >= max_paths:
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

        results = []
        for node_path in node_paths:
            edges = [
                self._edge_step(subgraph, u, v)
                for u, v in zip(node_path, node_path[1:])
            ]
            results.append({"nodes": node_path, "edges": edges})
        return results

    async def impact(self, path: str, max_depth: int = 5) -> list[dict[str, Any]]:
        """Walk upstream dependents: every note that links (directly or
        transitively) to ``path``. Used for change-impact analysis — when a
        note changes, these are the notes whose content relies on it."""
        subgraph = self._note_subgraph()
        if path not in subgraph:
            return []

        results: list[dict[str, Any]] = []
        visited = {path}
        frontier = [path]
        depth = 0
        while frontier and depth < max_depth:
            depth += 1
            next_frontier = []
            for node in frontier:
                for dependent, _, data in subgraph.in_edges(node, data=True):
                    if dependent in visited:
                        continue
                    visited.add(dependent)
                    metadata = data.get("metadata", {}) or {}
                    results.append(
                        {
                            "path": dependent,
                            "depth": depth,
                            "via": node,
                            "edge_type": data.get("edge_type", ""),
                            "origin": metadata.get("origin", "unknown"),
                        }
                    )
                    next_frontier.append(dependent)
            frontier = next_frontier
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
