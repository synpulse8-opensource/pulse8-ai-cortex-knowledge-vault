---
name: cortex-graph-search
description: >-
  Cortex knowledge graph and QMD search — NetworkX graph, edge types, vault_context,
  semantic/keyword/hybrid search. Use for graph stats, links, or search behavior.
---

# Cortex graph and search

## Knowledge graph

- **Storage:** `cortex/graph/store.py` — NetworkX `DiGraph`, persisted to `{vault}/.cortex/graph.json`.
- **Models:** `cortex/vault/models.py` — `NodeType`, `EdgeType`, `GraphNode`, `GraphEdge`.
- **Rebuild:** `cortex/graph/builder.py` scans vault markdown and wikilinks.

### Node types

`note`, `tag`, `agent`, `session`, `daily`, `feedback` (from path prefix or frontmatter `type`).

### Edge types

`links_to`, `authored_by`, `contradicts`, `derived_from`, `supersedes`, `memory_of`, `tagged_with`.

### API surface

- REST: `POST/GET/DELETE /api/v1/links`, `GET /api/v1/graph/stats`
- MCP: `vault_link`, `vault_context` (expands neighbors from search hits)

## QMD search

- **Module:** `cortex/search/qmd.py` — wraps QMD CLI for keyword, semantic, and hybrid modes.
- **Debounce:** After `vault_write`, `QmdDebounce` schedules index refresh (`cortex/search/debounce.py`).
- **Modes:** `keyword`, `semantic`, `hybrid` (default hybrid in many call sites).

### vault_context flow

1. Run search with `query`
2. Take top notes
3. Expand graph neighbors up to `max_depth`
4. Return combined context for agents

## VaultWatcher sync

`cortex/vault/watcher.py` updates graph on file changes so disk edits stay consistent without full rebuild.

## Debugging

- Empty search: check QMD index / vault path / `CORTEX_VAULT_PATH`
- Missing edges: run graph rebuild or trigger watcher; verify wikilink targets exist under allowed folders
- Stats: `GET /api/v1/graph/stats`

## Related skills

- Vault paths: `cortex-vault`
- MCP tools: `cortex-mcp`
