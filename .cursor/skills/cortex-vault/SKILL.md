---
name: cortex-vault
description: >-
  Cortex vault layout — wiki, raw, feedback folders, frontmatter, wikilinks, .cortex
  manifests, VaultWatcher. Use for note paths, vault structure, or filesystem layout.
---

# Cortex vault

Code: `cortex/vault/` (`reader.py`, `writer.py`, `watcher.py`, `index.py`, `feedback.py`, `models.py`).

## Folder semantics

| Path | Purpose |
|------|---------|
| `wiki/` | Published Markdown articles (compiled from `raw/`) |
| `raw/` | Source files before/during compilation |
| `agents/` | Agent definition notes |
| `sessions/` | Per-session notes |
| `daily/` | Daily notes |
| `feedback/` | Feedback submissions (`type: feedback`) |

Paths in APIs are **relative to vault root** (e.g. `wiki/transformers.md`).

## `.cortex/` metadata

| File | Purpose |
|------|---------|
| `graph.json` | Serialized knowledge graph (NetworkX) |
| `index.md` | Human-readable vault index (rebuilt after bulk ops) |
| `log.md` | Append-only audit log (`cortex/log/audit.py`) |
| `ingest-manifest.json` | SHA-256 hashes of successfully compiled raw files |
| `ingest-skip-manifest.json` | Skipped/failed ingest records |

## Notes and frontmatter

- Parsed via `python-frontmatter` in `read_note` / `write_note`.
- `infer_node_type()` in `reader.py`: path prefix or `type` in frontmatter → `NodeType`.
- Common fields: `title`, `tags`, `authored_by`, `created_at`, `updated_at`, `source_path`.
- Feedback notes add `status: OPEN`, `related_paths` (list of vault-relative `.md` paths).

## Wikilinks and tags

- Wikilinks: `[[page]]` or `[[page|label]]` — resolved under `wiki/`, `agents/`, `sessions/`, `daily/`, `feedback/`.
- Tags in frontmatter become graph nodes `tag:{name}` with `tagged_with` edges.

## Validation rules

- **Feedback `related_paths`:** each path must exist, be a file, and end in `.md`. Raw `.txt` cannot be linked — mention in feedback body instead.
- Writes use `mode="create"` or update; `write_note` sets timestamps and provenance.

## VaultWatcher

`cortex/vault/watcher.py` uses `watchfiles` to sync graph nodes/edges when markdown changes on disk. Started in `cortex/main.py` lifespan.

## Related skills

- Graph edges: `cortex-graph-search`
- Feedback CRUD: `cortex-feedback`
- Compile raw → wiki: `cortex-compiler`
