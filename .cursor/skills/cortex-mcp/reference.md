# MCP tools reference

All tools return JSON strings (HTTP) or dicts (stdio handlers). Errors often use `{"error": "..."}`.

## Tools

| Tool | Required args | Optional args | Purpose |
|------|---------------|---------------|---------|
| `vault_read` | `path` | — | Read note content + metadata |
| `vault_write` | `path`, `content` | `frontmatter`, `mode` | Create/update note; schedules QMD debounce |
| `vault_search` | `query` | `mode`, `top_k`, `collection`, `as_resource` | QMD search (`keyword`, `semantic`, `hybrid`) |
| `vault_link` | `action` | `source`, `target`, `edge_type` | `create` / `query` / `delete` edges |
| `vault_context` | `query` | `max_notes`, `max_depth`, `as_resource` | Search + graph expansion |
| `vault_ingest` | — | `content`, `filename`, `content_base64` | Write to `raw/` |
| `vault_compile` | — | — | Compile all pending raw sources |
| `vault_feedback` | `content` | `tags`, `related_paths` | Create feedback note (`status: OPEN`) |
| `vault_list_feedbacks` | — | — | List feedback metadata (no full body) |
| `vault_resource_read` | `resource_id` | — | Read a server-stored MCP resource (fallback for clients without `resources/read` support) |

## MCP resources (`cortex://resource/{id}`)

Cortex implements the [resources-as-tool-inputs pattern][cs-cat-mcp].
Tools that can produce token-heavy payloads accept an opt-in
`as_resource: true` flag: when set, the full payload is kept
server-side as an MCP resource and the caller receives a small handle.

[cs-cat-mcp]: https://microsoft.github.io/mcscatblog/posts/mcp-resources-as-tool-inputs/

Handle shape (returned in lieu of the full payload):

```json
{
  "resource_id": "7f8a3c...",
  "resource_uri": "cortex://resource/7f8a3c...",
  "summary": { "query": "...", "count": 8, "paths": ["..."] }
}
```

Clients with native MCP resources support call `resources/read` on the
URI. Clients that only expose tools (some Copilot Studio
configurations) call `vault_resource_read` with the same ID.

Store characteristics:

- In-memory, asyncio-safe
- TTL eviction (`CORTEX_RESOURCE_TTL_SECONDS`, default `3600`)
- LRU cap (`CORTEX_RESOURCE_MAX_ITEMS`, default `1000`)
- Shared between MCP and REST surfaces — produce via one, read via the other

## Example: vault_feedback

```json
{
  "content": "Search missed the security doc. Please ask admin to review.",
  "tags": ["admin-review", "search-quality"],
  "related_paths": ["wiki/some-article.md"]
}
```

`related_paths` must be existing `.md` files under the vault.

## Example: vault_link create

```json
{
  "action": "create",
  "source": "wiki/a.md",
  "target": "wiki/b.md",
  "edge_type": "contradicts"
}
```

Valid `edge_type` values: `links_to`, `authored_by`, `contradicts`, `derived_from`, `supersedes`, `memory_of`, `tagged_with` (see `EdgeType` in `cortex/vault/models.py`).
