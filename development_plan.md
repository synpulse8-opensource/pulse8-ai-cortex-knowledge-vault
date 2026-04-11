# CORTEX — Development Instructions

You are building **Cortex**, an agent-native knowledge OS built entirely on Markdown files. Cortex is a knowledge substrate where AI agents, AI assistants (Claude, Copilot), and humans collaborate through a unified MCP interface backed by a graph engine.

**Read this entire file before writing any code.**

---

## Inspiration

This project is inspired by Andrej Karpathy's LLM Wiki pattern:
https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

The core idea: instead of retrieving from raw documents at query time (RAG), an LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of Markdown files. Knowledge is compiled once and kept current, not re-derived on every query. The wiki is a persistent, compounding artifact.

Cortex extends this pattern with:
- A **typed knowledge graph** (not just wikilinks — contradiction, authorship, and derivation edges)
- An **MCP tool surface** so any AI consumer (Claude, Copilot, Keystone, CLI) plugs in
- **LLM-powered knowledge compilation** from raw ingested sources
- **QMD** (https://github.com/tobi/qmd) as the local search engine — hybrid BM25 + vector + LLM re-ranking
- **Zero database** — the filesystem IS the database. No SQLite, no Postgres, nothing. Just .md and .json files.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      Consumers                            │
│  Claude Desktop · Copilot · Keystone · Cursor · CLI       │
└────────────────────────┬─────────────────────────────────┘
                         │ MCP (stdio / SSE)
┌────────────────────────▼─────────────────────────────────┐
│                  Cortex MCP Server                        │
│  vault:read · vault:write · vault:search · vault:link     │
│  vault:context · vault:ingest · vault:compile             │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                    FastAPI Core                            │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Graph Engine  │  │ QMD Search   │  │ LLM Compiler   │  │
│  │ (NetworkX +   │  │ (CLI/MCP     │  │ (raw → wiki    │  │
│  │  JSON files)  │  │  bridge)     │  │  via LLM)      │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                 Vault (filesystem)                         │
│                                                           │
│  raw/          ← Immutable source material (PDFs, text,   │
│                  transcripts, URLs). LLM reads, never      │
│                  modifies.                                  │
│                                                           │
│  wiki/         ← LLM-generated knowledge articles.        │
│                  Structured, interlinked .md files.         │
│                  Entity pages, concept pages, summaries.    │
│                                                           │
│  agents/       ← .agent.md convention files                │
│  sessions/     ← .session.md auto-captured transcripts     │
│  daily/        ← Daily compilation logs                    │
│                                                           │
│  .cortex/      ← Internal state                            │
│    graph.json  ← Persisted graph edges                     │
│    log.md      ← Append-only operation log                 │
│    index.md    ← Auto-generated vault index                │
│    config.json ← Runtime config                            │
└───────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12+ | Fast iteration, rich ecosystem, Cursor-native |
| Package manager | uv | Fast, deterministic |
| Web framework | FastAPI (async) | Typed, OpenAPI docs, async-native |
| MCP SDK | `mcp[cli]` | Official Anthropic Python SDK, stdio + SSE |
| Search | **QMD** (`@tobilu/qmd`) | Local hybrid search with BM25 + vector + LLM re-ranking. Karpathy recommended. |
| Graph (memory) | NetworkX | Mature, typed node/edge attributes |
| Graph (persist) | JSON file (`.cortex/graph.json`) | No database. Load on startup, save on mutation. |
| LLM calls | Anthropic SDK (`anthropic`) | For knowledge compilation (raw → wiki) |
| Markdown parsing | python-frontmatter + regex | YAML frontmatter + wikilink extraction |
| File watching | watchfiles | Rust-backed, async fs.watch |
| Container | Docker | Single Dockerfile, mounts vault as volume |
| Testing | pytest + pytest-asyncio | Standard |

**NO DATABASE.** No SQLite, no Postgres, no Redis. The vault directory IS the entire persistence layer. QMD manages its own internal index transparently.

---

## Project Structure

```
cortex/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── README.md
├── CLAUDE.md                       # THIS FILE
│
├── cortex/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app + lifespan
│   ├── config.py                   # Pydantic settings
│   │
│   ├── vault/                      # Vault I/O layer
│   │   ├── __init__.py
│   │   ├── reader.py               # Read .md, parse frontmatter, extract wikilinks
│   │   ├── writer.py               # Write .md, merge frontmatter, inject provenance
│   │   ├── watcher.py              # fs.watch → reindex + graph update
│   │   └── models.py               # Note, Provenance, NodeType, Edge, EdgeType
│   │
│   ├── graph/                      # Graph engine
│   │   ├── __init__.py
│   │   ├── engine.py               # NetworkX wrapper + JSON persistence
│   │   ├── builder.py              # Scan vault → build graph
│   │   └── context.py              # Subgraph extraction for vault:context
│   │
│   ├── search/                     # QMD bridge
│   │   ├── __init__.py
│   │   └── qmd.py                  # Shell out to qmd CLI or call QMD MCP
│   │
│   ├── compiler/                   # LLM knowledge compilation
│   │   ├── __init__.py
│   │   ├── compiler.py             # Orchestrate: raw source → wiki articles
│   │   ├── extractor.py            # Extract entities, claims, links from source
│   │   └── prompts.py              # System prompts for compilation tasks
│   │
│   ├── mcp/                        # MCP server
│   │   ├── __init__.py
│   │   ├── server.py               # MCP server (stdio + SSE)
│   │   └── tools.py                # All tool definitions + handlers
│   │
│   ├── api/                        # REST API
│   │   ├── __init__.py
│   │   └── routes.py               # HTTP endpoints mirroring MCP tools
│   │
│   └── log/                        # Logging (file-based, no DB)
│       ├── __init__.py
│       └── audit.py                # Append to .cortex/log.md
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_vault.py
│   ├── test_graph.py
│   ├── test_compiler.py
│   └── test_mcp.py
│
├── scripts/
│   ├── serve.py                    # Start MCP server (stdio or SSE)
│   ├── compile.py                  # Manually trigger compilation of raw/ sources
│   ├── reindex.py                  # Rebuild graph + QMD index from scratch
│   └── lint.py                     # Vault health check
│
└── example_vault/                  # Sample vault for dev/testing
    ├── raw/
    │   ├── transformer-paper.txt
    │   └── meeting-transcript-2026-04-11.txt
    ├── wiki/
    │   ├── transformers.md
    │   ├── attention-mechanisms.md
    │   └── rnn-claims.md
    ├── agents/
    │   └── research-scout.agent.md
    ├── sessions/
    │   └── 2026-04-11.session.md
    ├── daily/
    │   └── 2026-04-11.md
    └── .cortex/
        ├── graph.json
        ├── log.md
        └── index.md
```

---

## Step 1 — Project Scaffold

```bash
uv init cortex
cd cortex
uv add fastapi uvicorn "mcp[cli]" networkx python-frontmatter watchfiles pydantic-settings anthropic httpx
uv add --dev pytest pytest-asyncio
```

QMD is installed separately in the container (it's a Node.js tool):
```bash
npm install -g @tobilu/qmd
```

---

## Step 2 — Configuration

Create `cortex/config.py`:

```python
from pathlib import Path
from pydantic_settings import BaseSettings


class CortexSettings(BaseSettings):
    # Vault
    vault_path: Path = Path("./vault")

    # QMD
    qmd_bin: str = "qmd"  # path to qmd binary

    # LLM (for knowledge compilation)
    anthropic_api_key: str = ""
    compiler_model: str = "claude-sonnet-4-20250514"
    compiler_max_tokens: int = 4096

    # MCP
    mcp_transport: str = "stdio"  # "stdio" | "sse"
    mcp_sse_host: str = "0.0.0.0"
    mcp_sse_port: int = 8420

    # Graph
    max_context_depth: int = 2
    max_context_notes: int = 8

    # Provenance
    default_author: str = "human"

    class Config:
        env_prefix = "CORTEX_"


settings = CortexSettings()
```

---

## Step 3 — Data Models

Create `cortex/vault/models.py` with these dataclasses:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any


class NodeType(str, Enum):
    NOTE = "note"
    AGENT_DEF = "agent_def"
    MEMORY = "memory"
    SESSION = "session"
    RAW_SOURCE = "raw_source"
    TAG = "tag"


class EdgeType(str, Enum):
    LINKS_TO = "links_to"
    AUTHORED_BY = "authored_by"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"
    MEMORY_OF = "memory_of"
    TAGGED_WITH = "tagged_with"


@dataclass
class Provenance:
    authored_by: str = "human"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model: Optional[str] = None
    confidence: Optional[float] = None
    source_path: Optional[str] = None


@dataclass
class Note:
    path: str                           # relative to vault root
    title: str
    content: str                        # raw markdown body
    frontmatter: dict[str, Any]
    node_type: NodeType
    provenance: Provenance
    wikilinks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class Edge:
    source: str
    target: str
    edge_type: EdgeType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SearchResult:
    path: str
    title: str
    score: float
    snippet: str
    node_type: NodeType = NodeType.NOTE
    edges: list[Edge] = field(default_factory=list)


@dataclass
class ContextWindow:
    notes: list[Note]
    edges: list[Edge]
    contradictions: list[tuple[str, str]]
    total_nodes_explored: int
    total_edges_explored: int
```

---

## Step 4 — Vault Reader & Writer

### Reader (`cortex/vault/reader.py`)

Implement:

1. `extract_wikilinks(content: str) -> list[str]` — regex `\[\[([^\]|]+)(?:\|[^\]]+)?\]\]`
2. `infer_node_type(path: str, frontmatter: dict) -> NodeType`:
   - `raw/` prefix → `RAW_SOURCE`
   - `.agent.md` suffix → `AGENT_DEF`
   - `.memory.md` suffix → `MEMORY`
   - `.session.md` suffix → `SESSION`
   - frontmatter `type` field if present
   - default → `NOTE`
3. `read_note(path: Path, vault_root: Path) -> Note` — read file, parse frontmatter with `python-frontmatter`, extract wikilinks. Title from frontmatter `title`, first `# heading`, or filename stem.
4. `scan_vault(vault_root: Path) -> list[Note]` — recursively find all .md files. Skip `.cortex/` directory. Include files in `wiki/`, `agents/`, `sessions/`, `daily/`. Files in `raw/` that are .md are also scanned.
5. `resolve_wikilink(link: str, vault_root: Path) -> str | None` — find matching .md file by name. Search `wiki/` first, then other directories.

