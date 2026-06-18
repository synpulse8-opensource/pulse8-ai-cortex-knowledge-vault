---
name: cortex-mcp
description: >-
  Cortex MCP server — vault_read, vault_write, vault_search, vault_feedback, and
  other tools. Use for MCP clients, Claude Desktop, Cursor MCP, streamable HTTP.
---

# Cortex MCP

## Transports

| Mode | How | Config |
|------|-----|--------|
| HTTP | `http://localhost:8420/mcp/` | `CORTEX_MCP_TRANSPORT=http`, Docker or `scripts/serve.py` |
| stdio | Claude Desktop subprocess | `CORTEX_MCP_TRANSPORT=stdio` |

HTTP uses FastMCP streamable HTTP (`stateless_http=True`, JSON responses).

## Authentication

| `AUTH_METHOD` | MCP behavior |
|---------------|--------------|
| `none` | Open |
| `apikey` | `x-api-key` header must match `API_KEY` / `CORTEX_API_KEY` |
| `oidc` | FastMCP OIDCProxy (browser login); API key fallback if configured |

REST uses `AuthMiddleware`; MCP uses `ApiKeyGuardMiddleware` when apikey. See `cortex-auth`.

## HTTP session flow

1. `POST /mcp/` — `initialize` (JSON-RPC 2.0)
2. Save `mcp-session-id` response header if present
3. `notifications/initialized`
4. `tools/call` with `name` and `arguments`

Header: `Accept: application/json, text/event-stream`

## Implementation map

| Layer | File |
|-------|------|
| Tool handlers (shared with REST logic) | `cortex/mcp/tools.py` |
| HTTP tool registration | `cortex/mcp/http_server.py` |
| stdio server | `cortex/mcp/server.py` |
| Mount on FastAPI app | `mount_mcp_on_app()` in `http_server.py` |

Handlers receive injected services: `vault_path`, `graph`, `qmd`, `qmd_debounce`, `compiler`.

## Cursor integration

This project may register a local MCP server (e.g. `user-cortex_local`) pointing at `http://localhost:8420/mcp/` with `x-api-key` when auth is enabled.

Use MCP tools for agent workflows; prefer `vault_context` for RAG-style retrieval.

## Tool list

See [reference.md](reference.md) for all 10 tools (including
`vault_resource_read`), parameters, and return shapes.

## MCP resources (`cortex://resource/{id}`)

Token-heavy tool outputs can be opted into the server-side resource
store via `as_resource: true` on `vault_search` / `vault_context`
(and `GET /api/v1/search?as_resource=true` on REST). The store is
in-memory, TTL-bounded, and LRU-capped; tune with
`CORTEX_RESOURCE_TTL_SECONDS` and `CORTEX_RESOURCE_MAX_ITEMS`. See
[reference.md](reference.md) for details.

## Adding a tool

Follow checklist in `cortex-contributing`: handler → `http_server.py` + `server.py` → tests → update reference + README.

## Related skills

- REST mirror: `cortex-api`
- Deploy/local URL: `cortex-deploy`
