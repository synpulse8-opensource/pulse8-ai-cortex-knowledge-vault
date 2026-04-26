"""Domain models — nodes, edges, provenance, and result types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any


class NodeType(str, Enum):
    """Type of node in the knowledge graph."""
    NOTE = "note"
    AGENT_DEF = "agent_def"
    MEMORY = "memory"
    SESSION = "session"
    RAW_SOURCE = "raw_source"
    TAG = "tag"


class EdgeType(str, Enum):
    """Type of directed edge between graph nodes."""
    LINKS_TO = "links_to"
    AUTHORED_BY = "authored_by"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"
    MEMORY_OF = "memory_of"
    TAGGED_WITH = "tagged_with"


@dataclass
class Provenance:
    """Authorship and origin metadata for a note."""
    authored_by: str = "human"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model: Optional[str] = None
    confidence: Optional[float] = None
    source_path: Optional[str] = None


@dataclass
class Note:
    """A parsed Markdown note with frontmatter, wikilinks, and tags."""
    path: str
    title: str
    content: str
    frontmatter: dict[str, Any]
    node_type: NodeType
    provenance: Provenance
    wikilinks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class Edge:
    """A typed directed edge in the knowledge graph."""
    source: str
    target: str
    edge_type: EdgeType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class SearchResult:
    """A single search hit with optional graph enrichment."""
    path: str
    title: str
    score: float
    snippet: str
    node_type: NodeType = NodeType.NOTE
    edges: list[Edge] = field(default_factory=list)


@dataclass
class ContextWindow:
    """Assembled context window returned by the context builder."""
    notes: list[Note]
    edges: list[Edge]
    contradictions: list[tuple[str, str]]
    total_nodes_explored: int
    total_edges_explored: int