### Writer (`cortex/vault/writer.py`)

Implement:

1. `merge_frontmatter(existing: dict, incoming: dict) -> dict` — deep merge. Incoming overrides but never deletes existing keys.
2. `inject_provenance(frontmatter: dict, authored_by: str, model: str | None = None, confidence: float | None = None) -> dict` — set `authored_by`, `updated_at` (ISO now). Set `created_at` only if absent. Set `model` and `confidence` if provided.
3. `write_note(path: Path, vault_root: Path, content: str, frontmatter: dict | None = None, mode: str = "upsert", authored_by: str = "human", model: str | None = None) -> Note`:
   - `create`: error if file exists
   - `update`: error if file doesn't exist, merge frontmatter
   - `upsert`: create or update
   - Always inject provenance
   - Create parent directories if needed
   - Return the resulting Note

---

## Step 5 — Graph Engine (JSON-persisted, no database)

### Engine (`cortex/graph/engine.py`)

The graph uses NetworkX in memory and persists to `.cortex/graph.json` on every mutation.

```python
import json
import networkx as nx
from pathlib import Path
from cortex.vault.models import Note, Edge, EdgeType, NodeType


class GraphEngine:
    def __init__(self, graph_path: Path):
        self.graph = nx.DiGraph()
        self.graph_path = graph_path

    # ── Persistence ──

    async def load(self) -> None:
        """Load graph from .cortex/graph.json. Create empty if missing."""
        if self.graph_path.exists():
            data = json.loads(self.graph_path.read_text())
            for node in data.get("nodes", []):
                self.graph.add_node(node["id"], **node.get("attrs", {}))
            for edge in data.get("edges", []):
                self.graph.add_edge(edge["source"], edge["target"], **edge.get("attrs", {}))

    async def save(self) -> None:
        """Persist graph to .cortex/graph.json."""
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [
                {"id": n, "attrs": dict(self.graph.nodes[n])}
                for n in self.graph.nodes
            ],
            "edges": [
                {"source": u, "target": v, "attrs": dict(d)}
                for u, v, d in self.graph.edges(data=True)
            ],
        }
        self.graph_path.write_text(json.dumps(data, indent=2, default=str))

    # ── Mutations (always call save() after) ──

    async def add_note_node(self, note: Note) -> None:
        self.graph.add_node(
            note.path,
            node_type=note.node_type.value,
            title=note.title,
            authored_by=note.provenance.authored_by,
        )
        await self.save()

    async def remove_note_node(self, path: str) -> None:
        if self.graph.has_node(path):
            self.graph.remove_node(path)
            await self.save()

    async def add_edge(self, edge: Edge) -> None:
        self.graph.add_edge(
            edge.source, edge.target,
            edge_type=edge.edge_type.value,
            metadata=edge.metadata,
            created_at=edge.created_at,
        )
        await self.save()

    async def remove_edge(self, source: str, target: str, edge_type: EdgeType) -> None:
        if self.graph.has_edge(source, target):
            data = self.graph.edges[source, target]
            if data.get("edge_type") == edge_type.value:
                self.graph.remove_edge(source, target)
                await self.save()

    # ── Queries (no save needed) ──

    async def get_edges(self, path: str, edge_types: list[EdgeType] | None = None, direction: str = "both") -> list[Edge]:
        """Get edges connected to a node. Direction: 'in', 'out', 'both'."""
        # ... iterate out_edges and in_edges, filter by edge_types, return Edge list

    async def get_contradictions(self, path: str) -> list[Edge]:
        return await self.get_edges(path, edge_types=[EdgeType.CONTRADICTS])

    async def find_orphans(self) -> list[str]:
        """Notes with no inbound edges."""
        # ... iterate nodes, check in_degree == 0

    async def get_stats(self) -> dict:
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "orphans": len(await self.find_orphans()),
        }
```

