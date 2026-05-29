---
name: cortex
description: >-
  PULSE8.ai Cortex knowledge vault — architecture, MCP, QMD, graph, compiler, deploy.
  Use when working in this repo on vault, ingest, search, auth, feedback, or Docker.
---

# PULSE8.ai Cortex (master)

Read [AGENTS.md](../../../AGENTS.md) for repo map and commands. This skill routes you to the right sub-skill.

## Architecture

```
MCP client (Cursor, Claude Desktop, …)
        │  MCP HTTP or stdio
        ▼
Cortex :8420  ── REST /api/v1/  +  MCP /mcp/
  │ AuthMiddleware (REST) / ApiKeyGuard or OIDC (MCP)
  │ GraphEngine + Compiler + VaultWatcher
  ▼
QMD :3100  (BM25 / hybrid search)
        ▼
Vault (bind-mounted)
  wiki/ raw/ agents/ sessions/ daily/ feedback/
  .cortex/  (graph.json, index.md, manifests, log.md)
```

## Vault layout (high level)

| Folder | Role |
|--------|------|
| `wiki/` | Compiled knowledge articles |
| `raw/` | Unprocessed sources (PDF, txt, …) |
| `agents/` | Agent definitions |
| `sessions/` | Session notes |
| `daily/` | Daily notes |
| `feedback/` | User/agent feedback on vault quality |
| `.cortex/` | Graph JSON, index, ingest manifests, audit log |

## Intent router

Load **one** sub-skill before editing code in that area:

| You want to… | Sub-skill |
|--------------|-----------|
| Run Docker, EC2, logs, `.env` | `cortex-deploy` |
| Note layout, frontmatter, paths | `cortex-vault` |
| MCP tools, Cursor MCP setup | `cortex-mcp` |
| REST API, curl | `cortex-api` |
| Ingest, compile, bulk pipeline | `cortex-compiler` |
| Graph, search, context window | `cortex-graph-search` |
| API key, Entra OIDC | `cortex-auth` |
| Feedback, Teams webhook | `cortex-feedback` |
| Change Python, tests, new tools | `cortex-contributing` |

## Audience

- **Operators:** `cortex-deploy`, `cortex-vault`, `cortex-mcp`, `cortex-compiler` (run/ingest/debug).
- **Contributors:** `cortex-contributing` plus the domain skill you are changing.

## Rules

- Do not implement across modules without reading the relevant sub-skill.
- MCP handlers live in `cortex/mcp/tools.py`; REST in `cortex/api/routes.py` — keep parity when adding features.
- Configuration: `cortex/config.py` (`CORTEX_*` env prefix).
