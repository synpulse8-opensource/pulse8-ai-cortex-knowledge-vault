<!-- mcp-name: io.github.synpulse8-opensource/pulse8-ai-cortex-knowledge-vault -->

<p align="center">
  <img src="assets/pulse8-banner.png" alt="PULSE8.ai" width="600" />
</p>

<h1 align="center">PULSE8.ai Cortex</h1>

<p align="center">
  <strong>The open-source knowledge layer for AI agents</strong>
  <br />
  <em>Knowledge that compounds.</em>
</p>

<p align="center">
  <a href="https://github.com/synpulse8-opensource/pulse8-ai-cortex-knowledge-vault/actions/workflows/pylint.yml"><img src="https://github.com/synpulse8-opensource/pulse8-ai-cortex-knowledge-vault/actions/workflows/pylint.yml/badge.svg" alt="Build"></a>
  <a href="https://github.com/synpulse8-opensource/pulse8-ai-cortex-knowledge-vault/releases/latest"><img src="https://img.shields.io/github/v/release/synpulse8-opensource/pulse8-ai-cortex-knowledge-vault" alt="Release"></a>
  <a href="LICENSE.md"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-blueviolet" alt="MCP">
  <img src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/NetworkX-graph%20engine-orange" alt="NetworkX">
</p>