### Builder (`cortex/graph/builder.py`)

Implement `build_graph(notes: list[Note], graph_path: Path) -> GraphEngine`:

1. Create GraphEngine with graph_path
2. Try to load existing graph.json (incremental)
3. Add all notes as nodes
4. For each note, resolve wikilinks → create `links_to` edges
5. For each note, extract tags → create `tagged_with` edges to tag nodes
6. For notes in `wiki/` that have `source_path` in frontmatter → create `derived_from` edge to the raw source
7. Save graph
8. Return engine

### Context Window (`cortex/graph/context.py`)

Implement `build_context_window(query, searcher, graph, reader, vault_root, max_notes=8, max_depth=2) -> ContextWindow`:

1. **Seed**: search via QMD → top-k note paths
2. **Expand**: BFS from seeds up to max_depth
3. **Rank**: (search_score × 0.6 + degree_centrality × 0.4), keep top max_notes
4. **Read**: load full Note content for top nodes
5. **Edges**: collect all edges between result nodes
6. **Contradictions**: find `contradicts` edges in subgraph
7. **Return**: ContextWindow

---

## Step 6 — QMD Search Bridge

### `cortex/search/qmd.py`

QMD is a Node.js CLI tool. Cortex shells out to it or optionally connects via QMD's MCP server. **Do NOT reimplement search. Use QMD.**

