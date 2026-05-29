# MCP tools reference

All tools return JSON strings (HTTP) or dicts (stdio handlers). Errors often use `{"error": "..."}`.

## Tools

| Tool | Required args | Optional args | Purpose |
|------|---------------|---------------|---------|
| `vault_read` | `path` | — | Read note content + metadata |
| `vault_write` | `path`, `content` | `frontmatter`, `mode` | Create/update note; schedules QMD debounce |
| `vault_search` | `query` | `mode`, `top_k` | QMD search (`keyword`, `semantic`, `hybrid`) |
| `vault_link` | `action` | `source`, `target`, `edge_type` | `create` / `query` / `delete` edges |
| `vault_context` | `query` | `max_notes`, `max_depth` | Search + graph expansion |
| `vault_ingest` | — | `content`, `filename`, `content_base64` | Write to `raw/` |
| `vault_compile` | — | — | Compile all pending raw sources |
| `vault_feedback` | `content` | `tags`, `related_paths` | Create feedback note (`status: OPEN`) |
| `vault_list_feedbacks` | — | — | List feedback metadata (no full body) |

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