PULSE8.ai Cortex is the **open-source knowledge layer for AI agents**: Git-native memory, a typed knowledge graph, and [MCP](https://modelcontextprotocol.io/)-powered retrieval on top of plain Markdown — so agents can build, evolve, and reuse persistent knowledge instead of re-deriving it on every query.

Under the hood it's a unified vault for AI agents and humans, backed by a typed knowledge graph, full-text + hybrid search, and a [MarkItDown](https://github.com/microsoft/markitdown)-powered file compiler. Drop files in (PDF, DOCX, PPTX, XLSX, HTML, images, and more), let agents read, write, search, link, and compile knowledge — no database required.

> Inspired by [Andrej Karpathy](https://github.com/karpathy)'s [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern — a persistent, compounding knowledge base maintained by LLMs instead of re-derived on every query. Search powered by [Tobi Lütke](https://github.com/tobi)'s [QMD](https://github.com/tobi/qmd).

---

## Why PULSE8.ai Cortex?

Most AI agents can access tools, but they cannot accumulate knowledge.

Traditional RAG systems retrieve documents. PULSE8.ai Cortex builds a **persistent, evolving knowledge layer** that grows over time and becomes more valuable the more agents and humans interact with it.

With PULSE8.ai Cortex, agents can:

- **Learn from interactions** — every read, write, ingest, and compile event is logged and graph-linked
- **Build and traverse knowledge graphs** — wikilinks, tags, and typed edges, maintained automatically
- **Store structured insights** — Markdown notes with typed nodes (`note`, `agent_def`, `session`, `daily`, `feedback`)
- **Retrieve context across projects** — `vault_context` builds a ranked subgraph from any seed query
- **Share knowledge through MCP** — one vault, every MCP-compatible client
- **Maintain long-term memory** — files survive sessions, deployments, and model upgrades
- **Version knowledge through Git** — the vault is a plain directory of Markdown, diff-friendly out of the box

| Aspect | Traditional RAG | PULSE8.ai Cortex |
| ------ | --------------- | ---------------- |
| Focus | Documents | Knowledge |
| Memory | Session-based | Persistent |
| Structure | Chunks | Markdown + typed graph |
| Evolution | Static index | Continuous, file-watched |
| Versioning | None | Git-native |
| Agent collaboration | Limited | First-class (MCP) |



## When to use PULSE8.ai Cortex

### Ideal use cases

- ✅ Persistent memory for AI agents
- ✅ Shared knowledge across multiple agents
- ✅ Git-versioned organisational knowledge
- ✅ MCP-compatible knowledge retrieval
- ✅ Knowledge graphs without a dedicated graph database
- ✅ Long-term accumulation of institutional knowledge
- ✅ Human + AI collaborative knowledge management

### Not ideal for

- ❌ Simple full-text document search (use a search engine)
- ❌ Pure vector-only retrieval with no graph (use a vector DB)
- ❌ Short-lived, stateless conversations
- ❌ Workflows that don't need persistent knowledge evolution



## PULSE8.ai Cortex vs alternatives


| Capability                     | PULSE8.ai Cortex | Traditional RAG | GraphRAG |
| ------------------------------ | :--------------: | :-------------: | :------: |
| Persistent knowledge           |        ✅        |       ❌        |    ⚠️    |
| Markdown-native storage        |        ✅        |       ❌        |    ❌    |
| MCP-compatible out of the box  |        ✅        |       ❌        |    ❌    |
| Knowledge graph                |        ✅        |       ❌        |    ✅    |
| Git versioning                 |        ✅        |       ❌        |    ❌    |
| Agent memory layer             |        ✅        |       ❌        |    ⚠️    |
| Human + AI collaboration       |        ✅        |       ❌        |    ⚠️    |
| Continuous knowledge evolution |        ✅        |       ❌        |    ⚠️    |
| Zero database required         |        ✅        |       ❌        |    ❌    |



## Works with

PULSE8.ai Cortex speaks [MCP](https://modelcontextprotocol.io/) — so it plugs into any AI client that does. The same vault is reachable over streamable HTTP or stdio, and mirrored 1:1 by a REST API at `/api/v1/`.


| Category              | Compatible with                                                                |
| --------------------- | ------------------------------------------------------------------------------ |
| **AI agents**         | Claude Desktop, Claude Code, OpenAI Agents, Gemini, custom agent frameworks    |
| **Development tools** | Cursor, VS Code, JetBrains IDEs                                                |
| **Agent frameworks**  | LangGraph, LangChain, CrewAI, AutoGen                                          |
| **MCP ecosystem**     | MCP clients, MCP servers, MCP tool registries                                  |
| **Human tools**       | Obsidian, any Markdown editor, any Git client                                  |


Because the vault is just files, humans and agents collaborate on the same knowledge — no proprietary format, no lock-in.



## Get started

> [!NOTE]
> PULSE8.ai Cortex requires Docker. An [OpenRouter API key](https://openrouter.ai/keys) is optional — needed only for LLM-powered cross-referencing between wiki articles. File conversion works out of the box without any API key.

1. Clone the repository:
  ```bash
    git clone https://github.com/synpulse8-opensource/pulse8-ai-cortex-knowledge-vault.git
    cd cortex-knowledge-vault
  ```
2. Launch PULSE8.ai Cortex:
  ```bash
    ./scripts/start.sh
  ```
    This builds and starts both **PULSE8.ai Cortex** (API + MCP on `:8420`) and **QMD** (search on `:3100`), waits for health checks, and you're ready to go.
3. Connect your MCP client (e.g. Claude Desktop) to `http://localhost:8420/mcp/`.

To stop: `./scripts/stop.sh`

### Cortex-only mode (macOS / native QMD)

If you want QMD to run natively (e.g. on macOS with Metal GPU acceleration), start only the Cortex container:

```bash
# Terminal 1: Run QMD natively
npm install -g @tobilu/qmd
VAULT_PATH=./example_vault node docker/qmd/server.mjs

# Terminal 2: Start only Cortex in Docker
./scripts/start.sh --cortex-only
```

To stop: `./scripts/stop.sh --cortex-only`

### GPU-accelerated QMD (EC2 / Linux with NVIDIA GPU)

For production deployments with NVIDIA GPU acceleration:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

See [docs/ec2-gpu-setup.md](docs/ec2-gpu-setup.md) for a full guide on instance selection, NVIDIA toolkit installation, and cost estimates.



## Features


|                              |                                                                                                                                                                              |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Knowledge Graph**          | Typed graph engine (NetworkX) — wikilinks, tags, and custom edges, auto-maintained on every file change                                                                      |
| **Full-Text Search**         | QMD search with hybrid (BM25 + vector + re-ranking) by default; keyword and semantic modes selectable. Results cached with a configurable TTL.                               |
| **File Compiler**            | Converts raw sources (PDF, DOCX, PPTX, XLSX, HTML, images, etc.) to Markdown via [MarkItDown](https://github.com/microsoft/markitdown). LLM used only for cross-referencing. |
| **MCP Server**               | Streamable HTTP + stdio transport — works with Claude Desktop, Cursor, and any MCP client                                                                                    |
| **Feedback & Notifications** | `vault_feedback` captures quality feedback as notes; optional Microsoft Teams webhook posts an adaptive card per submission                                                  |
| **Daily Activity Log**       | Every write/ingest/compile is mirrored into `daily/<date>.md` as a greppable, wikilinked timeline                                                                            |
| **Bulk Ingest**              | Ingest dozens or hundreds of files at once from a local directory with SHA-256 dedup and bounded concurrency                                                                 |
| **REST API**                 | FastAPI endpoints mirroring all MCP tools at `/api/v1/`, including multipart file upload and bulk ingest                                                                     |
| **Vault Watcher**            | Real-time filesystem monitoring — graph stays in sync automatically                                                                                                          |
| **Zero Database**            | Everything persists as Markdown + JSON on your filesystem                                                                                                                    |

## Runs without an LLM

Cortex is deterministic-first: ingestion (MarkItDown conversion), the knowledge graph (wikilinks, tags, `derived_from` edges), and QMD search all work with **zero LLM calls**. The LLM is an optional enrichment pass — cross-referencing, tagging, image captioning — not a dependency.

Pick a backend with `LLM_BACKEND` (env) / `CORTEX_LLM_BACKEND` (Python):

| Backend | What it covers |
|---------|----------------|
| `openai-compatible` (default) | OpenRouter, Azure OpenAI, Ollama, vLLM, LM Studio — anything speaking the OpenAI protocol. Point `LLM_BASE_URL` at your endpoint. |
| `bedrock` | AWS Bedrock via the standard AWS credential chain (no API key). Requires `boto3`. |
| `none` | Explicit zero-LLM mode. Guaranteed to construct no LLM client and make no model calls — suitable for air-gapped deployments. |

Air-gapped example with a local Ollama:

```bash
LLM_BACKEND=openai-compatible \
LLM_BASE_URL=http://localhost:11434/v1 \
LLM_API_KEY=ollama \
COMPILER_MODEL=llama3.1 \
./scripts/start.sh
```

Or fully deterministic: `LLM_BACKEND=none ./scripts/start.sh` (no API key needed).

## MCP resources (token-light large payloads)

PULSE8.ai Cortex implements the [resources-as-tool-inputs pattern](https://microsoft.github.io/mcscatblog/posts/mcp-resources-as-tool-inputs/) recommended by the Microsoft Copilot Studio CAT team: token-heavy tool outputs (large search result sets, full context windows) can be kept server-side and passed between tools as lightweight handles, so the LLM context window stays small.

**How it works.** Pass `as_resource: true` to `vault_search` or `vault_context` (or `?as_resource=true` on `GET /api/v1/search`). Instead of inlining the full payload, you get a handle:

```json
{
  "resource_id": "7f8a3c...",
  "resource_uri": "cortex://resource/7f8a3c...",
  "summary": { "query": "...", "count": 8, "paths": ["..."] }
}
```

Read it back through any of the three transports:

- **MCP resources protocol** — `resources/read` with the `cortex://resource/{id}` URI (Claude Desktop, Cursor, Copilot Studio MCP).
- **Fallback tool** — `vault_resource_read` for clients that only expose tools to the planning layer (some Copilot Studio configurations).
- **REST** — `GET /api/v1/resources/{resource_id}` (accepts the bare ID or the full URI).

The store is in-memory, asyncio-safe, TTL-evicted, and LRU-bounded:

| Env var | Default | Purpose |
|---------|---------|---------|
| `CORTEX_RESOURCE_TTL_SECONDS` | `3600` | Max age before a stored resource is evicted lazily on read |
| `CORTEX_RESOURCE_MAX_ITEMS` | `1000` | LRU cap before oldest entry is dropped |

The same `ResourceStore` is shared between MCP and REST — produce a handle via MCP, read it back via REST (or vice versa).

Microsoft Copilot Studio setup — agent instructions, tool selection, and the Custom Connector fallback — is documented in [docs/copilot-studio.md](docs/copilot-studio.md). No Cortex code change required.



## MCP tools


| Tool                   | Description                                                                                |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| `vault_read`           | Read a note by path                                                                        |
| `vault_write`          | Create or update a note                                                                    |
| `vault_search`         | Search the vault (keyword / semantic / hybrid). Supports `as_resource=true`                |
| `vault_link`           | Create, query, or delete graph edges                                                       |
| `vault_context`        | Build a context window: search → graph traversal → ranked subgraph. Supports `as_resource=true` |
| `vault_ingest`         | Ingest raw content or binary files (supports `content_base64` for binary)                  |
| `vault_compile`        | Compile unprocessed raw sources into wiki Markdown via MarkItDown                          |
| `vault_feedback`       | Submit feedback on vault quality (`status: OPEN`; optional `related_paths` of `.md` notes) |
| `vault_list_feedbacks` | List feedback note metadata (paths, tags, status; not full body)                           |
| `vault_resource_read`  | Read a server-stored MCP resource by ID (fallback for clients without `resources/read`)    |




## Architecture

```
┌──────────────────────────────────────────────┐
│  MCP Client (Claude Desktop, Cursor, etc.)   │
└──────────┬───────────────────────────────────┘
           │  MCP (HTTP or stdio)
┌──────────▼───────────────────────────────────┐
│  PULSE8.ai Cortex  :8420                     │
│  ┌──────────────────────────────────────┐     │
│  │ Auth (API Key or Microsoft Entra ID) │     │
│  └──────────────┬───────────────────────┘     │
│  ┌─────────┐ ┌──┴───────┐ ┌──────────────┐   │
│  │ MCP     │ │ REST API │ │ Vault Watcher│   │
│  │ /mcp/   │ │ /api/v1/ │ │ (watchfiles) │   │
│  └────┬────┘ └────┬─────┘ └──────┬───────┘   │
│       └───────────┼──────────────┘           │
│            ┌──────▼──────┐                   │
│            │ Graph Engine│                   │
│            │ + Compiler  │                   │
│            └─────────────┘                   │
└──────────┬───────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────┐
│  QMD  :3100                                  │
│  BM25 + vector search, auto-indexes on start │
└──────────┬───────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────┐
│  Vault (bind-mounted volume)                 │
│  wiki/ raw/ agents/ sessions/ daily/ feedback/ │
│  .cortex/ (graph.json, index.md, log.md)     │
└──────────────────────────────────────────────┘
```



## Vault layout

The vault is a plain directory of Markdown files organised by purpose. Cortex classifies each file into a typed node (`NodeType`) used by the graph engine and exposed in REST and MCP responses.


| Folder      | `NodeType`   | Purpose                                                          |
| ----------- | ------------ | ---------------------------------------------------------------- |
| `wiki/`     | `note`       | Compiled, interlinked knowledge articles                         |
| `raw/`      | `raw_source` | Unprocessed sources (PDF, DOCX, TXT, …) the compiler reads from  |
| `agents/`   | `agent_def`  | Agent definitions                                                |
| `sessions/` | `session`    | Per-session notes / conversation transcripts                     |
| `daily/`    | `daily`      | Daily notes (Obsidian Daily Notes convention)                    |
| `feedback/` | `feedback`   | Feedback on vault quality (`status`, `related_paths`)            |
| `.cortex/`  | *(skipped)*  | Cortex internals — `graph.json`, `index.md`, `log.md`, manifests |


### How classification works

Order of precedence (first match wins):

1. **Frontmatter `type:*`* — explicit override always wins (e.g. `type: note` in `agents/foo.md` resolves to `NodeType.NOTE`)
2. **Folder prefix** — files under `raw/ agents/ sessions/ daily/ feedback/` inherit the folder's type with no filename suffix needed (e.g. `daily/2026-06-10.md` → `daily`)
3. **Filename suffix** (backward-compatible) — `.agent.md`, `.session.md`, `.memory.md` are still honored anywhere (e.g. `wiki/legacy.agent.md` → `agent_def`)
4. **Default** — `NodeType.NOTE`

In practice this means you can drop `YYYY-MM-DD.md` straight into `daily/`, or an unsuffixed `planner.md` into `agents/`, and the graph and API will classify them correctly without any renaming.

### Daily activity log

Every `vault_write`, `vault_ingest`, and successful `compile` event (MCP **and** REST paths) is automatically mirrored into today's UTC daily note at `daily/YYYY-MM-DD.md`. The file is created on first event of the day and each subsequent event appends a `## [HH:MM] event | summary` block plus a `[[wiki-stem]]` wikilink (so the watcher draws a `LINKS_TO` edge to the affected note). The format follows the Karpathy log.md greppable-prefix pattern — `grep "^## \[" daily/2026-06-10.md` gives a clean timeline of the day.

Writes targeting `daily/`, `feedback/`, or `.cortex/` are deliberately **not** mirrored (would be self-referential noise). The hidden `.cortex/log.md` audit log is unaffected and continues to receive every operation.



## Bulk ingest

For ingesting many files at once (dozens or hundreds of PDFs, papers, docs), use the one-click shell script instead of feeding them one at a time through MCP. It reads directly from a local directory (recursively, including subfolders) — no wire overhead, no running server required — deduplicates via SHA-256 hashing, compiles with bounded concurrency, and rebuilds the index once at the end. Subpaths are preserved under the vault raw folder (e.g. `source/abcde/doc.html` → `raw/abcde/doc.html`).

### One-click script (recommended)

```bash
# Ingest all files from a directory
./scripts/bulk_ingest.sh ./my-papers/

# Dry-run to preview what would be ingested
./scripts/bulk_ingest.sh ./my-papers/ --dry-run

# Force re-ingest (bypass dedup manifest)
./scripts/bulk_ingest.sh ./my-papers/ --force

# Control LLM concurrency (default: 4)
./scripts/bulk_ingest.sh ./my-papers/ --concurrency 8
```

The script automatically loads your `.env` for the LLM key and vault path, prints a summary, then runs the full pipeline (copy, compile, reindex). No running Cortex server needed.

### Python CLI (direct)

```bash
CORTEX_VAULT_PATH=./example_vault uv run cortex-bulk-ingest --source ./my-papers/
```

### Inside Docker

```bash
# Set INGEST_DIR in .env or export it, then restart
export INGEST_DIR=/path/to/your/papers
docker compose up -d

# Run bulk ingest inside the container
docker exec pulse8-ai-cortex uv run cortex-bulk-ingest --source /ingest
```

### Via REST API

For programmatic use without MCP (requires running Cortex server):

```bash
curl -X POST http://localhost:8420/api/v1/bulk-ingest \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-secret-api-key" \
  -d '{"source_dir": "/ingest", "concurrency": 4}'
```

### Deduplication

The dedup manifest is stored at `.cortex/ingest-manifest.json`. Files are matched by content hash, not filename — renaming a file won't cause re-ingestion, and the same content under a different name will be skipped.



## Configuration

Copy the example and fill in your values:

```bash
cp .env.example .env
```


| Variable                       | Required | Default                        | Description                                                                                        |
| ------------------------------ | -------- | ------------------------------ | -------------------------------------------------------------------------------------------------- |
| `LLM_API_KEY`                  | No       | —                              | OpenRouter (or compatible) API key (for cross-referencing only)                                    |
| `COMPILER_MODEL`               | No       | `anthropic/claude-sonnet-4`    | Model for cross-reference detection                                                                |
| `LLM_BASE_URL`                 | No       | `https://openrouter.ai/api/v1` | LLM API base URL                                                                                   |
| `VAULT_DIR`                    | No       | `./example_vault`              | Path to your vault directory                                                                       |
| `INGEST_DIR`                   | No       | `./ingest`                     | Path to bulk-ingest source directory (mounted as `/ingest` in Docker)                              |
| `QMD_REFRESH_INTERVAL_SECONDS` | No       | `900`                          | Periodic re-index interval (seconds; `0` to disable)                                               |
| `QMD_SEARCH_MODE`              | No       | `hybrid`                       | Default search mode when unspecified: `hybrid` (BM25 + vector + re-rank), `semantic`, or `keyword` |
| `QMD_CACHE_TTL_SECONDS`        | No       | `30`                           | TTL for the search-result cache; raise it on read-heavy vaults to skip repeat QMD calls            |
| `QMD_SEARCH_TIMEOUT_SECONDS`   | No       | `120`                          | Per-request search timeout (increase for hybrid on CPU-only hosts)                                 |
| `QMD_EMBED_TIMEOUT_MS`         | No       | `600000`                       | Embed timeout in ms (increase for CPU-only deployments)                                            |
| `QMD_URL`                      | No       | —                              | External QMD URL for cortex-only mode (e.g. `http://host.docker.internal:3100`)                    |
| `AUTH_METHOD`                  | No       | `none`                         | Authentication method: `none`, `apikey`, or `oidc` (see [Authentication](#authentication))         |
| `API_KEY`                      | No       | —                              | Static API key for `x-api-key` header (used when `AUTH_METHOD=apikey`)                             |
| `OIDC_TENANT_ID`               | No       | —                              | Microsoft Entra ID tenant ID (used when `AUTH_METHOD=oidc`)                                        |
| `OIDC_CLIENT_ID`               | No       | —                              | Microsoft Entra ID app (client) ID                                                                 |
| `OIDC_CLIENT_SECRET`           | No       | —                              | Microsoft Entra ID client secret                                                                   |
| `OIDC_BASE_URL`                | No       | `http://localhost:8420`        | Public base URL of the Cortex server (used for OAuth callbacks)                                    |
| `TEAMS_WEBHOOK_URL`            | No       | —                              | Incoming webhook / Power Automate URL; posts an adaptive card on each new feedback note            |
| `TEAMS_APP_BASE_URL`           | No       | —                              | Optional public Cortex base URL for a "View in Cortex" link on the Teams card                      |


`OPENROUTER_API_KEY` and `CORTEX_LLM_API_KEY` are accepted as aliases for `LLM_API_KEY`. Variables above are set in `.env` (Docker reads them via Compose) and map to the `CORTEX_*` settings used by the app.



## Authentication

Cortex supports two authentication methods that protect both the REST API (`/api/v1/`) and the MCP endpoint (`/mcp/`). Set `AUTH_METHOD` in `.env` to choose:


| `AUTH_METHOD` | Description                                                   |
| ------------- | ------------------------------------------------------------- |
| `none`        | Default. All endpoints are open — no authentication required. |
| `apikey`      | Static API key. Clients pass `x-api-key` header.              |
| `oidc`        | Microsoft Entra ID (Azure AD) with OAuth 2.0 + MFA support.   |


### API Key (`AUTH_METHOD=apikey`)

The simplest option. Set the method and key in `.env`:

```
AUTH_METHOD=apikey
API_KEY=your-secret-api-key
```

Clients pass it via the `x-api-key` header:

```bash
# REST API
curl http://localhost:8420/api/v1/health \
  -H "x-api-key: your-secret-api-key"

# MCP (via curl)
curl -X POST http://localhost:8420/mcp/ \
  -H "x-api-key: your-secret-api-key" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}'
```

No OAuth discovery endpoints are served — no login popups. Requests without a valid key receive a `401`.

### Microsoft Entra ID (`AUTH_METHOD=oidc`)

For enterprise environments that require interactive login with MFA support:

```
AUTH_METHOD=oidc
OIDC_TENANT_ID=your-tenant-id
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
OIDC_BASE_URL=http://localhost:8420
```

This enables:

- **REST API**: OAuth 2.0 Authorization Code Flow via `GET /api/v1/login`. After login, pass the access token as `Authorization: Bearer <token>`. A valid `x-api-key` header is also accepted as a fallback when `API_KEY` is set.
- **MCP endpoint**: FastMCP's built-in OIDCProxy handles interactive browser-based login.

### Azure AD app registration

To use OIDC, register an app in the [Azure Portal](https://portal.azure.com):

1. Go to **Azure Active Directory → App registrations → New registration**
2. Set the redirect URI to `http://localhost:8420/api/v1/auth/callback` (Web platform)
3. Under **Certificates & secrets**, create a client secret
4. Under **API permissions**, add `openid`, `profile`, and `email` (Microsoft Graph → Delegated)
5. Copy the Tenant ID, Client ID, and Client Secret into `.env`



## MCP client setup

### Claude Desktop

An example config is included at `[claude_desktop_config.example.json](claude_desktop_config.example.json)`.

**HTTP with API key (recommended)** — PULSE8.ai Cortex runs as a persistent server:

```json
{
  "mcpServers": {
    "cortex": {
      "url": "http://localhost:8420/mcp/",
      "headers": {
        "x-api-key": "your-secret-api-key"
      }
    }
  }
}
```

**HTTP without auth** — when no authentication is configured:

```json
{
  "mcpServers": {
    "cortex": {
      "url": "http://localhost:8420/mcp/"
    }
  }
}
```

**Stdio** — Claude Desktop launches the server on demand (no auth needed):

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

### Cursor

Add to your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "cortex": {
      "url": "http://localhost:8420/mcp/",
      "headers": {
        "x-api-key": "your-secret-api-key"
      }
    }
  }
}
```



## How it works

**Watcher** and **Compiler** are independent components:

- The **Watcher** maintains the graph. Any `.md` file added, modified, or deleted triggers automatic node/edge updates.
- The **Compiler** converts raw source files to Markdown using [MarkItDown](https://github.com/microsoft/markitdown) and writes them to `wiki/`. Supported formats include PDF, DOCX, PPTX, XLSX, HTML, CSV, JSON, XML, images (EXIF/OCR), and plain text. The LLM is only used for optional cross-reference detection between articles.

They connect indirectly: the compiler writes to `wiki/`, the watcher picks those up and updates the graph.

### Supported file formats


| Format               | Extensions                             |
| -------------------- | -------------------------------------- |
| PDF                  | `.pdf`                                 |
| Microsoft Word       | `.docx`                                |
| Microsoft PowerPoint | `.pptx`                                |
| Microsoft Excel      | `.xlsx`, `.xls`                        |
| HTML                 | `.html`, `.htm`                        |
| Text-based           | `.csv`, `.json`, `.xml`, `.txt`, `.md` |
| Images               | `.jpg`, `.png`, etc. (EXIF metadata)   |


**Search** uses a two-stage pipeline:

1. **QMD** performs keyword/semantic search on file contents
2. **PULSE8.ai Cortex** enriches results with graph edges (wikilinks, tags, relationships between matched notes)

QMD answers *"what's relevant?"* — the graph answers *"how are these results connected?"*



## Real-world use cases

### Software engineering knowledge base

- Architecture Decision Records (ADRs)
- Coding standards and conventions
- Engineering handbooks and runbooks
- Platform and service documentation
- Domain-driven design models

### Banking & financial services

- Product documentation
- Regulatory and compliance knowledge
- Business domain models
- Wealth management expertise
- Institutional process know-how

### Enterprise knowledge management

- Internal wikis
- Project documentation and post-mortems
- Lessons learned and retrospectives
- Organisational memory
- Best practices and playbooks

### AI agent memory layer

- Shared memory across agents
- Long-term reasoning context
- Knowledge accumulation across sessions
- Multi-agent collaboration on a single vault



## Roadmap

### Near-term

- Enhanced knowledge-graph visualisation
- Agent activity timeline
- Knowledge quality scoring
- Additional MCP integrations

### Mid-term

- Multi-vault federation
- Enterprise governance and access policies
- Knowledge lineage tracking
- Cross-agent learning signals

### Long-term

- Self-improving organisational memory
- Autonomous knowledge curation
- Knowledge-driven agent ecosystems



## Development

```bash
# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v

# Run shell tests (requires bats-core)
bats tests/test_start_sh.bats

# Start PULSE8.ai Cortex locally (without Docker)
CORTEX_MCP_TRANSPORT=http CORTEX_VAULT_PATH=./example_vault uv run python scripts/serve.py
```

### Utility scripts


| Script                   | Description                                                |
| ------------------------ | ---------------------------------------------------------- |
| `scripts/serve.py`       | Dev server (HTTP or stdio based on `CORTEX_MCP_TRANSPORT`) |
| `scripts/compile.py`     | Batch-compile all raw sources                              |
| `scripts/reindex.py`     | Full reindex + graph rebuild                               |
| `scripts/bulk_ingest.sh` | One-click bulk ingest from a local directory               |
| `scripts/bulk_ingest.py` | Python CLI for bulk ingest (called by `bulk_ingest.sh`)    |
| `scripts/lint.py`        | Lint vault structure                                       |




## Data persistence

The vault directory is bind-mounted from your host into the containers. All data lives on your local disk and survives container restarts.

The QMD search index is stored in a Docker volume (`qmd-cache`). To force a full re-index:

```bash
docker compose down -v
./scripts/start.sh
```



## Releasing

Releases are automated through GitHub Actions. Publishing a GitHub Release triggers three workflows that build and publish everything:

| Workflow | Publishes to |
| -------- | ------------ |
| `publish-pypi.yml` | [PyPI](https://pypi.org/project/pulse8-ai-cortex-knowledge-vault/) |
| `publish-docker.yml` | GitHub Container Registry (`ghcr.io`) |
| `publish-mcp.yml` | [MCP Registry](https://registry.modelcontextprotocol.io) (GitHub OIDC auth) |

To cut a release:

1. **Bump the version** in `pyproject.toml` and `server.json` (keep them in sync), update `CHANGELOG.md`, and commit to `main`.

   ```bash
   # optional: validate the registry manifest locally before tagging
   mcp-publisher validate
   ```

2. **Create the GitHub Release** — via the UI (Releases → "Draft a new release" → new tag `vX.Y.Z`) or the CLI:

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z" --notes-file docs/releases/vX.Y.Z.md
   ```

3. **That's it** — the release event fires all three workflows. `publish-mcp.yml` waits for PyPI to serve the new version (so the `mcp-name` ownership marker in this README is verifiable), then publishes the server via GitHub OIDC under `io.github.synpulse8-opensource/*` (no token or local `mcp-publisher` needed).

4. **Verify** the registry entry once the workflow finishes:

   ```bash
   curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=pulse8-ai-cortex-knowledge-vault"
   ```

> [!IMPORTANT]
> PyPI versions are immutable — a version number can never be reused, even after deletion. Always increment to a new version; never re-release an existing one.



## Community

We believe AI agents need a dedicated knowledge layer — not another document store. If you share that vision:

- Star the [repository](https://github.com/synpulse8-opensource/pulse8-ai-cortex-knowledge-vault)
- Open a [discussion](https://github.com/synpulse8-opensource/pulse8-ai-cortex-knowledge-vault/discussions) or [issue](https://github.com/synpulse8-opensource/pulse8-ai-cortex-knowledge-vault/issues)
- Submit a pull request (see [Contributing](#contributing))
- Share your use cases — banking, engineering, research, or anything else

Together we can build the knowledge layer for agentic AI.



## Contributing

We welcome contributions! Please open an issue to discuss your idea before submitting a pull request.

```bash
# Fork and clone the repo
git clone https://github.com/<your-username>/cortex-knowledge-vault.git
cd cortex-knowledge-vault

# Create a branch
git checkout -b feat/my-feature

# Install dev dependencies
uv sync --all-extras

# Make changes, then run tests
uv run pytest tests/ -v

# Submit a pull request
```



## Reporting issues

Use [GitHub Issues](https://github.com/pulse8-ai/cortex-knowledge-vault/issues) to report bugs or request features.



## Acknowledgements

PULSE8.ai Cortex builds on ideas and tools from the open-source community:

- **[LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)** by [Andrej Karpathy](https://github.com/karpathy) — the core pattern of an LLM-maintained, persistent knowledge base that compiles and interlinks knowledge incrementally rather than re-discovering it from raw documents on every query. This gist is the direct inspiration for Cortex's architecture.
- **[QMD](https://github.com/tobi/qmd)** by [Tobi Lütke](https://github.com/tobi) — the on-device search engine powering all full-text and hybrid search in Cortex. QMD combines BM25, vector search, and LLM re-ranking, all running locally.
- **[MarkItDown](https://github.com/microsoft/markitdown)** by [Microsoft](https://github.com/microsoft) — the file-to-Markdown converter powering the Cortex compiler. Converts PDF, Office documents, HTML, images, and more into structured Markdown for ingestion into the vault.



## License

This project is licensed under the [PULSE8.ai Cortex Open Source License](LICENSE.md) (Apache License 2.0 with additional terms).