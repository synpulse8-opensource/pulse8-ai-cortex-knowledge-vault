"""Context window builder — search, BFS expand, rank, and assemble."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from pathlib import Path

from cortex.graph.engine import GraphEngine
from cortex.search.qmd import QMDSearch
from cortex.vault.models import ContextWindow, Edge, EdgeType, Note
from cortex.vault.reader import read_note

logger = logging.getLogger(__name__)


async def build_context_window(
    query: str,
    searcher: QMDSearch,
    graph: GraphEngine,
    vault_root: Path,
    max_notes: int = 8,
    max_depth: int = 2,
    mode: str = "hybrid",
) -> ContextWindow:
    """Build a context window by searching, expanding via BFS, and ranking.

    1. Seed: search via QMD → top-k note paths
    2. Expand: BFS from seeds up to max_depth
    3. Rank: (search_score × 0.6 + degree_centrality × 0.4)
    4. Read: load full Note content for top nodes
    5. Edges: collect all edges between result nodes
    6. Contradictions: find contradicts edges in subgraph
    """
    search_results = await searcher.search(query, mode=mode, top_k=max_notes * 2)

    scores: dict[str, float] = {}
    for r in search_results:
        path = r.get("path", "")
        if path and graph.graph.has_node(path):
            scores[path] = r.get("score", 0.0)

    if not scores:
        return ContextWindow(
            notes=[],
            edges=[],
            contradictions=[],
            total_nodes_explored=0,
            total_edges_explored=0,
        )

    explored_nodes: set[str] = set()
    queue: deque[tuple[str, int]] = deque()

    for path in scores:
        queue.append((path, 0))
        explored_nodes.add(path)

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue

        neighbors: set[str] = set()
        for _, target, _ in graph.graph.out_edges(current, data=True):
            neighbors.add(target)
        for source, _, _ in graph.graph.in_edges(current, data=True):
            neighbors.add(source)

        for neighbor in neighbors:
            if neighbor not in explored_nodes and graph.graph.has_node(neighbor):
                explored_nodes.add(neighbor)
                if neighbor not in scores:
                    scores[neighbor] = 0.0
                queue.append((neighbor, depth + 1))

    centrality = {}
    total_nodes = graph.graph.number_of_nodes()
    if total_nodes > 1:
        for node in scores:
            centrality[node] = graph.graph.degree(node) / (total_nodes - 1)
    else:
        for node in scores:
            centrality[node] = 0.0

    max_score = max(scores.values()) if scores else 1.0
    if max_score == 0:
        max_score = 1.0

    ranked: list[tuple[str, float]] = []
    for path, search_score in scores.items():
        normalized_search = search_score / max_score
        combined = normalized_search * 0.6 + centrality.get(path, 0.0) * 0.4
        ranked.append((path, combined))

    ranked.sort(key=lambda x: x[1], reverse=True)
    top_paths = [path for path, _ in ranked[:max_notes]]

    async def _read_one(path: str) -> Note | None:
        try:
            return await asyncio.to_thread(read_note, vault_root / path, vault_root)
        except (FileNotFoundError, Exception):
            return None

    loaded = await asyncio.gather(*(_read_one(p) for p in top_paths))
    notes: list[Note] = [n for n in loaded if n is not None]

    top_set = set(top_paths)
    collected_edges: list[Edge] = []
    contradictions: list[tuple[str, str]] = []
    total_edges_explored = 0

    edges_by_path = await graph.get_edges_batch(top_paths)
    for path in top_paths:
        edges = edges_by_path.get(path, [])
        total_edges_explored += len(edges)
        for edge in edges:
            if edge.source in top_set or edge.target in top_set:
                collected_edges.append(edge)
            if edge.edge_type == EdgeType.CONTRADICTS:
                contradictions.append((edge.source, edge.target))

    return ContextWindow(
        notes=notes,
        edges=collected_edges,
        contradictions=contradictions,
        total_nodes_explored=len(explored_nodes),
        total_edges_explored=total_edges_explored,
    )