```python
import asyncio
import json
import subprocess
from pathlib import Path
from cortex.config import settings


class QMDSearch:
    """Bridge to QMD search engine (https://github.com/tobi/qmd)."""

    def __init__(self, vault_path: Path, qmd_bin: str = "qmd"):
        self.vault_path = vault_path
        self.qmd_bin = qmd_bin
        self._initialized = False

    async def initialize(self) -> None:
        """Set up QMD collection for the vault wiki/ directory."""
        await self._run(["collection", "add", str(self.vault_path / "wiki"), "--name", "wiki"])
        await self._run(["collection", "add", str(self.vault_path / "agents"), "--name", "agents"])
        await self._run(["collection", "add", str(self.vault_path / "sessions"), "--name", "sessions"])
        await self._run(["collection", "add", str(self.vault_path / "daily"), "--name", "daily"])
        await self._run(["context", "add", "qmd://wiki", "Knowledge articles compiled from raw sources"])
        await self._run(["context", "add", "qmd://agents", "Agent definition files"])
        await self._run(["context", "add", "qmd://sessions", "Session transcripts"])
        await self.update()
        self._initialized = True

    async def update(self) -> None:
        """Re-index and re-embed all collections."""
        await self._run(["update"])
        await self._run(["embed"])

    async def search(self, query: str, mode: str = "hybrid", collection: str | None = None, top_k: int = 10) -> list[dict]:
        """
        Search the vault via QMD.
        mode: 'keyword' → qmd search, 'semantic' → qmd vsearch, 'hybrid' → qmd query
        """
        cmd_map = {"keyword": "search", "semantic": "vsearch", "hybrid": "query"}
        cmd = cmd_map.get(mode, "query")
        args = [cmd, query, "--json", "-n", str(top_k)]
        if collection:
            args.extend(["-c", collection])
        result = await self._run(args)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return []

    async def _run(self, args: list[str]) -> str:
        """Run a QMD CLI command and return stdout."""
        proc = await asyncio.create_subprocess_exec(
            self.qmd_bin, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"QMD error: {stderr.decode()}")
        return stdout.decode()
```

---

## Step 7 — LLM Knowledge Compiler

This is the Karpathy pattern: when raw sources land in `raw/`, the compiler reads them and produces structured wiki articles in `wiki/`.

### `cortex/compiler/prompts.py`

Define system prompts as constants:

```python
INGEST_SYSTEM_PROMPT = """You are a knowledge compiler for a Markdown wiki called Cortex.

Given a raw source document, you must:
1. Read the source carefully and identify key entities, concepts, claims, and relationships.
2. Produce one or more structured Markdown wiki articles.
3. Each article must have YAML frontmatter with: title, tags, authored_by (your model name), created_at, source_path (path to the raw source).
4. Use [[wikilinks]] to cross-reference other concepts. Link generously.
5. Flag any claims that might contradict existing knowledge with > [!contradiction] callouts.
6. Write clearly and concisely. The wiki is for both humans and LLMs to read.

Output format: return a JSON array of objects, each with:
- "filename": suggested filename (kebab-case, no extension)
- "frontmatter": YAML frontmatter as a dict
- "content": Markdown body content

Do NOT include the raw source text verbatim. Synthesize and structure it."""

COMPILE_SYSTEM_PROMPT = """You are maintaining a knowledge wiki called Cortex.

You will receive:
1. A NEW article that was just created from a raw source.
2. A list of EXISTING wiki articles (title + path + tags) from the index.

Your job:
1. Identify which existing articles should be updated with cross-references to the new article.
2. Identify if any existing claims are contradicted by the new article.
3. For each article to update, output the specific changes needed.

Output format: return a JSON array of objects, each with:
- "path": path to the existing article to update
- "action": "add_link" | "add_contradiction" | "update_content"
- "details": description of what to add or change"""
```

