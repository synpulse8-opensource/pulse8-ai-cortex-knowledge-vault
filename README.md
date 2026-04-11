# Cortex Knowledge Vault (a.k.a., Cortex 2.0)

Agent-native knowledge OS built on Markdown files.

Cortex is a knowledge substrate where AI agents, AI assistants, and humans collaborate through a unified MCP interface backed by a graph engine.

## Quick Start

### One-Click Launch (Docker)

```bash
./scripts/start.sh
```

This single command will:
1. Check for required configuration (prompts you if `LLM_API_KEY` is missing)
2. Save configuration to `.env`
3. Build and start both **QMD** (search) and **Cortex** (API + MCP) containers
4. Wait until both services are healthy

On first run you'll be prompted for your OpenRouter API key. Get one at [openrouter.ai/keys](https://openrouter.ai/keys).

### Manual Configuration

Copy the example env file and fill in your values:

```bash
cp .env.example .env
# Edit .env with your LLM_API_KEY
./scripts/start.sh
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | Yes | — | OpenRouter (or compatible) API key |
| `OPENROUTER_API_KEY` | Alt | — | Accepted as alias for `LLM_API_KEY` |
| `CORTEX_LLM_API_KEY` | Alt | — | Accepted as alias for `LLM_API_KEY` |
| `COMPILER_MODEL` | No | `anthropic/claude-sonnet-4` | LLM model for knowledge compilation |
| `LLM_BASE_URL` | No | `https://openrouter.ai/api/v1` | LLM API base URL |
| `VAULT_DIR` | No | `./example_vault` | Path to your vault directory |

The script checks `LLM_API_KEY`, `OPENROUTER_API_KEY`, and `CORTEX_LLM_API_KEY` in that order. If none are set, it prompts you interactively and saves to `.env`.

### Managing the Services

```bash
# Stop everything
./scripts/stop.sh

# View logs
docker compose logs -f

# Rebuild after code changes
docker compose up --build -d
```

## Development

```bash
# Install dependencies
uv sync --all-extras

# Run Python tests
uv run pytest tests/ -v

# Run shell tests (requires bats-core)
bats tests/test_start_sh.bats

# Run Cortex locally (without Docker)
CORTEX_MCP_TRANSPORT=http CORTEX_VAULT_PATH=./example_vault uv run python scripts/serve.py
```

## Claude Desktop Configuration

An example config file is included at [`claude_desktop_config.example.json`](claude_desktop_config.example.json).

Copy it to your Claude Desktop config location:

```bash
cp claude_desktop_config.example.json ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Then restart Claude Desktop. Cortex must be running (`./scripts/start.sh`) before Claude can connect.

### Option A: Persistent HTTP Server (recommended)

Start Cortex with `./scripts/start.sh`, then configure Claude Desktop to connect via Streamable HTTP:

```json
{
  "mcpServers": {
    "cortex": {
      "url": "http://localhost:8420/mcp/"
    }
  }
}
```

### Option B: Stdio (Claude Desktop launches the server)

```json
{
  "mcpServers": {
    "cortex": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/cortex", "python", "-m", "cortex.mcp"],
      "env": {
        "CORTEX_VAULT_PATH": "/path/to/your/vault"
      }
    }
  }
}
```

## Architecture

```
┌──────────────────────────────────────────────┐
│  Claude Desktop / AI Agent                   │
│  connects via MCP (HTTP or stdio)            │
└──────────┬───────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────┐
│  Cortex Container (:8420)                    │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ MCP     │ │ REST API │ │ Vault Watcher│  │
│  │ /mcp/   │ │ /api/v1/ │ │ (watchfiles) │  │
│  └────┬────┘ └────┬─────┘ └──────┬───────┘  │
│       │           │              │           │
│  ┌────▼───────────▼──────────────▼────────┐  │
│  │  Graph Engine (NetworkX)               │  │
│  │  Knowledge Compiler (LLM)             │  │
│  └────────────────────────────────────────┘  │
└──────────┬───────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────┐
│  QMD Container (:3100)                       │
│  Hybrid search: BM25 + vector + reranking    │
│  Auto-indexes vault on startup               │
└──────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────┐
│  Vault (mounted volume)                      │
│  wiki/ agents/ sessions/ daily/ raw/         │
│  .cortex/  (graph.json, index.md, log.md)    │
└──────────────────────────────────────────────┘
```

- **Vault**: Filesystem-based persistence (Markdown + YAML frontmatter)
- **Graph Engine**: NetworkX in-memory, JSON-persisted knowledge graph
- **Search (QMD)**: Separate container — BM25 keyword search (default), with optional hybrid mode on GPU
- **Compiler**: LLM-powered knowledge compilation (raw sources → wiki articles)
- **MCP Server**: Streamable HTTP + stdio transport for AI consumers
- **REST API**: FastAPI endpoints mirroring MCP tools
- **Watcher**: Real-time filesystem monitoring, auto-updates graph on vault changes

## MCP Tools

| Tool | Description |
|---|---|
| `vault_read` | Read a note by path |
| `vault_write` | Create or update a note |
| `vault_search` | Search the vault (keyword/semantic/hybrid) |
| `vault_link` | Create, query, or delete graph edges |
| `vault_ingest` | Ingest raw content and compile to wiki articles |

## Data Persistence

The vault directory is **bind-mounted** from your host filesystem into the containers. All data (notes, graph, index) lives on your local disk and survives container restarts or removal.

The QMD search index is stored in a named Docker volume (`qmd-cache`) and persists across `docker compose down`. To force a full re-index, remove the volume:

```bash
docker compose down -v
./scripts/start.sh
```

## Horizontal Scalability

The current architecture is designed for **single-instance deployment**. Both services use file-based state that does not support concurrent writes from multiple processes.

### Current Limitations

| Component | Storage | Constraint |
|---|---|---|
| Graph Engine | `graph.json` (file) | Single-writer — concurrent instances would overwrite each other |
| QMD Index | SQLite (`index.sqlite`) | Single-writer — multiple instances would corrupt the database |
| Vault Watcher | In-memory (`watchfiles`) | Each instance runs its own watcher, causing duplicate processing |
| MCP Sessions | In-memory | Sessions are not shared across instances |

### What Would Be Needed

To support horizontal scaling, the following changes would be required:

| Component | Current | Scaled Alternative |
|---|---|---|
| Graph Engine | JSON file + in-memory | Redis, Neo4j, or PostgreSQL |
| QMD Index | SQLite file | PostgreSQL + pgvector |
| Vault Watcher | Per-instance `watchfiles` | Single watcher + message queue (e.g. Redis pub/sub) |
| MCP Sessions | In-memory per process | Sticky sessions or shared session store |

### What You Can Do Today

- **Scale QMD reads**: Run multiple read-only QMD replicas behind a load balancer while a single primary handles indexing (`/setup`, `/update`)
- **Scale Cortex reads**: Place Cortex behind a reverse proxy for read-heavy workloads, accepting eventual consistency on the graph
- **Separate concerns**: QMD already runs as an independent container and can be deployed on a different host
