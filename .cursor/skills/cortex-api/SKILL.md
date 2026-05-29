---
name: cortex-api
description: >-
  Cortex REST API at /api/v1 — notes, search, graph, ingest, compile, bulk-ingest,
  feedbacks. Use for curl, HTTP clients, or FastAPI route changes.
---

# Cortex REST API

Router: `cortex/api/routes.py`, mounted at `/api/v1` in `cortex/main.py`.

OpenAPI: `http://localhost:8420/docs`

## Authentication

When `AUTH_METHOD` is not `none`, protected routes require:

- `x-api-key: <API_KEY>` when `apikey`, or
- `Authorization: Bearer <token>` when `oidc` (API key also accepted as fallback)

Unprotected prefixes (`cortex/auth/middleware.py`):

- `/api/v1/health`, `/api/v1/login`, `/api/v1/auth/callback`
- `/mcp`, `/.well-known/`, `/docs`, `/redoc`, `/openapi.json`

## Logging

| Stream | Source | Example |
|--------|--------|---------|
| stdout | `uvicorn.access` | `INFO: … "GET /api/v1/graph/stats" 200 OK` |
| stderr | `cortex.*` loggers | `INFO [cortex.api.routes] Bulk ingest request received: …` |

Tail both: `docker logs <container> 2>&1 | grep bulk`

App logging configured in `cortex/main.py` via `logging.basicConfig`.

## Shared logic with MCP

Many endpoints call the same functions as MCP (`cortex/mcp/tools.py`) or vault modules directly. Changing behavior usually requires updating both surfaces.

## Endpoint summary

See [reference.md](reference.md) for method, path, and tags.

## Common request bodies

**Feedback** (`POST /feedbacks`):

```json
{
  "content": "…",
  "tags": ["admin-review"],
  "related_paths": ["wiki/article.md"]
}
```

**Bulk ingest** (`POST /bulk-ingest`):

```json
{
  "source_dir": "/ingest",
  "concurrency": 4,
  "force": false,
  "dry_run": false
}
```

`source_dir` must exist on the **server filesystem** (e.g. `/ingest` in Docker, not a host path).

## Related skills

- MCP: `cortex-mcp`
- Auth: `cortex-auth`
- Compiler endpoints: `cortex-compiler`