### `cortex/compiler/compiler.py`

Implement the `KnowledgeCompiler` class:

```python
import json
from pathlib import Path
from anthropic import AsyncAnthropic
from cortex.config import settings
from cortex.vault.reader import read_note, scan_vault
from cortex.vault.writer import write_note
from cortex.compiler.prompts import INGEST_SYSTEM_PROMPT, COMPILE_SYSTEM_PROMPT


class KnowledgeCompiler:
    """Compiles raw sources into structured wiki articles using an LLM."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.compiler_model

    async def ingest_source(self, source_path: Path) -> list[Path]:
        """
        Read a raw source file, call LLM to produce wiki articles,
        write them to wiki/, return list of created file paths.
        """
        source_content = source_path.read_text()
        relative_source = str(source_path.relative_to(self.vault_path))

        # Get existing index for cross-referencing context
        index_content = self._build_index_context()

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=settings.compiler_max_tokens,
            system=INGEST_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"## Raw Source: {relative_source}\n\n{source_content}\n\n## Existing Wiki Index\n\n{index_content}"
            }],
        )

        # Parse LLM response as JSON array of articles
        articles = self._parse_articles(response.content[0].text)

        # Write each article to wiki/
        created_paths = []
        for article in articles:
            filename = article["filename"]
            if not filename.endswith(".md"):
                filename += ".md"
            note_path = self.vault_path / "wiki" / filename

            frontmatter = article.get("frontmatter", {})
            frontmatter["source_path"] = relative_source

            written = write_note(
                path=note_path,
                vault_root=self.vault_path,
                content=article["content"],
                frontmatter=frontmatter,
                mode="upsert",
                authored_by=self.model,
                model=self.model,
            )
            created_paths.append(note_path)

        return created_paths

    async def compile_cross_references(self, new_paths: list[Path]) -> None:
        """
        After new articles are created, ask LLM to identify
        cross-references and contradictions with existing articles.
        Then update existing articles accordingly.
        """
        # Read new articles
        new_articles = []
        for p in new_paths:
            note = read_note(p, self.vault_path)
            new_articles.append(f"### {note.title}\nPath: {note.path}\nTags: {', '.join(note.tags)}\n\n{note.content[:500]}")

        index_context = self._build_index_context()

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=settings.compiler_max_tokens,
            system=COMPILE_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"## New Articles\n\n{'---'.join(new_articles)}\n\n## Existing Wiki Index\n\n{index_context}"
            }],
        )

        updates = self._parse_updates(response.content[0].text)
        await self._apply_updates(updates)

    def _build_index_context(self) -> str:
        """Build a summary of existing wiki articles for LLM context."""
        wiki_dir = self.vault_path / "wiki"
        if not wiki_dir.exists():
            return "No existing articles."
        lines = []
        for md_file in sorted(wiki_dir.rglob("*.md")):
            note = read_note(md_file, self.vault_path)
            tags = ", ".join(note.tags) if note.tags else "none"
            lines.append(f"- [{note.title}]({note.path}) — tags: {tags}")
        return "\n".join(lines) if lines else "No existing articles."

    def _parse_articles(self, text: str) -> list[dict]:
        """Parse LLM response into article dicts. Handle JSON in markdown code blocks."""
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return []

    def _parse_updates(self, text: str) -> list[dict]:
        """Parse cross-reference updates from LLM response."""
        # Same pattern as _parse_articles
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return []

    async def _apply_updates(self, updates: list[dict]) -> None:
        """Apply cross-reference updates to existing articles."""
        for update in updates:
            path = self.vault_path / update["path"]
            if not path.exists():
                continue
            action = update.get("action", "")
            details = update.get("details", "")
            if action == "add_link":
                # Append a "See also" line to the article
                content = path.read_text()
                content += f"\n\nSee also: {details}\n"
                path.write_text(content)
            elif action == "add_contradiction":
                content = path.read_text()
                content += f"\n\n> [!contradiction]\n> {details}\n"
                path.write_text(content)
```

### `cortex/compiler/extractor.py`

Implement helpers for the ingestion pipeline:

1. `extract_text_from_pdf(path: Path) -> str` — use `subprocess` to call `pdftotext` or Python `pymupdf` / `pdfplumber`. Return plain text.
2. `extract_text_from_url(url: str) -> str` — use `httpx` to fetch, strip HTML to text.
3. `detect_source_type(path: Path) -> str` — return "pdf", "text", "markdown", "url" based on extension or content.

---

## Step 8 — Vault Index & Log (file-based, no database)

### Index (`cortex/vault/index.py`)

The index is an auto-generated `index.md` file in `.cortex/`. Updated on every vault:write and after compilation.

