# Feedback Collection — Design Spec

**Date:** 2026-05-28  
**Status:** Approved

## Problem

Users need a way to submit feedback when MCP search/read/context results do not meet their needs. Feedback should be persisted in the vault, searchable via QMD, and connected to the knowledge graph via tags and links to related notes.

## Goals

- Accept feedback through a dedicated MCP tool and REST API
- Store each submission as a markdown file under `feedback/`
- Index feedback in QMD (new collection)
- Add graph nodes and edges (tags + links to related vault notes)
- List, read, and delete feedback via REST

## Non-Goals

- Automatic capture of MCP tool name, query, or response payload
- Feedback workflow states (open/closed/triaged)
- UI implementation
- Email or external ticketing integration

## Decisions

| Topic | Decision |
|-------|----------|
| Content | User comment only (no required MCP context) |
| Tags | Optional; stored in frontmatter |
| Linkage | Both optional `related_paths` and `[[wikilinks]]` in body |
| MCP | Dedicated `vault_feedback(content, tags?, related_paths?)` |
| List API | `GET /api/v1/feedbacks` — metadata only |
| Detail API | `GET /api/v1/feedbacks/{filename}` — full note + edges |
| Filename | UTC `2026-05-28T16-45-00.md`; suffix `-2`, `-3` on collision |
| Module | New `cortex/vault/feedback.py` shared by MCP + REST |

## Storage

### Path

```
feedback/2026-05-28T16-45-00.md
```

- Timestamp: UTC, format `%Y-%m-%dT%H-%M-%S` (colons replaced with hyphens)
- Collision: append `-2`, `-3`, … before `.md` within the same second

### Frontmatter

```yaml
---
type: feedback
title: Feedback 2026-05-28T16:45:00Z
tags: [search-quality, stale-index]
related_paths:
  - wiki/1105-5-1-en-bg-security-events.md
created_at: '2026-05-28T16:45:00+00:00'
authored_by: human
---
```

### Body

User-provided `content` (markdown or plain text). May include `[[wikilinks]]` for additional graph edges.

## Graph Integration

### Node type

Add `NodeType.FEEDBACK = "feedback"`.

`infer_node_type()` returns `FEEDBACK` when:
- path starts with `feedback/`, or
- frontmatter `type: feedback`

### Edges on create

1. **`tagged_with`** — for each tag in frontmatter → `tag:{tag}` node
2. **`links_to`** — for each entry in `related_paths` (validated)
3. **`links_to`** — for each wikilink in body resolved via `resolve_wikilink()`

### Validation for `related_paths`

- Vault-relative path (e.g. `wiki/foo.md`)
- Must exist on disk as a `.md` file
- Invalid paths → HTTP 400 / MCP error (do not silently skip)

### On delete

- Remove file from disk
- `graph.remove_note_node(path)`
- Schedule QMD debounced update

## QMD Integration

- Add `feedback` to CLI collection list in `cortex/search/qmd.py`
- Optional context: `qmd context add qmd://feedback "User feedback on MCP responses and knowledge quality"`
- Docker QMD (`server.mjs`) auto-discovers `feedback/` when the directory exists; add explicit context line for parity
- After create/delete: `qmd_debounce.schedule()`

## MCP Tool

```
vault_feedback(
  content: str,
  tags: list[str] | None = None,
  related_paths: list[str] | None = None,
) -> { path, title, created_at, tags, related_paths, status }
```

- `content` required, non-empty after strip
- Auto-generates filename; caller does not supply path
- Uses shared `create_feedback()` handler

## REST API

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/v1/feedbacks` | — | `{ feedbacks: [{ path, created_at, preview, tags, related_paths }] }` newest first |
| GET | `/api/v1/feedbacks/{filename}` | — | Full note (content, frontmatter, edges) |
| POST | `/api/v1/feedbacks` | `{ content, tags?, related_paths? }` | Created metadata |
| DELETE | `/api/v1/feedbacks/{filename}` | — | `{ status: "deleted", path }` |

### List metadata fields

- **path** — e.g. `feedback/2026-05-28T16-45-00.md`
- **created_at** — from frontmatter
- **preview** — first non-empty line of body, truncated to 120 chars
- **tags** — from frontmatter
- **related_paths** — from frontmatter

Auth: same as existing API (`CORTEX_AUTH_METHOD`).

## Vault Index

Add `feedback` section to `rebuild_index()` in `cortex/vault/index.py`.

## Module: `cortex/vault/feedback.py`

| Function | Responsibility |
|----------|----------------|
| `generate_feedback_path(vault_root)` | Datetime filename with collision handling |
| `create_feedback(vault_root, graph, qmd_debounce, content, tags, related_paths, authored_by)` | Write file, graph edges, QMD schedule |
| `list_feedbacks(vault_root)` | Scan `feedback/*.md`, return metadata |
| `read_feedback(vault_root, graph, filename)` | Full note + edges |
| `delete_feedback(vault_root, graph, qmd_debounce, filename)` | Remove file + graph + QMD |

## Files to Change

| File | Change |
|------|--------|
| `cortex/vault/feedback.py` | New module |
| `cortex/vault/models.py` | `NodeType.FEEDBACK` |
| `cortex/vault/reader.py` | `infer_node_type`, wikilink search dirs |
| `cortex/vault/index.py` | `feedback` section |
| `cortex/mcp/tools.py` | `handle_vault_feedback` |
| `cortex/mcp/http_server.py` | Register MCP tool |
| `cortex/mcp/server.py` | Register MCP tool (stdio) |
| `cortex/api/routes.py` | Feedback endpoints |
| `cortex/search/qmd.py` | `feedback` collection + context |
| `docker/qmd/server.mjs` | Feedback context line |
| `tests/test_feedback.py` | Unit tests |
| `tests/test_api.py` | API tests |
| `tests/test_mcp.py` | MCP handler test |
| `example_vault/feedback/` | Optional sample (if needed for docs) |

## Watcher

No code changes required. `VaultWatcher` already processes `.md` files outside `.cortex/` and `raw/`, including `feedback/`.

## Error Handling

| Case | Behavior |
|------|----------|
| Empty content | 400 / MCP error |
| Invalid `related_paths` | 400 with path list in message |
| Delete missing file | 404 |
| Filename collision | Auto-suffix `-2`, `-3` |
| QMD update failure | Log warning; do not fail write |

## Testing

- Create feedback with tags + related_paths → file exists, graph edges present
- Create with wikilinks in body → additional `links_to` edges
- List returns metadata only (no full content)
- Delete removes file and graph node
- Invalid related_path rejected
- Filename collision handled