```python
async def rebuild_index(vault_root: Path) -> None:
    """Rebuild .cortex/index.md from vault contents."""
    index_path = vault_root / ".cortex" / "index.md"
    notes = scan_vault(vault_root)

    sections = {"wiki": [], "agents": [], "sessions": [], "daily": [], "raw": []}
    for note in notes:
        rel = note.path
        bucket = rel.split("/")[0] if "/" in rel else "wiki"
        if bucket in sections:
            tags = ", ".join(note.tags) if note.tags else ""
            sections[bucket].append(f"- [[{note.title}]] ({rel}) {f'— {tags}' if tags else ''}")

    lines = ["# Cortex Vault Index\n", f"_Auto-generated. {len(notes)} notes total._\n"]
    for section, items in sections.items():
        if items:
            lines.append(f"\n## {section.title()}\n")
            lines.extend(sorted(items))

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines))
```

### Audit Log (`cortex/log/audit.py`)

Append-only Markdown log at `.cortex/log.md`. No database.

```python
from datetime import datetime, timezone
from pathlib import Path


async def log_operation(vault_root: Path, consumer: str, tool: str, summary: str) -> None:
    """Append an entry to .cortex/log.md."""
    log_path = vault_root / ".cortex" / "log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"## [{timestamp}] {tool} | {consumer}\n\n{summary}\n\n"

    with open(log_path, "a") as f:
        f.write(entry)
```

---

## Step 9 — MCP Server

### Tool Definitions

Register 7 MCP tools in `cortex/mcp/tools.py`:

**vault_read** — Read note by path or glob. Returns frontmatter + content + edges from graph.

**vault_write** — Create/update note. Merge frontmatter, inject provenance, update graph, update QMD index, rebuild vault index.

**vault_search** — Delegate to QMD. Params: `query`, `mode` (keyword/semantic/hybrid), `collection`, `top_k`. Enrich results with edges from graph.

**vault_link** — Create/query/delete typed edges in graph. Params: `action`, `source`, `target`, `edge_type`, `metadata`.

**vault_context** — Build context window. Search via QMD → expand via graph BFS → return subgraph with contradictions.

**vault_ingest** — Accept raw source content. Write to `raw/` directory. Optionally trigger LLM compilation immediately.
- Params: `source_type` (text/pdf/url), `content`, `filename`, `auto_compile` (bool, default false)
- If auto_compile is true, call KnowledgeCompiler.ingest_source after writing to raw/

**vault_compile** — Manually trigger LLM compilation of unprocessed raw sources. Scans `raw/` for files not yet referenced by any `wiki/` article's `source_path` frontmatter. Compiles each and updates cross-references.

### Server Entrypoint (`cortex/mcp/server.py`)

```python
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server

app = Server("cortex")

# Register all tools via @app.list_tools() and @app.call_tool()
# Tools import shared services: graph, qmd_search, compiler, reader, writer

async def run_stdio():
    # Initialize vault, graph, QMD
    from cortex.config import settings
    from cortex.graph.engine import GraphEngine
    from cortex.graph.builder import build_graph
    from cortex.vault.reader import scan_vault
    from cortex.search.qmd import QMDSearch

    vault_path = settings.vault_path
    graph = GraphEngine(vault_path / ".cortex" / "graph.json")
    await graph.load()

    notes = scan_vault(vault_path)
    graph = await build_graph(notes, vault_path / ".cortex" / "graph.json")

    qmd = QMDSearch(vault_path, settings.qmd_bin)
    await qmd.initialize()

    # ... register tools with these dependencies
    # ... start stdio server

    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())
```

Make runnable via `python -m cortex.mcp.server` by creating `cortex/mcp/__main__.py`.

---

## Step 10 — FastAPI Application

Create `cortex/main.py`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from cortex.config import settings
from cortex.graph.engine import GraphEngine
from cortex.graph.builder import build_graph
from cortex.vault.reader import scan_vault
from cortex.search.qmd import QMDSearch
from cortex.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    vault_path = settings.vault_path
    # Load graph
    app.state.graph = GraphEngine(vault_path / ".cortex" / "graph.json")
    await app.state.graph.load()
    notes = scan_vault(vault_path)
    app.state.graph = await build_graph(notes, vault_path / ".cortex" / "graph.json")
    # Initialize QMD
    app.state.qmd = QMDSearch(vault_path, settings.qmd_bin)
    await app.state.qmd.initialize()
    # TODO: start file watcher as background task
    yield


app = FastAPI(title="Cortex", version="0.1.0", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
```

REST routes in `cortex/api/routes.py`:

```
GET    /notes/{path:path}         → vault:read
PUT    /notes/{path:path}         → vault:write
GET    /search?q=...&mode=...     → vault:search (delegates to QMD)
POST   /links                     → vault:link create
GET    /links?source=...          → vault:link query
DELETE /links/{source}/{target}   → vault:link delete
POST   /context                   → vault:context
POST   /ingest                    → vault:ingest (write to raw/)
POST   /compile                   → vault:compile (trigger LLM compilation)
GET    /graph/stats               → graph stats
GET    /health                    → status
```

---

## Step 11 — Container

### `Dockerfile`

```dockerfile
FROM python:3.12-slim

# Install Node.js (for QMD) + system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @tobilu/qmd \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY cortex/ cortex/
COPY scripts/ scripts/

# Create default vault directory
RUN mkdir -p /vault/raw /vault/wiki /vault/agents /vault/sessions /vault/daily /vault/.cortex

# Environment
ENV CORTEX_VAULT_PATH=/vault
ENV CORTEX_MCP_TRANSPORT=sse
ENV CORTEX_MCP_SSE_PORT=8420

EXPOSE 8420

# Default: run FastAPI with SSE MCP endpoint
CMD ["uv", "run", "uvicorn", "cortex.main:app", "--host", "0.0.0.0", "--port", "8420"]
```

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  cortex:
    build: .
    ports:
      - "8420:8420"
    volumes:
      - ./vault:/vault        # Mount your vault directory
    environment:
      - CORTEX_VAULT_PATH=/vault
      - CORTEX_ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - CORTEX_COMPILER_MODEL=claude-sonnet-4-20250514
      - CORTEX_MCP_TRANSPORT=sse
    restart: unless-stopped
```

### Usage

```bash
# Build and run
docker compose up -d

# The vault is mounted from ./vault on your host
# Drop raw files into ./vault/raw/ and call vault:compile

# Connect Claude Desktop via SSE MCP:
# In claude_desktop_config.json, point to http://localhost:8420/mcp

# Or run locally without Docker for stdio MCP:
uv run python -m cortex.mcp.server
```

---

## Step 12 — Example Vault

Create these sample files for development and testing:

### `example_vault/raw/transformer-paper.txt`
```
Title: Attention Is All You Need — Summary Notes

The transformer architecture introduces a model based entirely on attention mechanisms,
dispensing with recurrence and convolutions. Key innovation is multi-head self-attention
which allows the model to jointly attend to information from different representation
subspaces at different positions.

The model achieves state-of-the-art results on WMT 2014 English-to-German and
English-to-French translation tasks. Training time is significantly reduced compared
to recurrent models.

Key components:
- Scaled dot-product attention: Attention(Q,K,V) = softmax(QK^T / sqrt(d_k))V
- Multi-head attention: multiple attention functions in parallel
- Positional encoding: sine/cosine functions to inject position information
- Feed-forward networks: two linear transformations with ReLU
- Residual connections and layer normalization

The paper argues that recurrence is NOT necessary for sequence modeling, contradicting
the prevailing view that sequential processing is fundamental to language understanding.
```

### `example_vault/raw/meeting-2026-04-11.txt`
```
Meeting: Cortex Architecture Review
Date: 2026-04-11
Attendees: Jieke, Team

Decisions:
- Cortex is a passive knowledge substrate, not an orchestrator
- Keystone handles orchestration, Cortex handles knowledge storage and retrieval
- MCP tool surface is the primary interface (6 tools)
- QMD for local search — no custom search infrastructure
- No database — filesystem only with JSON graph persistence
- LLM-powered compilation from raw sources to wiki articles

Action items:
- Build MCP server first (vault:read, vault:write, vault:search)
- Integrate QMD for hybrid search
- Build knowledge compiler pipeline (raw → wiki via Claude)
- Containerize with Docker
```

### `example_vault/wiki/transformers.md`
(This would be generated by the compiler from the raw paper notes, but provide a sample for testing)

```markdown
---
title: Transformer Architecture
tags: [ml, architecture, attention, nlp]
authored_by: claude-sonnet-4-20250514
created_at: 2026-04-11T10:00:00Z
source_path: raw/transformer-paper.txt
---

# Transformer Architecture

The transformer model replaces recurrence entirely with self-attention mechanisms.

## Key Components

- **Multi-head attention**: parallel attention functions across subspaces
- **Positional encoding**: sine/cosine position injection
- **Feed-forward layers**: two linear transforms with ReLU
- **Residual connections + layer norm**

## Core Claim

Recurrence is not necessary for sequence modeling. This contradicts [[rnn-claims]].

See also: [[attention-mechanisms]]
```

### `example_vault/agents/research-scout.agent.md`
```markdown
---
type: agent
name: research-scout
model: claude-sonnet-4
tools:
  - vault_search
  - vault_write
  - vault_link
memory_scope: /wiki/**
---

# Research Scout

Agent definition for automated research enrichment.
Reads from Cortex vault, never from external sources directly.
```

### `example_vault/.cortex/graph.json`
```json
{
  "nodes": [],
  "edges": []
}
```

### `example_vault/.cortex/log.md`
```markdown
# Cortex Operation Log

```

### `example_vault/.cortex/index.md`
```markdown
# Cortex Vault Index

_Auto-generated._
```

---

## Step 13 — Tests

### `tests/conftest.py`

Create fixtures:
1. `tmp_vault` — temp directory with sample .md files mirroring example_vault
2. `test_graph` — GraphEngine loaded from tmp_vault
3. `mock_qmd` — mock QMDSearch that returns canned results (avoid requiring QMD in CI)

### Test files

- `test_vault.py` — reader/writer: frontmatter parsing, wikilink extraction, provenance injection, node type inference
- `test_graph.py` — engine: add/remove nodes/edges, JSON persistence round-trip, orphan detection, get_edges filtering
- `test_compiler.py` — mock LLM responses, verify article creation in wiki/, verify source_path in frontmatter
- `test_mcp.py` — tool handlers: vault_read returns content, vault_write creates file, vault_link cycle

---

## Step 14 — Scripts

### `scripts/compile.py`
```python
"""Compile unprocessed raw sources into wiki articles."""
import asyncio
from cortex.config import settings
from cortex.compiler.compiler import KnowledgeCompiler

async def main():
    compiler = KnowledgeCompiler(settings.vault_path)
    raw_dir = settings.vault_path / "raw"
    # Find unprocessed sources (not referenced by any wiki article's source_path)
    # ... scan wiki/ frontmatter for source_path values
    # ... find raw/ files not in that set
    # ... compile each
    pass

if __name__ == "__main__":
    asyncio.run(main())
```

### `scripts/reindex.py`
```python
"""Rebuild graph and QMD index from scratch."""
import asyncio
from cortex.config import settings
from cortex.vault.reader import scan_vault
from cortex.graph.builder import build_graph
from cortex.search.qmd import QMDSearch
from cortex.vault.index import rebuild_index

async def main():
    vault_path = settings.vault_path
    notes = scan_vault(vault_path)
    print(f"Found {len(notes)} notes")

    graph = await build_graph(notes, vault_path / ".cortex" / "graph.json")
    stats = await graph.get_stats()
    print(f"Graph: {stats['total_nodes']} nodes, {stats['total_edges']} edges, {stats['orphans']} orphans")

    qmd = QMDSearch(vault_path, settings.qmd_bin)
    await qmd.initialize()
    print("QMD index updated")

    await rebuild_index(vault_path)
    print("Vault index rebuilt")

if __name__ == "__main__":
    asyncio.run(main())
```

### `scripts/lint.py`
Vault health checks — run via `uv run python scripts/lint.py`:
1. Orphan detection (notes with no inbound links)
2. Broken wikilinks (links to non-existent notes)
3. Unprocessed raw sources (raw/ files with no corresponding wiki/ article)
4. Missing provenance (notes without authored_by)
5. Stale notes (not updated in 30+ days, optional)
Output results to stdout and optionally to `.cortex/lint-report.md`.

---

## Coding Standards

- `async/await` everywhere — no blocking I/O
- Type hints on all function signatures
- Docstrings on all public functions
- `from __future__ import annotations` in all files
- `pathlib.Path` for all file operations
- **NO DATABASE.** All persistence via .md, .json, and .txt files
- Handle errors gracefully — return error messages in MCP responses, never crash
- Python `logging` module, not print (except in scripts)
- Small focused functions — one responsibility each

## Important Constraints

- **Filesystem is the ONLY persistence.** No SQLite, no Postgres, no Redis. Graph → JSON. Index → Markdown. Log → Markdown. Search → QMD (manages its own index internally).
- **raw/ is immutable.** The LLM reads raw sources but NEVER modifies them. They are the source of truth.
- **wiki/ is LLM-owned.** The compiler writes and maintains wiki articles. Humans can edit too, but the LLM does the heavy lifting.
- **Frontmatter merge, never overwrite.** vault:write preserves existing keys.
- **Provenance is automatic.** Every vault:write injects authored_by + updated_at.
- **QMD is the search engine.** Do not reimplement search. Shell out to `qmd` CLI.
- **Container-ready.** The vault is a mounted volume. The app runs in a container with both Python and Node.js.
- **All .md files must remain valid Markdown.** Any editor (Obsidian, VS Code) should render them.

---

## Build Order

Execute in this exact sequence:

1. Project scaffold + pyproject.toml + uv sync
2. Dockerfile + docker-compose.yml
3. config.py
4. vault/models.py
5. vault/reader.py + vault/writer.py
6. graph/engine.py (with JSON persistence)
7. graph/builder.py
8. search/qmd.py (QMD bridge)
9. compiler/prompts.py + compiler/compiler.py + compiler/extractor.py
10. vault/index.py + log/audit.py
11. mcp/server.py + mcp/tools.py (all 7 tools)
12. graph/context.py
13. api/routes.py + main.py
14. vault/watcher.py (integrate into main.py lifespan)
15. example_vault/ sample files
16. tests/
17. scripts/ (serve.py, compile.py, reindex.py, lint.py)

**After each step, run tests to verify before moving on.**
